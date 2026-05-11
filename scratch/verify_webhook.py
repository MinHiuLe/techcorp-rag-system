import requests
import json

def test_webhook():
    url = "http://localhost:8000/webhook/minio"
    payload = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "data"},
                    "object": {"key": "IT/test_policy.pdf"}
                }
            }
        ]
    }
    
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Gửi giả lập MinIO event đến API...")
    test_webhook()
