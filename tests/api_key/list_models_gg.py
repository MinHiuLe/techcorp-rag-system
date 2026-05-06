import os
from google import genai

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

try:
    print(f"{'Model Name':<40} | {'Display Name'}")
    print("-" * 70)
    
    for model in client.models.list():
        print(f"{model.name:<40} | {model.display_name}")
        
except Exception as e:
    print(f"Lỗi truy vấn: {e}")