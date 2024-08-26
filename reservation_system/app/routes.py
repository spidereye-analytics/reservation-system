from fastapi import APIRouter, HTTPException, Body, Query, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from .models import AppointmentSlot, User
from .utils import generate_time_slots, get_available_slots, serialize_slot, get_or_create_user, validate_user_registration
from .dependencies import get_redis_client, get_db, UserRole
from .auth import authenticate_user, create_access_token, get_current_user, get_password_hash, role_required
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import os
import json
import logging

router = APIRouter()


# Pydantic models (move to a separate file, e.g., schemas.py)
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



# Route handlers
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

    validate_user_registration(name, email, password, role)
    new_user = get_or_create_user(db, email, name, password, role)
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
def reset_password(
        email: str,
        new_password: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Find the user whose password is being reset
    user_to_reset = db.query(User).filter(User.email == email).first()
    if not user_to_reset:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if the current user is authorized to reset the password
    if current_user.id != user_to_reset.id and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Not authorized to reset this user's password")

    # Reset the password
    user_to_reset.hashed_password = get_password_hash(new_password)
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
    if current_user.id != provider_id:
        raise HTTPException(status_code=403, detail="Not authorized to set availability for this provider")

    provider = db.query(User).filter_by(id=provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    try:
        new_time_slots = generate_time_slots(
            availability.get('general_schedule', {}),
            availability.get('exceptions', []),
            availability.get('manual_appointment_slots', [])
        )

        for slot in new_time_slots:
            start_time = datetime.fromisoformat(slot['start']).replace(tzinfo=timezone.utc)
            end_time = datetime.fromisoformat(slot['end']).replace(tzinfo=timezone.utc)

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

    start_date = start_date or datetime.now(timezone.utc)
    end_date = end_date or (start_date + timedelta(weeks=1))

    slots = get_available_slots(db, provider_id, start_date, end_date)
    return [slot for slot in slots if start_date <= datetime.fromisoformat(slot['start_time']) <= end_date]


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

    start_date = start_date or datetime.now(timezone.utc).date()
    end_date = end_date or (start_date + timedelta(weeks=1))

    booked_slots = db.query(AppointmentSlot).filter(
        AppointmentSlot.provider_id == provider_id,
        AppointmentSlot.start_time >= start_date,
        AppointmentSlot.start_time <= end_date,
        AppointmentSlot.status.in_(["booked", "reserved"])
    ).all()

    return [serialize_slot(slot, include_private_info=True) for slot in booked_slots]


@router.post('/appointments/reserve')
@role_required([UserRole.PATIENT.value])
async def reserve_appointment(
        request: ReserveAppointmentRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    start_time_dt = datetime.fromisoformat(request.start_time).replace(tzinfo=timezone.utc)
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

    existing_reservation = db.query(AppointmentSlot).filter_by(
        start_time=start_time_dt,
        reserved_by=current_user.id
    ).first()

    if existing_reservation:
        raise HTTPException(status_code=409, detail="You already have a reservation at this time")

    slot.status = "booked"
    slot.reserved_by = current_user.id
    slot.reserved_until = None
    slot.confirmed = True
    slot.client_id = current_user.id

    db.commit()

    return {"message": "Appointment booked successfully", "slot_id": slot.id}


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

    if slot.reserved_until and slot.reserved_until.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Reservation expired")

    slot.status = "booked"
    slot.reserved_by = None
    slot.reserved_until = None
    slot.confirmed = True
    slot.client_id = current_user.id

    db.commit()

    return {"message": "Reservation confirmed successfully"}


@router.post('/appointments/cancel')
def cancel_appointment(
        request: CancelAppointmentRequest = Body(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    slot = db.query(AppointmentSlot).filter_by(id=request.slot_id).first()

    if not slot:
        raise HTTPException(status_code=404, detail="Appointment slot not found")

    if slot.client_id != current_user.id and slot.provider_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this appointment")

    slot.status = "available"
    slot.reserved_by = None
    slot.reserved_until = None
    slot.confirmed = False
    slot.client_id = None

    db.commit()

    return {"message": "Appointment cancelled successfully", "slot_id": slot.id}
