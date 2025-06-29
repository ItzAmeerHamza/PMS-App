from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.doctors.router import router as doctor_router
from src.patients.router import router as patient_router
from src.appointments.router import router as appointment_router

# Create FastAPI app
app = FastAPI(
    title="Medical App API",
    description="A comprehensive medical management system API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware for web and desktop app access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers for each module
app.include_router(doctor_router, prefix="/api/v1")
app.include_router(patient_router, prefix="/api/v1")
app.include_router(appointment_router, prefix="/api/v1")

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Welcome to the Medical App API",
        "version": "1.0.0",
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