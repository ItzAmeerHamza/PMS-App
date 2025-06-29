# Medical App Backend

A FastAPI-based backend for a comprehensive medical management system.

## Project Structure

```
backend/
├── src/
│   ├── core/                    # Core functionality
│   │   ├── __init__.py
│   │   ├── config.py           # Configuration settings
│   │   ├── database.py         # Database connection
│   │   └── auth.py             # Authentication utilities
│   ├── doctors/                # Doctor module
│   │   ├── __init__.py
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── schemas.py          # Pydantic schemas
│   │   ├── service.py          # Business logic
│   │   └── router.py           # API endpoints
│   ├── patients/               # Patient module
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── router.py
│   ├── appointments/           # Appointment module
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── router.py
│   └── api/                    # API entry point
│       ├── __init__.py
│       └── main.py
├── requirements.txt
├── run.py                      # Application runner
└── README.md
```

## Features

- **Modular Architecture**: Each module (doctors, patients, appointments) has its own models, schemas, services, and routers
- **PostgreSQL Database**: Uses PostgreSQL with SQLAlchemy ORM
- **RESTful API**: Complete CRUD operations for all entities
- **CORS Support**: Configured for both web and desktop app access
- **API Documentation**: Automatic OpenAPI documentation at `/docs` and `/redoc`

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Database Setup**:
   - Create a PostgreSQL database
   - Update the database URL in `src/core/config.py`
   - Run database migrations (when implemented)

3. **Run the Application**:
   ```bash
   python run.py
   ```
   
   Or using uvicorn directly:
   ```bash
   uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

## API Endpoints

### Doctors
- `GET /api/v1/doctors/` - List all doctors
- `GET /api/v1/doctors/{id}` - Get doctor by ID
- `POST /api/v1/doctors/` - Create new doctor
- `PUT /api/v1/doctors/{id}` - Update doctor
- `DELETE /api/v1/doctors/{id}` - Delete doctor

### Patients
- `GET /api/v1/patients/` - List all patients (with search)
- `GET /api/v1/patients/{id}` - Get patient by ID
- `POST /api/v1/patients/` - Create new patient
- `PUT /api/v1/patients/{id}` - Update patient
- `DELETE /api/v1/patients/{id}` - Delete patient

### Appointments
- `GET /api/v1/appointments/` - List all appointments (with filtering)
- `GET /api/v1/appointments/{id}` - Get appointment by ID
- `POST /api/v1/appointments/` - Create new appointment
- `PUT /api/v1/appointments/{id}` - Update appointment
- `DELETE /api/v1/appointments/{id}` - Delete appointment
- `GET /api/v1/appointments/doctors/{id}/available-slots` - Get available slots

## Development

### Adding New Modules

To add a new module (e.g., `prescriptions`):

1. Create a new folder: `src/prescriptions/`
2. Add the required files:
   - `__init__.py`
   - `models.py` - SQLAlchemy models
   - `schemas.py` - Pydantic schemas
   - `service.py` - Business logic
   - `router.py` - API endpoints
3. Include the router in `src/api/main.py`

### Database Migrations

When you modify models, you'll need to create and run migrations:

```bash
# Initialize Alembic (if not already done)
alembic init alembic

# Create a migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head
```

## Environment Variables

Create a `.env` file in the root directory:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/medical_app
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

## API Documentation

Once the server is running, you can access:
- Interactive API docs: http://localhost:8000/docs
- ReDoc documentation: http://localhost:8000/redoc 