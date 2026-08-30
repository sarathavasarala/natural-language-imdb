import unittest
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import duckdb

from app.views import (
    _responses_api_completion,
    _should_use_responses_fallback,
    get_azure_client,
    get_azure_credentials,
    safe_chat_completion,
)


class ApiError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


class FoundryCallTests(unittest.TestCase):
    def test_foundry_resource_endpoint_uses_openai_v1_router(self):
        client, model = get_azure_client({
            "api_key": "key",
            "endpoint": "https://example.services.ai.azure.com/",
            "api_version": "2026-07-09",
            "model": "deployment",
        })

        self.assertEqual(str(client.base_url), "https://example.services.ai.azure.com/openai/v1/")
        self.assertEqual(model, "deployment")

    def test_json_credentials_include_api_version(self):
        request = Mock()
        request.headers.get.return_value = None
        request.is_json = True
        request.get_json.return_value = {
            "api_key": "key",
            "endpoint": "https://example.services.ai.azure.com",
            "api_version": "2026-07-09",
            "model": "deployment",
        }

        credentials = get_azure_credentials(request)

        self.assertEqual(credentials["api_version"], "2026-07-09")

    def test_responses_api_preserves_system_instructions(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text="SELECT 1;")
        messages = [
            {"role": "system", "content": "Return SQL only."},
            {"role": "user", "content": "Select one row."},
        ]

        response = _responses_api_completion(client, "deployment", messages)

        client.responses.create.assert_called_once_with(
            model="deployment",
            instructions="Return SQL only.",
            input=[{"role": "user", "content": "Select one row."}],
        )
        self.assertEqual(response.choices[0].message.content, "SELECT 1;")

    def test_chat_policy_error_falls_back_to_responses(self):
        client = Mock()
        client.chat.completions.create.side_effect = ApiError(
            "Chat Completions is not allowed by policy; use the Responses API",
            400,
        )
        client.responses.create.return_value = SimpleNamespace(output_text="SELECT 1;")

        response = safe_chat_completion(
            client,
            "deployment",
            [{"role": "user", "content": "Select one row."}],
        )

        self.assertEqual(response.choices[0].message.content, "SELECT 1;")

    def test_parameter_retry_can_still_fall_back_to_responses(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            ApiError("Unsupported parameter: temperature", 400),
            ApiError("Chat Completions is not supported; use the Responses API", 400),
        ]
        client.responses.create.return_value = SimpleNamespace(output_text="SELECT 1;")

        response = safe_chat_completion(
            client,
            "gpt-4o",
            [{"role": "user", "content": "Select one row."}],
            temperature=0.2,
        )

        self.assertEqual(response.choices[0].message.content, "SELECT 1;")
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_auth_error_does_not_send_a_second_request(self):
        error = ApiError("Incorrect API key", 401)
        client = Mock()
        client.chat.completions.create.side_effect = error

        with self.assertRaises(ApiError):
            safe_chat_completion(
                client,
                "deployment",
                [{"role": "user", "content": "Select one row."}],
            )

        client.responses.create.assert_not_called()
        self.assertFalse(_should_use_responses_fallback(error))

    def test_fix_single_quotes_does_not_corrupt_multiclause_like_queries(self):
        from app.views import fix_single_quotes_in_sql
        query = (
            "SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes "
            "FROM people p "
            "JOIN crew c ON p.person_id = c.person_id "
            "JOIN titles t ON c.title_id = t.title_id "
            "LEFT JOIN ratings r ON t.title_id = r.title_id "
            "WHERE p.name LIKE '%Christopher Nolan%' "
            "AND c.category = 'director' "
            "AND t.type = 'movie' "
            "ORDER BY t.premiered DESC;"
        )
        result = fix_single_quotes_in_sql(query)
        self.assertEqual(result, query)

    def test_fix_single_quotes_escapes_unescaped_apostrophes(self):
        from app.views import fix_single_quotes_in_sql
        query = "SELECT * FROM people WHERE name = 'Conan O'Brien' AND category = 'actor'"
        expected = "SELECT * FROM people WHERE name = 'Conan O''Brien' AND category = 'actor'"
        self.assertEqual(fix_single_quotes_in_sql(query), expected)

    def test_fix_single_quotes_preserves_already_escaped_quotes(self):
        from app.views import fix_single_quotes_in_sql
        query = "SELECT * FROM people WHERE name = 'Conan O''Brien' AND category = 'actor'"
        self.assertEqual(fix_single_quotes_in_sql(query), query)

    def test_validate_sql_query_blocks_dangerous_keywords(self):
        from app.views import validate_sql_query
        self.assertFalse(validate_sql_query("DROP TABLE titles;"))
        self.assertFalse(validate_sql_query("DELETE FROM people WHERE person_id = '123'"))
        self.assertFalse(validate_sql_query("UPDATE titles SET primary_title = 'hacked'"))
        self.assertFalse(validate_sql_query("TRUNCATE ratings;"))

    def test_local_duckdb_database_is_opened_read_only(self):
        import app.views as views

        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = os.path.join(temp_dir, "imdb.duckdb")
            connection = duckdb.connect(database_path)
            connection.execute("CREATE TABLE titles (title_id VARCHAR)")
            connection.execute("INSERT INTO titles VALUES ('tt0000001')")
            connection.close()

            old_connection = views._duckdb_con
            views._duckdb_con = None
            try:
                with patch.object(views, "DUCKDB_DATABASE_PATH", database_path), patch.object(
                    views, "AZURE_STORAGE_CONNECTION_STRING", ""
                ):
                    cursor = views.get_duckdb_database()
                    self.assertEqual(
                        cursor.execute("SELECT * FROM titles").fetchall(),
                        [("tt0000001",)],
                    )
                    with self.assertRaises(duckdb.InvalidInputException):
                        cursor.execute("CREATE TABLE should_fail (id INTEGER)")
            finally:
                if views._duckdb_con is not None:
                    views._duckdb_con.close()
                views._duckdb_con = old_connection

    def test_sync_copies_persistent_cache_to_runtime_storage(self):
        import app.views as views
        from scripts.sync_duckdb_database import sync_runtime_database

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "cache", "imdb.duckdb")
            runtime_path = os.path.join(temp_dir, "runtime", "imdb.duckdb")
            os.makedirs(os.path.dirname(cache_path))
            with open(cache_path, "wb") as cache_file:
                cache_file.write(b"database")
            with open(f"{cache_path}.etag", "w", encoding="utf-8") as etag_file:
                etag_file.write("etag-1")

            with patch.object(views, "DUCKDB_DATABASE_PATH", runtime_path), patch.object(
                views, "AZURE_STORAGE_CONNECTION_STRING", ""
            ), patch.dict(os.environ, {"DUCKDB_CACHE_PATH": cache_path}):
                self.assertEqual(sync_runtime_database(), runtime_path)

            with open(runtime_path, "rb") as runtime_file:
                self.assertEqual(runtime_file.read(), b"database")
            with open(f"{runtime_path}.etag", "r", encoding="utf-8") as etag_file:
                self.assertEqual(etag_file.read(), "etag-1")


if __name__ == "__main__":
    unittest.main()
