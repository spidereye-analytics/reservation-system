# Reservation System

## Overview
This is a FastAPI-based reservation system designed for service providers and clients. It allows providers to set their availability, and clients to browse available slots, make reservations, and manage their appointments.

## Features

### User Management
- User registration for providers, patients, and admins
- Secure authentication using JWT tokens
- Password reset functionality

### Availability Management
- Providers can set their general availability schedule
- Support for scheduling exceptions and manual appointment slots
- Time slots are generated in 15-minute increments

### Appointment Booking
- Patients can view available time slots for providers
- Reservation of appointment slots
- Confirmation of reserved appointments
- Cancellation of appointments by both patients and providers

### Caching
- Redis-based caching system for improved performance
- Periodic synchronization between cache and database

### Admin Functions
- Ability to view all providers in the system

## Technology Stack
- Backend: FastAPI (Python)
- Database: PostgreSQL
- Caching: Redis
- Testing: pytest
- Authentication: JWT
- Containerization: Docker and Docker Compose

## Installation

### Prerequisites
- Docker and Docker Compose
- Git

### Docker Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/reservation-system.git
   cd reservation-system
   ```

2. Create a `.env` file in the root directory with the following content:
   ```
   JWT_SECRET_KEY=your_secret_key
   ```

3. Build and start the Docker containers:
   ```bash
   docker-compose up --build
   ```

   This command will start the following services:
   - PostgreSQL database
   - Redis cache
   - Web application

4. The application will be available at `http://localhost:8000`

### Manual Setup (Alternative to Docker)

If you prefer to run the application without Docker:

1. Ensure you have Python 3.8+, PostgreSQL, and Redis installed on your system.

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   Create a `.env` file in the root directory with the following:
   ```
   DATABASE_URL=postgresql://user:password@localhost:5432/reservation_db
   REDIS_URL=redis://localhost:6379/0
   JWT_SECRET_KEY=your_secret_key
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   CONFIRMATION_GRACE_PERIOD_MINUTES=30
   CACHE_EXPIRY_SECONDS=3600
   ```

4. Initialize the database:
   ```bash
   python main.py --mode create-tables
   ```

5. Run the application:
   ```bash
   python main.py --mode server
   ```

## API Endpoints and Role Requirements

### Authentication
- `POST /register` - Register a new user (Public)
- `POST /token` - Obtain a JWT token (Public)
- `POST /reset-password` - Reset user password (Authenticated user or Admin)

### Providers
- `GET /providers` - Retrieve a list of providers (Admin only)
- `POST /providers/{provider_id}/availability` - Set availability for a provider (Provider only)
- `GET /providers/{provider_id}/time-slots` - Get available time slots for a provider (Any authenticated user)
- `GET /providers/{provider_id}/booked-appointments` - Get booked appointments for a provider (Provider only)

### Appointments
- `POST /appointments/reserve` - Reserve an appointment slot (Patient only)
- `POST /appointments/confirm` - Confirm a reserved appointment (Patient only)
- `POST /appointments/cancel` - Cancel an appointment (Patient for own appointments, Provider for their appointments)

## Caching Strategy

The system utilizes Redis for caching to enhance performance and reduce database load:

- Available time slots for providers are cached with a configurable expiry time.
- Cache is updated when providers modify their availability.
- A background task periodically checks and synchronizes the cache with the database.

Cache key structure:
```
provider:{provider_id}:timeslots:{date}
```

The `CACHE_EXPIRY_SECONDS` environment variable controls the cache validity period.

## Running Tests

For manual setup:

```bash
pytest
```

## Future Considerations

1. **Scalability**
   - Explore distributed caching solutions (e.g., Redis Cluster) with sharding

2. **Performance Optimization**
   - Optimize database queries and implement strategic indexing
   - Implement asynchronous processing for non-critical tasks

3. **Security Enhancements**
   - Implement rate limiting to prevent abuse
   - Add two-factor authentication for sensitive operations
   - Implement JWT secret rotation and token refresh mechanism

4. **Feature Expansions**
   - Develop a notification system for appointment reminders
   - Add support for recurring appointments
   - Implement a provider rating and review system

5. **Monitoring and Logging**
   - Set up comprehensive logging and error tracking
   - Implement monitoring and alerting for system health and performance

6. **API Versioning**
   - Implement API versioning to support future changes without breaking existing integrations

7. **Localization and Internationalization**
   - Add support for multiple languages and time zones

8. **Analytics**
   - Implement analytics to track system usage, popular time slots, and cancellation rates

9. **Compliance and Data Protection**
   - Ensure GDPR compliance for user data handling
   - Implement data retention and deletion policies

## Additional Notes

- The Docker setup uses PostgreSQL 13 and the latest Alpine-based Redis image. This can be pinned to prevent security vulnerabilities due to supply chain attacks.
- The web service uses a custom image `reservation-system:latest`. Ensure this image is built before running `docker-compose up`.
- Environment variables are set in the Docker Compose file, except for `JWT_SECRET_KEY` which should be set in a `.env` file for security.
- The application inside Docker runs on port 8000, which is mapped to the host's port 8000.
