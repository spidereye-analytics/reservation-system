import os
import logging

from fastapi import APIRouter, HTTPException, Body, Query
from fastapi_sqlalchemy import db
from .models import Provider, AppointmentSlot
from .utils import generate_time_slots
from .dependencies import get_redis_client
from datetime import datetime, timedelta
import json

router = APIRouter()
CACHE_EXPIRY_SECONDS = int(os.getenv('CACHE_EXPIRY_SECONDS', 10))

# Set up logging
logging.basicConfig(level=logging.INFO)

@router.get("/providers")
def get_providers():
    providers = db.session.query(Provider).all()
    return providers


@router.post("/providers")
def create_provider(provider: dict = Body(...)):
    name = provider.get("name")
    email = provider.get("email")

    if not name or not email:
        raise HTTPException(status_code=400, detail="Name and email are required")

    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Invalid email format")

    try:
        new_provider = Provider(name=name, email=email)
        db.session.add(new_provider)
        db.session.commit()
        return new_provider
    except Exception as e:
        db.session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/providers/{provider_id}/availability')
def set_provider_availability(provider_id: int, availability: dict = Body(...)):
    provider = db.session.query(Provider).filter_by(id=provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    try:
        general_schedule = availability.get('general_schedule', {})
        exceptions = availability.get('exceptions', [])
        manual_appointment_slots = availability.get('manual_appointment_slots', [])

        # Generate new time slots based on the availability details
        new_time_slots = generate_time_slots(general_schedule, exceptions, manual_appointment_slots)

        # Save generated time slots to the database
        for slot in new_time_slots:
            start_time = datetime.fromisoformat(slot['start'])
            end_time = datetime.fromisoformat(slot['end'])

            # Check if the slot already exists
            existing_slot = db.session.query(AppointmentSlot).filter_by(
                provider_id=provider_id,
                start_time=start_time,
                end_time=end_time
            ).first()

            if not existing_slot:
                new_slot = AppointmentSlot(
                    provider_id=provider_id,
                    start_time=start_time,
                    end_time=end_time,
                    status="available"
                )
                db.session.add(new_slot)

        db.session.commit()

        return {"message": "Availability set successfully"}
    except Exception as e:
        db.session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/providers/{provider_id}/time-slots')
def get_available_time_slots(provider_id: int, start_date: datetime = Query(None), end_date: datetime = Query(None)):
    provider = db.session.query(Provider).filter_by(id=provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if not start_date:
        start_date = datetime.utcnow().date()
    else:
        start_date = start_date.date()

    if not end_date:
        end_date = start_date + timedelta(weeks=1)
    else:
        end_date = end_date.date()

    redis_client = get_redis_client()
    available_slots = []

    current_date = start_date
    while current_date <= end_date:
        cache_key = f"provider:{provider_id}:timeslots:{current_date.isoformat()}"

        # Initialize daily_slots_serializable outside the if-else block to ensure it's always defined
        daily_slots_serializable = None

        # Check Redis cache for the entire day's slots
        cached_time_slots = redis_client.get(cache_key)
        if cached_time_slots:
            logging.info(f"Retrieved time slots for {current_date} from Redis cache.")
            daily_slots_serializable = json.loads(cached_time_slots)
        else:
            logging.info(f"Time slots for {current_date} not found in Redis cache. Fetching from PostgreSQL.")
            next_day = current_date + timedelta(days=1)
            daily_slots = db.session.query(AppointmentSlot).filter(
                AppointmentSlot.provider_id == provider_id,
                AppointmentSlot.start_time >= current_date,
                AppointmentSlot.start_time < next_day,
                AppointmentSlot.status == 'available'
            ).all()

            daily_slots_serializable = [
                {
                    "id": slot.id,
                    "provider_id": slot.provider_id,
                    "start_time": slot.start_time.isoformat(),
                    "end_time": slot.end_time.isoformat(),
                    "status": slot.status,
                    "client_id": slot.client_id
                }
                for slot in daily_slots
            ]
            redis_client.setex(cache_key, CACHE_EXPIRY_SECONDS, json.dumps(daily_slots_serializable))

        # Filter the slots within the desired date range
        for slot in daily_slots_serializable:
            slot_start_time = datetime.fromisoformat(slot['start_time'])
            if start_date <= slot_start_time.date() <= end_date:
                available_slots.append(slot)

        current_date += timedelta(days=1)

    return available_slots
