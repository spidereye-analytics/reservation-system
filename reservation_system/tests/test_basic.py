import logging
import pytest
import requests
import random
import string
from datetime import datetime, timedelta, timezone
from dateutil.parser import parse

BASE_URL = "http://localhost:8000"

@pytest.fixture(scope="module")
def base_url():
    return BASE_URL

def generate_random_email(role):
    return f"test_{role}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@example.com"

def register_user(base_url, role):
    user_data = {
        "name": f"Test {role.capitalize()}",
        "email": generate_random_email(role),
        "password": "testpassword123",
        "role": role
    }
    response = requests.post(f"{base_url}/register", json=user_data)
    assert response.status_code == 200, f"{role.capitalize()} registration failed: {response.text}"
    return response.json()["id"], user_data["email"], user_data["password"]

def login_user(base_url, email, password):
    login_data = {
        "username": email,
        "password": password
    }
    response = requests.post(f"{base_url}/token", data=login_data)
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]

@pytest.fixture
def get_tokens(base_url):
    provider_id, provider_email, provider_password = register_user(base_url, "provider")
    patient_id, patient_email, patient_password = register_user(base_url, "patient")
    admin_id, admin_email, admin_password = register_user(base_url, "admin")

    provider_token = login_user(base_url, provider_email, provider_password)
    patient_token = login_user(base_url, patient_email, patient_password)
    admin_token = login_user(base_url, admin_email, admin_password)

    return provider_token, patient_token, admin_token, provider_id, patient_id, admin_id

def set_provider_availability(base_url, provider_id, provider_token, start_date, end_date, exceptions=None):
    availability_data = {
        "general_schedule": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "times": [
                {"days": "M-F", "start": "9am", "end": "5pm"},
            ]
        },
        "exceptions": exceptions or [],
        "manual_appointment_slots": []
    }
    response = requests.post(
        f"{base_url}/providers/{provider_id}/availability",
        json=availability_data,
        headers={"Authorization": f"Bearer {provider_token}"}
    )
    assert response.status_code == 200, f"Setting provider availability failed: {response.text}"

