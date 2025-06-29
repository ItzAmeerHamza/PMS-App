from fastapi import FastAPI
from src.doctor.router.doctor import router as doctor_router
from src.patient.router.patient import router as patient_router

app = FastAPI(title="Medical App API")

# Include routers for each module
app.include_router(doctor_router)
app.include_router(patient_router)

@app.get("/")
def root():
    return {"message": "Welcome to the Medical App API"} 