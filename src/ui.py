import streamlit as st
import os
from dotenv import load_dotenv
from .agent import chat_pipeline

# Load biến môi trường (đặc biệt là cho LangSmith nếu có)
load_dotenv()

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="TechCorp Onboarding AI",
    page_icon="🤖",
    layout="centered"
)

st.title("🚀 TechCorp Onboarding Assistant")
st.markdown("Hỏi tôi bất kỳ điều gì về quy trình IT, bảo mật hoặc hệ thống nội bộ!")

# Khởi tạo session state để lưu lịch sử chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Hiển thị lịch sử chat
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Nhận input từ người dùng
if prompt := st.chat_input("Ví dụ: Quy trình cấp quyền Jira như thế nào?"):
    # Hiển thị câu hỏi của user
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Hiển thị trạng thái đang xử lý
    with st.chat_message("assistant"):
        with st.spinner("Đang tìm kiếm trong Knowledge Base..."):
            try:
                # Gọi pipeline từ agent.py
                response = chat_pipeline(prompt)
                st.markdown(response)
                # Lưu câu trả lời vào lịch sử
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                st.error(f"Đã xảy ra lỗi: {e}")