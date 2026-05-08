import streamlit as st
import requests
import os
import json
import time
import streamlit.components.v1 as components  # type: ignore
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="KnowBot · TechCorp",
    page_icon="💬",
    layout="centered"
)

api_url_env = os.getenv("API_URL", "")
default_base = api_url_env.replace("/chat", "") if api_url_env else "http://api:8000"

API_BASE_URL = os.getenv("API_BASE_URL", default_base)
CHAT_URL     = f"{API_BASE_URL}/chat"
CHAT_STREAM_URL = f"{API_BASE_URL}/chat/stream"
FEEDBACK_URL = f"{API_BASE_URL}/chat/feedback"
API_KEY      = os.getenv("API_KEY", "") 

REQUEST_TIMEOUT = 60

# ── Feedback Callback ────────────────────────────────────────────────────────
def handle_feedback(msg_index: int):
    feedback_val = st.session_state.get(f"fb_{msg_index}")
    if feedback_val is None:
        return
    
    is_positive = bool(feedback_val) 

    msg = st.session_state.messages[msg_index]
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

# ── Preview Source Dialog ─────────────────────────────────────────────────────
@st.dialog("📄 Chi tiết tài liệu nguồn", width="large")
def preview_source_dialog(file_name: str, raw_context: str = None):
    import os
    search_dirs = ["data", "docs/knowledge", "docs", "."]
    file_path = None
    
    def find_file(name, path):
        for root, dirs, files in os.walk(path):
            if name in files:
                return os.path.join(root, name)
        return None

    base_name = os.path.basename(file_name)

    for d in search_dirs:
        if os.path.exists(d):
            file_path = find_file(base_name, d)
            if file_path:
                break
                
    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            content = f"❌ Lỗi khi đọc file: {e}"
    else:
        content = f"❌ Không tìm thấy nội dung cho tài liệu: `{file_name}` trong hệ thống."

    target_injected = False
    if raw_context:
        retrieved_chunks = []
        blocks = raw_context.split("[Nguồn: ")
        for b in blocks:
            if b.strip() and b.startswith(file_name + "]"):
                chunk = b[len(file_name)+1:].strip()
                if chunk.endswith("---"):
                    chunk = chunk[:-3].strip()
                if chunk:
                    retrieved_chunks.append(chunk)
                    
        if retrieved_chunks:
            for chunk in retrieved_chunks:
                lines = [line.strip() for line in chunk.split('\n') if len(line.strip()) > 20]
                if lines:
                    search_str = lines[0]
                    if search_str in content:
                        replacement = f"""<div id="retrieval-target" style="padding: 15px; background: rgba(90, 169, 230, 0.05); border-left: 4px solid var(--primary); border-radius: 4px; margin: 10px 0;">
<mark class="pulse-mark" style="background-color: #fef08a; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em; color: #854d0e;">🎯 KẾT QUẢ TRÍCH XUẤT</mark>
<div style="margin-top: 10px; font-style: italic; color: #475569;">
{search_str}
</div>
</div>"""
                        content = content.replace(search_str, replacement, 1)
                        target_injected = True
                        break

    # Tính toán thông tin file
    file_size = len(content) if file_path else 0
    size_str = f"{file_size/1024:.1f} KB" if file_size > 1024 else f"{file_size} bytes"
    
    # Header Info Bar
    cols_meta = st.columns([3, 2, 2])
    cols_meta[0].caption(f"📍 **Đường dẫn:** `{file_name}`")
    cols_meta[1].caption(f"📏 **Kích thước:** `{size_str}`")
    cols_meta[2].caption(f"📄 **Định dạng:** `Markdown`" if file_name.endswith('.md') else f"📄 **Định dạng:** `Text`")
    
    st.divider()
    
    with st.container(height=500):
        if file_path and file_path.endswith('.md'):
            st.markdown(content, unsafe_allow_html=True)
        else:
            st.text(content)
            
    st.divider()
    cols_foot = st.columns([6, 2, 2])
    
    # Nút Copy sử dụng cơ chế của Streamlit (code block)
    with cols_foot[0]:
        if st.button("📋 Sao chép toàn bộ nội dung", use_container_width=True):
            st.code(content)
            st.toast("Nội dung đã được chuẩn bị trong khối code bên dưới. Bạn có thể nhấn nút copy của Streamlit!")
            
    if cols_foot[2].button("Đóng", use_container_width=True, type="primary"):
        st.rerun()

    if target_injected:
        components.html("""
            <script>
            setTimeout(function() {
                const parentDoc = window.parent.document;
                const target = parentDoc.getElementById('retrieval-target');
                if (target) {
                    target.scrollIntoView({behavior: 'smooth', block: 'center'});
                }
            }, 500);
            </script>
        """, height=0)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --bg: #f8fafc;
    --panel: #ffffff;
    --border: rgba(0, 0, 0, 0.05);
    --primary: #5aa9e6;
    --primary-soft: rgba(90, 169, 230, 0.1);
    --primary-glow: rgba(90, 169, 230, 0.15);
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

