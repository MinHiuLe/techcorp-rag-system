from config.settings import settings
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
class Generator:
    def __init__(self, llm_client):
        self.llm = llm_client
    @traceable(run_type="llm", name="Groq_Llama3_Generator")
    def generate(self, original_query: str, context: str) -> str:
        prompt = f"""
Bạn là AI Engineer nội bộ của TechCorp. Dựa vào tài liệu dưới đây, hãy trả lời câu hỏi.
NẾU KHÔNG CÓ THÔNG TIN: Hãy nói "Hệ thống chưa có tài liệu về vấn đề này" và TUYỆT ĐỐI KHÔNG trích dẫn nguồn.
NGƯỢC LẠI: BẮT BUỘC trích dẫn [Nguồn: tên_file] ở cuối câu trả lời.

CONTEXT:
{context}

QUESTION:
{original_query}
"""
        response = self.llm.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )

        run = get_current_run_tree()
        if run and hasattr(response, 'usage') and response.usage:
            run.add_metadata({
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            })

        return response.choices[0].message.content