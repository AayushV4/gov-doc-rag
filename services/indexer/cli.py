import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import boto3
import numpy as np
from botocore.config import Config
from langdetect import detect as lang_detect, LangDetectException

# --------- ENV & Defaults ----------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
PROCESSED_BUCKET = os.getenv("PROCESSED_BUCKET", "gov-doc-processed")

# Chunking defaults
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# Embeddings on Bedrock
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "cohere.embed-multilingual-v3"
)  # default multilingual
# Titan fallback examples: "amazon.titan-embed-text-v1" (will auto-pivot FR->EN)

# Vector backend
BACKEND = os.getenv("BACKEND", "pinecone")

# Pinecone config will be pulled from Secrets Manager by default
PINECONE_API_KEY_SECRET = os.getenv(
    "PINECONE_API_KEY_SECRET", "gov-doc-rag/PINECONE_API_KEY"
)
PINECONE_ENV_SECRET = os.getenv(
    "PINECONE_ENV_SECRET", "gov-doc-rag/PINECONE_ENVIRONMENT"
)
PINECONE_INDEX_SECRET = os.getenv("PINECONE_INDEX_SECRET", "gov-doc-rag/PINECONE_INDEX")


# ---------- AWS Clients ----------
def _s3():
    return boto3.client(
        "s3", region_name=AWS_REGION, config=Config(retries={"max_attempts": 10})
    )


def _secrets():
    return boto3.client(
        "secretsmanager",
        region_name=AWS_REGION,
        config=Config(retries={"max_attempts": 10}),
    )


def _translate():
    return boto3.client(
        "translate", region_name=AWS_REGION, config=Config(retries={"max_attempts": 10})
    )


def _bedrock():
    return boto3.client(
        "bedrock-runtime",
        region_name=AWS_REGION,
        config=Config(retries={"max_attempts": 10}),
    )


def get_secret_value(name: str) -> str:
    resp = _secrets().get_secret_value(SecretId=name)
    if "SecretString" in resp and resp["SecretString"]:
        return resp["SecretString"]
    raise RuntimeError(f"Secret {name} missing SecretString")


# ---------- Utilities ----------
def s3_read_json(s3_uri: str) -> Dict[str, Any]:
    if not s3_uri.startswith("s3://"):
        raise ValueError("Provide s3://bucket/key to normalized.json")
    bucket, key = s3_uri[5:].split("/", 1)
    body = _s3().get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(body.decode("utf-8"))


def _detect_lang(text: str) -> str:
    try:
        code = lang_detect(text[:4000])
        return "fr" if code.startswith("fr") else "en"
    except LangDetectException:
        return "en"


def _flatten_table(rows: List[List[str]]) -> str:
    # Convert a table to bullet lines "C1 | C2 | C3"
    out = []
    for r in rows:
        line = " | ".join([c.strip() for c in r])
        if line.strip():
            out.append(f"- {line}")
    return "\n".join(out)


def _split_paragraphs(text: str) -> List[str]:
    # Split by blank lines; merge short paras
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: List[str] = []
    buf = ""
    for p in paras:
        if len(buf) + 1 + len(p) <= CHUNK_SIZE:
            buf = (buf + "\n" + p).strip() if buf else p
        else:
            if buf:
                out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    return out


def _sliding_window(chunks: List[str], max_len: int, overlap: int) -> List[str]:
    # Ensure chunks stay under max_len; apply char-level overlap
    out: List[str] = []
    for ch in chunks:
        if len(ch) <= max_len:
            out.append(ch)
            continue
        i = 0
        while i < len(ch):
            out.append(ch[i : i + max_len])
            if i + max_len >= len(ch):
                break
            i = max(0, i + max_len - overlap)
    return out


@dataclass
class Chunk:
    id: str
    text: str
    metadata: Dict[str, Any]


