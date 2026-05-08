import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="KnowBot · TechCorp",
    page_icon="💬",
    layout="centered"
)

# Ưu tiên lấy API_BASE_URL (cho chat + feedback)
# Nếu không có, thử lấy từ API_URL (cũ) và lọc bỏ phần /chat
api_url_env = os.getenv("API_URL", "")
default_base = api_url_env.replace("/chat", "") if api_url_env else "http://api:8000"

API_BASE_URL = os.getenv("API_BASE_URL", default_base)
CHAT_URL     = f"{API_BASE_URL}/chat"
FEEDBACK_URL = f"{API_BASE_URL}/chat/feedback"
API_KEY      = os.getenv("API_KEY", "") # Cần API Key nếu API yêu cầu

# Timeout config — tăng lên 60s để handle multi-topic queries
REQUEST_TIMEOUT = 60

# ── Feedback Callback ────────────────────────────────────────────────────────
def handle_feedback(msg_index: int):
    # Lấy phản hồi từ state của widget
    feedback_val = st.session_state.get(f"fb_{msg_index}")
    if feedback_val is None:
        return
    
    # Map: 0 -> Thumbs Down (False), 1 -> Thumbs Up (True)
    is_positive = (feedback_val == "👍") # st.feedback("thumbs") trả về "👍" hoặc "👎" trong bản mới hoặc 0/1 tùy version. 
    # Trong Streamlit 1.35.0+, st.feedback("thumbs") trả về 0 (down) hoặc 1 (up) hoặc None.
    # Kiểm tra kiểu dữ liệu trả về
    is_positive = bool(feedback_val) 

    msg = st.session_state.messages[msg_index]
    # Query là tin nhắn ngay trước đó của user
    query = st.session_state.messages[msg_index-1]["content"] if msg_index > 0 else "Unknown"
    
    payload = {
        "query": query,
        "answer": msg["content"],
        "context": msg.get("raw_context", ""),
        "is_positive": is_positive,
        "session_id": "user_123",
        "source": msg.get("source")
    }
    
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    
    try:
        requests.post(FEEDBACK_URL, json=payload, headers=headers, timeout=5)
        st.toast("Cảm ơn bạn đã phản hồi! ❤️" if is_positive else "Cảm ơn bạn, chúng tôi sẽ cải thiện! 🛠️")
    except Exception as e:
        st.error(f"Không thể gửi phản hồi: {e}")

st.markdown("""
<style>
:root {
    --bg: #f8fafc;
    --panel: #ffffff;
    --border: rgba(0, 0, 0, 0.05);
    --primary: #5aa9e6;
    --primary-soft: rgba(90, 169, 230, 0.1);
    --text: #1e293b;
    --muted: #64748b;
    --transition-smooth: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    font-family: "Inter", "Segoe UI", Helvetica, Arial, sans-serif;
}

#MainMenu, footer, header { visibility: hidden; }

.main .block-container {
    padding: 2rem 1rem 6rem;
    max-width: 760px;
}

@keyframes reveal {
    0% { opacity: 0; transform: translateY(12px) scale(0.98); }
    100% { opacity: 1; transform: translateY(0) scale(1); }
}

.kb-header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 30px;
    animation: reveal 0.8s cubic-bezier(0.16, 1, 0.3, 1);
}

.kb-logo {
    width: 42px; height: 42px;
    border-radius: 12px;
    background: linear-gradient(135deg, #5aa9e6 0%, #4481eb 100%);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    box-shadow: 0 8px 20px rgba(90, 169, 230, 0.3);
}

.msg-wrap {
    display: flex;
    flex-direction: column;
    margin-bottom: 20px;
    animation: reveal 0.5s cubic-bezier(0.16, 1, 0.3, 1) backwards;
}

.msg-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--muted);
    margin-bottom: 6px;
    margin-left: 8px;
    letter-spacing: 0.02em;
}

.msg-bubble {
    padding: 14px 18px;
    border-radius: 20px;
    font-size: 0.96rem;
    line-height: 1.55;
    max-width: 85%;
    transition: var(--transition-smooth);
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.02);
    border: 1px solid transparent;
}

.msg-user { align-items: flex-end; }
.msg-user .msg-bubble {
    background: var(--primary);
    color: white;
    border-bottom-right-radius: 4px;
    box-shadow: 0 4px 15px rgba(90, 169, 230, 0.2);
}

.msg-bot { align-items: flex-start; }
.msg-bot .msg-bubble {
    background: var(--panel);
    border: 1px solid var(--border);
    color: var(--text);
    border-bottom-left-radius: 4px;
}

.msg-bubble:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.06);
}

.msg-user .msg-bubble:hover {
    box-shadow: 0 10px 25px rgba(90, 169, 230, 0.3);
}

.meta-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
    margin-left: 4px;
    flex-wrap: wrap;
}

.source-chip {
    font-size: 0.7rem;
    color: #64748b;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    padding: 2px 8px;
    border-radius: 4px;
    font-family: monospace;
}

.latency-chip {
    font-size: 0.7rem;
    color: #94a3b8;
    font-family: monospace;
}

[data-testid="stChatInput"] {
    border-radius: 18px !important;
    border: 1px solid var(--border) !important;
    background-color: rgba(255, 255, 255, 0.8) !important;
    backdrop-filter: blur(12px);
    transition: var(--transition-smooth) !important;
    padding: 4px !important;
}

[data-testid="stChatInput"]:focus-within {
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.08) !important;
    border-color: rgba(90, 169, 230, 0.3) !important;
    transform: translateY(-2px);
}

.empty-hero {
    text-align: center;
    padding: 5rem 1rem;
    animation: reveal 1s cubic-bezier(0.16, 1, 0.3, 1);
}

.empty-hero h2 {
    font-weight: 800;
    color: var(--text);
    letter-spacing: -0.02em;
}
</style>
""", unsafe_allow_html=True)

