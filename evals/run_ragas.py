import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import requests
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    answer_correctness,
    answer_relevancy,
    answer_similarity,
    context_precision,
    context_recall,
    faithfulness,
)


def load_golden_set(csv_path: str) -> List[Dict[str, Any]]:
    """Load the golden set CSV into a list of dictionaries."""
    golden_set = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            golden_set.append(row)
    return golden_set


def query_rag_api(
    api_url: str, question: str, lang: str = None, k: int = 6
) -> Dict[str, Any]:
    """Query the RAG API and return the response."""
    endpoint = f"{api_url}/ask"
    payload = {"query": question, "k": k}
    if lang:
        payload["lang_hint"] = lang

    try:
        response = requests.post(endpoint, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error querying API: {e}", file=sys.stderr)
        return {"answer": "", "citations": []}


def prepare_ragas_dataset(golden_set: List[Dict], api_responses: List[Dict]) -> Dataset:
    """
    Prepare data in RAGAS format.

    RAGAS expects:
    - question: The question asked
    - answer: The generated answer
    - contexts: List of retrieved context strings
    - ground_truth: The expected answer (for answer correctness)
    - ground_truths: List of reference contexts (for context recall)
    """
    data = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
        "ground_truths": [],
    }

    for golden, response in zip(golden_set, api_responses):
        # Question
        data["question"].append(golden["question"])

        # Generated answer
        data["answer"].append(response.get("answer", ""))

        # Retrieved contexts (from citations)
        contexts = [
            citation.get("snippet", "") for citation in response.get("citations", [])
        ]
        data["contexts"].append(contexts if contexts else [""])

        # Ground truth answer
        data["ground_truth"].append(golden["expected_answer"])

        # Ground truth contexts (from golden set)
        ground_truth_context = golden.get("ground_truth_context", "")
        data["ground_truths"].append(
            [ground_truth_context] if ground_truth_context else [""]
        )

    return Dataset.from_dict(data)


def calculate_citation_metrics(
    golden_set: List[Dict], api_responses: List[Dict]
) -> Dict[str, float]:
    """
    Calculate custom citation-based metrics:
    - Citation Precision: % of returned citations that are in expected_citations
    - Citation Recall: % of expected_citations that were returned
    - Citation F1: Harmonic mean of precision and recall
    """
    total_precision = 0.0
    total_recall = 0.0
    count = 0

    for golden, response in zip(golden_set, api_responses):
        expected_citations_str = golden.get("expected_citations", "")
        if not expected_citations_str:
            continue

        # Parse expected citations (format: "doc-id:page,doc-id:page")
        expected = set(cite.strip() for cite in expected_citations_str.split(","))

        # Parse returned citations
        returned = set()
        for citation in response.get("citations", []):
            doc_id = citation.get("doc_id", "")
            page = citation.get("page", 0)
            if doc_id and page:
                returned.add(f"{doc_id}:{page}")

        if not expected and not returned:
            continue

        # Calculate precision and recall
        if returned:
            precision = len(expected & returned) / len(returned)
        else:
            precision = 0.0

        if expected:
            recall = len(expected & returned) / len(expected)
        else:
            recall = 0.0

        total_precision += precision
        total_recall += recall
        count += 1

    if count == 0:
        return {"citation_precision": 0.0, "citation_recall": 0.0, "citation_f1": 0.0}

    avg_precision = total_precision / count
    avg_recall = total_recall / count
    f1 = (
        2 * (avg_precision * avg_recall) / (avg_precision + avg_recall)
        if (avg_precision + avg_recall) > 0
        else 0.0
    )

    return {
        "citation_precision": avg_precision,
        "citation_recall": avg_recall,
        "citation_f1": f1,
    }


def main():
    parser = argparse.ArgumentParser(description="Run RAGAS evaluation on golden set")
    parser.add_argument(
        "--golden-set",
        type=str,
        default="evals/golden_set.csv",
        help="Path to golden set CSV file",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the RAG API",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evals/results.json",
        help="Path to save evaluation results JSON",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=6,
        help="Number of documents to retrieve",
    )
    args = parser.parse_args()

    # Load golden set
    print(f"Loading golden set from {args.golden_set}...")
    golden_set = load_golden_set(args.golden_set)
    print(f"Loaded {len(golden_set)} evaluation examples")

    # Query API for each question
    print(f"\nQuerying API at {args.api_url}...")
    api_responses = []
    for i, item in enumerate(golden_set, 1):
        print(f"  [{i}/{len(golden_set)}] {item['question'][:60]}...")
        response = query_rag_api(
            args.api_url, item["question"], lang=item.get("lang"), k=args.k
        )
        api_responses.append(response)

    # Prepare RAGAS dataset
    print("\nPreparing RAGAS dataset...")
    dataset = prepare_ragas_dataset(golden_set, api_responses)

    # Run RAGAS evaluation
    print("\nRunning RAGAS evaluation...")
    print(
        "  Metrics: faithfulness, answer_relevancy, context_precision, context_recall"
    )
    print("           answer_similarity, answer_correctness")

    ragas_results = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
            answer_similarity,
            answer_correctness,
        ],
    )

    # Calculate custom citation metrics
    print("\nCalculating citation metrics...")
    citation_metrics = calculate_citation_metrics(golden_set, api_responses)

    # Combine results
    results = {
        "ragas_metrics": ragas_results,
        "citation_metrics": citation_metrics,
        "num_examples": len(golden_set),
        "api_url": args.api_url,
        "k": args.k,
    }

    # Print summary
    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print("\nRAGAS Metrics:")
    for metric, value in ragas_results.items():
        if isinstance(value, (int, float)):
            print(f"  {metric:25s}: {value:.4f}")

    print("\nCitation Metrics:")
    for metric, value in citation_metrics.items():
        print(f"  {metric:25s}: {value:.4f}")

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
