# Pattern B-lite Rollout

## Session Goal

Finish the latency optimization cycle that started with sync-pipeline observability: add deeper cache/rewrite measurements, implement controlled Pattern B-lite behind a feature flag, and benchmark sync vs Pattern B-lite before considering any full async work.

## Completed Work

- Added deeper timing metadata:
  - `embedding_ms`
  - `generation_cache_check_ms`
  - existing `cache_lookup_ms` remains the total pre-retrieval cache lookup time.
- Added `debug.rewrite_source` with values:
  - `skip`
  - `cache_hit`
  - `llm`
  - `fallback`
- Updated benchmark output:
  - each run includes `rewrite_source`
  - summary includes `rewrite_sources` counts per scenario.
- Added `RAG_PATTERN_B_LITE`, default `false`.
- Implemented Pattern B-lite only for eligible queries:
  - `analysis.intent == "technical"`
  - single-topic only
  - `profile.skip_rewrite == false`
  - `RAG_PATTERN_B_LITE == true`
- Pattern B-lite uses `ThreadPoolExecutor(max_workers=2)` to run concurrently after analyzer:
  - embedding + semantic generation cache lookup
  - rewrite cache / LLM rewrite
- Preserved current behavior for:
  - general intent
  - multi-topic
  - skip-rewrite technical queries
  - retrieval, rerank, context building, generation, streaming, prompts, and public API shape.
- Added tests for:
  - flag off sync behavior
  - flag on eligible and non-eligible paths
  - cache hit
  - rewrite cache hit
  - LLM rewrite
  - rewrite fallback
  - generation cache error fallback
  - benchmark `rewrite_source`, `rewrite_sources`, and delay validation.

## Files Changed

- `src/pipelines/orchestration.py`
- `evaluation/latency_benchmark.py`
- `evaluation/latency_benchmark_results.json`
- `evaluation/latency_benchmark_results_sync.json`
- `evaluation/latency_benchmark_results_pattern_b_lite.json`
- `tests/test_latency_benchmark.py`
- `tests/test_orchestration_timing.py`

## Verification

Targeted unit tests pass:

```bash
python -m unittest tests.test_orchestration_timing tests.test_latency_benchmark
```

Result:

```text
Ran 24 tests
OK
```

A/B benchmark commands:

```bash
docker compose -f docker-compose.dev.yml exec -e RAG_PATTERN_B_LITE=false api python evaluation/latency_benchmark.py --runs 5 --delay-seconds 15 --output evaluation/latency_benchmark_results_sync.json
docker compose -f docker-compose.dev.yml exec -e RAG_PATTERN_B_LITE=true api python evaluation/latency_benchmark.py --runs 5 --delay-seconds 15 --output evaluation/latency_benchmark_results_pattern_b_lite.json
```

Both runs completed successfully:

```text
Sync/off: 25/25 ok
Pattern B-lite/on: 25/25 ok
No route/intent mismatches
```

Key result for `cache_miss_with_rewrite`:

| Metric | Sync/off | Pattern B-lite/on |
|---|---:|---:|
| wall p50 | 4443.05 ms | 3488.62 ms |
| wall p95 | 6084.60 ms | 3878.16 ms |
| total p50 | 4437.85 ms | 3485.83 ms |
| cache_lookup p50 | 331.44 ms | 319.33 ms |
| rewrite p50 | 671.19 ms | 610.59 ms |
| rewrite_sources | `{"llm": 5}` | `{"llm": 5}` |

## Important Decisions

- Keep Pattern B-lite because the rewrite path showed a clear latency win:
  - about 954 ms lower wall p50
  - about 2206 ms lower wall p95
- Keep `RAG_PATTERN_B_LITE=false` as the default until explicitly enabled in runtime or benchmark commands.
- Do not proceed to full async now. The current gain is meaningful on the rewrite path, but not enough to justify asyncing the full pipeline.
- Continue treating `process_with_context()` as the source of truth for sync chat, streaming adapter behavior, cache writes, memory writes, PII handling, and LangSmith token tracking.

## Problems Found

- Benchmark runs still showed provider/infrastructure warnings:
  - Groq key rate-limit cooldowns.
  - Hugging Face unauthenticated warning.
  - Qdrant semantic cache collection init/query warnings in some runs.
- These warnings did not break benchmark success, but Qdrant semantic cache health should be checked separately if cache latency becomes noisy.

## Next Steps

- Decide deployment default:
  - keep `RAG_PATTERN_B_LITE=false` for conservative production rollout, or enable it in dev/staging first.
- If enabling in staging, monitor:
  - `cache_miss_with_rewrite` p50/p95
  - `rewrite_source`
  - `[RAG_TIMING]` logs
  - Groq/Cohere rate-limit warnings
  - semantic cache Qdrant health.
- Do not change prompts, retrieval, rerank, or generation in the same measurement cycle.
- Investigate Qdrant `semantic_cache` creation/availability separately if future benchmark output shows frequent cache lookup warnings.

## Similar Issue Checklist

- If Pattern B-lite appears to do nothing, confirm `RAG_PATTERN_B_LITE=true` is actually set inside the `api` container.
- If rewrite-path latency does not improve, confirm `rewrite_sources` is mostly `llm`; cached rewrite does not benefit from the same overlap.
- If non-eligible paths regress, confirm Pattern B-lite eligibility is still limited to technical, single-topic, non-skip-rewrite queries.
- If `general` shows nonzero cache timings, confirm the analyzer-first general return path is still intact.
- If benchmark comparison is noisy, rerun both A/B sides with the same query set, `--runs 5`, and `--delay-seconds 15` or higher.