# ── State ─────────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="kb-header">
    <div class="kb-logo">KB</div>
    <div>
        <div style="font-weight:700; font-size:1.1rem; color:#1e293b; line-height:1.2;">KnowBot</div>
        <div style="font-size:0.85rem; color:#64748b;">Hệ thống tri thức nội bộ TechCorp</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ── Render ────────────────────────────────────────────────────────────────────
def render_message(role: str, content: str, latency: float = None, source: str = None, index: int = 0):
    cls   = "msg-user" if role == "user" else "msg-bot"
    label = "Bạn" if role == "user" else "KnowBot"
    delay = min(index * 0.05, 0.5)

    meta_html = ""
    if role == "assistant":
        chips = ""
        if source:
            for s in source.split(","):
                s = s.strip()
                if s:
                    chips += f'<span class="source-chip">📄 {s}</span>'
        lat_html = f'<span class="latency-chip">⏱ {latency}s</span>' if latency else ""
        if chips or lat_html:
            meta_html = f'<div class="meta-row">{chips}{lat_html}</div>'

    st.markdown(f"""
    <div class="msg-wrap {cls}" style="animation-delay:{delay}s">
        <div class="msg-label">{label}</div>
        <div class="msg-bubble">{content}</div>
        {meta_html}
    </div>
    """, unsafe_allow_html=True)


# ── History ───────────────────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown("""
    <div class="empty-hero">
        <div style="font-size:3rem; margin-bottom:1rem;">👋</div>
        <h2>Xin chào!</h2>
        <p style="color:#64748b; font-size:1.05rem;">
            Tôi có thể giúp gì cho công việc của bạn hôm nay?
        </p>
        <p style="color:#94a3b8; font-size:0.85rem; margin-top:0.5rem;">
            Câu hỏi phức tạp (nhiều chủ đề) có thể mất 15–20s để xử lý.
        </p>
    </div>
    """, unsafe_allow_html=True)
else:
    for i, m in enumerate(st.session_state.messages):
        render_message(
            role    = m["role"],
            content = m["content"],
            latency = m.get("latency"),
            source  = m.get("source"),
            index   = i,
        )

        # Feedback widget cho assistant message
        if m["role"] == "assistant":
            # Tạo unique key cho feedback widget
            fb_key = f"fb_{i}"
            # Render feedback widget ngay bên dưới bubble
            st.feedback(
                "thumbs", 
                key=fb_key, 
                on_change=handle_feedback, 
                args=(i,)
            )

# ── Input ─────────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Nhập câu hỏi tại đây..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

# Xử lý API sau rerun
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_prompt = st.session_state.messages[-1]["content"]

    # Hiển thị hint nếu query phức tạp (nhiều "?")
    is_complex = last_prompt.count("?") >= 2
    spinner_msg = (
        "Đang xử lý câu hỏi phức tạp (multi-topic)... có thể mất 15–20s"
        if is_complex
        else "Đang truy vấn dữ liệu..."
    )

    with st.spinner(spinner_msg):
        headers = {"X-API-Key": API_KEY} if API_KEY else {}
        try:
            res = requests.post(
                CHAT_URL,
                json={"query": last_prompt, "session_id": "user_123"},
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )

            if res.status_code == 200:
                data    = res.json()
                answer  = data.get("answer", "Không có phản hồi.")
                latency = data.get("latency_seconds")
                source  = data.get("source")
                # Giả sử API chưa trả về context trực tiếp, ta có thể cần điều chỉnh API
                # Hiện tại app.py trả về ChatResponse (answer, source, latency)
                # Ta cần app.py trả về cả context để lưu feedback chính xác nhất.
                raw_context = data.get("context", "") # Cần check app.py có trả về ko
            else:
                answer  = f"Rất tiếc, đã có lỗi xảy ra (HTTP {res.status_code})."
                latency = None
                source  = None
                raw_context = None

        except requests.exceptions.Timeout:
            answer  = "⏱ Request timeout — câu hỏi quá phức tạp hoặc server đang bận."
            latency = None
            source  = None
            raw_context = None
        except Exception as e:
            answer  = f"Lỗi kết nối: {e}"
            latency = None
            source  = None
            raw_context = None

    st.session_state.messages.append({
        "role"   : "assistant",
        "content": answer,
        "latency": latency,
        "source" : source,
        "raw_context": raw_context
    })
    st.rerun()