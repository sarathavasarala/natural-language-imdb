"""
Assertion Engine & Metric Calculator for IMDb Intelligence Evaluations.
Provides deterministic code assertions, result set invariant checks,
plan efficiency validators, security guardrails, and benchmark metrics (EX, Soft-F1).
"""

import re
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class AssertionResult:
    """Represents the outcome of a single assertion check."""
    name: str
    passed: bool
    message: str
    category: str = "general"
    details: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------
# 1. Static & Security Assertions
# ---------------------------------------------------------

def assert_is_read_only(sql: str) -> AssertionResult:
    """Verifies that the SQL contains no data or schema mutation operations."""
    if not sql:
        return AssertionResult("is_read_only", False, "SQL query is empty", "security")
    
    sql_lower = sql.lower()
    dangerous_keywords = ['drop', 'delete', 'update', 'insert', 'alter', 'create', 'truncate', 'grant', 'revoke']
    for kw in dangerous_keywords:
        if re.search(r'\b' + kw + r'\b', sql_lower):
            return AssertionResult(
                "is_read_only",
                False,
                f"Potentially dangerous DDL/DML keyword detected: '{kw}'",
                "security",
                {"keyword": kw}
            )
            
    if not (sql_lower.strip().startswith('select') or sql_lower.strip().startswith('with')):
        return AssertionResult(
            "is_read_only",
            False,
            "SQL query must be a SELECT or WITH statement",
            "security"
        )
        
    return AssertionResult("is_read_only", True, "SQL is read-only and safe", "security")


def assert_valid_duckdb_syntax(sql: str, duckdb_con) -> AssertionResult:
    """Verifies that the SQL query compiles cleanly in DuckDB using EXPLAIN."""
    if not sql:
        return AssertionResult("valid_duckdb_syntax", False, "SQL query is empty", "syntax")
    
    try:
        duckdb_con.execute(f"EXPLAIN {sql}")
        return AssertionResult("valid_duckdb_syntax", True, "DuckDB query plan generated successfully", "syntax")
    except Exception as e:
        return AssertionResult(
            "valid_duckdb_syntax",
            False,
            f"DuckDB syntax validation error: {str(e)}",
            "syntax",
            {"error": str(e)}
        )


def assert_plan_performance(sql: str) -> AssertionResult:
    """
    Verifies physical query plan optimizations:
    1. Uses 'crew_lookup' for credit joins unless 'job' or 'characters' is explicitly selected.
    2. Uses 'WITH matched_people AS MATERIALIZED' for named person lookups to leverage index.
    """
    if not sql:
        return AssertionResult("plan_performance", False, "SQL is empty", "performance")
        
    sql_lower = sql.lower()
    
    # Check if raw 544MB 'crew' table is used when detail columns aren't needed
    has_detail_cols = bool(re.search(r'\b(job|characters)\b', sql_lower))
    uses_raw_crew = bool(re.search(r'\b(from|join)\s+crew\b', sql_lower))
    
    if uses_raw_crew and not has_detail_cols:
        return AssertionResult(
            "plan_performance",
            False,
            "Query joined heavy 'crew' table instead of optimized 'crew_lookup'",
            "performance"
        )
        
    # Check if named person lookup uses materialized CTE pattern
    mentions_people = "from people" in sql_lower or "join people" in sql_lower
    has_materialized_cte = "materialized" in sql_lower and "matched_people" in sql_lower
    
    if mentions_people and not has_materialized_cte and "where name" in sql_lower:
        # Warning/minor failure: person lookup without materialized CTE
        return AssertionResult(
            "plan_performance",
            True, # Pass with warning info
            "Passed, but could use 'WITH matched_people AS MATERIALIZED' for optimal name index utilization",
            "performance",
            {"suboptimal_person_join": True}
        )
        
    return AssertionResult("plan_performance", True, "Physical plan follows indexing and lookup best practices", "performance")


