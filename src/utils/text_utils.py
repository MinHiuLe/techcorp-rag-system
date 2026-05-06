import unicodedata
import re

def clean_text(text: str) -> str:
    """
    Làm sạch văn bản, chuẩn hóa Unicode. 
    Giải quyết triệt để lỗi Surrogate trong tiếng Việt.
    """
    if not text: 
        return ""
    text = str(text)
    text = unicodedata.normalize("NFC", text)
    return text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="ignore").strip()

def extract_json(text: str) -> str:
    """Robust JSON extraction from LLM output (handles markdown, extra text)."""
    if not text:
        return ""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)
    return text