@keyframes blink-cursor {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
}

@keyframes thinking-pulse {
    0%, 100% { opacity: 0.4; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1.2); }
}

@keyframes stream-glow {
    0% { box-shadow: 0 0 0 0 rgba(90, 169, 230, 0.2); }
    70% { box-shadow: 0 0 0 10px rgba(90, 169, 230, 0); }
    100% { box-shadow: 0 0 0 0 rgba(90, 169, 230, 0); }
}

@keyframes fade-in-up {
    0% { opacity: 0; transform: translateY(8px); }
    100% { opacity: 1; transform: translateY(0); }
}

@keyframes shimmer {
    0% { background-position: -1000px 0; }
    100% { background-position: 1000px 0; }
}

@keyframes pulse-highlight {
    0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(254, 240, 138, 0.7); }
    70% { transform: scale(1.05); box-shadow: 0 0 0 10px rgba(254, 240, 138, 0); }
    100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(254, 240, 138, 0); }
}

.pulse-mark {
    display: inline-block;
    animation: pulse-highlight 2s infinite;
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

/* ── Streaming Effects ─────────────────────────────────────────── */
.stream-bubble {
    position: relative;
    overflow: hidden;
}

.stream-bubble::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    border-radius: 20px;
    animation: stream-glow 2s infinite;
    pointer-events: none;
}

.stream-cursor {
    display: inline-block;
    width: 2px;
    height: 1.1em;
    background-color: var(--primary);
    margin-left: 2px;
    vertical-align: text-bottom;
    animation: blink-cursor 0.8s step-end infinite;
    border-radius: 1px;
}

.thinking-bubble {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 14px 18px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 20px;
    border-bottom-left-radius: 4px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.02);
    max-width: 85%;
    animation: reveal 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.thinking-dot {
    width: 8px;
    height: 8px;
    background: var(--primary);
    border-radius: 50%;
    animation: thinking-pulse 1.4s ease-in-out infinite;
}

.thinking-dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-dot:nth-child(3) { animation-delay: 0.4s; }

.thinking-text {
    font-size: 0.9rem;
    color: var(--muted);
    margin-left: 4px;
    font-style: italic;
}

/* Markdown trong stream */
.stream-content p { margin: 0 0 0.6em 0; }
.stream-content p:last-child { margin-bottom: 0; }
.stream-content code {
    background: rgba(90, 169, 230, 0.1);
    color: #2563eb;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
    font-family: 'SF Mono', Monaco, monospace;
}
.stream-content pre {
    background: #1e293b;
    color: #e2e8f0;
    padding: 12px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 0.6em 0;
}
.stream-content pre code {
    background: transparent;
    color: inherit;
    padding: 0;
}
.stream-content strong { color: #0f172a; }
.stream-content ul, .stream-content ol { margin: 0.4em 0; padding-left: 1.2em; }
.stream-content li { margin: 0.2em 0; }
.stream-content blockquote {
    border-left: 3px solid var(--primary);
    margin: 0.6em 0;
    padding-left: 12px;
    color: var(--muted);
    font-style: italic;
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
    display: none; 
}

.latency-chip {
    font-size: 0.7rem;
    color: #94a3b8;
    font-family: monospace;
}

div[data-testid="stHorizontalBlock"] {
    gap: 8px !important;
    align-items: center !important;
}

div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    width: auto !important;
    flex: 0 1 auto !important;
    min-width: 0 !important;
}

