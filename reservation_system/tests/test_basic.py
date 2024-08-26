import pytest
import requests
import random
import string
from datetime import datetime, timedelta, timezone

BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="module")
def base_url():
    return BASE_URL


@pytest.fixture
def get_tokens():
    def create_user(role):
        email = f"test_{role}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@example.com"
        password = "testpassword123"

        # Register user
        register_response = requests.post(f"{BASE_URL}/register", json={
            "name": f"Test {role.capitalize()}",
            "email": email,
            "password": password,
            "role": role
        })
        assert register_response.status_code == 200, f"{role.capitalize()} registration failed: {register_response.text}"
        user_id = register_response.json()["id"]

        # Login
        login_response = requests.post(f"{BASE_URL}/token", data={
            "username": email,
            "password": password
        })
        assert login_response.status_code == 200, f"{role.capitalize()} login failed: {login_response.text}"
        token = login_response.json()["access_token"]

        return token, user_id

    provider_token, provider_id = create_user("provider")
    patient_token, patient_id = create_user("patient")
    # Admin token and ID will only be used for test_get_providers
    admin_token, admin_id = create_user("admin")

    return provider_token, patient_token, admin_token, provider_id, patient_id, admin_id


def test_user_registration(base_url):
    def generate_random_email(role):
        return f"test_{role}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@example.com"

    def register_user(role):
        user_data = {
            "name": f"Test {role.capitalize()}",
            "email": generate_random_email(role),
            "password": "testpassword123",
            "role": role
        }
        response = requests.post(f"{base_url}/register", json=user_data)
        assert response.status_code == 200, f"{role.capitalize()} registration failed: {response.text}"
        assert "id" in response.json(), f"User ID not found in response: {response.text}"

    register_user("provider")
    register_user("patient")


def test_user_login(base_url):
    def register_and_login(role):
        email = f"test_{role}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@example.com"
        password = "testpassword123"

        # Register
        register_data = {
            "name": f"Test {role.capitalize()}",
            "email": email,
            "password": password,
            "role": role
        }
        register_response = requests.post(f"{base_url}/register", json=register_data)
        assert register_response.status_code == 200, f"{role.capitalize()} registration failed: {register_response.text}"

        # Login
        login_data = {
            "username": email,
            "password": password
        }
        login_response = requests.post(f"{base_url}/token", data=login_data)
        assert login_response.status_code == 200, f"{role.capitalize()} login failed: {login_response.text}"
        assert "access_token" in login_response.json()

    register_and_login("provider")
    register_and_login("patient")


