# Retrieval and Formatting Fix Report

## Root Cause Analysis
The issue of collapsing structured table content into summarized bullet lists originated from two main areas:
1. **Extraction/Parsing:** The `python-docx` parser duplicated text artifacts for merged cells in tables, creating dense, repetitive text blocks that confused the LLM during generation.
2. **LLM Generation:** The prompt instructions lacked strict boundaries for multi-source contexts. The LLM naturally attempted to synthesize and summarize tabular data to minimize token usage, resulting in flattened lists and merged rows. This caused loss of critical metadata columns (e.g., responsible unit, timeline).

## Impacted Files
- `src/pipelines/parser.py`: Corrected duplicated cell extraction.
- `src/schemas.py`: Updated payload schema.
- `src/pipelines/ingestion.py`: Added table structure detection.
- `src/core/generator.py`: Added multi-source isolation and strict formatting validation rules.

## Schema Changes
- Added `is_table: bool` (default: `False`) to `ChunkPayload` in `src/schemas.py` to allow the downstream system to identify chunks containing markdown tables.

## Implementation Plan
1. **Improve Parser Normalization:** Modified `_parse_docx` in `src/pipelines/parser.py`. We now track the XML element IDs (`cell._tc`) of cells within rows to skip duplicates caused by vertically or horizontally merged cells.
2. **Detect Table Structures:** Updated `process_and_upload` in `src/pipelines/ingestion.py` to detect tabular structures during the chunking phase using a robust regex (`re.MULTILINE`), setting the new `is_table` flag.
3. **Preserve Source-level Isolation:** Injected strict instructions (`MULTI-SOURCE ISOLATION`) into the `STANDARD` and `FULL` generation prompts inside `src/core/generator.py` to force the LLM to separate tables based on document sources rather than synthesizing them.
4. **Validation for Multi-source Rendering:** Appended an explicit checklist rule in the `FULL` generation prompt, enforcing self-validation during generation to prevent merging.

## Formatting Strategy
- **Prompt Anchoring:** The LLM is explicitly instructed to never simplify tables into bullet points and must preserve metadata columns (e.g., *responsible unit, timeline, notes, dependencies*).
- **Source Splitting:** For multi-document extraction, the format enforces one explicit table/section per source.

## Risks & Tradeoffs
- **Token Consumption:** Explicitly rendering full tables rather than summarizing them will increase `completion_tokens` usage.
- **Latency:** Increased token generation may slightly increase response latency in the UI.
- **Backwards Compatibility:** To leverage the new `is_table` flag, existing documents in the Qdrant collection need to be re-ingested.

## Testing Checklist
- [ ] **Extraction Test:** Upload a DOCX with merged table cells and ensure no duplicated token loops appear in chunks.
- [ ] **Single-Source Table:** Ask for "Quy trình onboarding". Verify the output is a pristine Markdown table retaining all metadata columns.
- [ ] **Multi-Source Rendering:** Ask a query that pulls from multiple department policies (e.g., "Quy định onboarding của IT và HR"). Verify that two separate tables are rendered and properly attributed to their respective sources.
- [ ] **Chunk Schema Validation:** Inspect Qdrant payloads to verify `is_table` is properly evaluated to `true` for table-heavy sections.

## Rollback Strategy
If token limits are consistently exceeded or hallucinations occur:
1. Revert `ChunkPayload` modifications in `src/schemas.py`.
2. Remove table flag parsing from `src/pipelines/ingestion.py`.
3. Restore `src/core/generator.py` and `src/pipelines/parser.py` using `git checkout`.
4. Flush the Qdrant index and restore from the last known stable snapshot.
