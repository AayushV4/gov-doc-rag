#!/usr/bin/env python3
"""
Compare RAGAS evaluation results between two runs (e.g., baseline vs reranker).

Usage:
    python -m evals.compare_results results_baseline.json results_reranker.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


def load_results(filepath: str) -> Dict[str, Any]:
    """Load evaluation results from JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def calculate_improvement(baseline: float, reranker: float) -> Dict[str, Any]:
    """
    Calculate improvement metrics.

    Returns:
    - absolute_diff: reranker - baseline
    - relative_improvement: (reranker - baseline) / baseline * 100
    - better: whether reranker is better
    """
    abs_diff = reranker - baseline
    if baseline != 0:
        rel_improvement = (abs_diff / baseline) * 100
    else:
        rel_improvement = float("inf") if abs_diff > 0 else 0.0

    return {
        "absolute_diff": abs_diff,
        "relative_improvement": rel_improvement,
        "better": abs_diff > 0,
    }


def compare_metrics(baseline_results: Dict, reranker_results: Dict) -> Dict[str, Any]:
    """Compare metrics between baseline and reranker results."""
    comparison = {
        "ragas_metrics": {},
        "citation_metrics": {},
    }

    # Compare RAGAS metrics
    baseline_ragas = baseline_results.get("ragas_metrics", {})
    reranker_ragas = reranker_results.get("ragas_metrics", {})

    for metric in baseline_ragas:
        if isinstance(baseline_ragas[metric], (int, float)) and isinstance(
            reranker_ragas.get(metric), (int, float)
        ):
            comparison["ragas_metrics"][metric] = {
                "baseline": baseline_ragas[metric],
                "reranker": reranker_ragas[metric],
                **calculate_improvement(baseline_ragas[metric], reranker_ragas[metric]),
            }

    # Compare citation metrics
    baseline_citation = baseline_results.get("citation_metrics", {})
    reranker_citation = reranker_results.get("citation_metrics", {})

    for metric in baseline_citation:
        if isinstance(baseline_citation[metric], (int, float)) and isinstance(
            reranker_citation.get(metric), (int, float)
        ):
            comparison["citation_metrics"][metric] = {
                "baseline": baseline_citation[metric],
                "reranker": reranker_citation[metric],
                **calculate_improvement(
                    baseline_citation[metric], reranker_citation[metric]
                ),
            }

    # Add reranker-specific metrics
    reranker_specific = reranker_results.get("reranker_metrics", {})
    if reranker_specific.get("has_rerank_scores"):
        comparison["reranker_specific"] = reranker_specific

    return comparison


def print_comparison(
    comparison: Dict[str, Any], baseline_file: str, reranker_file: str
):
    """Print formatted comparison results."""
    print("\n" + "=" * 80)
    print("EVALUATION COMPARISON: BASELINE vs RERANKER")
    print("=" * 80)
    print(f"\nBaseline: {baseline_file}")
    print(f"Reranker: {reranker_file}")

    # RAGAS metrics comparison
    if comparison["ragas_metrics"]:
        print("\n" + "-" * 80)
        print("RAGAS METRICS COMPARISON")
        print("-" * 80)
        print(
            f"{'Metric':<30} {'Baseline':>10} {'Reranker':>10} {'Δ Abs':>10} {'Δ %':>10} {'Better':>8}"
        )
        print("-" * 80)

        for metric, values in comparison["ragas_metrics"].items():
            baseline_val = values["baseline"]
            reranker_val = values["reranker"]
            abs_diff = values["absolute_diff"]
            rel_diff = values["relative_improvement"]
            better = "✓" if values["better"] else "✗"

            print(
                f"{metric:<30} {baseline_val:>10.4f} {reranker_val:>10.4f} "
                f"{abs_diff:>+10.4f} {rel_diff:>+9.2f}% {better:>8}"
            )

    # Citation metrics comparison
    if comparison["citation_metrics"]:
        print("\n" + "-" * 80)
        print("CITATION METRICS COMPARISON")
        print("-" * 80)
        print(
            f"{'Metric':<30} {'Baseline':>10} {'Reranker':>10} {'Δ Abs':>10} {'Δ %':>10} {'Better':>8}"
        )
        print("-" * 80)

        for metric, values in comparison["citation_metrics"].items():
            baseline_val = values["baseline"]
            reranker_val = values["reranker"]
            abs_diff = values["absolute_diff"]
            rel_diff = values["relative_improvement"]
            better = "✓" if values["better"] else "✗"

            print(
                f"{metric:<30} {baseline_val:>10.4f} {reranker_val:>10.4f} "
                f"{abs_diff:>+10.4f} {rel_diff:>+9.2f}% {better:>8}"
            )

    # Reranker-specific metrics
    if "reranker_specific" in comparison and comparison["reranker_specific"].get(
        "has_rerank_scores"
    ):
        print("\n" + "-" * 80)
        print("RERANKER-SPECIFIC METRICS")
        print("-" * 80)

        reranker_metrics = comparison["reranker_specific"]
        print(f"{'Metric':<40} {'Value':>15}")
        print("-" * 80)
        for metric, value in reranker_metrics.items():
            if metric not in ["has_rerank_scores", "message"] and isinstance(
                value, (int, float)
            ):
                print(f"{metric:<40} {value:>15.4f}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if comparison["ragas_metrics"]:
        improvements = sum(
            1 for v in comparison["ragas_metrics"].values() if v["better"]
        )
        total = len(comparison["ragas_metrics"])
        print(
            f"RAGAS metrics improved: {improvements}/{total} "
            f"({improvements/total*100:.1f}%)"
        )

    if comparison["citation_metrics"]:
        improvements = sum(
            1 for v in comparison["citation_metrics"].values() if v["better"]
        )
        total = len(comparison["citation_metrics"])
        print(
            f"Citation metrics improved: {improvements}/{total} "
            f"({improvements/total*100:.1f}%)"
        )

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Compare baseline vs reranker evaluation results"
    )
    parser.add_argument("baseline", type=str, help="Path to baseline results JSON file")
    parser.add_argument("reranker", type=str, help="Path to reranker results JSON file")
    parser.add_argument(
        "--output", type=str, help="Path to save comparison JSON (optional)"
    )
    args = parser.parse_args()

    # Load results
    try:
        baseline_results = load_results(args.baseline)
        reranker_results = load_results(args.reranker)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Compare results
    comparison = compare_metrics(baseline_results, reranker_results)

    # Print comparison
    print_comparison(comparison, args.baseline, args.reranker)

    # Save comparison if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(comparison, f, indent=2, default=str)

        print(f"\nComparison saved to {args.output}")


if __name__ == "__main__":
    main()