def build_chunks(normalized: Dict[str, Any]) -> List[Chunk]:
    doc_id = normalized["doc_id"]
    source_s3 = normalized.get("source_s3", "")
    chunks: List[Chunk] = []
    for page in normalized["pages"]:
        page_num = page["page"]
        lang = page.get("lang") or _detect_lang(page.get("text", ""))
        # 1) Paragraphs
        paras = _split_paragraphs(page.get("text", ""))
        paras = _sliding_window(paras, CHUNK_SIZE, CHUNK_OVERLAP)
        for i, p in enumerate(paras):
            cid = f"{doc_id}-p{page_num}-seg{i}"
            chunks.append(
                Chunk(
                    id=cid,
                    text=p,
                    metadata={
                        "doc_id": doc_id,
                        "page": page_num,
                        "lang": lang,
                        "source_s3": source_s3,
                        "type": "text",
                    },
                )
            )
        # 2) Tables
        for ti, tbl in enumerate(page.get("tables", []) or []):
            flat = _flatten_table(tbl.get("rows", []))
            if flat.strip():
                parts = _sliding_window([flat], CHUNK_SIZE, CHUNK_OVERLAP)
                for j, part in enumerate(parts):
                    cid = f"{doc_id}-p{page_num}-table{ti}-seg{j}"
                    chunks.append(
                        Chunk(
                            id=cid,
                            text=part,
                            metadata={
                                "doc_id": doc_id,
                                "page": page_num,
                                "lang": lang,
                                "source_s3": source_s3,
                                "type": "table",
                            },
                        )
                    )
    return chunks


# ---------- Embeddings via Bedrock ----------
def _cohere_embed(texts: List[str], mode: str) -> List[List[float]]:
    # mode: "search_document" or "search_query"
    # Cohere has a max batch size of 128
    MAX_BATCH = 96  # Use 96 to be safe
    all_embeddings = []

    for i in range(0, len(texts), MAX_BATCH):
        batch = texts[i : i + MAX_BATCH]
        body = json.dumps({"texts": batch, "input_type": mode})
        resp = _bedrock().invoke_model(modelId=EMBEDDING_MODEL, body=body)
        payload = json.loads(resp["body"].read())

        # bedrock cohere returns {"embeddings":[ [..], [..] ]}
        if "embeddings" in payload:
            all_embeddings.extend(payload["embeddings"])
        # fallback if wrapped
        elif (
            "data" in payload and payload["data"] and "embedding" in payload["data"][0]
        ):
            all_embeddings.extend([d["embedding"] for d in payload["data"]])
        else:
            raise RuntimeError("Unexpected Cohere embedding response")

    return all_embeddings


def _titan_embed(texts: List[str]) -> List[List[float]]:
    vecs: List[List[float]] = []
    for tx in texts:
        body = json.dumps({"inputText": tx})
        # modelId like "amazon.titan-embed-text-v1"
        resp = _bedrock().invoke_model(modelId=EMBEDDING_MODEL, body=body)
        payload = json.loads(resp["body"].read())
        # titan returns {"embedding":[..]} or {"vector":[..]} depending on version
        v = payload.get("embedding") or payload.get("vector")
        if not v:
            raise RuntimeError("Unexpected Titan embedding response")
        vecs.append(v)
    return vecs


def embed_texts(
    texts: List[str], as_query: bool = False, source_langs: Optional[List[str]] = None
) -> np.ndarray:
    model = EMBEDDING_MODEL.lower()
    # Optional pivot if model is monolingual
    if ("titan" in model or "english" in model) and source_langs:
        tx = []
        for t, lg in zip(texts, source_langs):
            if lg and lg.startswith("fr"):
                r = _translate().translate_text(
                    Text=t, SourceLanguageCode="fr", TargetLanguageCode="en"
                )
                tx.append(r["TranslatedText"])
            else:
                tx.append(t)
        texts = tx

    if "cohere.embed" in model or "cohere" in model:
        mode = "search_query" if as_query else "search_document"
        vecs = _cohere_embed(texts, mode)
    else:
        vecs = _titan_embed(texts)

    return np.array(vecs, dtype=np.float32)


# ---------- Pinecone Adapter ----------
def pinecone_connect() -> Tuple[Any, str]:
    from pinecone import Pinecone, ServerlessSpec

    api_key = get_secret_value(PINECONE_API_KEY_SECRET)
    env = get_secret_value(PINECONE_ENV_SECRET)  # e.g., "us-east-1-aws"
    index_name = get_secret_value(PINECONE_INDEX_SECRET)

    pc = Pinecone(api_key=api_key)
    indexes = {ix["name"]: ix for ix in pc.list_indexes()}
    if index_name not in indexes:
        # create with dimension inferred from a probe embedding
        probe = embed_texts(["dimension probe"], as_query=False)
        dim = int(probe.shape[1])
        # parse region from env like "us-east-1-aws"
        region = env.split("-aws")[0] if "-aws" in env else env
        pc.create_index(
            name=index_name,
            dimension=dim,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=region),
        )
        # wait for ready
        while True:
            info = pc.describe_index(index_name)
            if info.status["ready"]:
                break
    return pc.Index(index_name), index_name


