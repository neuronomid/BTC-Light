import json
import redis
from typing import Any, Optional
from config.settings import REDIS_HOST, REDIS_PORT, REDIS_DB
from loguru import logger

class RedisClient:
    def __init__(self):
        self._client: Optional[redis.Redis] = None

    def connect(self):
        try:
            self._client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True
            )
            self._client.ping()
            logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            raise

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self.connect()
        return self._client

    def publish(self, channel: str, data: dict):
        self.client.publish(channel, json.dumps(data))

    def set_json(self, key: str, data: dict, ttl: Optional[int] = None):
        payload = json.dumps(data)
        if ttl:
            self.client.setex(key, ttl, payload)
        else:
            self.client.set(key, payload)

    def get_json(self, key: str) -> Optional[dict]:
        raw = self.client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def subscribe(self, channel: str):
        pubsub = self.client.pubsub()
        pubsub.subscribe(channel)
        return pubsub

redis_client = RedisClient()
