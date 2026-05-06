import json
import redis
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
