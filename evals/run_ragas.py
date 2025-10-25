import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from langchain_aws import ChatBedrock, BedrockEmbeddings

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


def analyze_reranker_metrics(api_responses: List[Dict]) -> Dict[str, Any]:
    """
    Analyze reranker performance if rerank scores are present.

    Returns:
    - has_rerank_scores: Whether responses include rerank scores
    - avg_rerank_score: Average rerank score across all citations
    - min_rerank_score: Minimum rerank score
    - max_rerank_score: Maximum rerank score
    - rerank_score_distribution: Distribution by quartile
    """
    rerank_scores = []
    has_scores = False

    for response in api_responses:
        for citation in response.get("citations", []):
            score = citation.get("rerank_score")
            if score is not None:
                has_scores = True
                rerank_scores.append(score)

    if not has_scores or not rerank_scores:
        return {
            "has_rerank_scores": False,
            "message": "No rerank scores found in responses",
        }

    sorted_scores = sorted(rerank_scores)
    n = len(sorted_scores)

    return {
        "has_rerank_scores": True,
        "num_scored_citations": len(rerank_scores),
        "avg_rerank_score": sum(rerank_scores) / n,
        "min_rerank_score": min(rerank_scores),
        "max_rerank_score": max(rerank_scores),
        "median_rerank_score": sorted_scores[n // 2],
        "q1_rerank_score": sorted_scores[n // 4],
        "q3_rerank_score": sorted_scores[3 * n // 4],
    }


def setup_bedrock_llm(region: str = "us-east-1"):
    """Configure Bedrock LLM for RAGAS evaluation."""
    llm = ChatBedrock(
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        region_name=region,
        model_kwargs={
            "temperature": 0.0,
            "max_tokens": 2048,
        },
    )

    embeddings = BedrockEmbeddings(
        model_id="cohere.embed-english-v3",
        region_name=region,
    )

    return llm, embeddings


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

    print("\nSetting up AWS Bedrock for evaluation...")
    llm, embeddings = setup_bedrock_llm(region="us-east-1")

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
        llm=llm,
        embeddings=embeddings,
    )

    # Calculate custom citation metrics
    print("\nCalculating citation metrics...")
    citation_metrics = calculate_citation_metrics(golden_set, api_responses)

    # Analyze reranker performance
    print("\nAnalyzing reranker metrics...")
    reranker_metrics = analyze_reranker_metrics(api_responses)

    # Combine results
    results = {
        "ragas_metrics": ragas_results,
        "citation_metrics": citation_metrics,
        "reranker_metrics": reranker_metrics,
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

    print("\nReranker Metrics:")
    if reranker_metrics.get("has_rerank_scores"):
        for metric, value in reranker_metrics.items():
            if metric != "has_rerank_scores" and isinstance(value, (int, float)):
                print(f"  {metric:25s}: {value:.4f}")
    else:
        print(f"  {reranker_metrics.get('message', 'No reranker data')}")

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
