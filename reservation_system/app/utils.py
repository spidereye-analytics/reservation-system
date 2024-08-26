import re
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session
from .models import AppointmentSlot


def parse_time_string(time_str):
    """Helper function to parse time strings in either 'HH:MM' or 'h:mma' formats."""
    try:
        return datetime.strptime(time_str, "%I%p").time()  # Handle '8am', '4pm', etc.
    except ValueError:
        return datetime.strptime(time_str, "%H:%M").time()  # Handle '10:00', '14:00', etc.


def round_up_to_next_15_minutes(dt):
    """Round a datetime object up to the next 15-minute interval."""
    if dt.minute % 15 == 0:
        return dt
    return dt + timedelta(minutes=(15 - dt.minute % 15))


def generate_time_slots(general_schedule, exceptions, manual_appointment_slots):
    """
    Generate time slots in 15-minute increments considering the general schedule, exceptions, and manual appointment slots.

    :param general_schedule: Weekly recurring time slots within a date range.
    :param exceptions: List of specific date exceptions.
    :param manual_appointment_slots: Specific manual appointment slots.
    :return: List of final available time slots in 15-minute increments.
    """
    day_map = {
        "M": 0,
        "T": 1,
        "W": 2,
        "Th": 3,
        "F": 4,
        "Sa": 5,
        "Su": 6
    }

    time_slots = []

    # Generate time slots based on the general schedule
    if general_schedule:
        start_date = datetime.strptime(general_schedule['start_date'], "%Y-%m-%d").date()
        end_date = datetime.strptime(general_schedule['end_date'], "%Y-%m-%d").date()

        for slot in general_schedule['times']:
            days = slot['days']
            start_time = parse_time_string(slot['start'])
            end_time = parse_time_string(slot['end'])

            if '-' in days:
                start_day, end_day = days.split('-')
                start_idx = day_map[start_day]
                end_idx = day_map[end_day] + 1
                day_indices = range(start_idx, end_idx)
            else:
                day_indices = [day_map[days]]

            current_date = start_date
            while current_date <= end_date:
                for day_idx in day_indices:
                    if current_date.weekday() == day_idx:
                        slot_start = datetime.combine(current_date, start_time)
                        slot_end = datetime.combine(current_date, end_time)

                        # Round start and end times to the next 15-minute interval
                        slot_start = round_up_to_next_15_minutes(slot_start)
                        slot_end = round_up_to_next_15_minutes(slot_end)

                        # Generate 15-minute increments
                        while slot_start < slot_end:
                            next_slot_end = slot_start + timedelta(minutes=15)
                            time_slots.append({
                                "start": slot_start.isoformat(),
                                "end": next_slot_end.isoformat()
                            })
                            slot_start = next_slot_end
                current_date += timedelta(days=1)

    # Apply exceptions to the generated slots
    for exception in exceptions:
        date = datetime.strptime(exception['date'], "%Y-%m-%d").date()
        if not exception['times']:
            # Remove all slots for this date
            time_slots = [slot for slot in time_slots if datetime.fromisoformat(slot['start']).date() != date]
        else:
            # Modify or add new time slots for this date
            time_slots = [slot for slot in time_slots if datetime.fromisoformat(slot['start']).date() != date]
            for time_range in exception['times']:
                start_time = datetime.combine(date, parse_time_string(time_range['start']))
                end_time = datetime.combine(date, parse_time_string(time_range['end']))

                # Round start and end times to the next 15-minute interval
                start_time = round_up_to_next_15_minutes(start_time)
                end_time = round_up_to_next_15_minutes(end_time)

                # Generate 15-minute increments for exceptions
                while start_time < end_time:
                    next_slot_end = start_time + timedelta(minutes=15)
                    time_slots.append({
                        "start": start_time.isoformat(),
                        "end": next_slot_end.isoformat()
                    })
                    start_time = next_slot_end

    # Add manual appointment slots, which override other rules
    for manual_slot in manual_appointment_slots:
        date = datetime.strptime(manual_slot['date'], "%Y-%m-%d").date()
        for time_range in manual_slot['times']:
            start_time = datetime.combine(date, parse_time_string(time_range['start']))
            end_time = datetime.combine(date, parse_time_string(time_range['end']))

            # Round start and end times to the next 15-minute interval
            start_time = round_up_to_next_15_minutes(start_time)
            end_time = round_up_to_next_15_minutes(end_time)

            # Generate 15-minute increments for manual slots
            while start_time < end_time:
                next_slot_end = start_time + timedelta(minutes=15)
                time_slots.append({
                    "start": start_time.isoformat(),
                    "end": next_slot_end.isoformat()
                })
                start_time = next_slot_end

    # Return the time slots sorted by start time
    return sorted(time_slots, key=lambda x: x['start'])


