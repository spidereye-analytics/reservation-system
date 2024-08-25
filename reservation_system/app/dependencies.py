import os
from redis import Redis

# Get Redis URL from environment or default to 'redis://localhost:6379/0'
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Initialize the Redis client with the provided URL
redis_client = Redis.from_url(REDIS_URL)

def get_redis_client():
    return redis_client
