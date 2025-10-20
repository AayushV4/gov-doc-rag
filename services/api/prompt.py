from typing import List, Dict

SYSTEM_PROMPT = """You are a careful government-document assistant.
- Answer using ONLY the provided context chunks.
- If the context is insufficient, say you don't have enough information.
- Always include inline citations like [doc_id:PAGE].
- Prefer clear, concise language suitable for public sector readers.
"""


def build_user_prompt(question: str, contexts: List[Dict]) -> str:
    lines = ["Context:"]
    for i, c in enumerate(contexts, 1):
        cid = c["metadata"].get("doc_id", "unk")
        page = c["metadata"].get("page", "unk")
        text = (c["metadata"].get("text") or "").strip()
        lines.append(f"[{cid}:{page}] {text}")
    lines.append("")
    lines.append("User question:")
    lines.append(question.strip())
    return "\n".join(lines)
