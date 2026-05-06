from google import genai
import os

# Khởi tạo client
client = genai.Client(api_key="AIzaSyB7soej7ToYYjDY-cAQFNfgh089v6NHhN4")

try:
    # Với SDK mới, bạn gọi trực tiếp từ client.models
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite", 
        contents="API này đã hoạt động chưa?"
    )
    
    print("--- Kết quả ---")
    print(response.text)
    print("---------------")
    print("API hoạt động tốt trên SDK mới!")

except Exception as e:
    print(f"Lỗi rồi: {e}")