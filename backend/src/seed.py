from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import models


SAMPLE_DETAILS = {
    "PCM-500": {
        "salt": "Paracetamol",
        "pack_size": "Strip of 10",
        "rack_location": "A-01",
        "barcode": "8901001000011",
        "requires_prescription": False,
    },
    "AMX-250": {
        "salt": "Amoxicillin trihydrate",
        "pack_size": "Strip of 10",
        "rack_location": "A-04",
        "barcode": "8901001000028",
        "requires_prescription": True,
    },
    "CTZ-10": {
        "salt": "Cetirizine hydrochloride",
        "pack_size": "Strip of 10",
        "rack_location": "B-02",
        "barcode": "8901001000035",
        "requires_prescription": False,
    },
    "OME-20": {
        "salt": "Omeprazole",
        "pack_size": "Strip of 15",
        "rack_location": "A-08",
        "barcode": "8901001000042",
        "requires_prescription": True,
    },
    "MET-500": {
        "salt": "Metformin hydrochloride",
        "pack_size": "Strip of 10",
        "rack_location": "C-01",
        "barcode": "8901001000059",
        "requires_prescription": True,
    },
    "AZI-500": {
        "salt": "Azithromycin dihydrate",
        "pack_size": "Strip of 3",
        "rack_location": "A-06",
        "barcode": "8901001000066",
        "requires_prescription": True,
    },
    "IBU-400": {
        "salt": "Ibuprofen",
        "pack_size": "Strip of 10",
        "rack_location": "B-05",
        "barcode": "8901001000073",
        "requires_prescription": False,
    },
    "ORS-01": {
        "salt": "Oral rehydration salts",
        "pack_size": "Single sachet",
        "rack_location": "D-01",
        "barcode": "8901001000080",
        "requires_prescription": False,
    },
}


def backfill_medicine_details(db: Session) -> None:
    """Fill catalog details on the sample medicines when those fields are still empty."""
    changed = False
    for sku, details in SAMPLE_DETAILS.items():
        medicine = db.query(models.Medicine).filter(models.Medicine.sku == sku).first()
        if not medicine or medicine.pack_size:
            continue
        for field, value in details.items():
            setattr(medicine, field, value)
        changed = True
    if changed:
        db.commit()


def backfill_visit_details(db: Session) -> None:
    """Fill the complaint on the sample visits when that field is still empty."""
    complaints = {
        "Viral fever": "Fever and body ache",
        "Type 2 diabetes follow-up": "Follow-up for blood sugar",
    }
    changed = False
    visits = db.query(models.Prescription).filter(models.Prescription.complaint.is_(None)).all()
    for visit in visits:
        complaint = complaints.get(visit.diagnosis or "")
        if complaint:
            visit.complaint = complaint
            changed = True
    if changed:
        db.commit()