def test_provider_availability(base_url, get_tokens):
    provider_token, _, _, provider_id, _, _ = get_tokens

    # Set availability
    start_date = datetime.now(timezone.utc).date()
    end_date = start_date + timedelta(days=30)
    availability_data = {
        "general_schedule": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "times": [
                {"days": "M-F", "start": "9am", "end": "5pm"},
            ]
        },
        "exceptions": [],
        "manual_appointment_slots": []
    }
    response = requests.post(
        f"{base_url}/providers/{provider_id}/availability",
        json=availability_data,
        headers={"Authorization": f"Bearer {provider_token}"}
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Availability set successfully"}

    # Get availability
    start_date = datetime.now(timezone.utc).date()
    end_date = start_date + timedelta(days=7)
    response = requests.get(
        f"{base_url}/providers/{provider_id}/time-slots",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        headers={"Authorization": f"Bearer {provider_token}"}
    )
    assert response.status_code == 200
    slots = response.json()
    assert len(slots) > 0
    assert all(slot["status"] == "available" for slot in slots)


def test_patient_reserve_appointment(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, _, _ = get_tokens

    # Set provider availability
    start_date = datetime.now(timezone.utc).date()
    end_date = start_date + timedelta(days=30)
    availability_data = {
        "general_schedule": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "times": [
                {"days": "M-F", "start": "9am", "end": "5pm"},
            ]
        },
        "exceptions": [],
        "manual_appointment_slots": []
    }
    provider_response = requests.post(
        f"{base_url}/providers/{provider_id}/availability",
        json=availability_data,
        headers={"Authorization": f"Bearer {provider_token}"}
    )
    assert provider_response.status_code == 200

    # Get available slots
    slots_response = requests.get(
        f"{base_url}/providers/{provider_id}/time-slots",
        params={"start_date": (start_date + timedelta(days=1)).isoformat(),
                "end_date": (start_date + timedelta(days=2)).isoformat()},
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    assert slots_response.status_code == 200
    slots = slots_response.json()
    assert len(slots) > 0

    # Reserve an appointment
    slot_to_reserve = slots[0]
    reserve_data = {
        "provider_id": provider_id,
        "start_time": slot_to_reserve["start_time"]
    }
    reserve_response = requests.post(
        f"{base_url}/appointments/reserve",
        json=reserve_data,
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    assert reserve_response.status_code == 200
    assert "slot_id" in reserve_response.json()


def test_get_provider_booked_appointments(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, _, _ = get_tokens

    # Set provider availability
    start_date = datetime.now(timezone.utc).date()
    end_date = start_date + timedelta(days=30)
    availability_data = {
        "general_schedule": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "times": [
                {"days": "M-F", "start": "9am", "end": "5pm"},
            ]
        },
        "exceptions": [],
        "manual_appointment_slots": []
    }
    requests.post(
        f"{base_url}/providers/{provider_id}/availability",
        json=availability_data,
        headers={"Authorization": f"Bearer {provider_token}"}
    )

    # Book an appointment
    slots_response = requests.get(
        f"{base_url}/providers/{provider_id}/time-slots",
        params={"start_date": (start_date + timedelta(days=1)).isoformat(),
                "end_date": (start_date + timedelta(days=2)).isoformat()},
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    slots = slots_response.json()
    slot_to_reserve = slots[0]

    reserve_response = requests.post(
        f"{base_url}/appointments/reserve",
        json={"provider_id": provider_id, "start_time": slot_to_reserve["start_time"]},
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    assert reserve_response.status_code == 200

    # Get booked appointments
    booked_response = requests.get(
        f"{base_url}/providers/{provider_id}/booked-appointments",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        headers={"Authorization": f"Bearer {provider_token}"}
    )
    assert booked_response.status_code == 200
    booked_appointments = booked_response.json()
    assert len(booked_appointments) > 0
    assert booked_appointments[0]["start_time"] == slot_to_reserve["start_time"]


def test_get_providers(base_url, get_tokens):
    _, _, admin_token, _, _, _ = get_tokens

    # Get the list of providers
    response = requests.get(
        f"{base_url}/providers",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200, f"Get providers failed: {response.text}"
    providers = response.json()
    assert len(providers) > 0
    assert "id" in providers[0] and "name" in providers[0] and "email" in providers[0]


def test_patient_reserve_multiple_appointments(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, _, _ = get_tokens

    # Set provider availability
    start_date = datetime.now(timezone.utc).date()
    end_date = start_date + timedelta(days=30)
    availability_data = {
        "general_schedule": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "times": [
                {"days": "M-F", "start": "9am", "end": "5pm"},
            ]
        },
        "exceptions": [],
        "manual_appointment_slots": []
    }
    requests.post(
        f"{base_url}/providers/{provider_id}/availability",
        json=availability_data,
        headers={"Authorization": f"Bearer {provider_token}"}
    )

    # Get available slots
    slots_response = requests.get(
        f"{base_url}/providers/{provider_id}/time-slots",
        params={"start_date": (start_date + timedelta(days=1)).isoformat(),
                "end_date": (start_date + timedelta(days=2)).isoformat()},
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    slots = slots_response.json()
    assert len(slots) >= 2

    # Reserve two appointments
    slot_to_reserve_1 = slots[0]
    slot_to_reserve_2 = slots[1]

    reserve_response_1 = requests.post(
        f"{base_url}/appointments/reserve",
        json={"provider_id": provider_id, "start_time": slot_to_reserve_1["start_time"]},
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    assert reserve_response_1.status_code == 200

    reserve_response_2 = requests.post(
        f"{base_url}/appointments/reserve",
        json={"provider_id": provider_id, "start_time": slot_to_reserve_2["start_time"]},
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    assert reserve_response_2.status_code == 200


def test_provider_availability_with_exceptions(base_url, get_tokens):
    provider_token, _, _, provider_id, _, _ = get_tokens

    # Set availability with exceptions
    start_date = datetime.now(timezone.utc).date()
    end_date = start_date + timedelta(days=30)
    availability_data = {
        "general_schedule": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "times": [
                {"days": "M-F", "start": "9am", "end": "5pm"},
            ]
        },
        "exceptions": [
            {"date": (start_date + timedelta(days=7)).isoformat(), "times": [{"start": "1pm", "end": "2pm"}]}
        ],
        "manual_appointment_slots": []
    }
    response = requests.post(
        f"{base_url}/providers/{provider_id}/availability",
        json=availability_data,
        headers={"Authorization": f"Bearer {provider_token}"}
    )
    assert response.status_code == 200, f"Set availability with exceptions failed: {response.text}"

    # Get availability to check exceptions
    response = requests.get(
        f"{base_url}/providers/{provider_id}/time-slots",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        headers={"Authorization": f"Bearer {provider_token}"}
    )
    assert response.status_code == 200
    slots = response.json()

    # Ensure all slots are captured and counted correctly
    exception_date = (start_date + timedelta(days=7)).isoformat()
    exception_slots = [slot for slot in slots if slot["start_time"].startswith(exception_date)]
    assert len(exception_slots) == 4  # Expect 4 slots


def test_confirm_appointment(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, _, _ = get_tokens

    # Set provider availability and reserve an appointment
    start_date = datetime.now(timezone.utc).date()
    end_date = start_date + timedelta(days=30)
    availability_data = {
        "general_schedule": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "times": [
                {"days": "M-F", "start": "9am", "end": "5pm"},
            ]
        },
        "exceptions": [],
        "manual_appointment_slots": []
    }
    requests.post(
        f"{base_url}/providers/{provider_id}/availability",
        json=availability_data,
        headers={"Authorization": f"Bearer {provider_token}"}
    )

    slots_response = requests.get(
        f"{base_url}/providers/{provider_id}/time-slots",
        params={"start_date": (start_date + timedelta(days=1)).isoformat(),
                "end_date": (start_date + timedelta(days=2)).isoformat()},
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    slots = slots_response.json()
    assert len(slots) > 0, "No available slots found to reserve"

    slot_to_reserve = slots[0]

    reserve_response = requests.post(
        f"{base_url}/appointments/reserve",
        json={"provider_id": provider_id, "start_time": slot_to_reserve["start_time"]},
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    assert reserve_response.status_code == 200, f"Reserve appointment failed: {reserve_response.text}"
    slot_id = reserve_response.json()["slot_id"]

    # Confirm the appointment
    confirm_data = {"slot_id": slot_id}
    confirm_response = requests.post(
        f"{base_url}/appointments/confirm",
        json=confirm_data,
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    assert confirm_response.status_code == 200, f"Confirm appointment failed: {confirm_response.text}"
    assert confirm_response.json() == {"message": "Reservation confirmed successfully"}

    # Verify the slot is now confirmed
    booked_response = requests.get(
        f"{base_url}/providers/{provider_id}/booked-appointments",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        headers={"Authorization": f"Bearer {provider_token}"}
    )
    assert booked_response.status_code == 200, f"Get booked appointments failed: {booked_response.text}"
    booked_appointments = booked_response.json()
    confirmed_appointment = next((appointment for appointment in booked_appointments if appointment["id"] == slot_id),
                                 None)
    assert confirmed_appointment is not None, "Confirmed appointment not found"
    assert confirmed_appointment["confirmed"] is True, "Appointment was not marked as confirmed"


def test_cancel_appointment(base_url, get_tokens):
    provider_token, patient_token, _, provider_id, patient_id, _ = get_tokens

    # Set provider availability and book an appointment
    start_date = datetime.now(timezone.utc).date()
    end_date = start_date + timedelta(days=30)
    availability_data = {
        "general_schedule": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "times": [
                {"days": "M-F", "start": "9am", "end": "5pm"},
            ]
        },
        "exceptions": [],
        "manual_appointment_slots": []
    }
    requests.post(
        f"{base_url}/providers/{provider_id}/availability",
        json=availability_data,
        headers={"Authorization": f"Bearer {provider_token}"}
    )

    slots_response = requests.get(
        f"{base_url}/providers/{provider_id}/time-slots",
        params={"start_date": (start_date + timedelta(days=1)).isoformat(),
                "end_date": (start_date + timedelta(days=2)).isoformat()},
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    slots = slots_response.json()
    assert len(slots) > 0, "No available slots found to reserve"

    slot_to_reserve = slots[0]

    reserve_response = requests.post(
        f"{base_url}/appointments/reserve",
        json={"provider_id": provider_id, "start_time": slot_to_reserve["start_time"]},
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    assert reserve_response.status_code == 200, f"Reserve appointment failed: {reserve_response.text}"
    slot_id = reserve_response.json()["slot_id"]

    # Cancel the appointment
    cancel_data = {"slot_id": slot_id}
    cancel_response = requests.post(
        f"{base_url}/appointments/cancel",
        json=cancel_data,
        headers={"Authorization": f"Bearer {patient_token}"}
    )
    assert cancel_response.status_code == 200, f"Cancel appointment failed: {cancel_response.text}"
    resp = cancel_response.json()
    assert  resp["message"] == "Appointment cancelled successfully"
    assert slot_id == resp["slot_id"]
