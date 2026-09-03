"""
Core Evaluation Engine for IMDb Intelligence.
Orchestrates test case loading, SQL generation (Live LLM or Gold baseline),
DuckDB execution, telemetry collection, assertion validation, and metric aggregation.
"""

import os
import json
import time
import duckdb
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from evals.assertions import (
    AssertionResult,
    assert_is_read_only,
    assert_valid_duckdb_syntax,
    assert_plan_performance,
    assert_proper_type_filter,
    assert_required_columns,
    assert_row_count_bounds,
    assert_must_contain_ids,
    assert_must_exclude_ids,
    assert_predicate_compliance,
    assert_monotonic_order,
    assert_reflection_diagnosis,
    assert_corrected_entity,
    calculate_soft_f1,
    calculate_jaccard_similarity
)


class EvalMode(str, Enum):
    GOLD = "gold"      # Offline: Runs and validates Gold SQL assertions with 0 API tokens
    LIVE = "live"      # Online: Calls Azure OpenAI to generate SQL & reflection
    MOCK = "mock"      # Offline: Uses mocked/recorded SQL strings


@dataclass
class TestCaseResult:
    test_id: str
    category: str
    query: str
    description: str
    sql: str
    passed: bool
    execution_time_ms: float
    row_count: int
    assertions: List[AssertionResult]
    soft_f1: float = 1.0
    jaccard: float = 1.0
    diagnosis: Optional[str] = None
    corrected_entity: Optional[str] = None
    error: Optional[str] = None


@dataclass
class EvalSuiteResult:
    mode: EvalMode
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate: float
    avg_soft_f1: float
    avg_latency_ms: float
    p95_latency_ms: float
    category_summary: Dict[str, Dict[str, Any]]
    results: List[TestCaseResult] = field(default_factory=list)


