import os
import json
import time
import logging
import sys
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from pythonjsonlogger import jsonlogger
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Response, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from langdetect import detect as lang_detect, LangDetectException

import boto3
from botocore.config import Config
from tenacity import retry, wait_exponential, stop_after_attempt

# local modules
from services.api.prompt import SYSTEM_PROMPT, build_user_prompt


# ========= Structured Logging Setup =========
def setup_logging():
    """Configure structured JSON logging for CloudWatch."""
    # Create JSON formatter
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    root_handler = logging.StreamHandler(sys.stdout)
    root_handler.setFormatter(formatter)
    root_logger.addHandler(root_handler)

    # Configure uvicorn loggers specifically
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = False

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        uvicorn_logger.addHandler(handler)
        uvicorn_logger.setLevel(logging.INFO)


setup_logging()
logger = logging.getLogger(__name__)


# ========= Env & Defaults =========
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BACKEND = os.getenv("BACKEND", "pinecone")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "cohere.embed-multilingual-v3")
LLM_MODEL = os.getenv(
    "LLM_MODEL", "anthropic.claude-3-haiku-20240307-v1:0"
)  # keep small/cheap default
RAW_BUCKET = os.getenv("RAW_BUCKET", "gov-doc-raw")
PROCESSED_BUCKET = os.getenv("PROCESSED_BUCKET", "gov-doc-processed")

# secrets
PINECONE_API_KEY_SECRET = os.getenv(
    "PINECONE_API_KEY_SECRET", "gov-doc-rag/PINECONE_API_KEY"
)
PINECONE_ENV_SECRET = os.getenv(
    "PINECONE_ENV_SECRET", "gov-doc-rag/PINECONE_ENVIRONMENT"
)
PINECONE_INDEX_SECRET = os.getenv("PINECONE_INDEX_SECRET", "gov-doc-rag/PINECONE_INDEX")

GUARDRAIL_SECRET = os.getenv(
    "BEDROCK_GUARDRAIL_SECRET", "gov-doc-rag/BEDROCK_GUARDRAIL_ID"
)
GUARDRAIL_SSM_PARAM = os.getenv(
    "BEDROCK_GUARDRAIL_PARAM", "/gov-doc-rag/BEDROCK_GUARDRAIL_ID"
)

# ingestion toggle for raw uploads (Phase 2 logic)
INGEST_SSE = (os.getenv("INGEST_SSE") or "").upper().strip()
INGEST_KMS_KEY_ID = os.getenv("INGEST_KMS_KEY_ID")


# ========= AWS Clients =========
def _cfg():
    return Config(retries={"max_attempts": 10, "mode": "adaptive"})


def s3():
    return boto3.client("s3", region_name=AWS_REGION, config=_cfg())


def sm():
    return boto3.client("secretsmanager", region_name=AWS_REGION, config=_cfg())


def ssm():
    return boto3.client("ssm", region_name=AWS_REGION, config=_cfg())


def bedrock():
    return boto3.client("bedrock-runtime", region_name=AWS_REGION, config=_cfg())


def translate():
    return boto3.client("translate", region_name=AWS_REGION, config=_cfg())


# ========= Helpers =========
def detect_lang(text: str) -> str:
    try:
        code = lang_detect(text[:4000])
        return "fr" if code.startswith("fr") else "en"
    except LangDetectException:
        return "en"


def secret_string(name: str) -> Optional[str]:
    try:
        resp = sm().get_secret_value(SecretId=name)
        if resp.get("SecretString"):
            return resp["SecretString"]
    except Exception as e:
        logger.warning("Failed to get secret", extra={"secret": name, "error": str(e)})
        return None
    return None


def ssm_param(name: str) -> Optional[str]:
    try:
        resp = ssm().get_parameter(Name=name)
        return resp["Parameter"]["Value"]
    except Exception as e:
        logger.warning(
            "Failed to get SSM parameter", extra={"param": name, "error": str(e)}
        )
        return None


def guardrail_cfg() -> Optional[Dict[str, Any]]:
    gid = secret_string(GUARDRAIL_SECRET) or ssm_param(GUARDRAIL_SSM_PARAM)
    if gid and gid.strip().lower() != "unset":
        # Bedrock Guardrails apply via 'guardrailConfig' for supported models
        return {
            "guardrailIdentifier": gid,
            "guardrailVersion": "DRAFT",
        }  # or "1" if you've published
    return None


# ========= Embeddings (Bedrock) =========
@retry(wait=wait_exponential(multiplier=0.5, max=4), stop=stop_after_attempt(3))
def cohere_embed(texts: List[str], mode: str) -> List[List[float]]:
    body = json.dumps({"texts": texts, "input_type": mode})
    resp = bedrock().invoke_model(modelId=EMBEDDING_MODEL, body=body)
    payload = json.loads(resp["body"].read())
    if "embeddings" in payload:
        return payload["embeddings"]
    if "data" in payload and payload["data"] and "embedding" in payload["data"][0]:
        return [d["embedding"] for d in payload["data"]]
    raise RuntimeError("Unexpected Cohere embedding response")


