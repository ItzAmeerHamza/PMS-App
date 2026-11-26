"""Builders for databases in the shape PharmaCare wrote before Alembic.

``build_oldest`` matches a file created before the catalog/visit columns existed and
then patched by the old startup ALTER TABLE (columns appended at the end), with no
sales tables. ``build_pre_alembic`` matches a file created by the last create_all
(billing tables present). Rows are synthetic.
"""

import hashlib
import sqlite3
from pathlib import Path

LEGACY_PASSWORD = "legacy-pass-123"


def legacy_pbkdf2(password: str, salt_hex: str = "00112233445566778899aabbccddeeff") -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 120_000).hex()
    return f"{salt_hex}${digest}"


OLDEST_DDL = [
    """CREATE TABLE pharmacies (id INTEGER NOT NULL, name VARCHAR(255) NOT NULL, address VARCHAR(500),
       phone VARCHAR(20), license_number VARCHAR(100), created_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (id))""",
    """CREATE TABLE staff (id INTEGER NOT NULL, pharmacy_id INTEGER NOT NULL, full_name VARCHAR(255) NOT NULL,
       username VARCHAR(64) NOT NULL, password_hash VARCHAR(255) NOT NULL, role VARCHAR(40) NOT NULL, is_active BOOLEAN,
       created_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (id), FOREIGN KEY(pharmacy_id) REFERENCES pharmacies (id))""",
    """CREATE TABLE medicines (id INTEGER NOT NULL, pharmacy_id INTEGER NOT NULL, sku VARCHAR(64) NOT NULL,
       name VARCHAR(255) NOT NULL, generic_name VARCHAR(255), manufacturer VARCHAR(255), form VARCHAR(50),
       strength VARCHAR(50), category VARCHAR(100), unit_price NUMERIC(10, 2), reorder_level INTEGER, is_active BOOLEAN,
       created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME, PRIMARY KEY (id),
       CONSTRAINT uq_medicine_sku_per_pharmacy UNIQUE (pharmacy_id, sku), FOREIGN KEY(pharmacy_id) REFERENCES pharmacies (id))""",
    """CREATE TABLE patients (id INTEGER NOT NULL, pharmacy_id INTEGER NOT NULL, first_name VARCHAR(255) NOT NULL,
       last_name VARCHAR(255) NOT NULL, phone VARCHAR(20) NOT NULL, date_of_birth DATE, gender VARCHAR(20),
       address VARCHAR(500), allergies TEXT, notes TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME,
       PRIMARY KEY (id), FOREIGN KEY(pharmacy_id) REFERENCES pharmacies (id))""",
    """CREATE TABLE staff_sessions (token VARCHAR(64) NOT NULL, staff_id INTEGER NOT NULL, expires_at DATETIME NOT NULL,
       created_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (token), FOREIGN KEY(staff_id) REFERENCES staff (id))""",
    """CREATE TABLE stock_batches (id INTEGER NOT NULL, medicine_id INTEGER NOT NULL, batch_number VARCHAR(64) NOT NULL,
       expiry_date DATE NOT NULL, quantity INTEGER NOT NULL, cost_price NUMERIC(10, 2), selling_price NUMERIC(10, 2),
       created_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (id), FOREIGN KEY(medicine_id) REFERENCES medicines (id))""",
    """CREATE TABLE prescriptions (id INTEGER NOT NULL, pharmacy_id INTEGER NOT NULL, patient_id INTEGER NOT NULL,
       doctor_name VARCHAR(255), diagnosis VARCHAR(500), notes TEXT, status VARCHAR(20) NOT NULL,
       prescribed_at DATETIME DEFAULT CURRENT_TIMESTAMP, dispensed_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
       PRIMARY KEY (id), FOREIGN KEY(pharmacy_id) REFERENCES pharmacies (id), FOREIGN KEY(patient_id) REFERENCES patients (id))""",
    """CREATE TABLE prescription_items (id INTEGER NOT NULL, prescription_id INTEGER NOT NULL, medicine_id INTEGER NOT NULL,
       dosage VARCHAR(100), frequency VARCHAR(100), duration_days INTEGER, quantity INTEGER NOT NULL, instructions VARCHAR(500),
       PRIMARY KEY (id), FOREIGN KEY(prescription_id) REFERENCES prescriptions (id), FOREIGN KEY(medicine_id) REFERENCES medicines (id))""",
    "CREATE UNIQUE INDEX ix_staff_username ON staff (username)",
]

