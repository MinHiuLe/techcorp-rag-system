import unittest
from unittest.mock import MagicMock, patch

from tests.dependency_stubs import install_runtime_stubs

install_runtime_stubs()

from src.pipelines import orchestration
from src.pipelines.orchestration import ProductionRAG
from src.schemas import QueryAnalysis


class _Vec:
    def __init__(self, values=None):
        self.values = values or [0.1, 0.2, 0.3]

    def tolist(self):
        return self.values


class _DenseModel:
    def encode(self, value):
        if isinstance(value, list):
            return [_Vec([idx + 0.1, idx + 0.2]) for idx, _ in enumerate(value)]
        return _Vec()


class _Memory:
    def get_history(self, session_id):
        return []

    def add_message(self, session_id, query, answer):
        return None


class _Cache:
    def __init__(self, cached_answer=None, rewritten=None):
        self.cached_answer = cached_answer
        self.rewritten = rewritten
        self.embedding_calls = 0

    def get_embedding(self, query):
        self.embedding_calls += 1
        return None

    def store_embedding(self, query, embedding):
        return None

    def check_generation(self, query_embedding, min_tier):
        return self.cached_answer

    def get_rewrite(self, query):
        return self.rewritten

    def store_rewrite(self, query, rewritten):
        return None

    def store_generation(self, **kwargs):
        return None


class _CacheWithGenerationError(_Cache):
    def check_generation(self, query_embedding, min_tier):
        raise RuntimeError("generation cache failed")


