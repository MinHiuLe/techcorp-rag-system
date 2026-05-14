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


class TestOrchestrationTiming(unittest.TestCase):
    def _rag(self, analysis, cached_answer=None, rewritten=None, rewrite_return=None):
        rag = ProductionRAG.__new__(ProductionRAG)
        rag.memory = _Memory()
        rag.cache = _Cache(cached_answer=cached_answer, rewritten=rewritten)
        rag.dense_model = _DenseModel()
        rag.analyzer = MagicMock()
        rag.analyzer.analyze.return_value = analysis
        rag.rewriter = MagicMock()
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
        rag.retriever.search.assert_not_called()
        rag.generator.generate.assert_not_called()

    def test_cache_miss_without_rewrite_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.2, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis)

        metadata = self._metadata(rag)

        self.assertFalse(metadata["debug"]["cache_hit"])
        self.assertFalse(metadata["debug"]["rewrite_attempted"])
        self.assertFalse(metadata["debug"]["rewrite_used"])
        self.assertEqual(metadata["debug"]["route"], "technical_single_topic")
        self.assertEqual(metadata["debug"]["top_k"], 2)

    def test_cache_miss_with_rewrite_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis, rewritten="rewritten vpn setup")

        metadata = self._metadata(rag)

        self.assertTrue(metadata["debug"]["rewrite_attempted"])
        self.assertTrue(metadata["debug"]["rewrite_used"])
        self.assertEqual(metadata["debug"]["route"], "technical_single_topic")
        self.assertGreaterEqual(metadata["timings_ms"]["rewrite_ms"], 0.0)
        rag.retriever.search.assert_called_once()

    def test_rewrite_attempted_without_rewrite_used_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        query = "How to setup VPN?"
        rag = self._rag(analysis, rewrite_return=query)

        metadata = self._metadata(rag, query=query)

        self.assertTrue(metadata["debug"]["rewrite_attempted"])
        self.assertFalse(metadata["debug"]["rewrite_used"])

    def test_multi_topic_metadata(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.85, ambiguity_score=0.1, entities=[])
        rag = self._rag(analysis)
        rag._decompose_query = MagicMock(return_value=["VPN?", "Docker?"])

        metadata = self._metadata(rag, query="How to setup VPN? How to setup Docker?")

        self.assertTrue(metadata["debug"]["is_multi_topic"])
        self.assertEqual(metadata["debug"]["route"], "technical_multi_topic")
        self.assertGreaterEqual(metadata["timings_ms"]["retrieval_ms"], 0.0)

    def test_general_intent_metadata(self):
        analysis = QueryAnalysis(intent="general", complexity_score=0.1, ambiguity_score=0.0, entities=[])
        rag = self._rag(analysis)

        metadata = self._metadata(rag, query="Xin chao")

        self.assertEqual(metadata["debug"]["intent"], "general")
        self.assertEqual(metadata["debug"]["route"], "general")
        self.assertEqual(metadata["timings_ms"]["cache_lookup_ms"], 0.0)
        self.assertEqual(metadata["timings_ms"]["retrieval_ms"], 0.0)
        self.assertEqual(rag.cache.embedding_calls, 0)


if __name__ == "__main__":
    unittest.main()
