# Unified Table Formatting and Intent Hallucination Fix Report

## Root Cause Analysis
During this session, two major issues were identified and resolved:
1. **Intent Misclassification (Hallucination):** Queries involving "khách hàng" (customer) and "thanh toán" (payment) were being classified as `general` rather than `technical`. This caused the system to bypass the RAG pipeline and provide generic, hallucinated answers.
2. **Formatting Inconsistency:** Despite previous attempts to enforce tables, the LLM continued to output lists or text blocks for certain data types (e.g., Jira roles, payment timelines). Additionally, raw `<div>` tags appeared in the UI due to LLM attempting HTML styling and lack of proper CSS for table tags in the custom chat bubbles.

## Technical Changes

### 1. Intent Detection Enhancement (`src/core/analyzer.py`)
- Expanded `_TECHNICAL_KEYWORDS` to include critical business terms: `"thanh toán"`, `"thanh toán chậm"`, `"khách hàng"`, `"thu hồi nợ"`, `"collection risk"`.
- This ensures that finance and customer-related procedural questions are correctly routed through the RAG pipeline.

### 2. Universal Table Enforcement (`src/core/generator.py`)
- **Generalized Prompting:** Updated `STANDARD` and `FULL` prompts to mandate Markdown tables for *any* entity-attribute list (Roles, Permissions, Timelines, Steps).
- **One-Shot Examples:** Injected explicit Markdown table examples into the system prompts to guide the LLM's structural output.
- **Strict No-HTML Rule:** Added aggressive instructions forbidding the use of any HTML tags (e.g., `<div>`, `<table>`, `<br>`), enforcing pure Markdown for better UI compatibility.

### 3. UI Table Styling (`src/api/streamlit_app.py`)
- Injected specific CSS rules into the `msg-bubble` class to style `<table>`, `<th>`, and `<td>` tags.
- This ensures that tables generated via the `markdown` library are visible with borders, padding, and proper alignment.

### 4. Cache & State Management
- Implemented a mandatory cache-clearing step after prompt updates. Since the semantic cache stores previously generated answers, updates to system prompts are only visible for repeat queries if the cache is flushed.

## Impacted Files
- `src/core/analyzer.py`: Updated technical keywords for intent detection.
- `src/core/generator.py`: Unified table logic and HTML guardrails in prompts.
- `src/api/streamlit_app.py`: Added CSS for Markdown table rendering.

## Testing & Verification
- [x] **Hallucination Test:** "nếu khách hàng thanh toán chậm..." now correctly triggers RAG.
- [x] **Table Format Test:** "Project Roles trong jira..." now renders as a structured table.
- [x] **HTML Guardrail:** No literal `<div>` or `<br>` tags appear in the output.

## Operational Note
When updating system prompts in `generator.py`, the following operations must be performed:
1. Restart the `api` and `ui` containers to reload the code.
2. Run `app.clear_cache()` and `app.clear_memory()` to prevent stale responses.
