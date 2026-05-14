import json
import tempfile
import unittest
from pathlib import Path

from evaluation import latency_benchmark


class _FakeRAG:
    def __init__(self):
        self.calls = []
        self.clear_count = 0

    def clear_cache(self):
        self.clear_count += 1

    def process_with_context(self, query, session_id="default"):
        self.calls.append((query, session_id))
        is_warmup = session_id.endswith("_warmup")
        return {
            "answer": f"Answer for {query}",
            "context": "" if query == "hello" else "context",
            "metadata": {
                "tokens": {"total_tokens": 3},
                "timings_ms": {
                    "analyzer_ms": 1.0,
                    "cache_lookup_ms": 2.0,
                    "rewrite_ms": 0.0,
                    "retrieval_ms": 3.0,
                    "rerank_ms": 4.0,
                    "generation_ms": 5.0,
                    "total_ms": 15.0,
                },
                "debug": {
                    "route": "cache_hit" if is_warmup or query == "vpn" else "general",
                    "intent": "technical" if query == "vpn" else "general",
                    "cache_hit": query == "vpn" and not is_warmup,
                    "rewrite_attempted": False,
                    "rewrite_used": False,
                    "is_multi_topic": False,
                    "top_k": 2,
                    "model_name": "test-model",
                },
            },
        }


class TestLatencyBenchmark(unittest.TestCase):
    def test_load_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queries.json"
            path.write_text(json.dumps([{"id": "general", "query": "hello"}]), encoding="utf-8")

            queries = latency_benchmark.load_queries(path)

        self.assertEqual(queries[0]["id"], "general")
        self.assertEqual(queries[0]["query"], "hello")

    def test_cache_hit_warmup_and_result_shape(self):
        fake = _FakeRAG()
        queries = [
            {
                "id": "cache_hit",
                "label": "Cache hit",
                "query": "vpn",
                "expected_route": "cache_hit",
                "expected_intent": "technical",
            }
        ]

        results = latency_benchmark.run_benchmark(queries, rag_factory=lambda: fake)

        self.assertEqual(len(fake.calls), 2)
        self.assertTrue(fake.calls[0][1].endswith("_warmup"))
        self.assertEqual(fake.clear_count, 1)
        result = results[0]
        self.assertEqual(result["id"], "cache_hit")
        self.assertEqual(result["label"], "Cache hit")
        self.assertEqual(result["expected_route"], "cache_hit")
        self.assertEqual(result["actual_route"], "cache_hit")
        self.assertTrue(result["cache_hit"])
        self.assertIn("timings_ms", result)
        self.assertIn("wall_ms", result)
        self.assertEqual(result["status"], "ok")

    def test_write_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.json"
            latency_benchmark.write_results([{"id": "one"}], path)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload, [{"id": "one"}])

    def test_preserves_expected_fields_for_non_cache_query(self):
        fake = _FakeRAG()
        queries = [
            {
                "id": "general_intent",
                "label": "General intent",
                "query": "hello",
                "expected_route": "general",
                "expected_intent": "general",
            }
        ]

        results = latency_benchmark.run_benchmark(queries, rag_factory=lambda: fake)

        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(results[0]["expected_intent"], "general")
        self.assertEqual(results[0]["actual_intent"], "general")
        self.assertFalse(results[0]["context_present"])
        self.assertIn("Answer for hello", results[0]["answer_preview"])

    def test_repeated_runs_return_summary(self):
        fake = _FakeRAG()
        queries = [
            {
                "id": "cache_hit",
                "label": "Cache hit",
                "query": "vpn",
                "expected_route": "cache_hit",
                "expected_intent": "technical",
            }
        ]

        results = latency_benchmark.run_benchmark_repeated(
            queries,
            runs=2,
            rag_factory=lambda: fake,
        )

        self.assertIn("runs", results)
        self.assertIn("summary", results)
        self.assertEqual(len(results["runs"]), 2)
        self.assertEqual(len(fake.calls), 4)
        self.assertTrue(fake.calls[0][1].endswith("_warmup"))
        self.assertTrue(fake.calls[2][1].endswith("_warmup"))
        summary = results["summary"][0]
        self.assertEqual(summary["id"], "cache_hit")
        self.assertEqual(summary["runs"], 2)
        self.assertIn("avg", summary["wall_ms"])
        self.assertIn("p95", summary["timings_ms"]["total_ms"])

    def test_single_run_wrapper_preserves_list_shape(self):
        fake = _FakeRAG()
        queries = [{"id": "general_intent", "label": "General", "query": "hello"}]

        results = latency_benchmark.run_benchmark_repeated(
            queries,
            runs=1,
            rag_factory=lambda: fake,
        )

        self.assertIsInstance(results, list)
        self.assertEqual(results[0]["id"], "general_intent")

    def test_delay_between_single_run_scenarios(self):
        fake = _FakeRAG()
        sleeps = []
        queries = [
            {"id": "one", "label": "One", "query": "hello"},
            {"id": "two", "label": "Two", "query": "hello"},
        ]

        latency_benchmark.run_benchmark(
            queries,
            rag_factory=lambda: fake,
            delay_seconds=1.5,
            sleeper=sleeps.append,
        )

        self.assertEqual(sleeps, [1.5])

    def test_delay_between_repeated_run_blocks(self):
        fake = _FakeRAG()
        sleeps = []
        queries = [
            {
                "id": "cache_hit",
                "label": "Cache hit",
                "query": "vpn",
                "expected_route": "cache_hit",
                "expected_intent": "technical",
            }
        ]

        latency_benchmark.run_benchmark_repeated(
            queries,
            runs=3,
            rag_factory=lambda: fake,
            delay_seconds=2.0,
            sleeper=sleeps.append,
        )

        self.assertEqual(sleeps, [2.0, 2.0])


if __name__ == "__main__":
    unittest.main()
