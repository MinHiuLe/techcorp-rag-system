import streamlit as st
import os
from dotenv import load_dotenv
from .agent import chat_pipeline


load_dotenv()

st.set_page_config(
    page_title="TechCorp Onboarding AI",
    page_icon="🤖",
    layout="centered"
)

st.title("🚀 TechCorp Onboarding Assistant")
st.markdown("Hỏi tôi bất kỳ điều gì về quy trình IT, bảo mật hoặc hệ thống nội bộ!")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ví dụ: Quy trình cấp quyền Jira như thế nào?"):

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Đang tìm kiếm trong Knowledge Base..."):
            try:
                response = chat_pipeline(prompt)
                st.markdown(response)

                st.session_state.messages.append(
                    {"role": "assistant", "content": response}
                )

            except Exception as e:
                st.error(f"Đã xảy ra lỗi: {e}")