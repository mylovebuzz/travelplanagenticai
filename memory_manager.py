import redis
import json
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass

@dataclass
class Message:
    role: str
    content: str
    timestamp: str = None
    tool_calls: Optional[List] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        return {"role": self.role, "content": self.content,
                "timestamp": self.timestamp, "tool_calls": self.tool_calls}

    @classmethod
    def from_dict(cls, data):
        return cls(role=data["role"], content=data["content"],
                   timestamp=data.get("timestamp"), tool_calls=data.get("tool_calls"))

class ConversationMemory:

    def __init__(self, redis_url="redis://localhost:6379", ttl=3600, max_history=20):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.ttl = ttl # 1 hour
        self.max_history = max_history
        try:
            self.redis.ping()
            print("✅ Redis 连接成功")
        except redis.ConnectionError:
            print("⚠️ Redis 连接失败，将使用内存缓存（重启后丢失）")
            self._use_memory_fallback()

    def _use_memory_fallback(self):
        self._memory_cache = {}
        self.redis = None

    def _get_key(self, session_id: str) -> str:
        return f"conversation:{session_id}"

    def add_message(self, session_id: str, role: str, content: str, tool_calls: List = None):
        if tool_calls:
            if callable(tool_calls):
                try:
                    tool_calls = tool_calls()
                except:
                    tool_calls = str(tool_calls)
            if not isinstance(tool_calls, (list, str, int, float, bool, type(None))):
                try:
                    if hasattr(tool_calls, '__dict__'):
                        tool_calls = tool_calls.__dict__
                    else:
                        tool_calls = str(tool_calls)
                except:
                    tool_calls = str(tool_calls)
            try:
                json.dumps(tool_calls)
            except (TypeError, json.JSONEncodeError):
                tool_calls = str(tool_calls)

        message = Message(role=role, content=content, tool_calls=tool_calls)
        if self.redis:
        #key = f"conversation:{session_id}"
            key = self._get_key(session_id)
        #message = {"role": role, "content": content, timestamp: datetime.now().isoformat()}
        #self.redis.rpush(key, json.dumps(message))
            try:
                self.redis.rpush(key, json.dumps(message.to_dict(), default=str))
            except TypeError as e:
                print(f"⚠️ 序列化失败: {e}")
                simple_message = {"role": role, "content": content, "timestamp": message.timestamp}
                self.redis.rpush(key, json.dumps(simple_message, default=str))

        message = Message(role=role, content=content, tool_calls=tool_calls)
        if self.redis:
        #key = f"conversation:{session_id}"
            key = self._get_key(session_id)
        #message = {"role": role, "content": content, timestamp: datetime.now().isoformat()}
        #self.redis.rpush(key, json.dumps(message))
            try:
                self.redis.rpush(key, json.dumps(message.to_dict(), default=str))
            except TypeError as e:
                print(f"⚠️ 序列化失败: {e}")
                simple_message = {"role": role, "content": content, "timestamp": message.timestamp}
                self.redis.rpush(key, json.dumps(simple_message, default=str))
            self.redis.expire(key, self.ttl)
            length = self.redis.llen(key)
            if length > self.max_history:
                self.redis.lpop(key)
        else:
            if session_id not in self._memory_cache:
                self._memory_cache[session_id] = []
            self._memory_cache[session_id].append(message)
            if len(self._memory_cache[session_id]) > self.max_history:
                self._memory_cache[session_id].pop(0)

    def get_history(self, session_id: str, limit: int = None) -> List[Dict]:
        if limit is None:
            limit = self.max_history
        if self.redis:
        #key = f"conversation:{session_id}"
            key = self._get_key(session_id)
            messages = self.redis.lrange(key, -limit, -1)
            return [json.loads(m) for m in messages]
        else:
            messages = self._memory_cache.get(session_id, [])
            return [m.to_dict() for m in messages[-limit:]]

    def get_formatted_history(self, session_id: str, limit: int = 10) -> List[tuple]:
        history = self.get_history(session_id, limit)
        formatted = []
        for msg in history:
            if msg["role"] in ["user", "assistant"]:
                formatted.append((msg["role"], msg["content"]))
        return formatted

    def clear_session(self, session_id: str):
        if self.redis:
            self.redis.delete(self._get_key(session_id))
        else:
            if session_id in self._memory_cache:
                del self._memory_cache[session_id]

    def get_session_info(self, session_id: str) -> Dict:
        history = self.get_history(session_id)
        return {"session_id": session_id, "message_count": len(history),
                "expires_in": self.redis.ttl(self._get_key(session_id)) if self.redis else None}

    def clear(self, session_id: str):
        slef.redis.delete(f"conversation:{session_id}")

_memory_instance = None

def get_memory():
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ConversationMemory()
    return _memory_instance
