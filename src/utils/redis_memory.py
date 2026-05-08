import json
import redis
import time
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from config.settings import settings

class RedisMemory:
    def __init__(self, redis_url: str = settings.REDIS_URL, expiration: int = 3600 * 24):
        """
        Quản lý bộ nhớ phiên chat bằng Redis.
        :param expiration: Thời gian sống của session (giây). Mặc định 24h.
        """
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.expiration = expiration

    def _get_key(self, session_id: str) -> str:
        return f"session_memory:{session_id}"

    def status(self) -> dict:
        try:
            self.client.ping()
            return {"healthy": True, "message": "Connected"}
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        key = self._get_key(session_id)
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return []

    def add_message(self, session_id: str, user_query: str, bot_answer: str, max_turns: int = 3):
        history = self.get_history(session_id)
        history.append({"user": user_query, "bot": bot_answer})
        
        # Giới hạn số lượng turn
        if len(history) > max_turns:
            history = history[-max_turns:]
            
        key = self._get_key(session_id)
        self.client.set(key, json.dumps(history), ex=self.expiration)

    def clear(self, session_id: str):
        key = self._get_key(session_id)
        self.client.delete(key)

    def save_feedback(self, session_id: str, query: str, answer: str, context: str, is_positive: bool, source: str = None):
        """
        Lưu phản hồi từ người dùng vào Redis và ghi log persistent vào file.
        """
        # Sử dụng giờ Việt Nam (UTC+7)
        vn_tz = timezone(timedelta(hours=7))
        timestamp = datetime.now(vn_tz).strftime("%Y-%m-%d %H:%M:%S")
        feedback_data = {
            "timestamp": timestamp,
            "session_id": session_id,
            "query": query,
            "answer": answer,
            "context": context,
            "is_positive": is_positive,
            "source": source
        }
        
        # 1. Lưu vào Redis (truy xuất nhanh/hàng đợi)
        self.client.lpush("kb:feedback_logs", json.dumps(feedback_data))
        
        # 2. Ghi vào file persistent (để theo dõi lâu dài)
        # Thư mục storage/ đã được mount volume trong docker-compose
        log_path = "storage/feedback_audit.jsonl"
        try:
            # Tạo thư mục nếu chưa có (trong trường hợp chạy local ko qua docker)
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(feedback_data, ensure_ascii=False) + "\n")
        except Exception as e:
            # Không để lỗi ghi file làm crash app, chỉ log lại
            print(f"⚠️ Warning: Không thể ghi feedback vào file: {e}")