ROWS = [
    "INSERT INTO pharmacies (id, name, address) VALUES (1, 'Synthetic Pharmacy', '1 Test Street')",
    f"INSERT INTO staff (id, pharmacy_id, full_name, username, password_hash, role, is_active) "
    f"VALUES (1, 1, 'Legacy Manager', 'manager', '{legacy_pbkdf2(LEGACY_PASSWORD)}', 'store_manager', 1)",
    "INSERT INTO medicines (id, pharmacy_id, sku, name, generic_name, manufacturer, unit_price, reorder_level, is_active) "
    "VALUES (1, 1, 'TST-1', 'Testamol 500mg', 'Testamol', 'Acme Labs', 10.00, 5, 1)",
    "INSERT INTO medicines (id, pharmacy_id, sku, name, generic_name, manufacturer, unit_price, reorder_level, is_active) "
    "VALUES (2, 1, 'TST-2', 'Samplecillin 250mg', 'Samplecillin', 'Acme Labs', 20.00, 5, 1)",
    "INSERT INTO stock_batches (id, medicine_id, batch_number, expiry_date, quantity) VALUES (1, 1, 'B-1', '2099-01-01', 50)",
    "INSERT INTO stock_batches (id, medicine_id, batch_number, expiry_date, quantity) VALUES (2, 2, 'B-2', '2099-01-01', 30)",
    "INSERT INTO patients (id, pharmacy_id, first_name, last_name, phone) VALUES (1, 1, 'Alpha', 'Synthetic', '0300-0000001')",
    "INSERT INTO patients (id, pharmacy_id, first_name, last_name, phone) VALUES (2, 1, 'Beta', 'Synthetic', '0300-0000002')",
    "INSERT INTO prescriptions (id, pharmacy_id, patient_id, doctor_name, diagnosis, status) VALUES (1, 1, 1, 'Dr Test', 'Test diagnosis', 'recorded')",
    "INSERT INTO prescription_items (id, prescription_id, medicine_id, dosage, quantity) VALUES (1, 1, 1, '1 tab', 4)",
]

# What the old startup appended with ALTER TABLE.
PATCHES = [
    "ALTER TABLE medicines ADD COLUMN salt VARCHAR(255)",
    "ALTER TABLE medicines ADD COLUMN pack_size VARCHAR(80)",
    "ALTER TABLE medicines ADD COLUMN rack_location VARCHAR(80)",
    "ALTER TABLE medicines ADD COLUMN barcode VARCHAR(64)",
    "ALTER TABLE medicines ADD COLUMN requires_prescription BOOLEAN DEFAULT 0",
    "ALTER TABLE medicines ADD COLUMN notes TEXT",
    "ALTER TABLE prescriptions ADD COLUMN complaint VARCHAR(500)",
    "ALTER TABLE prescription_items ADD COLUMN medicine_name VARCHAR(255)",
    "ALTER TABLE prescription_items ADD COLUMN medicine_salt VARCHAR(255)",
    "ALTER TABLE prescription_items ADD COLUMN medicine_company VARCHAR(255)",
]


def build_oldest(path: Path, patched: bool = False) -> None:
    conn = sqlite3.connect(path)
    try:
        for statement in OLDEST_DDL + ROWS + (PATCHES if patched else []):
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def build_pre_alembic(path: Path) -> None:
    """The last create_all shape: every baseline table, including sales."""
    import importlib

    baseline = importlib.import_module("migrations.versions.0001_baseline")
    conn = sqlite3.connect(path)
    try:
        for ddl in baseline.TABLES.values():
            conn.execute(ddl)
        for statement in baseline.INDEXES:
            conn.execute(statement)
        for statement in ROWS:
            if statement.startswith("INSERT INTO prescriptions "):
                statement = statement.replace("diagnosis, status)", "diagnosis, status, complaint)").replace(
                    "'recorded')", "'recorded', 'Test complaint')"
                )
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def counts(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(path)
    try:
        tables = ["pharmacies", "staff", "medicines", "stock_batches", "patients", "prescriptions", "prescription_items"]
        return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
    finally:
        conn.close()
