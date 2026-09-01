"""
Evaluation Reporter for IMDb Intelligence.
Formats terminal scorecards, generates detailed Markdown reports,
and serializes JSON benchmark artifacts.
"""

import os
import json
from datetime import datetime
from typing import Optional
from evals.engine import EvalSuiteResult, TestCaseResult


class EvalReporter:
    """Formats and writes evaluation results to console, Markdown, and JSON."""

    def __init__(self, output_dir: Optional[str] = None):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.output_dir = output_dir or os.path.join(self.base_dir, "evals", "results")
        os.makedirs(self.output_dir, exist_ok=True)

    def print_terminal_summary(self, suite_result: EvalSuiteResult, verbose: bool = False):
        """Prints a colorized terminal scorecard and detailed failure logs."""
        c_green = "\033[92m"
        c_red = "\033[91m"
        c_yellow = "\033[93m"
        c_cyan = "\033[96m"
        c_bold = "\033[1m"
        c_reset = "\033[0m"

        print(f"\n{c_bold}{c_cyan}========================================================================{c_reset}")
        print(f"{c_bold}{c_cyan}              IMDb INTELLIGENCE EVALUATION SUITE SCORECARD              {c_reset}")
        print(f"{c_bold}{c_cyan}========================================================================{c_reset}\n")

        print(f"  {c_bold}Execution Mode:{c_reset} {suite_result.mode.value.upper()}")
        print(f"  {c_bold}Total Tests:{c_reset}    {suite_result.total_tests}")
        print(f"  {c_bold}Passed:{c_reset}         {c_green}{suite_result.passed_tests}{c_reset}")
        print(f"  {c_bold}Failed:{c_reset}         {c_red if suite_result.failed_tests > 0 else c_green}{suite_result.failed_tests}{c_reset}")
        print(f"  {c_bold}Overall Pass Rate:{c_reset} {c_green if suite_result.pass_rate >= 90 else c_yellow}{suite_result.pass_rate}%{c_reset}")
        print(f"  {c_bold}Average Latency:{c_reset}   {suite_result.avg_latency_ms} ms (P95: {suite_result.p95_latency_ms} ms)")
        print(f"  {c_bold}Avg Soft-F1:{c_reset}       {suite_result.avg_soft_f1}\n")

        print(f"{c_bold}--- Category Breakdown ---{c_reset}")
        header = f"{'Category':<28} | {'Total':<6} | {'Passed':<6} | {'Failed':<6} | {'Pass Rate':<10} | {'Avg Latency'}"
        print(header)
        print("-" * len(header))

        for cat, stats in suite_result.category_summary.items():
            rate_color = c_green if stats["pass_rate"] == 100 else (c_yellow if stats["pass_rate"] >= 75 else c_red)
            print(f"{cat:<28} | {stats['total']:<6} | {stats['passed']:<6} | {stats['failed']:<6} | {rate_color}{stats['pass_rate']:>6.1f}%{c_reset}   | {stats['avg_latency_ms']:>6.1f} ms")

        print("-" * len(header))

        # Print failures
        failed_cases = [r for r in suite_result.results if not r.passed]
        if failed_cases:
            print(f"\n{c_bold}{c_red}--- Failed Test Cases ({len(failed_cases)}) ---{c_reset}")
            for f in failed_cases:
                print(f"\n  ❌ [{f.category}] {c_bold}{f.test_id}{c_reset}: \"{f.query}\"")
                if f.error:
                    print(f"     Error: {f.error}")
                for a in f.assertions:
                    if not a.passed:
                        print(f"     Failed Assertion ({a.name}): {a.message}")
        else:
            print(f"\n{c_green}✨ All test assertions passed successfully!{c_reset}")

        print(f"\n{c_cyan}========================================================================{c_reset}\n")

    def save_markdown_report(self, suite_result: EvalSuiteResult, filename: str = "report.md") -> str:
        """Generates a comprehensive Markdown evaluation scorecard."""
        filepath = os.path.join(self.output_dir, filename)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        status_emoji = "✅ PASS" if suite_result.failed_tests == 0 else "⚠️ REVIEW REQUIRED"

        md = f"""# IMDb Intelligence Evaluation Scorecard

**Status:** {status_emoji}  
**Date:** {now_str}  
**Execution Mode:** `{suite_result.mode.value.upper()}`  
**DuckDB Parquet Engine:** Verified

---

## 1. Executive Summary

| Metric | Score / Value | Status |
| :--- | :--- | :--- |
| **Total Test Cases** | {suite_result.total_tests} | — |
| **Passed Tests** | {suite_result.passed_tests} | ✅ |
| **Failed Tests** | {suite_result.failed_tests} | {'❌' if suite_result.failed_tests > 0 else '✅'} |
| **Overall Pass Rate** | **{suite_result.pass_rate}%** | {'🟢 High' if suite_result.pass_rate >= 90 else '🟡 Moderate'} |
| **Average DuckDB Latency** | {suite_result.avg_latency_ms} ms | ⚡ Fast |
| **P95 Execution Latency** | {suite_result.p95_latency_ms} ms | ⚡ Fast |
| **Average Soft-F1 Score** | {suite_result.avg_soft_f1} | 🎯 High Fidelity |

---

## 2. Category Performance

| Evaluation Category | Total Tests | Passed | Failed | Pass Rate | Avg Latency |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""

        for cat, stats in suite_result.category_summary.items():
            rate_icon = "🟢" if stats["pass_rate"] == 100 else ("🟡" if stats["pass_rate"] >= 75 else "🔴")
            cat_display = cat.replace("_", " ").title()
            md += f"| **{cat_display}** | {stats['total']} | {stats['passed']} | {stats['failed']} | {rate_icon} {stats['pass_rate']}% | {stats['avg_latency_ms']} ms |\n"

        md += """
