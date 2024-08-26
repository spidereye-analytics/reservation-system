from fastapi import APIRouter, HTTPException, Body, Query, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from .models import AppointmentSlot, User
from .utils import generate_time_slots
from .dependencies import get_redis_client, get_db, UserRole
from .auth import authenticate_user, create_access_token, get_current_user, get_password_hash, role_required
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import os
import json
import logging

router = APIRouter()


class UserRegistration(BaseModel):
    name: str
    email: str
    password: str
    role: str


class ReserveAppointmentRequest(BaseModel):
    provider_id: int
    start_time: str


class ConfirmReservationRequest(BaseModel):
    slot_id: int


class CancelAppointmentRequest(BaseModel):
    slot_id: int



@router.post("/register")
async def register_user(
        user: UserRegistration = Body(None),
        name: str = Query(None),
        email: str = Query(None),
        password: str = Query(None),
        role: str = Query(None),
        db: Session = Depends(get_db)
):
    name = user.name if user else name
    email = user.email if user else email
    password = user.password if user else password
    role = user.role if user else role

    if not all([name, email, password, role]):
        raise HTTPException(status_code=400, detail="All fields are required")

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    if role not in [UserRole.PROVIDER.value, UserRole.PATIENT.value, UserRole.ADMIN.value]:
        raise HTTPException(status_code=400, detail="Invalid role")

    hashed_password = get_password_hash(password)
    new_user = User(name=name, email=email, hashed_password=hashed_password, role=role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User registered successfully", "id": new_user.id}


@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30)))
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/reset-password")
def reset_password(email: str, new_password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed_password = get_password_hash(new_password)
    user.hashed_password = hashed_password
    db.commit()
    return {"message": "Password reset successfully"}


@router.get("/providers")
@role_required([UserRole.ADMIN.value])
async def get_providers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logging.info(f"get_providers called by user: {current_user.email}")
    providers = db.query(User).filter(User.role == UserRole.PROVIDER.value).all()
    return [{"id": provider.id, "name": provider.name, "email": provider.email} for provider in providers]


@router.post('/providers/{provider_id}/availability')
@role_required([UserRole.PROVIDER.value])
async def set_provider_availability(
        provider_id: int,
        availability: dict = Body(...),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    logging.info(f"Setting availability for provider {provider_id}")
    if current_user.id != provider_id:
        raise HTTPException(status_code=403, detail="Not authorized to set availability for this provider")

    provider = db.query(User).filter_by(id=provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    try:
        general_schedule = availability.get('general_schedule', {})
        exceptions = availability.get('exceptions', [])
        manual_appointment_slots = availability.get('manual_appointment_slots', [])

        new_time_slots = generate_time_slots(general_schedule, exceptions, manual_appointment_slots)

        for slot in new_time_slots:
            start_time = datetime.fromisoformat(slot['start']).replace(tzinfo=timezone.utc)
            end_time = datetime.fromisoformat(slot['end']).replace(tzinfo=timezone.utc)

            # Ensure that all appointments are in the future
            if start_time <= datetime.now(timezone.utc):
                continue

            existing_slot = db.query(AppointmentSlot).filter_by(
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
                db.add(new_slot)

        db.commit()
        logging.info(f"Availability set successfully for provider {provider_id}")
        return {"message": "Availability set successfully"}
    except Exception as e:
        db.rollback()
        logging.error(f"Error setting availability for provider {provider_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/providers/{provider_id}/time-slots')
def get_available_time_slots(
        provider_id: int,
        start_date: datetime = Query(None),
        end_date: datetime = Query(None),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    provider = db.query(User).filter_by(id=provider_id, role='provider').first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if not start_date:
        start_date = datetime.now(timezone.utc).date()
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

        daily_slots_serializable = None
        cached_time_slots = redis_client.get(cache_key)
        if cached_time_slots:
            logging.info(f"Retrieved from Redis: {cache_key}")
            daily_slots_serializable = json.loads(cached_time_slots)
        else:
            logging.info(f"Retrieved from PostgreSQL: {cache_key}")
            next_day = current_date + timedelta(days=1)
            daily_slots = db.query(AppointmentSlot).filter(
                AppointmentSlot.provider_id == provider_id,
                AppointmentSlot.start_time >= current_date,
                AppointmentSlot.start_time < next_day
            ).all()

            daily_slots_serializable = [
                {
                    "id": slot.id,
                    "provider_id": slot.provider_id,
                    "start_time": slot.start_time.isoformat(),
                    "end_time": slot.end_time.isoformat(),
                    "status": slot.status,
                    "client_id": slot.client_id if current_user.role == UserRole.PROVIDER.value and current_user.id == provider_id else None,
                    "reserved_by": slot.reserved_by if current_user.role == UserRole.PROVIDER.value and current_user.id == provider_id else None,
                    "reserved_until": slot.reserved_until.isoformat() if (
                            slot.reserved_until and current_user.role == UserRole.PROVIDER.value and current_user.id == provider_id) else None,
                    "confirmed": slot.confirmed if current_user.role == UserRole.PROVIDER.value and current_user.id == provider_id else None
                }
                for slot in daily_slots
            ]
            redis_client.setex(cache_key, int(os.getenv('CACHE_EXPIRY_SECONDS', 3600)),
                               json.dumps(daily_slots_serializable))

        for slot in daily_slots_serializable:
            slot_start_time = datetime.fromisoformat(slot['start_time'])
            if start_date <= slot_start_time.date() <= end_date and slot['status'] == 'available':
                available_slots.append(slot)

        current_date += timedelta(days=1)

    return available_slots


@router.get('/providers/{provider_id}/booked-appointments')
def get_booked_appointments(
        provider_id: int,
        start_date: datetime = Query(None),
        end_date: datetime = Query(None),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    provider = db.query(User).filter_by(id=provider_id, role='provider').first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if not start_date:
        start_date = datetime.now(timezone.utc).date()
    else:
        start_date = start_date.date()

    if not end_date:
        end_date = start_date + timedelta(weeks=1)
    else:
        end_date = end_date.date()

    booked_slots = db.query(AppointmentSlot).filter(
        AppointmentSlot.provider_id == provider_id,
        AppointmentSlot.start_time >= start_date,
        AppointmentSlot.start_time <= end_date,
        AppointmentSlot.status != 'available'
    ).all()

    return [
        {
            "id": slot.id,
            "provider_id": slot.provider_id,
            "start_time": slot.start_time.isoformat(),
            "end_time": slot.end_time.isoformat(),
            "status": slot.status,
            "reserved_by": slot.reserved_by,
            "reserved_until": slot.reserved_until.isoformat() if slot.reserved_until else None,
            "confirmed": slot.confirmed,
            "client_id": slot.client_id
        }
        for slot in booked_slots
    ]


@router.post('/appointments/reserve')
@role_required([UserRole.PATIENT.value])
async def reserve_appointment(
        request: ReserveAppointmentRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    try:
        start_time_dt = datetime.fromisoformat(request.start_time)

        # Ensure start_time_dt is timezone-aware
        if start_time_dt.tzinfo is None:
            start_time_dt = start_time_dt.replace(tzinfo=timezone.utc)

        current_time = datetime.now(timezone.utc)
        if start_time_dt <= current_time + timedelta(hours=24):
            raise HTTPException(status_code=400, detail="Reservations must be made at least 24 hours in advance")

        slot = db.query(AppointmentSlot).filter_by(
            provider_id=request.provider_id,
            start_time=start_time_dt,
            status="available"
        ).first()

        if not slot:
            raise HTTPException(status_code=409, detail="Slot not available")

        # Check if the patient already has a reservation at this time
        existing_reservation = db.query(AppointmentSlot).filter_by(
            start_time=start_time_dt,
            reserved_by=current_user.id
        ).first()

        if existing_reservation:
            raise HTTPException(status_code=409, detail="You already have a reservation at this time")

        slot.status = "reserved"
        slot.reserved_by = current_user.id
        slot.reserved_until = current_time + timedelta(minutes=int(os.getenv('CONFIRMATION_GRACE_PERIOD_MINUTES', 30)))
        slot.confirmed = False

        db.commit()

        return {"message": "Appointment reserved successfully", "slot_id": slot.id}
    except Exception as e:
        db.rollback()
        logging.error(f"Error in reserve_appointment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An error occurred while reserving the appointment: {str(e)}")


@router.post('/appointments/confirm')
@role_required([UserRole.PATIENT.value])
async def confirm_reservation(
        request: ConfirmReservationRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    slot = db.query(AppointmentSlot).filter_by(id=request.slot_id).first()

    if not slot:
        raise HTTPException(status_code=404, detail="Appointment slot not found")

    if slot.reserved_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to confirm this appointment")

    # Convert reserved_until to timezone-aware datetime (assuming UTC)
    if slot.reserved_until and slot.reserved_until.tzinfo is None:
        slot.reserved_until = slot.reserved_until.replace(tzinfo=timezone.utc)

    if slot.reserved_until and slot.reserved_until < datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Reservation expired")

    slot.status = "confirmed"
    slot.reserved_by = None
    slot.reserved_until = None
    slot.confirmed = True
    slot.client_id = current_user.id

    db.commit()

    return {"message": "Reservation confirmed successfully"}


@router.post('/appointments/cancel')
@role_required([UserRole.PATIENT.value, UserRole.PROVIDER.value])
def cancel_appointment(
        request: CancelAppointmentRequest = Body(...),  # Ensure request is parsed from the body
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Fetch the appointment slot by ID
    slot = db.query(AppointmentSlot).filter_by(id=request.slot_id).first()

    if not slot:
        raise HTTPException(status_code=404, detail="Appointment slot not found")

    # # Check if the current user is authorized to cancel the appointment
    if slot.client_id != current_user.id and slot.provider_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this appointment")

    # If the current user is authorized, cancel the appointment
    slot.status = "available"
    slot.reserved_by = None
    slot.reserved_until = None
    slot.confirmed = False
    slot.client_id = None

    db.commit()

    return {"message": "Appointment cancelled successfully", "slot_id": slot.id}