div[data-testid="stHorizontalBlock"] button {
    font-size: 0.7rem !important;
    color: #64748b !important;
    background-color: #f1f5f9 !important;
    border: 1px solid #e2e8f0 !important;
    padding: 2px 8px !important;
    border-radius: 4px !important;
    font-family: monospace !important;
    min-height: 24px !important;
    height: auto !important;
    line-height: 1.5 !important;
    transition: all 0.2s !important;
    margin: 0 !important;
}

div[data-testid="stHorizontalBlock"] button p {
    font-size: 0.7rem !important;
    margin: 0 !important;
    color: #64748b !important;
}

div[data-testid="stHorizontalBlock"] button:hover {
    background-color: #e2e8f0 !important;
    border-color: #cbd5e1 !important;
    color: #1e293b !important;
    transform: translateY(-1px);
}
div[data-testid="stHorizontalBlock"] button:hover p {
    color: #1e293b !important;
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

/* Scrollbar đẹp */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
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
def render_message(role: str, content: str, latency: float = None, source: str = None, raw_context: str = None, index: int = 0):
    cls   = "msg-user" if role == "user" else "msg-bot"
    label = "Bạn" if role == "user" else "KnowBot"
    delay = min(index * 0.05, 0.5)

    meta_html = ""
    sources = []
    if role == "assistant":
        if source:
            sources = [s.strip() for s in source.split(",") if s.strip()]
            
        lat_html = f'<span class="latency-chip">⏱ {latency}s</span>' if latency else ""
        if lat_html:
            meta_html = f'<div class="meta-row">{lat_html}</div>'

    st.markdown(f"""
    <div class="msg-wrap {cls}" style="animation-delay:{delay}s; margin-bottom: 5px;">
        <div class="msg-label">{label}</div>
        <div class="msg-bubble">{content}</div>
        {meta_html}
    </div>
    """, unsafe_allow_html=True)
    
    if sources:
        cols = st.columns(len(sources)) 
        for idx, s in enumerate(sources):
            if cols[idx].button(f"📄 {s}", key=f"btn_src_{index}_{idx}", help="Nhấn để xem trước nội dung tài liệu"):
                preview_source_dialog(s, raw_context)

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
            raw_context = m.get("raw_context"),
            index   = i,
        )

        if m["role"] == "assistant":
            fb_key = f"fb_{i}"
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

    placeholder = st.empty()
    
    # ── Hiệu ứng "Đang suy nghĩ" ─────────────────────────────────────────────
    thinking_html = """
    <div class="msg-wrap msg-bot" style="margin-bottom: 5px;">
        <div class="msg-label">KnowBot</div>
        <div class="thinking-bubble">
            <div class="thinking-dot"></div>
            <div class="thinking-dot"></div>
            <div class="thinking-dot"></div>
            <span class="thinking-text">Đang suy nghĩ...</span>
        </div>
    </div>
    """
    placeholder.markdown(thinking_html, unsafe_allow_html=True)
    
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    
    try:
        start_time = time.time()
        res = requests.post(
            CHAT_URL,
            json={"query": last_prompt, "session_id": "user_123"},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        if res.status_code == 200:
            data = res.json()
            full_answer = data.get("answer", "")
            source = data.get("source", "")
            raw_context = data.get("context", "")
            latency = data.get("latency_seconds", round(time.time() - start_time, 2))
            
            # Final render với markdown thật
            final_html = f"""
            <div class="msg-wrap msg-bot" style="margin-bottom: 5px; animation: fade-in-up 0.3s ease;">
                <div class="msg-label">KnowBot</div>
                <div class="msg-bubble">{full_answer}</div>
            </div>
            """
            placeholder.markdown(final_html, unsafe_allow_html=True)
            
            st.session_state.messages.append({
                "role"   : "assistant",
                "content": full_answer,
                "latency": latency,
                "source" : source,
                "raw_context": raw_context
            })
            st.rerun()
        else:
            st.error(f"Lỗi hệ thống (HTTP {res.status_code})")
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Rất tiếc, đã có lỗi xảy ra (HTTP {res.status_code}).",
            })
            st.rerun()

    except Exception as e:
        st.error(f"Lỗi kết nối: {e}")
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"Lỗi kết nối: {e}",
        })
        st.rerun()