def seed_if_empty(db: Session) -> None:
    if db.query(models.Pharmacy).first():
        return

    pharmacy = models.Pharmacy(
        name="City Care Pharmacy",
        address="14 MG Road, Bengaluru",
        phone="080-4000-1200",
        license_number="KA-PH-2024-1182",
    )
    db.add(pharmacy)
    db.flush()

    catalog = [
        {
            "sku": "PCM-500",
            "name": "Paracetamol 500mg",
            "salt": "Paracetamol",
            "generic_name": "Paracetamol",
            "manufacturer": "Cipla",
            "form": "tablet",
            "strength": "500mg",
            "pack_size": "Strip of 10",
            "category": "Analgesic",
            "barcode": "8901001000011",
            "rack_location": "A-01",
            "requires_prescription": False,
            "unit_price": 12.00,
            "reorder_level": 40,
            "batches": [
                {"batch_number": "PCM-A12", "expiry_date": date.today() + timedelta(days=400), "quantity": 180, "cost_price": 6, "selling_price": 12},
            ],
        },
        {
            "sku": "AMX-250",
            "name": "Amoxicillin 250mg",
            "salt": "Amoxicillin trihydrate",
            "generic_name": "Amoxicillin",
            "manufacturer": "Sun Pharma",
            "form": "capsule",
            "strength": "250mg",
            "pack_size": "Strip of 10",
            "category": "Antibiotic",
            "barcode": "8901001000028",
            "rack_location": "A-04",
            "requires_prescription": True,
            "unit_price": 48.00,
            "reorder_level": 20,
            "batches": [
                {"batch_number": "AMX-09", "expiry_date": date.today() + timedelta(days=50), "quantity": 24, "cost_price": 28, "selling_price": 48},
            ],
        },
        {
            "sku": "CTZ-10",
            "name": "Cetirizine 10mg",
            "salt": "Cetirizine hydrochloride",
            "generic_name": "Cetirizine",
            "manufacturer": "Dr. Reddy's",
            "form": "tablet",
            "strength": "10mg",
            "pack_size": "Strip of 10",
            "category": "Antihistamine",
            "barcode": "8901001000035",
            "rack_location": "B-02",
            "requires_prescription": False,
            "unit_price": 18.00,
            "reorder_level": 30,
            "batches": [
                {"batch_number": "CTZ-22", "expiry_date": date.today() + timedelta(days=220), "quantity": 90, "cost_price": 8, "selling_price": 18},
            ],
        },
        {
            "sku": "OME-20",
            "name": "Omeprazole 20mg",
            "salt": "Omeprazole",
            "generic_name": "Omeprazole",
            "manufacturer": "Abbott",
            "form": "capsule",
            "strength": "20mg",
            "pack_size": "Strip of 15",
            "category": "Antacid",
            "barcode": "8901001000042",
            "rack_location": "A-08",
            "requires_prescription": True,
            "unit_price": 35.00,
            "reorder_level": 25,
            "batches": [
                {"batch_number": "OME-04", "expiry_date": date.today() + timedelta(days=18), "quantity": 16, "cost_price": 18, "selling_price": 35},
            ],
        },
        {
            "sku": "MET-500",
            "name": "Metformin 500mg",
            "salt": "Metformin hydrochloride",
            "generic_name": "Metformin",
            "manufacturer": "USV",
            "form": "tablet",
            "strength": "500mg",
            "pack_size": "Strip of 10",
            "category": "Antidiabetic",
            "barcode": "8901001000059",
            "rack_location": "C-01",
            "requires_prescription": True,
            "unit_price": 22.00,
            "reorder_level": 50,
            "batches": [
                {"batch_number": "MET-71", "expiry_date": date.today() + timedelta(days=500), "quantity": 8, "cost_price": 10, "selling_price": 22},
            ],
        },
        {
            "sku": "AZI-500",
            "name": "Azithromycin 500mg",
            "salt": "Azithromycin dihydrate",
            "generic_name": "Azithromycin",
            "manufacturer": "Alkem",
            "form": "tablet",
            "strength": "500mg",
            "pack_size": "Strip of 3",
            "category": "Antibiotic",
            "barcode": "8901001000066",
            "rack_location": "A-06",
            "requires_prescription": True,
            "unit_price": 85.00,
            "reorder_level": 15,
            "batches": [
                {"batch_number": "AZI-15", "expiry_date": date.today() + timedelta(days=300), "quantity": 42, "cost_price": 48, "selling_price": 85},
            ],
        },
        {
            "sku": "IBU-400",
            "name": "Ibuprofen 400mg",
            "salt": "Ibuprofen",
            "generic_name": "Ibuprofen",
            "manufacturer": "Pfizer",
            "form": "tablet",
            "strength": "400mg",
            "pack_size": "Strip of 10",
            "category": "NSAID",
            "barcode": "8901001000073",
            "rack_location": "B-05",
            "requires_prescription": False,
            "unit_price": 16.00,
            "reorder_level": 30,
            "batches": [
                {"batch_number": "IBU-33", "expiry_date": date.today() + timedelta(days=260), "quantity": 70, "cost_price": 7, "selling_price": 16},
            ],
        },
        {
            "sku": "ORS-01",
            "name": "ORS Sachet",
            "salt": "Oral rehydration salts",
            "generic_name": "Oral rehydration salts",
            "manufacturer": "WHO Formula",
            "form": "sachet",
            "strength": "21g",
            "pack_size": "Single sachet",
            "category": "Electrolyte",
            "barcode": "8901001000080",
            "rack_location": "D-01",
            "requires_prescription": False,
            "unit_price": 8.00,
            "reorder_level": 40,
            "batches": [
                {"batch_number": "ORS-08", "expiry_date": date.today() + timedelta(days=140), "quantity": 120, "cost_price": 3, "selling_price": 8},
            ],
        },
    ]

    medicines = {}
    for item in catalog:
        batches = item.pop("batches")
        medicine = models.Medicine(pharmacy_id=pharmacy.id, **item)
        db.add(medicine)
        db.flush()
        medicines[medicine.sku] = medicine
        for batch in batches:
            db.add(models.StockBatch(medicine_id=medicine.id, **batch))

    patients = [
        models.Patient(
            pharmacy_id=pharmacy.id,
            first_name="Ananya",
            last_name="Rao",
            phone="9876501122",
            date_of_birth=date(1994, 3, 12),
            gender="female",
            address="Indiranagar, Bengaluru",
            allergies="Penicillin",
            notes="Prefers evening visits",
        ),
        models.Patient(
            pharmacy_id=pharmacy.id,
            first_name="Karthik",
            last_name="Menon",
            phone="9845017788",
            date_of_birth=date(1986, 11, 2),
            gender="male",
            address="Jayanagar, Bengaluru",
            allergies=None,
            notes="Type 2 diabetes",
        ),
        models.Patient(
            pharmacy_id=pharmacy.id,
            first_name="Meera",
            last_name="Iyer",
            phone="9900123344",
            date_of_birth=date(2001, 7, 21),
            gender="female",
            address="Koramangala, Bengaluru",
            allergies="Dust",
            notes=None,
        ),
    ]
    db.add_all(patients)
    db.flush()

    first = models.Prescription(
        pharmacy_id=pharmacy.id,
        patient_id=patients[0].id,
        doctor_name="Dr. S. Nair",
        complaint="Fever and body ache",
        diagnosis="Viral fever",
        notes="Rest and hydration",
        status="dispensed",
        dispensed_at=datetime.now(timezone.utc),
    )
    db.add(first)
    db.flush()
    db.add_all(
        [
            models.PrescriptionItem(
                prescription_id=first.id,
                medicine_id=medicines["PCM-500"].id,
                dosage="500mg",
                frequency="1-0-1",
                duration_days=3,
                quantity=6,
                instructions="After food",
            ),
            models.PrescriptionItem(
                prescription_id=first.id,
                medicine_id=medicines["CTZ-10"].id,
                dosage="10mg",
                frequency="0-0-1",
                duration_days=5,
                quantity=5,
                instructions="At night",
            ),
        ]
    )

    second = models.Prescription(
        pharmacy_id=pharmacy.id,
        patient_id=patients[1].id,
        doctor_name="Dr. Priya Shah",
        complaint="Follow-up for blood sugar",
        diagnosis="Type 2 diabetes follow-up",
        status="recorded",
    )
    db.add(second)
    db.flush()
    db.add(
        models.PrescriptionItem(
            prescription_id=second.id,
            medicine_id=medicines["MET-500"].id,
            dosage="500mg",
            frequency="1-0-1",
            duration_days=7,
            quantity=6,
            instructions="With meals",
        )
    )

    db.commit()