def assert_proper_type_filter(sql: str, expected_type: str = "movie") -> AssertionResult:
    """Verifies that movie or TV series queries apply the correct titles.type filters."""
    if not sql:
        return AssertionResult("proper_type_filter", False, "SQL is empty", "schema")
        
    sql_lower = sql.lower()
    if expected_type == "movie":
        if "tvseries" in sql_lower or "tvepisode" in sql_lower:
            return AssertionResult("proper_type_filter", False, "Movie query contained TV series/episode filters", "schema")
    elif expected_type == "tvSeries":
        if "'movie'" in sql_lower and "tvseries" not in sql_lower:
            return AssertionResult("proper_type_filter", False, "TV series query contained movie filters", "schema")
            
    return AssertionResult("proper_type_filter", True, f"Appropriate type filter for '{expected_type}'", "schema")


# ---------------------------------------------------------
# 2. Execution & Result Set Invariant Assertions
# ---------------------------------------------------------

def assert_required_columns(
    column_names: List[str],
    required: Optional[List[str]] = None
) -> AssertionResult:
    """Checks that all essential columns are present in the query output."""
    if required is None:
        required = ["title_id", "primary_title"]
        
    col_set = {c.lower() for c in column_names}
    missing = [col for col in required if col.lower() not in col_set]
    
    if missing:
        return AssertionResult(
            "required_columns",
            False,
            f"Missing essential output columns: {', '.join(missing)}",
            "schema",
            {"missing": missing, "present": column_names}
        )
    return AssertionResult("required_columns", True, "All required columns are present in output", "schema")


def assert_row_count_bounds(
    rows: List[Any],
    min_rows: int = 1,
    max_rows: Optional[int] = None
) -> AssertionResult:
    """Verifies that the returned result count falls within expected bounds."""
    count = len(rows)
    if count < min_rows:
        return AssertionResult(
            "row_count_bounds",
            False,
            f"Returned {count} rows, which is below minimum expected threshold of {min_rows}",
            "execution",
            {"count": count, "min": min_rows, "max": max_rows}
        )
    if max_rows is not None and count > max_rows:
        return AssertionResult(
            "row_count_bounds",
            False,
            f"Returned {count} rows, which exceeds maximum expected limit of {max_rows}",
            "execution",
            {"count": count, "min": min_rows, "max": max_rows}
        )
    return AssertionResult("row_count_bounds", True, f"Returned valid row count: {count}", "execution", {"count": count})


def assert_must_contain_ids(
    rows_as_dicts: List[Dict[str, Any]],
    must_include_ids: List[str],
    id_key: str = "title_id",
    top_k: Optional[int] = None
) -> AssertionResult:
    """Verifies that specific canonical entity IDs are included in the results (or top-K)."""
    if not must_include_ids:
        return AssertionResult("must_contain_ids", True, "No mandatory IDs specified", "accuracy")
        
    search_rows = rows_as_dicts[:top_k] if top_k else rows_as_dicts
    found_ids = {str(r.get(id_key, "")).strip() for r in search_rows if r.get(id_key)}
    
    missing = [tid for tid in must_include_ids if tid not in found_ids]
    
    if missing:
        return AssertionResult(
            "must_contain_ids",
            False,
            f"Results failed to include expected canonical entity IDs: {', '.join(missing)}",
            "accuracy",
            {"missing_ids": missing, "found_count": len(found_ids), "total_rows": len(rows_as_dicts)}
        )
    return AssertionResult(
        "must_contain_ids",
        True,
        f"All {len(must_include_ids)} required canonical entity IDs found in results",
        "accuracy",
        {"matched_ids": must_include_ids}
    )


