import json
import unittest
from unittest.mock import patch

from evoagent.llm import JsonChatClient


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


class JsonChatClientTests(unittest.TestCase):
    def test_retries_and_extracts_json_object_from_wrapped_model_content(self):
        malformed = _Response(
            b'{"choices":[{"message":{"content":""}}]}'
        )
        wrapped = _Response(
            b'{"choices":[{"message":{"content":"Here is the result:\\n{\\"action\\":\\"final\\"}\\n"}}]}'
        )
        client = JsonChatClient(
            "https://api.deepseek.com", "test-key", "deepseek-v4-pro",
            provider="deepseek",
        )

        with patch("urllib.request.urlopen", side_effect=[malformed, wrapped]) as urlopen:
            result = client.complete_json("lead", "Return JSON.", "{}")

        self.assertEqual({"action": "final"}, result)
        self.assertEqual(2, urlopen.call_count)

    def test_deepseek_disables_thinking_for_structured_agent_output(self):
        response = _Response(
            b'{"choices":[{"message":{"content":"{\\"action\\":\\"final\\"}"}}]}'
        )
        client = JsonChatClient(
            "https://api.deepseek.com", "test-key", "deepseek-v4-pro",
            provider="deepseek",
        )

        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            result = client.complete_json("lead", "Return JSON.", "{}")

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual({"action": "final"}, result)
        self.assertEqual({"type": "disabled"}, payload["thinking"])

    def test_non_deepseek_provider_does_not_receive_deepseek_thinking_option(self):
        response = _Response(
            b'{"choices":[{"message":{"content":"{\\"action\\":\\"final\\"}"}}]}'
        )
        client = JsonChatClient(
            "https://example.com/v1", "test-key", "custom-model",
            provider="custom",
        )

        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            client.complete_json("lead", "Return JSON.", "{}")

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertNotIn("thinking", payload)
