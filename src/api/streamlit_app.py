import streamlit as st
import requests
import os

# ─────────────────────────────
# CONFIG
# ─────────────────────────────
st.set_page_config(
    page_title="KnowBot · TechCorp",
    page_icon="💬",
    layout="centered"
)

API_URL = os.getenv("API_URL", "http://localhost:8000/chat")

# ─────────────────────────────
# UI STYLE (NÂNG CẤP HIỆU ỨNG MƯỢT MÀ)
# ─────────────────────────────
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

/* APP BACKGROUND */
html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    font-family: "Inter", "Segoe UI", Helvetica, Arial, sans-serif;
}

#MainMenu, footer, header { visibility: hidden; }

.main .block-container {
    padding: 2rem 1rem 6rem;
    max-width: 760px;
}

/* KEYFRAMES */
@keyframes reveal {
    0% { opacity: 0; transform: translateY(12px) scale(0.98); }
    100% { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes pulse-subtle {
    0% { transform: scale(1); }
    50% { transform: scale(1.02); }
    100% { transform: scale(1); }
}

/* HEADER */
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

/* MESSAGE WRAPPER */
.msg-wrap {
    display: flex;
    flex-direction: column;
    margin-bottom: 20px;
    will-change: transform, opacity;
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

/* BUBBLE */
.msg-bubble {
    padding: 14px 18px;
    border-radius: 20px;
    font-size: 0.96rem;
    line-height: 1.55;
    max-width: 85%;
    transition: var(--transition-smooth);
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.02);
    position: relative;
    border: 1px solid transparent;
}

/* USER STYLE */
.msg-user { align-items: flex-end; }
.msg-user .msg-bubble {
    background: var(--primary);
    color: white;
    border-bottom-right-radius: 4px;
    box-shadow: 0 4px 15px rgba(90, 169, 230, 0.2);
}

/* BOT STYLE */
.msg-bot { align-items: flex-start; }
.msg-bot .msg-bubble {
    background: var(--panel);
    border: 1px solid var(--border);
    color: var(--text);
    border-bottom-left-radius: 4px;
}

/* HOVER EFFECT - NHẸ NHÀNG */
.msg-bubble:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.06);
}

.msg-user .msg-bubble:hover {
    box-shadow: 0 10px 25px rgba(90, 169, 230, 0.3);
}

/* CHAT INPUT */
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

/* EMPTY STATE */
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

/* LOADING SPINNER CUSTOM */
.stSpinner > div {
    border-top-color: var(--primary) !important;
}

</style>
""", unsafe_allow_html=True)

# ─────────────────────────────
# STATE
# ─────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# ─────────────────────────────
# HEADER
# ─────────────────────────────
st.markdown("""
<div class="kb-header">
    <div class="kb-logo">KB</div>
    <div>
        <div style="font-weight:700; font-size:1.1rem; color:#1e293b; line-height:1.2;">KnowBot</div>
        <div style="font-size:0.85rem; color:#64748b;">Hệ thống tri thức nội bộ TechCorp</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────
# RENDER MESSAGE
# ─────────────────────────────
def render_message(role, content, index):
    cls = "msg-user" if role == "user" else "msg-bot"
    label = "Bạn" if role == "user" else "KnowBot"
    # Thêm một chút delay staggered cho mỗi message dựa trên index để tạo hiệu ứng mượt
    delay = min(index * 0.05, 0.5) 
    
    st.markdown(f"""
    <div class="msg-wrap {cls}" style="animation-delay: {delay}s;">
        <div class="msg-label">{label}</div>
        <div class="msg-bubble">{content}</div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────
# HISTORY
# ─────────────────────────────
if not st.session_state.messages:
    st.markdown("""
    <div class="empty-hero">
        <div style="font-size: 3rem; margin-bottom: 1rem;">👋</div>
        <h2>Xin chào!</h2>
        <p style="color: #64748b; font-size: 1.05rem;">Tôi có thể giúp gì cho công việc của bạn hôm nay?</p>
    </div>
    """, unsafe_allow_html=True)
else:
    for i, m in enumerate(st.session_state.messages):
        render_message(m["role"], m["content"], i)

# ─────────────────────────────
# INPUT
# ─────────────────────────────
if prompt := st.chat_input("Nhập câu hỏi tại đây..."):

    st.session_state.messages.append({"role": "user", "content": prompt})
    # Render ngay lập tức tin nhắn user để tạo cảm giác phản hồi nhanh
    st.rerun()

# Logic xử lý API sau khi rerun để đảm bảo UI mượt
if len(st.session_state.messages) > 0 and st.session_state.messages[-1]["role"] == "user":
    last_prompt = st.session_state.messages[-1]["content"]
    
    with st.spinner("Đang truy vấn dữ liệu..."):
        try:
            res = requests.post(API_URL, json={
                "query": last_prompt,
                "session_id": "user_123"
            }, timeout=30)

            if res.status_code == 200:
                answer = res.json().get("answer", "Không có phản hồi.")
            else:
                answer = "Rất tiếc, đã có lỗi xảy ra khi kết nối hệ thống."
        except Exception as e:
            answer = f"Lỗi kết nối: {e}"

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.rerun()