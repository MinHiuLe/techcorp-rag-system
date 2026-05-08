# Knowledge Item: Source Viewer Implementation & Intent Detection Refinement
**Date:** 2026-05-09
**ID:** 090526_01

## 1. Context & Problem
Users needed a way to verify the source of information without leaving the chat interface. Additionally, some specific HR-related queries (e.g., about pregnancy/leave) were being misclassified as "general" intent by the LLM, leading to empty retrieval results.

## 2. Implemented Solutions

### A. Interactive Source Viewer (Streamlit)
Implemented in `src/api/streamlit_app.py`:
- **Interactive Chips:** Replaced static HTML chips with `st.button` elements. Used targeted CSS to maintain the original "tag" aesthetic (inline flex, small font, grey background).
- **Modal Preview:** Used `@st.dialog` to show the full Markdown content of the source file.
- **Smart Auto-Scroll:** 
    - The modal parses `raw_context` to identify which specific chunks were retrieved.
    - It searches the full document for the first 20+ character line of the retrieved chunk.
    - It injects a `<div id="retrieval-target">` anchor and a visual `🎯 KẾT QUẢ TRÍCH XUẤT` marker.
    - Uses `st.components.v1.html` to execute a JS snippet calling `scrollIntoView()` on the anchor after the modal renders.

### B. Intent Detection Guardrails
Updated `src/core/analyzer.py`:
- **Keyword-based Override:** Expanded `_TECHNICAL_KEYWORDS` with terms like `thai sản`, `xin nghỉ`, `có thai`, `vợ sinh`.
- **Logic:** If the LLM classifies a query as `general` but any of these keywords are present, the intent is forced to `technical`. This ensures the RAG pipeline is triggered for conversational but policy-relevant HR questions.

## 3. Architecture & Technical Notes
- **File Access:** The UI container must have the same volume mounts as the API for `data/` and `docs/knowledge/` to enable direct file reading in the Streamlit app.
- **JS Injection:** The auto-scroll relies on `window.parent.document` access, which works in standard Streamlit deployments but may require adjustment if the UI is embedded in complex iframes.
- **Performance:** Modal rendering and file reading are performed on-demand to minimize impact on the main chat loop.

## 4. Files Modified
- [streamlit_app.py](file:///wsl.localhost/Ubuntu/home/lmhieu/techcorp_onboard_knowledge_base/src/api/streamlit_app.py): UI implementation of buttons and dialog.
- [analyzer.py](file:///wsl.localhost/Ubuntu/home/lmhieu/techcorp_onboard_knowledge_base/src/core/analyzer.py): Intent detection guardrails.

---
*This document serves as a record of UI/UX improvements and retrieval reliability fixes.*
