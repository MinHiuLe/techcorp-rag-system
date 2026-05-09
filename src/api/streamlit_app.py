import streamlit as st
import requests
import os
import json
import time
import base64
import markdown
import streamlit.components.v1 as components  # type: ignore
from markdown.extensions.tables import TableExtension
from markdown.extensions.fenced_code import FencedCodeExtension
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
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            try:
                with open(file_path, "rb") as f:
                    pdf_bytes = f.read()
                    base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                
                # Metadata Info Bar
                size_str = f"{len(pdf_bytes)/1024:.1f} KB" if len(pdf_bytes) > 1024 else f"{len(pdf_bytes)} bytes"
                cols_meta = st.columns([3, 2, 2])
                cols_meta[0].caption(f"📍 **Đường dẫn:** `{file_name}`")
                cols_meta[1].caption(f"📏 **Kích thước:** `{size_str}`")
                cols_meta[2].caption(f"📄 **Định dạng:** `PDF`")
                st.divider()

                # PDF Viewer
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="700" type="application/pdf" style="border:none; border-radius:8px;"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
                
                if st.button("Đóng", use_container_width=True, type="primary"):
                    st.rerun()
                return 
            except Exception as e:
                st.error(f"❌ Lỗi khi đọc file PDF: {e}")
                return

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
                        replacement = f'<div id="retrieval-target"></div><mark style="background-color: #fef08a; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">🎯 KẾT QUẢ TRÍCH XUẤT</mark>\n\n{search_str}'
                        content = content.replace(search_str, replacement, 1)
                        target_injected = True
                        break

    # Metadata Info Bar cho Text/MD
    file_size = len(content) if file_path else 0
    size_str = f"{file_size/1024:.1f} KB" if file_size > 1024 else f"{file_size} bytes"
    
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
            
    cols = st.columns([8, 2])
    if cols[1].button("Đóng", use_container_width=True, type="primary"):
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
    white-space: pre-wrap;
    word-break: break-word;
}

.msg-bubble p:last-child { margin-bottom: 0; }

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

/* Streaming Effects */
.stream-bubble { position: relative; overflow: hidden; }
.stream-bubble::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    border-radius: 20px; animation: stream-glow 2s infinite; pointer-events: none;
}
.stream-cursor {
    display: inline-block; width: 2px; height: 1.1em; background-color: var(--primary);
    margin-left: 2px; vertical-align: text-bottom; animation: blink-cursor 0.8s step-end infinite;
}

.thinking-bubble {
    display: flex; align-items: center; gap: 6px; padding: 14px 18px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 20px;
    border-bottom-left-radius: 4px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.02);
    max-width: 85%; animation: reveal 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.thinking-dot {
    width: 8px; height: 8px; background: var(--primary); border-radius: 50%;
    animation: thinking-pulse 1.4s ease-in-out infinite;
}
.thinking-dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-dot:nth-child(3) { animation-delay: 0.4s; }

.thinking-text { font-size: 0.9rem; color: var(--muted); margin-left: 4px; font-style: italic; }

.meta-row { display: flex; align-items: center; gap: 8px; margin-top: 6px; margin-left: 4px; flex-wrap: wrap; }
.latency-chip { font-size: 0.7rem; color: #94a3b8; font-family: monospace; }

div[data-testid="stHorizontalBlock"] button {
    font-size: 0.7rem !important; color: #64748b !important; background-color: #f1f5f9 !important;
    border: 1px solid #e2e8f0 !important; padding: 2px 8px !important; border-radius: 4px !important;
    font-family: monospace !important; min-height: 24px !important; height: auto !important;
}

[data-testid="stChatInput"] {
    border-radius: 18px !important; border: 1px solid var(--border) !important;
    background-color: rgba(255, 255, 255, 0.8) !important; backdrop-filter: blur(12px);
    transition: var(--transition-smooth) !important;
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

    # Pre-render markdown to HTML
    body_html = markdown.markdown(content, extensions=[TableExtension(), FencedCodeExtension()])

    st.markdown(f"""
    <div class="msg-wrap {cls}" style="animation-delay:{delay}s; margin-bottom: 5px;">
        <div class="msg-label">{label}</div>
        <div class="msg-bubble">{body_html}</div>
        {meta_html}
    </div>
    """, unsafe_allow_html=True)
    
    if sources:
        cols = st.columns(len(sources)) 
        for idx, s in enumerate(sources):
            if cols[idx].button(f"📄 {s}", key=f"btn_src_{index}_{idx}"):
                preview_source_dialog(s, raw_context)

# ── History ───────────────────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown('<div style="text-align:center; padding:5rem 1rem;"><h2>Xin chào!</h2><p>Tôi có thể giúp gì cho công việc của bạn hôm nay?</p></div>', unsafe_allow_html=True)
else:
    for i, m in enumerate(st.session_state.messages):
        render_message(role=m["role"], content=m["content"], latency=m.get("latency"), source=m.get("source"), raw_context=m.get("raw_context"), index=i)
        if m["role"] == "assistant":
            st.feedback("thumbs", key=f"fb_{i}", on_change=handle_feedback, args=(i,))

# ── Input ─────────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Nhập câu hỏi tại đây..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_prompt = st.session_state.messages[-1]["content"]
    placeholder = st.empty()
    placeholder.markdown('<div class="msg-wrap msg-bot"><div class="msg-label">KnowBot</div><div class="thinking-bubble"><div class="thinking-dot"></div><div class="thinking-dot"></div><div class="thinking-dot"></div></div></div>', unsafe_allow_html=True)
    
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    try:
        start_time = time.time()
        res = requests.post(CHAT_STREAM_URL, json={"query": last_prompt, "session_id": "user_123"}, headers=headers, stream=True, timeout=REQUEST_TIMEOUT)

        if res.status_code == 200:
            full_answer = ""
            stream_state = {"source": None, "raw_context": None}
            
            for line in res.iter_lines():
                if line:
                    data = json.loads(line.decode('utf-8'))
                    if data["type"] == "metadata":
                        stream_state["source"] = data.get("source")
                        stream_state["raw_context"] = data.get("context")
                    elif data["type"] == "content":
                        full_answer += data.get("content", "")
                        placeholder.markdown(f'<div class="msg-wrap msg-bot"><div class="msg-label">KnowBot</div><div class="msg-bubble stream-bubble">{full_answer}<span class="stream-cursor"></span></div></div>', unsafe_allow_html=True)

            latency = round(time.time() - start_time, 2)
            # Final render with proper markdown
            body_html = markdown.markdown(full_answer, extensions=[TableExtension(), FencedCodeExtension()])
            placeholder.markdown(f'<div class="msg-wrap msg-bot"><div class="msg-label">KnowBot</div><div class="msg-bubble">{body_html}</div></div>', unsafe_allow_html=True)
            
            st.session_state.messages.append({"role": "assistant", "content": full_answer, "latency": latency, "source": stream_state["source"], "raw_context": stream_state["raw_context"]})
            st.rerun()
    except Exception as e:
        st.error(f"Lỗi: {e}")