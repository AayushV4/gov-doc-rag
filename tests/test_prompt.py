from services.api.prompt import build_user_prompt


def test_build_prompt_includes_citations():
    contexts = [
        {"metadata": {"doc_id": "abc", "page": 1, "text": "hello world"}},
        {"metadata": {"doc_id": "def", "page": 2, "text": "bonjour le monde"}},
    ]
    q = "What is stated?"
    up = build_user_prompt(q, contexts)
    assert "[abc:1]" in up and "[def:2]" in up
    assert "User question:" in up
