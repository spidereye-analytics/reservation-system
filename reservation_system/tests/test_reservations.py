import requests

def test_availability(base_url):
    # General schedule with exceptions and manual appointment slots
    response = requests.post(f"{base_url}/providers/1/availability", json={
        "general_schedule": {
            "start_date": "2024-08-01",
            "end_date": "2024-08-31",
            "times": [
                {"days": "M-W", "start": "8am", "end": "4pm"},
                {"days": "Th", "start": "2pm", "end": "4pm"}
            ]
        },
        "exceptions": [
            {"date": "2024-08-15", "times": [{"start": "10:00", "end": "12:00"}]},
            {"date": "2024-08-16", "times": []}  # "Off" on this date
        ],
        "manual_appointment_slots": [
            {"date": "2024-08-17", "times": [{"start": "9am", "end": "11am"}, {"start": "1pm", "end": "3pm"}]}
        ]
    })
    assert response.status_code == 200
    assert response.json() == {"message": "Availability set"}

    # Add a conflicting reservation
    response = requests.post(f"{base_url}/appointments/reserve", json={
        'provider_id': 1,
        'start_time': '2024-08-15T10:00:00'
    })
    assert response.status_code == 200
    assert response.json() == {"message": "Appointment reserved"}

    # Update the schedule to conflict with the existing reservation
    response = requests.post(f"{base_url}/providers/1/availability", json={
        "general_schedule": {
            "start_date": "2024-08-01",
            "end_date": "2024-08-31",
            "times": [
                {"days": "M-W", "start": "8am", "end": "4pm"},
                {"days": "Th", "start": "3pm", "end": "5pm"}  # Changing the time to 3pm-5pm on Thursday
            ]
        }
    })
    assert response.status_code == 200
    assert response.json() == {"message": "Availability set and conflicting appointments canceled"}
