import json,time
from app.core.config import get_settings
class MemoryCache:
    def __init__(self):self.data={}
    async def get(self,key):
        item=self.data.get(key)
        if not item or item[0]<time.time():self.data.pop(key,None);return None
        return item[1]
    async def set(self,key,value,ttl):self.data[key]=(time.time()+ttl,value)
class RedisCache:
    def __init__(self,url):
        from redis.asyncio import from_url
        self.client=from_url(url,decode_responses=True)
    async def get(self,key):
        raw=await self.client.get(key);return json.loads(raw) if raw else None
    async def set(self,key,value,ttl):await self.client.set(key,json.dumps(value),ex=ttl)
_cache=None
def get_cache():
    global _cache
    if _cache is None:
        url=get_settings().redis_url;_cache=RedisCache(url) if url else MemoryCache()
    return _cache