def pinecone_upsert(chunks: List[Chunk]) -> int:
    index, index_name = pinecone_connect()
    # batch to avoid large payloads
    batch = []
    total = 0
    BATCH_SIZE = 64

    texts = [c.text for c in chunks]
    langs = [c.metadata.get("lang", "en") for c in chunks]
    vectors = embed_texts(texts, as_query=False, source_langs=langs)

    for i, c in enumerate(chunks):
        vec = vectors[i].tolist()
        meta = c.metadata.copy()
        meta["chunk_id"] = c.id
        meta["text"] = c.text[:5000]  # keep a preview/snippet in metadata
        batch.append({"id": c.id, "values": vec, "metadata": meta})
        if len(batch) >= BATCH_SIZE:
            index.upsert(vectors=batch)
            total += len(batch)
            batch = []
    if batch:
        index.upsert(vectors=batch)
        total += len(batch)
    return total


def pinecone_query(
    query: str, k: int = 6, lang_hint: Optional[str] = None
) -> List[Dict[str, Any]]:
    index, _ = pinecone_connect()
    q_lang = lang_hint or _detect_lang(query)
    q_vec = embed_texts([query], as_query=True, source_langs=[q_lang])[0].tolist()
    res = index.query(vector=q_vec, top_k=k, include_metadata=True)
    # v2 client response has 'matches'
    return getattr(res, "matches", res.get("matches", []))


# ---------- CLI ----------
def cmd_index(args: argparse.Namespace) -> int:
    s3_uri = args.s3_uri
    print(f"→ Loading normalized JSON from {s3_uri}")
    normalized = s3_read_json(s3_uri)

    print("→ Building chunks...")
    chunks = build_chunks(normalized)
    print(f"   Built {len(chunks)} chunks")

    if BACKEND != "pinecone":
        print(
            f"BACKEND={BACKEND} not implemented in this CLI yet. Set BACKEND=pinecone."
        )
        return 2

    print("→ Connecting to Pinecone and upserting...")
    count = pinecone_upsert(chunks)
    print(f"✅ Upserted {count} vectors")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    q = args.query
    k = args.k
    lang = args.lang
    if BACKEND != "pinecone":
        print(
            f"BACKEND={BACKEND} not implemented in this CLI yet. Set BACKEND=pinecone."
        )
        return 2

    print(f"→ Query: {q} (k={k}, lang={lang or 'auto'})")
    matches = pinecone_query(q, k=k, lang_hint=lang)
    for m in matches:
        meta = m["metadata"] if isinstance(m, dict) else m.metadata
        score = m["score"] if isinstance(m, dict) else m.score
        print(
            f"- score={score:.4f}  doc_id={meta.get('doc_id')} page={meta.get('page')} lang={meta.get('lang')}"
        )
        snippet = (meta.get("text") or "").replace("\n", " ")
        print(f"  snippet: {snippet[:180]}{'...' if len(snippet)>180 else ''}")
    return 0


def main():
    p = argparse.ArgumentParser(description="Gov Doc RAG - Indexer")
    sub = p.add_subparsers(dest="cmd")

    ix = sub.add_parser("index", help="Index a normalized.json from S3")
    ix.add_argument("s3_uri", help="s3://bucket/key to normalized.json")
    ix.set_defaults(func=cmd_index)

    qq = sub.add_parser("query", help="Test retrieval")
    qq.add_argument("query")
    qq.add_argument("--k", type=int, default=6)
    qq.add_argument("--lang", help="en|fr (optional)")
    qq.set_defaults(func=cmd_query)

    ns = p.parse_args()
    if not getattr(ns, "func", None):
        p.print_help()
        sys.exit(1)
    sys.exit(ns.func(ns))


if __name__ == "__main__":
    main()