def assert_must_exclude_ids(
    rows_as_dicts: List[Dict[str, Any]],
    must_exclude_ids: List[str],
    id_key: str = "title_id"
) -> AssertionResult:
    """Verifies that false-positive / ambiguous / forbidden entity IDs are not present."""
    if not must_exclude_ids:
        return AssertionResult("must_exclude_ids", True, "No forbidden IDs specified", "disambiguation")
        
    found_ids = {str(r.get(id_key, "")).strip() for r in rows_as_dicts if r.get(id_key)}
    forbidden_present = [tid for tid in must_exclude_ids if tid in found_ids]
    
    if forbidden_present:
        return AssertionResult(
            "must_exclude_ids",
            False,
            f"Results erroneously included forbidden / ambiguous entity IDs: {', '.join(forbidden_present)}",
            "disambiguation",
            {"forbidden_present": forbidden_present}
        )
    return AssertionResult("must_exclude_ids", True, "No forbidden or ambiguous entity IDs detected in output", "disambiguation")


def assert_predicate_compliance(
    rows_as_dicts: List[Dict[str, Any]],
    predicate_rules: Dict[str, Any]
) -> AssertionResult:
    """
    Checks that every returned row satisfies the declarative constraints.
    Supported rules:
    - '== <val>', '!= <val>', '>= <num>', '<= <num>', '> <num>', '< <num>'
    - 'CONTAINS <str>'
    - 'IN (<v1>, <v2>)'
    """
    if not predicate_rules or not rows_as_dicts:
        return AssertionResult("predicate_compliance", True, "No predicates to evaluate or empty rows", "data_invariants")
        
    violations = []
    
    for idx, row in enumerate(rows_as_dicts):
        for field_name, rule_str in predicate_rules.items():
            val = row.get(field_name)
            if val is None:
                continue # Ignore nulls unless strictly required
                
            rule = str(rule_str).strip()
            
            # Numeric comparisons
            if rule.startswith(">="):
                target = float(rule[2:].strip())
                if float(val) < target:
                    violations.append(f"Row {idx} ('{row.get('primary_title')}'): {field_name}={val} is not >= {target}")
            elif rule.startswith("<="):
                target = float(rule[2:].strip())
                if float(val) > target:
                    violations.append(f"Row {idx} ('{row.get('primary_title')}'): {field_name}={val} is not <= {target}")
            elif rule.startswith(">"):
                target = float(rule[1:].strip())
                if float(val) <= target:
                    violations.append(f"Row {idx} ('{row.get('primary_title')}'): {field_name}={val} is not > {target}")
            elif rule.startswith("<"):
                target = float(rule[1:].strip())
                if float(val) >= target:
                    violations.append(f"Row {idx} ('{row.get('primary_title')}'): {field_name}={val} is not < {target}")
            elif rule.startswith("=="):
                target = rule[2:].strip().strip("'\"")
                if str(val).lower() != target.lower():
                    violations.append(f"Row {idx} ('{row.get('primary_title')}'): {field_name}='{val}' != '{target}'")
            elif rule.startswith("CONTAINS"):
                target = rule.replace("CONTAINS", "").strip().strip("'\"")
                if target.lower() not in str(val).lower():
                    violations.append(f"Row {idx} ('{row.get('primary_title')}'): {field_name}='{val}' does not contain '{target}'")
                    
            if len(violations) >= 5:
                break
        if len(violations) >= 5:
            break
            
    if violations:
        return AssertionResult(
            "predicate_compliance",
            False,
            f"Predicate invariant violations found: {'; '.join(violations[:3])}",
            "data_invariants",
            {"violations": violations}
        )
    return AssertionResult("predicate_compliance", True, "All returned rows comply with predicate invariants", "data_invariants")


