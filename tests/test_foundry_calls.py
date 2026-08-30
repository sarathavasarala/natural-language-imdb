import unittest
from types import SimpleNamespace
from unittest.mock import Mock

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


if __name__ == "__main__":
    unittest.main()
