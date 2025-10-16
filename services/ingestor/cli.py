# (full working CLI)
# Uploads a local PDF to S3 (gov-doc-raw), runs Textract async (TABLES, FORMS),
# normalizes results, and writes normalized.json + page-*.txt to gov-doc-processed.

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional
from collections import defaultdict
import boto3
from botocore.config import Config
from langdetect import detect as lang_detect, LangDetectException

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
RAW_BUCKET = os.getenv("RAW_BUCKET", "gov-doc-raw")
PROCESSED_BUCKET = os.getenv("PROCESSED_BUCKET", "gov-doc-processed")
TX_FEATURES = ["TABLES", "FORMS"]
POLL_SECONDS = 4
POLL_MAX_MINUTES = 30


def _s3() -> Any:
    return boto3.client(
        "s3", region_name=AWS_REGION, config=Config(retries={"max_attempts": 10})
    )


def _textract() -> Any:
    return boto3.client(
        "textract", region_name=AWS_REGION, config=Config(retries={"max_attempts": 10})
    )


def upload_file_to_raw(local_path: str, doc_id: str) -> str:
    key = f"{doc_id}/{os.path.basename(local_path)}"
    s3 = _s3()

    # Toggle SSE for the *raw* upload only:
    #   INGEST_SSE=AES256  -> use SSE-S3 (no CMK needed; Textract-friendly)
    #   INGEST_SSE=KMS     -> force SSE-KMS with the key in INGEST_KMS_KEY_ID
    #   (unset)            -> use the bucket default (likely SSE-KMS)
    sse_mode = (os.getenv("INGEST_SSE") or "").upper().strip()
    extra_args = None

    if sse_mode == "AES256":
        extra_args = {"ServerSideEncryption": "AES256"}
        print("   (uploading with SSE-S3/AES256 for Textract compatibility)")
    elif sse_mode in ("KMS", "AWS:KMS"):
        kms_key = os.getenv("INGEST_KMS_KEY_ID")
        if kms_key:
            extra_args = {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": kms_key}
            print(f"   (uploading with SSE-KMS key {kms_key})")

    if extra_args:
        s3.upload_file(local_path, RAW_BUCKET, key, ExtraArgs=extra_args)
    else:
        s3.upload_file(local_path, RAW_BUCKET, key)

    return key


def start_textract(s3_key: str) -> str:
    # Minimal, robust call (no JobTag)
    resp = _textract().start_document_analysis(
        DocumentLocation={"S3Object": {"Bucket": RAW_BUCKET, "Name": s3_key}},
        FeatureTypes=TX_FEATURES,
    )
    return resp["JobId"]


def poll_textract(job_id: str) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []
    next_token: Optional[str] = None
    waited = 0
    while True:
        resp = _textract().get_document_analysis(
            **({"JobId": job_id} | ({"NextToken": next_token} if next_token else {}))
        )
        status = resp["JobStatus"]
        pages.append(resp)
        next_token = resp.get("NextToken")
        if next_token:
            continue
        if status == "SUCCEEDED":
            return pages
        if status in ("FAILED", "PARTIAL_SUCCESS"):
            raise RuntimeError(f"Textract job {job_id} ended with {status}")
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        if waited > POLL_MAX_MINUTES * 60:
            raise TimeoutError("Textract timeout")


def _blocks_index(blocks):
    return {b["Id"]: b for b in blocks}


def _get_text_for_ids(ids, block_map):
    parts = []
    for bid in ids or []:
        b = block_map.get(bid)
        if not b:
            continue
        if b.get("BlockType") == "WORD":
            parts.append(b.get("Text", ""))
        elif (
            b.get("BlockType") == "SELECTION_ELEMENT"
            and b.get("SelectionStatus") == "SELECTED"
        ):
            parts.append("[X]")
    return " ".join([p for p in parts if p])


def _extract_tables(blocks):
    block_map = _blocks_index(blocks)
    tables = []
    for b in blocks:
        if b.get("BlockType") != "TABLE":
            continue
        cell_text = defaultdict(dict)
        for rel in b.get("Relationships", []) or []:
            if rel.get("Type") != "CHILD":
                continue
            for cid in rel.get("Ids", []):
                cell = block_map.get(cid)
                if not cell or cell.get("BlockType") != "CELL":
                    continue
                row = int(cell.get("RowIndex", 1))
                col = int(cell.get("ColumnIndex", 1))
                text = ""
                for rel2 in cell.get("Relationships", []) or []:
                    if rel2.get("Type") == "CHILD":
                        text = _get_text_for_ids(rel2.get("Ids", []), block_map)
                cell_text[row][col] = text.strip()
        if not cell_text:
            continue
        max_row = max(cell_text.keys())
        max_col = max(max(cols.keys()) for cols in cell_text.values())
        rows = [
            [cell_text.get(r, {}).get(c, "") for c in range(1, max_col + 1)]
            for r in range(1, max_row + 1)
        ]
        tables.append({"rows": rows})
    return tables


def _bbox(block):
    bb = (block.get("Geometry") or {}).get("BoundingBox")
    if not bb:
        return None
    return {
        "left": float(bb.get("Left", 0.0)),
        "top": float(bb.get("Top", 0.0)),
        "width": float(bb.get("Width", 0.0)),
        "height": float(bb.get("Height", 0.0)),
    }


def _page_lang(text: str) -> str:
    try:
        code = lang_detect(text[:4000])
        return "fr" if code.startswith("fr") else "en"
    except LangDetectException:
        return "en"


def normalize(textract_pages, doc_id, source_key, metadata):
    all_blocks = []
    [all_blocks.extend(p.get("Blocks", [])) for p in textract_pages]
    by_page = defaultdict(list)
    [by_page[int(b.get("Page", 1))].append(b) for b in all_blocks]
    pages_out = []
    for n in sorted(by_page.keys()):
        blocks = by_page[n]
        lines = [b for b in blocks if b.get("BlockType") == "LINE" and b.get("Text")]
        text = "\n".join(ln["Text"] for ln in lines)
        blocks_out = [
            {"type": "LINE", "text": ln["Text"], "bbox": _bbox(ln)} for ln in lines
        ]
        tables_out = _extract_tables(blocks)
        lang = _page_lang(text)
        pages_out.append(
            {
                "page": n,
                "lang": lang,
                "text": text,
                "blocks": blocks_out,
                "tables": tables_out,
            }
        )
    return {
        "doc_id": doc_id,
        "source_s3": f"s3://{RAW_BUCKET}/{source_key}",
        "metadata": metadata,
        "pages": pages_out,
    }


def write_outputs(doc_id, normalized):
    data = json.dumps(normalized, ensure_ascii=False, indent=2).encode("utf-8")
    _s3().put_object(
        Bucket=PROCESSED_BUCKET,
        Key=f"{doc_id}/normalized.json",
        Body=data,
        ContentType="application/json",
    )
    for p in normalized["pages"]:
        key = f"{doc_id}/pages/page-{p['page']:03d}.txt"
        _s3().put_object(
            Bucket=PROCESSED_BUCKET,
            Key=key,
            Body=(p.get("text", "") or "").encode("utf-8"),
            ContentType="text/plain",
        )


def cmd_upload(args):
    if not os.path.isfile(args.file):
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    doc_id = args.doc_id or str(uuid.uuid4())
    doc_meta = {
        "title": args.title or os.path.basename(args.file),
        "dept": args.dept or "",
        "date": args.date or "",
    }

    print(f"→ Uploading to s3://{RAW_BUCKET}/{doc_id}/ ...")
    s3_key = upload_file_to_raw(args.file, doc_id)

    # sanity check the object exists and encryption mode
    try:
        obj_head = _s3().head_object(Bucket=RAW_BUCKET, Key=s3_key)
        enc = obj_head.get("ServerSideEncryption")
        print(f"   (s3 object ok; SSE={enc})")
    except Exception as e:
        print(f"!! head_object failed: {e}")
        raise

    print("→ Starting Textract analysis ...")
    job_id = start_textract(s3_key)
    print(f"   JobId: {job_id}")

    print("→ Polling Textract... (large PDFs can take a while)")
    pages = poll_textract(job_id)
    print(f"   Chunks: {len(pages)}")

    print("→ Normalizing...")
    normalized = normalize(pages, doc_id, s3_key, doc_meta)

    print("→ Writing outputs...")
    write_outputs(doc_id, normalized)

    print(f"✅ Done. doc_id={doc_id}")
    print(f"   raw:       s3://{RAW_BUCKET}/{s3_key}")
    print(f"   processed: s3://{PROCESSED_BUCKET}/{doc_id}/normalized.json")
    return 0


def main():
    p = argparse.ArgumentParser(description="Gov Doc RAG - Ingestor (Textract)")
    s = p.add_subparsers(dest="cmd")
    up = s.add_parser("upload", help="Upload a PDF and run Textract")
    up.add_argument("file")
    up.add_argument("--doc-id")
    up.add_argument("--title")
    up.add_argument("--dept")
    up.add_argument("--date")
    up.set_defaults(func=cmd_upload)
    ns = p.parse_args()
    if not getattr(ns, "func", None):
        p.print_help()
        sys.exit(1)
    sys.exit(ns.func(ns))


if __name__ == "__main__":
    main()