@retry(wait=wait_exponential(multiplier=0.5, max=4), stop=stop_after_attempt(3))
def titan_embed(texts: List[str]) -> List[List[float]]:
    out = []
    for t in texts:
        body = json.dumps({"inputText": t})
        resp = bedrock().invoke_model(modelId=EMBEDDING_MODEL, body=body)
        payload = json.loads(resp["body"].read())
        v = payload.get("embedding") or payload.get("vector")
        if not v:
            raise RuntimeError("Unexpected Titan embedding response")
        out.append(v)
    return out


def embed_texts(
    texts: List[str], as_query: bool, langs: Optional[List[str]]
) -> List[List[float]]:
    model = EMBEDDING_MODEL.lower()
    # pivot French -> English when using monolingual embeddings
    if ("titan" in model or "english" in model) and langs:
        tx = []
        for t, lg in zip(texts, langs):
            if lg and lg.startswith("fr"):
                r = translate().translate_text(
                    Text=t, SourceLanguageCode="fr", TargetLanguageCode="en"
                )
                tx.append(r["TranslatedText"])
            else:
                tx.append(t)
        texts = tx
    if "cohere" in model:
        mode = "search_query" if as_query else "search_document"
        return cohere_embed(texts, mode)
    else:
        return titan_embed(texts)


# ========= Pinecone =========
@dataclass
class PineconeIndex:
    index: Any


_pinecone_cached: Optional[PineconeIndex] = None


def pinecone_connect() -> PineconeIndex:
    global _pinecone_cached
    if _pinecone_cached:
        return _pinecone_cached
    import pinecone  # v3+

    api_key = secret_string(PINECONE_API_KEY_SECRET)
    env = secret_string(PINECONE_ENV_SECRET)
    index_name = secret_string(PINECONE_INDEX_SECRET)
    if not (api_key and env and index_name):
        raise HTTPException(500, "Missing Pinecone secrets in Secrets Manager")

    pc = pinecone.Pinecone(api_key=api_key)
    # assume index created by indexer; if not, fail loudly (keeps API simple)
    idx = pc.Index(index_name)
    _pinecone_cached = PineconeIndex(index=idx)
    logger.info("Connected to Pinecone", extra={"index": index_name})
    return _pinecone_cached


def pinecone_query(
    query: str, k: int, lang_hint: Optional[str]
) -> List[Dict[str, Any]]:
    idx = pinecone_connect().index
    q_lang = lang_hint or detect_lang(query)
    q_vec = embed_texts([query], as_query=True, langs=[q_lang])[0]
    res = idx.query(
        vector=q_vec,
        top_k=k,
        include_metadata=True,
    )
    return getattr(res, "matches", res.get("matches", []))


# ========= LLM call (Claude on Bedrock) =========
def claude_chat(messages):
    """
    Accepts a list of dicts like:
      {"role":"system","content":"..."} (optional, pulled out to top-level)
      {"role":"user","content":"..."} or {"role":"assistant","content":"..."}
    Converts to Anthropic 'messages' schema for Bedrock:
      system: "<text>"
      messages: [{"role":"user","content":[{"type":"text","text":"..."}]}, ...]
    """
    # Pull out system text if present
    system_text = None
    converted = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        # normalize to plain string
        if isinstance(content, list):
            # support content=[{"type":"text","text":"..."}] shapes
            if content and isinstance(content[0], dict) and "text" in content[0]:
                content = content[0]["text"]
            else:
                content = " ".join([str(x) for x in content])

        if role == "system":
            system_text = str(content)
            continue

        if role not in ("user", "assistant"):
            role = "user"  # safe fallback

        converted.append(
            {"role": role, "content": [{"type": "text", "text": str(content)}]}
        )

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 800,
        "temperature": 0.2,
        "messages": converted,
    }
    if system_text:
        body["system"] = system_text

    # IMPORTANT: Do NOT include 'guardrailConfig' in the body for Anthropic
    resp = bedrock().invoke_model(modelId=LLM_MODEL, body=json.dumps(body))
    payload = json.loads(resp["body"].read())
    # Anthropic Messages response shape: {"content":[{"type":"text","text":"..."}], ...}
    return payload["content"][0]["text"]


# ========= FastAPI app =========
app = FastAPI(title="Gov Doc RAG API", version="0.1.0")


@app.on_event("startup")
async def startup_event():
    logger.info(
        "API server starting",
        extra={
            "region": AWS_REGION,
            "backend": BACKEND,
            "embedding_model": EMBEDDING_MODEL,
            "llm_model": LLM_MODEL,
        },
    )


