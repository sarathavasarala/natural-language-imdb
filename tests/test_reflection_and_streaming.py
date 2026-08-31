import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from app import create_app
from app.views import (
    extract_filter_literals,
    reflect_on_zero_results
)


class TestReflectionAndStreaming(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_extract_filter_literals(self):
        sql = """
        WITH matched_people AS (
            SELECT person_id FROM people WHERE name = 'gorge clooney'
        )
        SELECT t.primary_title FROM titles t 
        JOIN crew c ON t.title_id = c.title_id 
        WHERE t.type = 'movie' AND t.genres LIKE '%Drama%' AND t.premiered >= 2010
        """
        literals = extract_filter_literals(sql, "gorge clooney movies")
        self.assertIn("gorge clooney", literals)
        self.assertNotIn("2010", literals)
        self.assertNotIn("movie", literals)
        self.assertNotIn("Drama", literals)

    def test_reflect_on_zero_results_parses_json(self):
        probe_data = {
            "gorge clooney": {
                "person_exact": False,
                "title_exact": False,
                "person_fuzzy": [{"name": "George Clooney", "similarity": 0.94}],
                "title_fuzzy": []
            }
        }
        
        mock_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='```json\n{"diagnosis": "MISSPELLED_ENTITY", "explanation": "Showing results for George Clooney", "corrected_entity": "George Clooney", "corrected_sql": "SELECT 1"}\n```'
                    )
                )
            ]
        )

        with patch("app.views.get_azure_client", return_value=(MagicMock(), "gpt-4o")):
            with patch("app.views.safe_chat_completion", return_value=mock_response):
                res = reflect_on_zero_results("gorge clooney", "SELECT 1", probe_data)
                self.assertEqual(res["diagnosis"], "MISSPELLED_ENTITY")
                self.assertEqual(res["corrected_entity"], "George Clooney")
                self.assertEqual(res["corrected_sql"], "SELECT 1")

    def test_search_stream_empty_query_returns_error(self):
        response = self.client.post(
            "/api/search/stream",
            json={"query": ""},
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data_lines = response.get_data(as_text=True)
        self.assertIn('"type": "error"', data_lines)

    def test_mobile_synopsis_button_handler_present_in_js(self):
        with open("app/static/app.js", "r", encoding="utf-8") as f:
            js_content = f.read()
        self.assertIn(".btn-card-synopsis", js_content)
        self.assertIn("'.btn-ai-synopsis, .btn-card-synopsis'", js_content)


if __name__ == "__main__":
    unittest.main()
