# Reservation System

This is a FastAPI-based reservation system where providers can submit their availability, clients can retrieve available slots, make reservations, and confirm them. The application also includes functionality for managing user authentication and authorization.

## Features

- **User Registration and Authentication**
  - Register as a provider, patient, or admin.
  - Secure login with JWT-based authentication.
  
- **Availability Management**
  - Providers can set their availability, including general schedules, exceptions, and manual slots.
  - Time slots are generated in 15-minute increments.

- **Appointment Booking**
  - Patients can reserve appointment slots.
  - Reserved appointments must be confirmed within a specified time or they will expire.

- **Appointment Confirmation and Cancellation**
  - Patients can confirm their reservations.
  - Both patients and providers can cancel appointments.

## Installation

### Prerequisites

- Python 3.8+
- PostgreSQL
- Redis

### Setup

1. **Clone the Repository**
   ```bash
   git clone https://github.com/your-repository/reservation-system.git
   cd reservation-system
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set Up Environment Variables**
   Create a `.env` file in the root directory with the following variables:
   ```bash
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/reservation
   REDIS_URL=redis://localhost:6379/0
   JWT_SECRET_KEY=your-secret-key
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   CONFIRMATION_GRACE_PERIOD_MINUTES=30
   CACHE_EXPIRY_SECONDS=3600
   ```

4. **Initialize the Database**
   ```bash
   python main.py --mode create-tables
   ```

5. **Run the Application**
   ```bash
   python main.py --mode server
   ```

   The application will be available at `http://localhost:8000`.

## API Endpoints

### Authentication

- **POST /register**
  - Register a new user.

- **POST /token**
  - Obtain a JWT token for authentication.

### Providers

- **GET /providers**
  - Retrieve a list of providers (Admin access only).

- **POST /providers/{provider_id}/availability**
  - Set availability for a provider.

- **GET /providers/{provider_id}/time-slots**
  - Get available time slots for a provider.

- **GET /providers/{provider_id}/booked-appointments**
  - Get booked appointments for a provider.

### Appointments

- **POST /appointments/reserve**
  - Reserve an appointment slot.

- **POST /appointments/confirm**
  - Confirm a reserved appointment.

- **POST /appointments/cancel**
  - Cancel an appointment.

## Running Tests

The project includes a set of tests written with `pytest`. To run the tests:

```bash
pytest
```


This README omits the database migration details and focuses on the current, relevant features and setup of the project.