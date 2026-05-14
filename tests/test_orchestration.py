import unittest
from unittest.mock import MagicMock

from tests.dependency_stubs import install_runtime_stubs

install_runtime_stubs()

from src.pipelines.orchestration import ProductionRAG
from src.schemas import QueryAnalysis

class TestOrchestration(unittest.TestCase):
    def setUp(self):
        self.rag = ProductionRAG.__new__(ProductionRAG)
        self.rag.memory = MagicMock()

    def test_clear_memory(self):
        self.rag.clear_memory("session_1")
        self.rag.memory.clear.assert_called_once_with("session_1")

    def test_is_multi_topic(self):
        a_low = QueryAnalysis(intent="technical", complexity_score=0.2, ambiguity_score=0.1, entities=[])
        a_high = QueryAnalysis(intent="technical", complexity_score=0.9, ambiguity_score=0.1, entities=[])
        
        self.assertFalse(self.rag._is_multi_topic("Hỏi 1 câu", a_low))
        self.assertTrue(self.rag._is_multi_topic("Hỏi 2 câu? Câu 2?", a_low))
        self.assertTrue(self.rag._is_multi_topic("Câu phức tạp", a_high))

    def test_merge_docs(self):
        docs_per_query = [
            [{"text": "doc1", "source": "s1"}, {"text": "doc2", "source": "s2"}],
            [{"text": "doc2", "source": "s2"}, {"text": "doc3", "source": "s3"}]
        ]
        merged = self.rag._merge_docs(docs_per_query)
        self.assertEqual(len(merged), 3)
        # doc2 appears twice, so it should be first
        self.assertEqual(merged[0]["text"], "doc2")

if __name__ == '__main__':
    unittest.main()
