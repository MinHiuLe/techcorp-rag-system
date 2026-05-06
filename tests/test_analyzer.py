import unittest
from unittest.mock import MagicMock
from src.core.analyzer import QueryAnalyzer

class TestQueryAnalyzer(unittest.TestCase):
    def setUp(self):
        self.mock_llm = MagicMock()
        self.analyzer = QueryAnalyzer(self.mock_llm)

    def test_technical_intent(self):
        # Mock response for technical query
        self.mock_llm.chat.completions.create.return_value.choices[0].message.content = '{"intent": "technical", "complexity_score": 0.5, "ambiguity_score": 0.1, "entities": ["Docker"]}'
        
        analysis = self.analyzer.analyze("Cách cài đặt Docker?", "")
        self.assertEqual(analysis.intent, "technical")
        self.assertGreaterEqual(analysis.complexity_score, 0.4)

    def test_general_intent(self):
        # Mock response for general query
        self.mock_llm.chat.completions.create.return_value.choices[0].message.content = '{"intent": "general", "complexity_score": 0.1, "ambiguity_score": 0.0, "entities": []}'
        
        analysis = self.analyzer.analyze("Chào bạn", "")
        self.assertEqual(analysis.intent, "general")

    def test_technical_keyword_override(self):
        # Mock response for general but query contains technical keyword
        self.mock_llm.chat.completions.create.return_value.choices[0].message.content = '{"intent": "general", "complexity_score": 0.1, "ambiguity_score": 0.0, "entities": []}'
        
        # "Docker" is a technical keyword
        analysis = self.analyzer.analyze("Chào bạn, mình muốn hỏi về Docker", "")
        self.assertEqual(analysis.intent, "technical")

    def test_simple_fact_clamp(self):
        # High complexity from LLM for a simple fact
        self.mock_llm.chat.completions.create.return_value.choices[0].message.content = '{"intent": "technical", "complexity_score": 0.8, "ambiguity_score": 0.1, "entities": ["VPN"]}'
        
        analysis = self.analyzer.analyze("Địa chỉ server VPN là gì?", "")
        # Should be clamped to 0.15 by _is_simple_fact
        self.assertEqual(analysis.complexity_score, 0.15)

    def test_procedure_raise(self):
        # Low complexity from LLM for a procedure
        self.mock_llm.chat.completions.create.return_value.choices[0].message.content = '{"intent": "technical", "complexity_score": 0.2, "ambiguity_score": 0.1, "entities": ["Jira"]}'
        
        analysis = self.analyzer.analyze("Các bước cấp quyền Jira?", "")
        # Should be raised to 0.35
        self.assertEqual(analysis.complexity_score, 0.35)

if __name__ == '__main__':
    unittest.main()