class AskIn(BaseModel):
    query: str
    k: int = 6
    lang_hint: Optional[str] = None


@app.get("/health")
def health():
    return {"ok": True, "region": AWS_REGION, "backend": BACKEND}


@app.head("/health")
def health_head():
    return Response(status_code=200)


@app.post("/ask")
def ask(inp: AskIn):
    logger.info(
        "Processing query",
        extra={"query_length": len(inp.query), "k": inp.k, "lang_hint": inp.lang_hint},
    )

    if BACKEND != "pinecone":
        raise HTTPException(
            400, f"BACKEND={BACKEND} not supported here; set to pinecone"
        )

    # 1) retrieve
    matches = pinecone_query(inp.query, k=inp.k, lang_hint=inp.lang_hint)
    logger.info("Retrieved matches", extra={"match_count": len(matches)})

    contexts: List[Dict[str, Any]] = []
    for m in matches:
        meta = m["metadata"] if isinstance(m, dict) else m.metadata
        contexts.append({"metadata": meta})

    # 2) prompt
    sys_prompt = SYSTEM_PROMPT
    user_prompt = build_user_prompt(inp.query, contexts)
    messages = [
        {"role": "system", "content": [{"type": "text", "text": sys_prompt}]},
        {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
    ]

    # 3) LLM
    logger.info("Calling LLM", extra={"model": LLM_MODEL})
    answer = claude_chat(messages)

    # 4) If user is FR and model answered EN, translate back (heuristic)
    q_lang = inp.lang_hint or detect_lang(inp.query)
    if q_lang == "fr":
        try:
            a_lang = detect_lang(answer)
        except Exception:
            a_lang = "en"
        if a_lang != "fr":
            logger.info("Translating answer to French")
            answer = translate().translate_text(
                Text=answer, SourceLanguageCode="en", TargetLanguageCode="fr"
            )["TranslatedText"]

    # 5) citations
    cites = []
    for m in matches:
        meta = m["metadata"] if isinstance(m, dict) else m.metadata
        cites.append(
            {
                "doc_id": meta.get("doc_id"),
                "page": meta.get("page"),
                "snippet": meta.get("text"),
                "bbox": None,  # page bbox would require deeper line mapping; included for schema stability
            }
        )

    logger.info(
        "Query processed successfully",
        extra={"citation_count": len(cites), "answer_length": len(answer)},
    )

    return JSONResponse({"answer": answer, "citations": cites})


@app.middleware("http")
async def hsts_middleware(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains; preload"
    )
    return resp


# ========== /upload (simple wrapper over Phase 2 logic) ==========
# Accepts a PDF and runs Textract → normalized.json
@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    dept: Optional[str] = Form(None),
    date: Optional[str] = Form(None),
):
    logger.info(
        "Processing upload",
        extra={"filename": file.filename, "title": title, "dept": dept},
    )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF is supported")

    # save temp
    tmp_path = f"/tmp/{int(time.time())}-{file.filename}"
    with open(tmp_path, "wb") as f:
        f.write(await file.read())

    # import ingestor functions directly
    from services.ingestor.cli import (
        upload_file_to_raw,
        start_textract,
        poll_textract,
        normalize,
        write_outputs,
    )

    import uuid

    doc_id = str(uuid.uuid4())
    logger.info("Starting document ingestion", extra={"doc_id": doc_id})

    # raw upload encryption toggle as in Phase 2
    if INGEST_SSE == "AES256":
        os.environ["INGEST_SSE"] = "AES256"
    elif INGEST_SSE in ("KMS", "AWS:KMS") and INGEST_KMS_KEY_ID:
        os.environ["INGEST_SSE"] = "KMS"
        os.environ["INGEST_KMS_KEY_ID"] = INGEST_KMS_KEY_ID

    key = upload_file_to_raw(tmp_path, doc_id)
    # sanity: head object
    s3().head_object(Bucket=RAW_BUCKET, Key=key)
    job_id = start_textract(key)
    logger.info("Textract job started", extra={"job_id": job_id, "doc_id": doc_id})

    pages = poll_textract(job_id)
    meta = {"title": title or file.filename, "dept": dept or "", "date": date or ""}
    normalized = normalize(pages, doc_id, key, meta)
    write_outputs(doc_id, normalized)

    logger.info(
        "Document ingestion complete",
        extra={"doc_id": doc_id, "page_count": len(pages)},
    )

    # cleanup
    try:
        os.remove(tmp_path)
    except Exception:
        pass

    return {
        "doc_id": doc_id,
        "raw": f"s3://{RAW_BUCKET}/{key}",
        "processed": f"s3://{PROCESSED_BUCKET}/{doc_id}/normalized.json",
    }
