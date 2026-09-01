"""
CLI Runner for IMDb Intelligence Evaluation Suite.
Usage:
    python -m evals.run [--category CATEGORY] [--mode {gold,live}] [--verbose]
"""

import sys
import argparse
from evals.engine import EvalEngine, EvalMode
from evals.reporter import EvalReporter


def main():
    parser = argparse.ArgumentParser(description="Run IMDb Intelligence AI Evaluation Suite")
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter tests by category: plain_and_easy, disambiguation, regional_cinema, relational_queries, typo_and_reflection, security_and_performance"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["gold", "live"],
        default="gold",
        help="Evaluation execution mode: 'gold' (offline baseline) or 'live' (Azure OpenAI)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Optional Azure OpenAI API Key override"
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=None,
        help="Optional Azure OpenAI Endpoint override"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Optional Azure OpenAI Model override (e.g. gpt-5.4)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose assertion traces for each test case"
    )
    args = parser.parse_args()

    mode = EvalMode.LIVE if args.mode == "live" else EvalMode.GOLD

    creds = None
    if args.api_key or args.endpoint or args.model:
        creds = {
            "api_key": args.api_key or "",
            "endpoint": args.endpoint or "",
            "model": args.model or "gpt-5.4"
        }

    print(f"\n🚀 Launching IMDb Intelligence Eval Suite (Mode: {mode.value.upper()})...")
    if args.category:
        print(f"🎯 Filter: Category = '{args.category}'")

    engine = EvalEngine()
    reporter = EvalReporter()

    suite_result = engine.run_suite(category=args.category, mode=mode, creds=creds)

    # 1. Print terminal summary
    reporter.print_terminal_summary(suite_result, verbose=args.verbose)

    # 2. Save Markdown scorecard
    md_path = reporter.save_markdown_report(suite_result)
    print(f"📄 Markdown Scorecard generated at: {md_path}")

    # 3. Save JSON artifact
    json_path = reporter.save_json_artifact(suite_result)
    print(f"💾 JSON Artifact saved at: {json_path}\n")

    # Return exit code based on failures
    if suite_result.failed_tests > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
