# Configuration Guide

This document explains how to configure the Medical App Backend using environment variables.

## Environment Variables

Create a `.env` file in the `backend/` directory with the following variables:

### Database Configuration

You can configure the database in two ways:

**Option 1: Full Database URL**
```env
DATABASE_URL=postgresql://username:password@localhost:5432/database_name
```

**Option 2: Individual Database Components**
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=medical_app
DB_USER=postgres
DB_PASSWORD=your_password
```

### JWT Configuration
```env
SECRET_KEY=your-super-secret-key-change-this-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Application Configuration
```env
APP_NAME=Medical App API
APP_VERSION=1.0.0
DEBUG=True
```

### CORS Configuration
```env
# Comma-separated list of allowed origins
CORS_ORIGINS=http://localhost:3000,http://localhost:8080,*
```

## Example .env File

```env
# Database Configuration
DATABASE_URL=postgresql://postgres:mypassword@localhost:5432/medical_app

# JWT Configuration
SECRET_KEY=my-super-secret-jwt-key-for-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Application Configuration
APP_NAME=Medical App API
APP_VERSION=1.0.0
DEBUG=True

# CORS Configuration
CORS_ORIGINS=http://localhost:3000,http://localhost:8080,*
```

## Local Development Setup

1. **Install PostgreSQL** (if not already installed)
2. **Create Database**:
   ```sql
   CREATE DATABASE medical_app;
   CREATE USER medical_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE medical_app TO medical_user;
   ```

3. **Create .env file** with your database credentials
4. **Run the application**:
   ```bash
   python run.py
   ```

## Production Configuration

For production, make sure to:

1. Use a strong `SECRET_KEY`
2. Set `DEBUG=False`
3. Configure specific `CORS_ORIGINS` instead of `*`
4. Use environment-specific database credentials
5. Consider using connection pooling for the database 