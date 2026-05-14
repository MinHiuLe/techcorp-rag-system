import json
import unittest

from fastapi.testclient import TestClient

from tests.dependency_stubs import install_runtime_stubs

install_runtime_stubs()

from src.api import app as app_module


class _FakeRAG:
    def process_with_context(self, raw_query, session_id="default"):
        return {
            "answer": "Test answer",
            "context": "[Nguon: source.md]\nTest context",
            "metadata": {
                "latency": 0.01,
                "timings_ms": {"total_ms": 10.0},
                "debug": {"route": "technical_single_topic"},
            },
        }

    def process_with_context_stream(self, raw_query, session_id="default"):
        yield "Test ", "[Nguon: source.md]\nTest context"
        yield "answer", "[Nguon: source.md]\nTest context"


class TestApiSmoke(unittest.TestCase):
    def setUp(self):
        self.previous_engine = app_module.rag_engine
        self.previous_api_keys = app_module.settings.API_KEYS
        app_module.rag_engine = _FakeRAG()
        app_module.settings.API_KEYS = ""
        self.client = TestClient(app_module.app)

    def tearDown(self):
        app_module.rag_engine = self.previous_engine
        app_module.settings.API_KEYS = self.previous_api_keys

    def test_chat_response_shape(self):
        response = self.client.post(
            "/chat",
            json={"query": "How to setup VPN?", "session_id": "smoke"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload.keys()),
            {"answer", "source", "context", "latency_seconds", "status"},
        )
        self.assertEqual(payload["status"], "success")
        self.assertIn("source", payload)
        self.assertIsInstance(payload["latency_seconds"], float)

    def test_chat_stream_shape(self):
        with self.client.stream(
            "POST",
            "/chat/stream",
            json={"query": "How to setup VPN?", "session_id": "smoke"},
        ) as response:
            self.assertEqual(response.status_code, 200)
            lines = [json.loads(line) for line in response.iter_lines() if line]

        self.assertGreaterEqual(len(lines), 2)
        self.assertEqual(lines[0]["type"], "metadata")
        self.assertIn("source", lines[0])
        self.assertIn("context", lines[0])
        self.assertTrue(all(line["type"] == "content" for line in lines[1:]))
        self.assertEqual("".join(line["content"] for line in lines[1:]), "Test answer")


if __name__ == "__main__":
    unittest.main()
