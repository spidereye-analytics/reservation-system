# cache_checker.py
import json
import time
from fastapi_sqlalchemy import db
from .models import User
from .utils import generate_time_slots
from .dependencies import get_redis_client
import logging

def acquire_lock(redis_client, lock_key, ttl=10):
    return redis_client.set(lock_key, "locked", nx=True, ex=ttl)

def release_lock(redis_client, lock_key):
    redis_client.delete(lock_key)

def compare_time_slots(correct_time_slots, cached_time_slots):
    discrepancies = []
    correct_set = {tuple(sorted(slot.items())) for slot in correct_time_slots}
    cached_set = {tuple(sorted(slot.items())) for slot in cached_time_slots}

    for item in correct_set - cached_set:
        discrepancies.append(f"Missing in cache: {dict(item)}")
        logging.info(f"Missing in cache: {dict(item)}")

    for item in cached_set - correct_set:
        discrepancies.append(f"Unexpected in cache: {dict(item)}")
        logging.info(f"Unexpected in cache: {dict(item)}")

    return discrepancies

def check_and_sync_cache():
    redis_client = get_redis_client()

    with db():
        providers = db.session.query(User).filter(User.role == 'provider').all()

        for provider in providers:
            cache_key = f"availability:provider:{provider.id}"
            lock_key = f"lock:{cache_key}"

            if acquire_lock(redis_client, lock_key):
                try:
                    cached_time_slots = redis_client.get(cache_key)

                    if cached_time_slots:
                        cached_time_slots = json.loads(cached_time_slots)
                    else:
                        cached_time_slots = []

                    # Generate the correct time slots from the database
                    correct_time_slots = generate_time_slots(
                        provider.general_schedule,
                        provider.exceptions,
                        provider.manual_appointment_slots
                    )

                    diff = compare_time_slots(correct_time_slots, cached_time_slots)

                    if diff:
                        print(f"Discrepancy found for provider {provider.id}:")
                        print(diff)
                        redis_client.set(cache_key, json.dumps(correct_time_slots), ex=3600)  # Cache for 1 hour
                        print(f"Cache updated for provider {provider.id}.")
                    else:
                        print(f"Cache is consistent for provider {provider.id}.")
                finally:
                    release_lock(redis_client, lock_key)
            else:
                print(f"Cache check skipped for provider {provider.id} because another process is running.")