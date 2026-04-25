import os
import sys
import json
import time
from groq import Groq
from dotenv import load_dotenv
from langsmith import Client
from langsmith.evaluation import evaluate


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR)
sys.path.append(BASE_DIR)

load_dotenv()
os.environ["EVAL_MODE"] = "true"

from src.agent import ProductionRAG
from evaluation.eval_schemas import RetrievalEvalResult, GenerationEvalResult
from evaluation.eval_prompts import RETRIEVAL_EVAL_PROMPT, GENERATION_EVAL_PROMPT
import random

print("[System] Đang khởi tạo hệ thống RAG và LLM-Judge...")

rag_pipeline = ProductionRAG()
ls_client = Client()
judge_llm = Groq(api_key=os.getenv("GROQ_API_KEY"))
JUDGE_MODEL = "llama-3.3-70b-versatile"


def run_rag_pipeline(inputs: dict) -> dict:
    time.sleep(random.uniform(4.0, 6.0)) 
    query = inputs["question"]
    rag_pipeline.clear_memory()

    try:
        answer, context = rag_pipeline.process_with_context(query)
        return {"answer": answer, "context": context}
    except Exception as e:
        print(f"⚠️ RAG Pipeline lỗi: {e}")
        return {"answer": "Error", "context": ""}


def _call_judge(prompt: str, schema_class, retries=4) -> dict:
    base_delay = 5  # Giây bắt đầu đợi nếu gặp lỗi
    
    for attempt in range(retries):
        try:
            # Nghỉ nhẹ 1s trước mỗi nhát chém của Giám khảo
            time.sleep(1) 
            response = judge_llm.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            result = schema_class(**json.loads(response.choices[0].message.content))
            return result.model_dump()
            
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate limit" in error_str:
                # Thuật toán Exponential Backoff: Lần 1 đợi 5s, lần 2 đợi 10s, lần 3 đợi 20s...
                wait_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"⏳ Bị Rate Limit (429)! Đang làm mát hệ thống. Đợi {wait_time:.1f}s... (Thử lại {attempt+1}/{retries})")
                time.sleep(wait_time)
            else:
                print(f"⚠️ Giám khảo lỗi không xác định: {e} (Thử lại {attempt+1}/{retries})")
                time.sleep(2)

    print("❌ BỎ QUA test case này: LLM Judge hoàn toàn kiệt sức.")
    return {
        "context_recall": 0,
        "context_precision": 0.0,
        "strict_faithfulness": 0,
        "answer_relevance": 0.0,
        "reasoning": "Rate Limit Exceeded sau nhiều lần thử."
    }

def evaluate_retrieval(run, example) -> list:
    if not run.outputs or "context" not in run.outputs:
        return [{"key": "context_error", "score": 0, "comment": "Pipeline không trả về context"}]

    question = example.inputs["question"]
    ground_truth = example.outputs["ground_truth"]
    context = run.outputs["context"]

    prompt = RETRIEVAL_EVAL_PROMPT.format(
        question=question,
        ground_truth=ground_truth,
        context=context
    )

    scores = _call_judge(prompt, RetrievalEvalResult)

    return [
        {"key": "context_recall", "score": scores.get("context_recall", 0), "comment": scores.get("reasoning", "")},
        {"key": "context_precision", "score": scores.get("context_precision", 0), "comment": scores.get("reasoning", "")}
    ]


def evaluate_generation(run, example) -> list:
    if not run.outputs or "context" not in run.outputs:
        return [{"key": "generation_error", "score": 0, "comment": "Pipeline không trả về context"}]

    question = example.inputs["question"]
    context = run.outputs["context"]
    generated_answer = run.outputs["answer"]

    prompt = GENERATION_EVAL_PROMPT.format(
        question=question,
        context=context,
        generated_answer=generated_answer
    )

    scores = _call_judge(prompt, GenerationEvalResult)

    return [
        {"key": "strict_faithfulness", "score": scores.get("strict_faithfulness", 0), "comment": scores.get("reasoning", "")},
        {"key": "answer_relevance", "score": scores.get("answer_relevance", 0), "comment": scores.get("reasoning", "")}
    ]


if __name__ == "__main__":
    DATASET_NAME = "TechCorp_IT_Onboarding_GT"

    print(f"\n🚀 BẮT ĐẦU CHẠY EXPERIMENT TRÊN DATASET: {DATASET_NAME}")
    print("-" * 50)

    experiment_results = evaluate(
        run_rag_pipeline,
        data=DATASET_NAME,
        evaluators=[evaluate_retrieval, evaluate_generation],
        experiment_prefix="TechCorp-RAG-Eval",
        max_concurrency=1,
    )

    print("\n" + "=" * 50)
    print("✅ ĐÁNH GIÁ HOÀN TẤT!")