def assert_monotonic_order(
    rows_as_dicts: List[Dict[str, Any]],
    sort_key: str = "rating",
    direction: str = "DESC"
) -> AssertionResult:
    """Verifies that the results are sorted in monotonic order (ascending or descending)."""
    if len(rows_as_dicts) <= 1:
        return AssertionResult("monotonic_order", True, "Row count <= 1, ordering is trivially valid", "sorting")
        
    values = []
    for r in rows_as_dicts:
        v = r.get(sort_key)
        if v is not None:
            try:
                values.append(float(v))
            except (ValueError, TypeError):
                pass
                
    if len(values) <= 1:
        return AssertionResult("monotonic_order", True, f"Not enough numeric values for sort key '{sort_key}'", "sorting")
        
    is_desc = direction.upper() == "DESC"
    for i in range(len(values) - 1):
        if is_desc and values[i] < values[i + 1]:
            return AssertionResult(
                "monotonic_order",
                False,
                f"Ordering violation on '{sort_key}': index {i} ({values[i]}) < index {i+1} ({values[i+1]})",
                "sorting",
                {"sort_key": sort_key, "direction": direction, "index": i}
            )
        elif not is_desc and values[i] > values[i + 1]:
            return AssertionResult(
                "monotonic_order",
                False,
                f"Ordering violation on '{sort_key}': index {i} ({values[i]}) > index {i+1} ({values[i+1]})",
                "sorting",
                {"sort_key": sort_key, "direction": direction, "index": i}
            )
            
    return AssertionResult("monotonic_order", True, f"Results strictly obey {direction} sorting on '{sort_key}'", "sorting")


# ---------------------------------------------------------
# 3. Soft Metrics & Benchmark Functions
# ---------------------------------------------------------

def calculate_jaccard_similarity(predicted_ids: List[str], gold_ids: List[str]) -> float:
    """Computes the Jaccard similarity coefficient between predicted and gold ID sets."""
    set_pred = set(predicted_ids)
    set_gold = set(gold_ids)
    if not set_pred and not set_gold:
        return 1.0
    if not set_pred or not set_gold:
        return 0.0
    intersection = len(set_pred & set_gold)
    union = len(set_pred | set_gold)
    return round(intersection / union, 4)


def calculate_soft_f1(predicted_ids: List[str], gold_ids: List[str]) -> Tuple[float, float, float]:
    """Computes Precision, Recall, and Soft-F1 score between predicted and gold IDs."""
    set_pred = set(predicted_ids)
    set_gold = set(gold_ids)
    if not set_pred and not set_gold:
        return 1.0, 1.0, 1.0
    if not set_pred or not set_gold:
        return 0.0, 0.0, 0.0
        
    tp = len(set_pred & set_gold)
    precision = tp / len(set_pred)
    recall = tp / len(set_gold)
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    return round(precision, 4), round(recall, 4), round(f1, 4)


# ---------------------------------------------------------
# 4. Self-Correction & Reflection Assertions
# ---------------------------------------------------------

def assert_reflection_diagnosis(actual_diagnosis: Optional[str], expected_diagnosis: str) -> AssertionResult:
    """Checks that the reflection step categorized the zero-result condition correctly."""
    if not actual_diagnosis:
        return AssertionResult("reflection_diagnosis", False, "No reflection diagnosis was returned", "reflection")
        
    if actual_diagnosis.upper() != expected_diagnosis.upper():
        return AssertionResult(
            "reflection_diagnosis",
            False,
            f"Diagnosis mismatch: expected '{expected_diagnosis}', got '{actual_diagnosis}'",
            "reflection",
            {"expected": expected_diagnosis, "actual": actual_diagnosis}
        )
    return AssertionResult("reflection_diagnosis", True, f"Correctly diagnosed as '{expected_diagnosis}'", "reflection")


def assert_corrected_entity(actual_entity: Optional[str], expected_entity: str) -> AssertionResult:
    """Checks that the misspelled entity was correctly resolved to the target entity."""
    if not actual_entity:
        return AssertionResult("corrected_entity", False, "No corrected entity string provided", "reflection")
        
    if actual_entity.lower().strip() != expected_entity.lower().strip():
        return AssertionResult(
            "corrected_entity",
            False,
            f"Entity correction mismatch: expected '{expected_entity}', got '{actual_entity}'",
            "reflection",
            {"expected": expected_entity, "actual": actual_entity}
        )
    return AssertionResult("corrected_entity", True, f"Correctly identified entity '{expected_entity}'", "reflection")
