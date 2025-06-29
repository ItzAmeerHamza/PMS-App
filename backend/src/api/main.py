from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.router import router as user_router
from src.doctors.router import router as doctor_router
from src.patients.router import router as patient_router
from src.appointments.router import router as appointment_router
from src.core.config import settings

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="A comprehensive medical management system API",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    debug=settings.debug
)

# Add CORS middleware for web and desktop app access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers for each module
app.include_router(user_router, prefix="/api/v1")
app.include_router(doctor_router, prefix="/api/v1")
app.include_router(patient_router, prefix="/api/v1")
app.include_router(appointment_router, prefix="/api/v1")

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to the {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 