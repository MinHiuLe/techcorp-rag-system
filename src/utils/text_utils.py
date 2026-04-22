import unicodedata

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