IMDB_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS titles (
    title_id VARCHAR,
    primary_title VARCHAR,
    original_title VARCHAR,
    type VARCHAR,
    original_language VARCHAR,
    origin_country VARCHAR,
    is_adult INTEGER,
    premiered INTEGER,
    ended INTEGER,
    runtime_minutes INTEGER,
    genres VARCHAR,
    overview VARCHAR,
    poster_path VARCHAR
);
CREATE TABLE IF NOT EXISTS ratings (
    title_id VARCHAR,
    rating FLOAT,
    votes INTEGER
);
CREATE TABLE IF NOT EXISTS people (
    person_id VARCHAR,
    name VARCHAR,
    born INTEGER,
    died INTEGER
);
CREATE TABLE IF NOT EXISTS crew (
    title_id VARCHAR,
    person_id VARCHAR,
    category VARCHAR,
    job VARCHAR,
    characters VARCHAR
);
CREATE TABLE IF NOT EXISTS crew_lookup (
    person_id VARCHAR,
    category VARCHAR,
    title_id VARCHAR
);
CREATE TABLE IF NOT EXISTS akas (
    title_id VARCHAR,
    title VARCHAR,
    region VARCHAR,
    language VARCHAR,
    types VARCHAR,
    attributes VARCHAR,
    is_original_title INTEGER
);
"""


class EvalEngine:
    """Evaluation harness for running test cases and collecting benchmarks."""

    def __init__(self, db_path: Optional[str] = None, dataset_path: Optional[str] = None):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = db_path or os.path.join(self.base_dir, "db", "imdb.duckdb")
        self.dataset_path = dataset_path or os.path.join(self.base_dir, "evals", "dataset.json")
        self._duckdb_con = None
        self.is_schema_only = False

    def get_db(self):
        """Returns a read-only DuckDB connection (disk-backed or in-memory schema fallback for CI)."""
        if self._duckdb_con is None:
            if os.path.exists(self.db_path):
                self._duckdb_con = duckdb.connect(self.db_path, read_only=True)
                self.is_schema_only = False
            else:
                # In headless CI or clean checkouts where the 2.3 GB DuckDB file is not stored in git,
                # provision an in-memory DuckDB connection loaded with the exact IMDb table schemas.
                self._duckdb_con = duckdb.connect(":memory:")
                self._duckdb_con.execute(IMDB_SCHEMA_DDL)
                self.is_schema_only = True
        return self._duckdb_con

    def load_dataset(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Loads test cases from dataset.json with optional category filtering."""
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if category:
            data = [t for t in data if t.get("category") == category]
        return data

    def execute_sql(self, sql: str) -> Tuple[List[Dict[str, Any]], List[str], float]:
        """Executes SQL against DuckDB and returns (rows_as_dicts, column_names, elapsed_ms)."""
        con = self.get_db()
        start = time.perf_counter()
        cursor = con.cursor()
        cursor.execute(sql)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        
        col_names = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        rows_dicts = [dict(zip(col_names, r)) for r in rows]
        return rows_dicts, col_names, elapsed_ms

    def run_single_test(self, test_case: Dict[str, Any], mode: EvalMode = EvalMode.GOLD, creds: Optional[Dict[str, Any]] = None) -> TestCaseResult:
        """Executes a single test case through the assertion pipeline."""
        test_id = test_case["id"]
        category = test_case["category"]
        query = test_case["query"]
        desc = test_case.get("description", "")
        rules = test_case.get("assertions", {})
        
        sql_to_run = ""
        diagnosis = None
        corrected_entity = None
        error_msg = None
        
        # 1. Obtain SQL
        if mode == EvalMode.GOLD:
            sql_to_run = test_case.get("gold_sql", "")
        elif mode == EvalMode.LIVE:
            try:
                # Import views dynamically to allow standalone execution
                from app.views import generate_response, probe_duckdb_entities, reflect_on_zero_results, extract_filter_literals
                sql_to_run = generate_response(query, creds=creds)
            except Exception as e:
                error_msg = f"LLM SQL Generation failed: {str(e)}"
                return TestCaseResult(
                    test_id=test_id,
                    category=category,
                    query=query,
                    description=desc,
                    sql="",
                    passed=False,
                    execution_time_ms=0.0,
                    row_count=0,
                    assertions=[AssertionResult("llm_generation", False, error_msg, "llm")],
                    error=error_msg
                )

        assertion_results: List[AssertionResult] = []
        
        # 2. Static & Safety Assertions
        assertion_results.append(assert_is_read_only(sql_to_run))
        assertion_results.append(assert_valid_duckdb_syntax(sql_to_run, self.get_db()))
        
        if rules.get("check_plan_performance"):
            assertion_results.append(assert_plan_performance(sql_to_run))
            
        if rules.get("expected_type"):
            assertion_results.append(assert_proper_type_filter(sql_to_run, rules["expected_type"]))

        # If static checks failed critically, stop before execution
        if any(not a.passed for a in assertion_results if a.category in ("security", "syntax")):
            return TestCaseResult(
                test_id=test_id,
                category=category,
                query=query,
                description=desc,
                sql=sql_to_run,
                passed=False,
                execution_time_ms=0.0,
                row_count=0,
                assertions=assertion_results,
                error="Static syntax or security check failed"
            )

        # 3. Execution Assertions
        rows_dicts = []
        col_names = []
        elapsed_ms = 0.0
        
        try:
            rows_dicts, col_names, elapsed_ms = self.execute_sql(sql_to_run)
        except Exception as e:
            assertion_results.append(AssertionResult("sql_execution", False, f"DuckDB Execution Error: {e}", "execution"))
            return TestCaseResult(
                test_id=test_id,
                category=category,
                query=query,
                description=desc,
                sql=sql_to_run,
                passed=False,
                execution_time_ms=0.0,
                row_count=0,
                assertions=assertion_results,
                error=str(e)
            )

        # 4. Result Invariant Assertions
        if not self.is_schema_only:
            if "min_rows" in rules:
                assertion_results.append(assert_row_count_bounds(rows_dicts, min_rows=rules["min_rows"], max_rows=rules.get("max_rows")))
                
            if col_names:
                assertion_results.append(assert_required_columns(col_names, required=["title_id", "primary_title"]))
                
            if rules.get("must_include_title_ids"):
                assertion_results.append(assert_must_contain_ids(rows_dicts, rules["must_include_title_ids"]))
                
            if rules.get("must_exclude_title_ids"):
                assertion_results.append(assert_must_exclude_ids(rows_dicts, rules["must_exclude_title_ids"]))
                
            if rules.get("predicate_rules"):
                assertion_results.append(assert_predicate_compliance(rows_dicts, rules["predicate_rules"]))
                
            if rules.get("order_by"):
                parts = rules["order_by"].split()
                sort_key = parts[0]
                direction = parts[1] if len(parts) > 1 else "DESC"
                assertion_results.append(assert_monotonic_order(rows_dicts, sort_key=sort_key, direction=direction))
        else:
            assertion_results.append(
                AssertionResult(
                    "schema_validation",
                    True,
                    "SQL compiled, explained, and executed against schema (row bounds require local DuckDB artifact)",
                    "schema"
                )
            )

        # 5. Reflection Assertions (if expected_diagnosis is set)
        if rules.get("expected_diagnosis"):
            if mode == EvalMode.GOLD:
                # In Gold mode, verify the gold tag is present
                assertion_results.append(assert_reflection_diagnosis(rules["expected_diagnosis"], rules["expected_diagnosis"]))
            elif mode == EvalMode.LIVE:
                try:
                    from app.views import probe_duckdb_entities, reflect_on_zero_results, extract_filter_literals
                    literals = extract_filter_literals(sql_to_run, query)
                    probe_data = probe_duckdb_entities(literals)
                    ref = reflect_on_zero_results(query, sql_to_run, probe_data, creds=creds)
                    diagnosis = ref.get("diagnosis")
                    corrected_entity = ref.get("corrected_entity")
                    assertion_results.append(assert_reflection_diagnosis(diagnosis, rules["expected_diagnosis"]))
                    if rules.get("expected_corrected_entity"):
                        assertion_results.append(assert_corrected_entity(corrected_entity, rules["expected_corrected_entity"]))
                except Exception as e:
                    assertion_results.append(AssertionResult("reflection_execution", False, f"Reflection error: {e}", "reflection"))

        # 6. Soft-F1 & Jaccard vs Gold
        soft_f1 = 1.0
        jaccard = 1.0
        if mode == EvalMode.LIVE and test_case.get("gold_sql"):
            try:
                gold_rows, _, _ = self.execute_sql(test_case["gold_sql"])
                gold_ids = [r["title_id"] for r in gold_rows if "title_id" in r]
                pred_ids = [r["title_id"] for r in rows_dicts if "title_id" in r]
                _, _, soft_f1 = calculate_soft_f1(pred_ids, gold_ids)
                jaccard = calculate_jaccard_similarity(pred_ids, gold_ids)
            except Exception:
                pass

        all_passed = all(a.passed for a in assertion_results)
        
        return TestCaseResult(
            test_id=test_id,
            category=category,
            query=query,
            description=desc,
            sql=sql_to_run,
            passed=all_passed,
            execution_time_ms=elapsed_ms,
            row_count=len(rows_dicts),
            assertions=assertion_results,
            soft_f1=soft_f1,
            jaccard=jaccard,
            diagnosis=diagnosis,
            corrected_entity=corrected_entity,
            error=error_msg
        )

    def run_suite(self, category: Optional[str] = None, mode: EvalMode = EvalMode.GOLD, creds: Optional[Dict[str, Any]] = None) -> EvalSuiteResult:
        """Runs the entire evaluation suite or a filtered category."""
        test_cases = self.load_dataset(category=category)
        results: List[TestCaseResult] = []
        
        for case in test_cases:
            res = self.run_single_test(case, mode=mode, creds=creds)
            results.append(res)
            
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = round((passed / total * 100) if total > 0 else 0.0, 2)
        
        latencies = sorted([r.execution_time_ms for r in results])
        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        p95_idx = int(len(latencies) * 0.95)
        p95_latency = latencies[p95_idx] if latencies else 0.0
        
        avg_soft_f1 = round(sum(r.soft_f1 for r in results) / total, 4) if total > 0 else 1.0
        
        # Category summary
        categories = sorted(list({r.category for r in results}))
        cat_summary = {}
        for cat in categories:
            cat_res = [r for r in results if r.category == cat]
            c_total = len(cat_res)
            c_passed = sum(1 for r in cat_res if r.passed)
            cat_summary[cat] = {
                "total": c_total,
                "passed": c_passed,
                "failed": c_total - c_passed,
                "pass_rate": round((c_passed / c_total * 100) if c_total > 0 else 0.0, 2),
                "avg_latency_ms": round(sum(r.execution_time_ms for r in cat_res) / c_total, 2) if c_total > 0 else 0.0
            }
            
        return EvalSuiteResult(
            mode=mode,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            pass_rate=pass_rate,
            avg_soft_f1=avg_soft_f1,
            avg_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            category_summary=cat_summary,
            results=results
        )
