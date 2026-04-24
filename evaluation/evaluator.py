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


print("[System] Đang khởi tạo hệ thống RAG và LLM-Judge...")

rag_pipeline = ProductionRAG()
ls_client = Client()
judge_llm = Groq(api_key=os.getenv("GROQ_API_KEY"))
JUDGE_MODEL = "llama-3.3-70b-versatile"


def run_rag_pipeline(inputs: dict) -> dict:
    time.sleep(2.5)
    query = inputs["question"]
    rag_pipeline.clear_memory()

    try:
        answer, context = rag_pipeline.process_with_context(query)
        return {"answer": answer, "context": context}
    except Exception as e:
        print(f"⚠️ RAG Pipeline lỗi: {e}")
        return {"answer": "Error", "context": ""}


def _call_judge(prompt: str, schema_class, retries=3) -> dict:
    for attempt in range(retries):
        try:
            time.sleep(2.5)
            response = judge_llm.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            result = schema_class(**json.loads(response.choices[0].message.content))
            return result.model_dump()
        except Exception as e:
            print(f"⚠️ Giám khảo bận (Thử lại {attempt+1}/{retries}). Lỗi: {e}")
            time.sleep(5)

    print("❌ Bỏ qua test case này do quá tải API.")
    return {
        "context_recall": 0,
        "context_precision": 0.0,
        "strict_faithfulness": 0,
        "answer_relevance": 0.0,
        "reasoning": "Rate Limit Exceeded"
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