class TestOrchestrationTiming(unittest.TestCase):
    def _rag(self, analysis, cached_answer=None, rewritten=None, rewrite_return=None, rewrite_error=None, cache=None):
        rag = ProductionRAG.__new__(ProductionRAG)
        rag.memory = _Memory()
        rag.cache = cache or _Cache(cached_answer=cached_answer, rewritten=rewritten)
        rag.dense_model = _DenseModel()
        rag.analyzer = MagicMock()
        rag.analyzer.analyze.return_value = analysis
        rag.rewriter = MagicMock()
        if rewrite_error is not None:
            rag.rewriter.rewrite.side_effect = rewrite_error
        else:
            rag.rewriter.rewrite.return_value = rewrite_return if rewrite_return is not None else rewritten or "rewritten query"
        rag.retriever = MagicMock()
        rag.retriever.search.return_value = [{"text": "context text", "source": "source.md"}]
        rag.retriever.search_with_vec.return_value = [{"text": "context text", "source": "source.md"}]
        rag.policy = MagicMock()
        rag.policy.apply_policy.return_value = [{"text": "context text", "source": "source.md"}]
        rag.generator = MagicMock()
        rag.generator.generate.return_value = ("answer", {"total_tokens": 3})
        return rag

    def _metadata(self, rag, query="How to setup VPN?"):
        with patch.object(orchestration.ContextBuilder, "build", return_value="[Nguon: source.md]\ncontext text"):
            return rag.process_with_context(query, session_id="test")["metadata"]

    def test_cache_hit_path_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.2, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis, cached_answer="cached answer")

        metadata = self._metadata(rag)

        self.assertTrue(metadata["debug"]["cache_hit"])
        self.assertEqual(metadata["debug"]["route"], "cache_hit")
        self.assertIn("cache_lookup_ms", metadata["timings_ms"])
        self.assertIn("embedding_ms", metadata["timings_ms"])
        self.assertIn("generation_cache_check_ms", metadata["timings_ms"])
        self.assertGreaterEqual(metadata["timings_ms"]["embedding_ms"], 0.0)
        self.assertGreaterEqual(metadata["timings_ms"]["generation_cache_check_ms"], 0.0)
        rag.retriever.search.assert_not_called()
        rag.generator.generate.assert_not_called()

    def test_cache_miss_without_rewrite_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.2, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis)

        with patch.object(orchestration, "RAG_PATTERN_B_LITE", True):
            metadata = self._metadata(rag)

        self.assertFalse(metadata["debug"]["cache_hit"])
        self.assertFalse(metadata["debug"]["rewrite_attempted"])
        self.assertFalse(metadata["debug"]["rewrite_used"])
        self.assertEqual(metadata["debug"]["rewrite_source"], "skip")
        self.assertEqual(metadata["debug"]["route"], "technical_single_topic")
        self.assertEqual(metadata["debug"]["top_k"], 2)

    def test_cache_miss_with_rewrite_cache_hit_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis, rewritten="rewritten vpn setup")

        metadata = self._metadata(rag)

        self.assertTrue(metadata["debug"]["rewrite_attempted"])
        self.assertTrue(metadata["debug"]["rewrite_used"])
        self.assertEqual(metadata["debug"]["rewrite_source"], "cache_hit")
        self.assertEqual(metadata["debug"]["route"], "technical_single_topic")
        self.assertGreaterEqual(metadata["timings_ms"]["rewrite_ms"], 0.0)
        rag.retriever.search.assert_called_once()

    def test_cache_miss_with_llm_rewrite_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis, rewrite_return="rewritten vpn setup")

        metadata = self._metadata(rag)

        self.assertTrue(metadata["debug"]["rewrite_attempted"])
        self.assertTrue(metadata["debug"]["rewrite_used"])
        self.assertEqual(metadata["debug"]["rewrite_source"], "llm")
        rag.rewriter.rewrite.assert_called_once()

    def test_rewrite_attempted_without_rewrite_used_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        query = "How to setup VPN?"
        rag = self._rag(analysis, rewrite_return=query)

        metadata = self._metadata(rag, query=query)

        self.assertTrue(metadata["debug"]["rewrite_attempted"])
        self.assertFalse(metadata["debug"]["rewrite_used"])
        self.assertEqual(metadata["debug"]["rewrite_source"], "llm")

    def test_rewrite_fallback_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        query = "How to setup VPN?"
        rag = self._rag(analysis, rewrite_error=RuntimeError("rewrite failed"))

        metadata = self._metadata(rag, query=query)

        self.assertTrue(metadata["debug"]["rewrite_attempted"])
        self.assertFalse(metadata["debug"]["rewrite_used"])
        self.assertEqual(metadata["debug"]["rewrite_source"], "fallback")
        rag.retriever.search.assert_called_once()
        self.assertEqual(rag.retriever.search.call_args.args[0], query)

    def test_pattern_b_lite_disabled_uses_sync_path(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis, rewrite_return="rewritten vpn setup")

        with patch.object(orchestration, "RAG_PATTERN_B_LITE", False), \
                patch.object(orchestration, "ThreadPoolExecutor") as executor:
            metadata = self._metadata(rag)

        executor.assert_not_called()
        self.assertEqual(metadata["debug"]["rewrite_source"], "llm")

    def test_pattern_b_lite_cache_hit_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis, cached_answer="cached answer", rewrite_return="rewritten vpn setup")

        with patch.object(orchestration, "RAG_PATTERN_B_LITE", True):
            metadata = self._metadata(rag)

        self.assertTrue(metadata["debug"]["cache_hit"])
        self.assertEqual(metadata["debug"]["route"], "cache_hit")
        rag.retriever.search.assert_not_called()
        rag.generator.generate.assert_not_called()

    def test_pattern_b_lite_rewrite_cache_hit_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis, rewritten="rewritten vpn setup")

        with patch.object(orchestration, "RAG_PATTERN_B_LITE", True):
            metadata = self._metadata(rag)

        self.assertEqual(metadata["debug"]["rewrite_source"], "cache_hit")
        self.assertEqual(rag.retriever.search.call_args.args[0], "rewritten vpn setup")

    def test_pattern_b_lite_llm_rewrite_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis, rewrite_return="rewritten vpn setup")

        with patch.object(orchestration, "RAG_PATTERN_B_LITE", True):
            metadata = self._metadata(rag)

        self.assertEqual(metadata["debug"]["rewrite_source"], "llm")
        self.assertEqual(rag.retriever.search.call_args.args[0], "rewritten vpn setup")

    def test_pattern_b_lite_rewrite_error_fallback_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        query = "How to setup VPN?"
        rag = self._rag(analysis, rewrite_error=RuntimeError("rewrite failed"))

        with patch.object(orchestration, "RAG_PATTERN_B_LITE", True):
            metadata = self._metadata(rag, query=query)

        self.assertEqual(metadata["debug"]["rewrite_source"], "fallback")
        self.assertEqual(rag.retriever.search.call_args.args[0], query)

    def test_pattern_b_lite_cache_error_still_retrieves(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        cache = _CacheWithGenerationError()
        rag = self._rag(analysis, rewrite_return="rewritten vpn setup", cache=cache)

        with patch.object(orchestration, "RAG_PATTERN_B_LITE", True):
            metadata = self._metadata(rag)

        self.assertFalse(metadata["debug"]["cache_hit"])
        self.assertEqual(metadata["debug"]["rewrite_source"], "llm")
        self.assertGreaterEqual(metadata["timings_ms"]["generation_cache_check_ms"], 0.0)
        rag.retriever.search.assert_called_once()

    def test_multi_topic_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.85, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis)
        rag._decompose_query = MagicMock(return_value=["VPN?", "Docker?"])

        with patch.object(orchestration, "RAG_PATTERN_B_LITE", True):
            metadata = self._metadata(rag, query="How to setup VPN? How to setup Docker?")

        self.assertTrue(metadata["debug"]["is_multi_topic"])
        self.assertEqual(metadata["debug"]["rewrite_source"], "skip")
        self.assertEqual(metadata["debug"]["route"], "technical_multi_topic")
        self.assertGreaterEqual(metadata["timings_ms"]["retrieval_ms"], 0.0)

    def test_general_intent_metadata(self):
        analysis = QueryAnalysis(intent="general", complexity_score=0.1, ambiguity_score=0.0, entities=[])
        rag = self._rag(analysis)

        with patch.object(orchestration, "RAG_PATTERN_B_LITE", True):
            metadata = self._metadata(rag, query="Xin chao")

        self.assertEqual(metadata["debug"]["intent"], "general")
        self.assertEqual(metadata["debug"]["route"], "general")
        self.assertEqual(metadata["debug"]["rewrite_source"], "skip")
        self.assertEqual(metadata["timings_ms"]["cache_lookup_ms"], 0.0)
        self.assertEqual(metadata["timings_ms"]["embedding_ms"], 0.0)
        self.assertEqual(metadata["timings_ms"]["generation_cache_check_ms"], 0.0)
        self.assertEqual(metadata["timings_ms"]["rewrite_ms"], 0.0)
        self.assertEqual(metadata["timings_ms"]["retrieval_ms"], 0.0)
        self.assertEqual(rag.cache.embedding_calls, 0)


if __name__ == "__main__":
    unittest.main()
