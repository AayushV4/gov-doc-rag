import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from pinecone import Pinecone


QUESTION_GENERATION_PROMPT = """You are an expert at creating evaluation questions for a government document Q&A system.

Given this excerpt from a Canadian government document, generate {num_questions} realistic questions that:
1. Can be answered using ONLY the information in this excerpt
2. Represent real questions Canadian citizens might ask
3. Cover different difficulty levels (easy factual, medium procedural, hard policy/complex)
4. Are clear and unambiguous
5. Include both English and French questions (bilingual)

Document excerpt:
---
{context}
---

For each question, provide:
- question: The question text
- lang: Language code (en or fr)
- category: One of [factual, procedural, policy, comparison]
- difficulty: One of [easy, medium, hard]
- expected_answer: A concise but complete answer based on the excerpt
- relevant_pages: Page numbers from the document that support the answer

Return your response as a JSON array:
[
  {{
    "question": "...",
    "lang": "en",
    "category": "factual",
    "difficulty": "easy",
    "expected_answer": "...",
    "relevant_pages": [12, 13]
  }},
  ...
]

JSON output:
"""


def get_bedrock_client(region: str = "us-east-1"):
    """Create Bedrock client."""
    return boto3.client("bedrock-runtime", region_name=region)


def get_pinecone_client(api_key: Optional[str] = None) -> Pinecone:
    """Create Pinecone client."""
    api_key = api_key or os.environ.get("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY environment variable not set")
    return Pinecone(api_key=api_key)


def sample_documents(
    pinecone_client: Pinecone,
    index_name: str,
    doc_id: Optional[str] = None,
    count: int = 5,
) -> List[Dict]:
    """
    Sample documents from Pinecone.

    If doc_id is provided, get chunks from that specific document.
    Otherwise, sample random chunks.
    """
    index = pinecone_client.Index(index_name)

    # Query with a dummy vector to get random results
    # In production, you might want to maintain a separate metadata store
    dummy_vector = [0.0] * 1024  # Cohere multilingual-v3 dimension

    if doc_id:
        results = index.query(
            vector=dummy_vector,
            top_k=count,
            filter={"doc_id": {"$eq": doc_id}},
            include_metadata=True,
        )
    else:
        results = index.query(vector=dummy_vector, top_k=count, include_metadata=True)

    return [match.metadata for match in results.matches]


def generate_questions_with_claude(
    bedrock_client,
    context: str,
    num_questions: int = 3,
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
) -> List[Dict[str, Any]]:
    """Use Claude to generate evaluation questions from context."""

    prompt = QUESTION_GENERATION_PROMPT.format(
        num_questions=num_questions, context=context
    )

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        response = bedrock_client.invoke_model(
            modelId=model_id, body=json.dumps(payload)
        )

        response_body = json.loads(response["body"].read())
        generated_text = response_body["content"][0]["text"]

        # Extract JSON from response
        # Claude sometimes wraps JSON in markdown code blocks
        generated_text = generated_text.strip()
        if generated_text.startswith("```json"):
            generated_text = generated_text[7:]
        if generated_text.startswith("```"):
            generated_text = generated_text[3:]
        if generated_text.endswith("```"):
            generated_text = generated_text[:-3]

        questions = json.loads(generated_text.strip())
        return questions

    except Exception as e:
        print(f"Error generating questions: {e}", file=sys.stderr)
        return []


def append_to_golden_set(csv_path: str, questions: List[Dict], doc_metadata: Dict):
    """Append generated questions to golden_set.csv."""

    # Read existing CSV to get the next question ID
    existing_count = 0
    if Path(csv_path).exists():
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_count = sum(1 for _ in reader)

    # Open in append mode
    file_exists = Path(csv_path).exists() and Path(csv_path).stat().st_size > 0

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        fieldnames = [
            "question_id",
            "question",
            "lang",
            "category",
            "difficulty",
            "expected_answer",
            "expected_citations",
            "ground_truth_context",
            "notes",
        ]

        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for i, q in enumerate(questions, start=existing_count + 1):
            # Build expected citations
            doc_id = doc_metadata.get("doc_id", "unknown")
            pages = q.get("relevant_pages", [])
            expected_citations = ",".join([f"{doc_id}:{p}" for p in pages])

            row = {
                "question_id": i,
                "question": q.get("question", ""),
                "lang": q.get("lang", "en"),
                "category": q.get("category", "factual"),
                "difficulty": q.get("difficulty", "medium"),
                "expected_answer": q.get("expected_answer", ""),
                "expected_citations": expected_citations,
                "ground_truth_context": doc_metadata.get("text", "")[:500],  # Truncate
                "notes": "Generated automatically with Claude",
            }

            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description="Generate evaluation questions from indexed documents"
    )
    parser.add_argument(
        "--count", type=int, default=10, help="Number of questions to generate"
    )
    parser.add_argument(
        "--doc-id", type=str, help="Specific document ID to generate questions from"
    )
    parser.add_argument(
        "--index-name", type=str, default="gov-docs", help="Pinecone index name"
    )
    parser.add_argument(
        "--bedrock-region", type=str, default="us-east-1", help="AWS Bedrock region"
    )
    parser.add_argument(
        "--golden-set",
        type=str,
        default="evals/golden_set.csv",
        help="Path to golden_set.csv",
    )
    parser.add_argument(
        "--questions-per-doc",
        type=int,
        default=3,
        help="Questions to generate per document",
    )

    args = parser.parse_args()

    # Initialize clients
    print("Initializing clients...")
    bedrock_client = get_bedrock_client(region=args.bedrock_region)
    pinecone_client = get_pinecone_client()

    # Sample documents
    print(f"Sampling documents from Pinecone index '{args.index_name}'...")
    num_docs_needed = (
        args.count + args.questions_per_doc - 1
    ) // args.questions_per_doc

    documents = sample_documents(
        pinecone_client, args.index_name, doc_id=args.doc_id, count=num_docs_needed
    )

    print(f"Retrieved {len(documents)} document chunks")

    # Generate questions for each document
    all_questions = []
    for i, doc in enumerate(documents, 1):
        context = doc.get("text", "")
        if not context:
            print(f"  [{i}/{len(documents)}] Skipping document with no text")
            continue

        print(
            f"  [{i}/{len(documents)}] Generating {args.questions_per_doc} questions from doc {doc.get('doc_id', 'unknown')}..."
        )

        questions = generate_questions_with_claude(
            bedrock_client, context, num_questions=args.questions_per_doc
        )

        if questions:
            print(f"    Generated {len(questions)} questions")
            append_to_golden_set(args.golden_set, questions, doc)
            all_questions.extend(questions)
        else:
            print("    Failed to generate questions")

        if len(all_questions) >= args.count:
            break

    print(f"\n✓ Generated {len(all_questions)} questions")
    print(f"✓ Appended to {args.golden_set}")
    print("\nNext steps:")
    print(f"  1. Review and edit {args.golden_set} manually")
    print("  2. Run evaluation: python -m evals.run_ragas")


if __name__ == "__main__":
    main()
