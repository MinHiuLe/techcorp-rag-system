import streamlit as st
import requests
import os


st.set_page_config(
    page_title="TechCorp AI Assistant",
    page_icon="🤖",
    layout="centered"
)


API_URL = os.getenv("API_URL", "http://localhost:8000/chat")

st.title("🤖 TechCorp IT Onboarding")
st.markdown("---")


if "messages" not in st.session_state:
    st.session_state.messages = []


with st.sidebar:
    st.header("Cấu hình")
    session_id = st.text_input("Session ID", value="user_123")

    if st.button("Xóa lịch sử Chat"):
        requests.delete("http://localhost:8000/chat/memory")
        st.session_state.messages = []
        st.rerun()

    st.info(
        "Hệ thống sử dụng Llama-3-70B & Hybrid Search để cung cấp câu trả lời chính xác nhất từ tài liệu nội bộ."
    )


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


if prompt := st.chat_input("Hỏi tôi về quy trình IT, Docker, Jira..."):

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("🔍 *Đang truy vấn tài liệu...*")

        try:
            payload = {"query": prompt, "session_id": session_id}
            response = requests.post(API_URL, json=payload)

            if response.status_code == 200:
                data = response.json()
                full_response = data["answer"]
                latency = data["latency_seconds"]

                message_placeholder.markdown(full_response)
                st.caption(f"⏱️ Thời gian xử lý: {latency} giây")

                st.session_state.messages.append(
                    {"role": "assistant", "content": full_response}
                )
            else:
                st.error(f"Lỗi hệ thống: {response.status_code}")

        except Exception as e:
            st.error(f"Không thể kết nối tới Backend: {str(e)}")