import json
import time
from fastapi_sqlalchemy import db
from .models import Provider
from .utils import generate_time_slots
from .dependencies import get_redis_client
from deepdiff import DeepDiff
import logging


def acquire_lock(redis_client, lock_key, ttl=10):
    """
    Attempt to acquire a lock with a specified time-to-live (TTL) in seconds.
    """
    return redis_client.set(lock_key, "locked", nx=True, ex=ttl)


def release_lock(redis_client, lock_key):
    """
    Release a lock by deleting the lock key.
    """
    redis_client.delete(lock_key)


def compare_time_slots(correct_time_slots, cached_time_slots):
    """
    Compare the correct time slots with the cached ones and log every key that is inconsistent.
    """
    discrepancies = []

    # Convert lists of dictionaries to sets of tuples for easier comparison
    correct_set = {tuple(sorted(slot.items())) for slot in correct_time_slots}
    cached_set = {tuple(sorted(slot.items())) for slot in cached_time_slots}

    # Find items in the correct slots that are missing in the cache
    for item in correct_set - cached_set:
        discrepancies.append(f"Missing in cache: {dict(item)}")
        logging.info(f"Missing in cache: {dict(item)}")

    # Find items in the cache that shouldn't be there (i.e., not in correct slots)
    for item in cached_set - correct_set:
        discrepancies.append(f"Unexpected in cache: {dict(item)}")
        logging.info(f"Unexpected in cache: {dict(item)}")

    return discrepancies


def check_and_sync_cache():
    redis_client = get_redis_client()

    with db():
        providers = db.session.query(Provider).all()

        for provider in providers:
            cache_key = f"availability:provider:{provider.id}"
            lock_key = f"lock:{cache_key}"

            # Attempt to acquire the lock
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

                    # Compare the correct time slots with the cached ones
                    diff = compare_time_slots(correct_time_slots, cached_time_slots)

                    if diff:
                        print(f"Discrepancy found for provider {provider.id}:")
                        print(diff)
                        redis_client.set(cache_key, json.dumps(correct_time_slots), ex=3600)  # Cache for 1 hour
                        print(f"Cache updated for provider {provider.id}.")
                    else:
                        print(f"Cache is consistent for provider {provider.id}.")
                finally:
                    # Release the lock
                    release_lock(redis_client, lock_key)
            else:
                print(f"Cache check skipped for provider {provider.id} because another process is running.")
