# Knowledge Item: Handling General Intents
**Date:** 2026-05-08
**ID:** 080526_01

## 1. Context & Problem
Previously, KnowBot had a hardcoded response for any query classified as having a "general" intent (greetings, small talk, or basic non-technical knowledge). 

**Symptoms:**
- User: "hello" -> Bot: "Xin chào! Tôi là hệ thống AI nội bộ TechCorp."
- User: "ngày mai là thứ mấy" (what day is tomorrow) -> Bot: "Xin chào! Tôi là hệ thống AI nội bộ TechCorp."

The system failed to provide actual answers for non-technical queries because it short-circuited the pipeline before reaching the LLM generator.

## 2. Root Cause Analysis
In `src/pipelines/orchestration.py`, the code explicitly checked for `analysis.intent == "general"` and returned a static string, ignoring the user's specific question.

## 3. Proposed & Implemented Solution

### A. Generator Enhancement
Added a new prompt tier named `GENERAL` in `src/core/generator.py`. 
- **System Prompt:** Instructs the AI to be friendly, answer basic questions (greetings, dates, simple math) naturally, but avoid hallucinating internal TechCorp policies.
- **Goal:** Maintain the "TechCorp AI" persona while being useful for non-RAG tasks.

### B. Orchestration Update
Modified the logic in `src/pipelines/orchestration.py` to:
1. Detect `general` intent.
2. Instead of a static string, call `self.generator.generate` using the `GENERAL` prompt tier.
3. Pass an empty context since no retrieval is needed for general queries.
4. Provide a graceful fallback to the old greeting in case of LLM connection issues.

## 4. Files Modified
- [generator.py](file:///wsl.localhost/Ubuntu/home/lmhieu/techcorp_onboard_knowledge_base/src/core/generator.py): Added `GENERAL` prompt template.
- [orchestration.py](file:///wsl.localhost/Ubuntu/home/lmhieu/techcorp_onboard_knowledge_base/src/pipelines/orchestration.py): Updated intent handling logic.

## 5. Verification Results
- **Greeting:** "hello" now receives a dynamic, friendly response.
- **General Knowledge:** "ngày mai là thứ mấy" is now answered correctly by the LLM instead of receiving a greeting.
- **Safety:** The system still refuses to fabricate internal policies if not provided in context.

---
*This document serves as a Knowledge Item (KI) for future sessions to understand the rationale behind the general intent handling logic.*