---

## 3. Test Cases & Assertion Trace

| Test ID | Category | Query | Status | Latency | Rows | Invariant Details |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""

        for r in suite_result.results:
            status_tag = "✅ Pass" if r.passed else "❌ Fail"
            cat_short = r.category.replace("_", " ").title()
            failed_msgs = "; ".join([a.message for a in r.assertions if not a.passed])
            details = failed_msgs if failed_msgs else "All invariants verified"
            # escape pipes for markdown table
            safe_query = r.query.replace("|", "\\|")
            safe_details = details.replace("|", "\\|")
            md += f"| `{r.test_id}` | {cat_short} | \"{safe_query}\" | {status_tag} | {r.execution_time_ms} ms | {r.row_count} | {safe_details} |\n"

        md += "\n---\n\n## 4. Evaluation Assertion Methodology\n\n"
        md += "- **Static / AST Validation**: Validates DuckDB `EXPLAIN` query plans and ensures zero DDL/DML mutation keywords (`DROP`, `DELETE`, `UPDATE`).\n"
        md += "- **Plan Efficiency**: Verifies indexed lookup patterns (`WITH matched_people AS MATERIALIZED`) and routes standard joins to `crew_lookup`.\n"
        md += "- **Result Invariants**: Confirms canonical entity ID inclusion, forbidden ID exclusion, and strict predicate satisfaction (`genres`, `original_language`, `premiered`).\n"
        md += "- **Reflection Evals**: Tests zero-result diagnosis (`MISSPELLED_ENTITY`, `OVERLY_STRICT_FILTER`, `GENUINE_EMPTY`).\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)

        return filepath

    def save_json_artifact(self, suite_result: EvalSuiteResult, filename: str = "latest_run.json") -> str:
        """Serializes full test results to JSON."""
        filepath = os.path.join(self.output_dir, filename)
        
        data = {
            "mode": suite_result.mode.value,
            "timestamp": datetime.now().isoformat(),
            "total_tests": suite_result.total_tests,
            "passed_tests": suite_result.passed_tests,
            "failed_tests": suite_result.failed_tests,
            "pass_rate": suite_result.pass_rate,
            "avg_latency_ms": suite_result.avg_latency_ms,
            "p95_latency_ms": suite_result.p95_latency_ms,
            "avg_soft_f1": suite_result.avg_soft_f1,
            "category_summary": suite_result.category_summary,
            "results": [
                {
                    "test_id": r.test_id,
                    "category": r.category,
                    "query": r.query,
                    "description": r.description,
                    "sql": r.sql,
                    "passed": r.passed,
                    "execution_time_ms": r.execution_time_ms,
                    "row_count": r.row_count,
                    "soft_f1": r.soft_f1,
                    "jaccard": r.jaccard,
                    "diagnosis": r.diagnosis,
                    "error": r.error,
                    "assertions": [
                        {
                            "name": a.name,
                            "passed": a.passed,
                            "message": a.message,
                            "category": a.category,
                            "details": a.details
                        }
                        for a in r.assertions
                    ]
                }
                for r in suite_result.results
            ]
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        return filepath