def get_available_slots(base_url, provider_id, token, start_date, end_date):
    response = requests.get(
        f"{base_url}/providers/{provider_id}/time-slots",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, f"Get available slots failed: {response.text}"
    return response.json()

def reserve_appointment(base_url, provider_id, start_time, token):
    reserve_data = {
        "provider_id": provider_id,
        "start_time": start_time
    }
    response = requests.post(
        f"{base_url}/appointments/reserve",
        json=reserve_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, f"Reserve appointment failed: {response.text}"
    return response.json()["slot_id"]

def confirm_appointment(base_url, slot_id, token):
    confirm_data = {"slot_id": slot_id}
    response = requests.post(
        f"{base_url}/appointments/confirm",
        json=confirm_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, f"Confirm appointment failed: {response.text}"

def cancel_appointment(base_url, slot_id, token):
    cancel_data = {"slot_id": slot_id}
    response = requests.post(
        f"{base_url}/appointments/cancel",
        json=cancel_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, f"Cancel appointment failed: {response.text}"
    return response.json()

def get_booked_appointments(base_url, provider_id, token, start_date, end_date):
    response = requests.get(
        f"{base_url}/providers/{provider_id}/booked-appointments",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, f"Get booked appointments failed: {response.text}"
    return response.json()

# Test cases

def test_user_registration(base_url):
    register_user(base_url, "provider")
    register_user(base_url, "patient")

def test_user_login(base_url):
    for role in ["provider", "patient"]:
        user_id, email, password = register_user(base_url, role)
        token = login_user(base_url, email, password)
        assert token, f"{role.capitalize()} login failed"

def test_provider_availability(base_url, get_tokens):
    provider_token, _, _, provider_id, _, _ = get_tokens
    start_date = datetime.now(timezone.utc).date() + timedelta(days=2)
    end_date = start_date + timedelta(days=30)

    set_provider_availability(base_url, provider_id, provider_token, start_date, end_date)

    slots = get_available_slots(base_url, provider_id, provider_token, start_date, start_date + timedelta(days=7))
    assert len(slots) > 0
    assert all(slot["status"] == "available" for slot in slots)

def test_patient_reserve_appointment(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, _, _ = get_tokens
    start_date = datetime.now(timezone.utc).date() + timedelta(days=2)
    end_date = start_date + timedelta(days=30)

    set_provider_availability(base_url, provider_id, provider_token, start_date, end_date)

    slots = get_available_slots(base_url, provider_id, patient_token, start_date, start_date + timedelta(days=1))
    assert len(slots) > 0

    slot_id = reserve_appointment(base_url, provider_id, slots[0]["start_time"], patient_token)
    assert slot_id

def test_24_hour_advance_booking_rule(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, _, _ = get_tokens
    tomorrow = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_date = tomorrow + timedelta(days=7)

    set_provider_availability(base_url, provider_id, provider_token, tomorrow.date(), end_date.date())

    # Try to book less than 24 hours in advance
    less_than_24h = datetime.now(timezone.utc) + timedelta(hours=23)
    with pytest.raises(AssertionError):
        reserve_appointment(base_url, provider_id, less_than_24h.isoformat(), patient_token)

    # Book more than 24 hours in advance
    more_than_24h = tomorrow + timedelta(days=1, hours=9)
    slot_id = reserve_appointment(base_url, provider_id, more_than_24h.isoformat(), patient_token)
    assert slot_id

    booked_appointments = get_booked_appointments(base_url, provider_id, provider_token, tomorrow.date(), end_date.date())
    assert any(appointment["id"] == slot_id for appointment in booked_appointments)

def test_get_providers(base_url, get_tokens):
    _, _, admin_token, _, _, _ = get_tokens

    response = requests.get(
        f"{base_url}/providers",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200, f"Get providers failed: {response.text}"
    providers = response.json()
    assert len(providers) > 0
    assert all(key in providers[0] for key in ["id", "name", "email"])

def test_patient_reserve_multiple_appointments(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, _, _ = get_tokens
    start_date = datetime.now(timezone.utc).date() + timedelta(days=2)
    end_date = start_date + timedelta(days=30)

    set_provider_availability(base_url, provider_id, provider_token, start_date, end_date)

    slots = get_available_slots(base_url, provider_id, patient_token, start_date, start_date + timedelta(days=1))
    assert len(slots) >= 2

    slot_id_1 = reserve_appointment(base_url, provider_id, slots[0]["start_time"], patient_token)
    slot_id_2 = reserve_appointment(base_url, provider_id, slots[1]["start_time"], patient_token)

    assert slot_id_1 and slot_id_2

def test_provider_availability_with_exceptions(base_url, get_tokens):
    provider_token, _, _, provider_id, _, _ = get_tokens
    start_date = datetime.now(timezone.utc).date() + timedelta(days=2)
    end_date = start_date + timedelta(days=30)
    exception_date = start_date + timedelta(days=7)

    exceptions = [
        {"date": exception_date.isoformat(), "times": [{"start": "1pm", "end": "2pm"}]}
    ]

    set_provider_availability(base_url, provider_id, provider_token, start_date, end_date, exceptions)

    slots = get_available_slots(base_url, provider_id, provider_token, start_date, end_date)
    exception_slots = [slot for slot in slots if slot["start_time"].startswith(exception_date.isoformat())]
    assert len(exception_slots) == 4  # Expect 4 slots (1 hour divided into 15-minute slots)

def test_get_provider_booked_appointments(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, _, _ = get_tokens
    start_date = datetime.now(timezone.utc).date() + timedelta(days=2)
    end_date = start_date + timedelta(days=30)

    set_provider_availability(base_url, provider_id, provider_token, start_date, end_date)

    slots = get_available_slots(base_url, provider_id, patient_token, start_date, start_date + timedelta(days=1))
    slot_id = reserve_appointment(base_url, provider_id, slots[0]["start_time"], patient_token)

    booked_appointments = get_booked_appointments(base_url, provider_id, provider_token, start_date, end_date)
    assert len(booked_appointments) > 0

    booked_appointment = next((appointment for appointment in booked_appointments if appointment["id"] == slot_id), None)
    assert booked_appointment is not None
    assert booked_appointment["provider_id"] == provider_id
    assert booked_appointment["status"] == "booked"
    assert booked_appointment["confirmed"] is True

def test_confirm_appointment(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, _, _ = get_tokens
    start_date = datetime.now(timezone.utc).date() + timedelta(days=2)
    end_date = start_date + timedelta(days=30)

    set_provider_availability(base_url, provider_id, provider_token, start_date, end_date)

    slots = get_available_slots(base_url, provider_id, patient_token, start_date, start_date + timedelta(days=1))
    slot_id = reserve_appointment(base_url, provider_id, slots[0]["start_time"], patient_token)

    confirm_appointment(base_url, slot_id, patient_token)

    booked_appointments = get_booked_appointments(base_url, provider_id, provider_token, start_date, end_date)
    confirmed_appointment = next((appointment for appointment in booked_appointments if appointment["id"] == slot_id), None)
    assert confirmed_appointment is not None
    assert confirmed_appointment["confirmed"] is True

def test_cancel_appointment(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, _, _ = get_tokens
    start_date = datetime.now(timezone.utc).date() + timedelta(days=2)
    end_date = start_date + timedelta(days=30)

    set_provider_availability(base_url, provider_id, provider_token, start_date, end_date)

    slots = get_available_slots(base_url, provider_id, patient_token, start_date, start_date + timedelta(days=1))
    slot_id = reserve_appointment(base_url, provider_id, slots[0]["start_time"], patient_token)
    confirm_appointment(base_url, slot_id, patient_token)

    cancel_result = cancel_appointment(base_url, slot_id, patient_token)
    assert cancel_result["message"] == "Appointment cancelled successfully"
    assert cancel_result["slot_id"] == slot_id

    booked_appointments = get_booked_appointments(base_url, provider_id, provider_token, start_date, end_date)
    cancelled_appointment = next((appointment for appointment in booked_appointments if appointment["id"] == slot_id), None)
    assert cancelled_appointment is None

    available_slots = get_available_slots(base_url, provider_id, patient_token, start_date, start_date + timedelta(days=1))
    assert any(slot["id"] == slot_id for slot in available_slots)