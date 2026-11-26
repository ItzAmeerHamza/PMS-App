"""Baseline: the schema PharmaCare had before Alembic.

Works on three kinds of database:
- empty: creates every table;
- created by the old `create_all` startup (any age): creates missing tables
  (older files have no sales tables) and adds columns that the old startup
  `ALTER TABLE` patch added;
- already at this baseline: changes nothing.

It also runs, once, the data fixes the old startup repeated on every launch.
The DDL is the exact SQL SQLAlchemy's `create_all` produced, so new and old files match.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-26
"""

from alembic import op
from sqlalchemy import inspect

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

TABLES = {
    "pharmacies": """
CREATE TABLE pharmacies (
	id INTEGER NOT NULL,
	name VARCHAR(255) NOT NULL,
	address VARCHAR(500),
	phone VARCHAR(20),
	license_number VARCHAR(100),
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
)""",
    "staff": """
CREATE TABLE staff (
	id INTEGER NOT NULL,
	pharmacy_id INTEGER NOT NULL,
	full_name VARCHAR(255) NOT NULL,
	username VARCHAR(64) NOT NULL,
	password_hash VARCHAR(255) NOT NULL,
	role VARCHAR(40) NOT NULL,
	is_active BOOLEAN,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(pharmacy_id) REFERENCES pharmacies (id)
)""",
    "medicines": """
CREATE TABLE medicines (
	id INTEGER NOT NULL,
	pharmacy_id INTEGER NOT NULL,
	sku VARCHAR(64) NOT NULL,
	name VARCHAR(255) NOT NULL,
	salt VARCHAR(255),
	generic_name VARCHAR(255),
	manufacturer VARCHAR(255),
	form VARCHAR(50),
	strength VARCHAR(50),
	pack_size VARCHAR(80),
	category VARCHAR(100),
	barcode VARCHAR(64),
	rack_location VARCHAR(80),
	unit_price NUMERIC(10, 2),
	reorder_level INTEGER,
	requires_prescription BOOLEAN,
	notes TEXT,
	is_active BOOLEAN,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	updated_at DATETIME,
	PRIMARY KEY (id),
	CONSTRAINT uq_medicine_sku_per_pharmacy UNIQUE (pharmacy_id, sku),
	FOREIGN KEY(pharmacy_id) REFERENCES pharmacies (id)
)""",
    "patients": """
CREATE TABLE patients (
	id INTEGER NOT NULL,
	pharmacy_id INTEGER NOT NULL,
	first_name VARCHAR(255) NOT NULL,
	last_name VARCHAR(255) NOT NULL,
	phone VARCHAR(20) NOT NULL,
	date_of_birth DATE,
	gender VARCHAR(20),
	address VARCHAR(500),
	allergies TEXT,
	notes TEXT,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	updated_at DATETIME,
	PRIMARY KEY (id),
	FOREIGN KEY(pharmacy_id) REFERENCES pharmacies (id)
)""",
    "staff_sessions": """
CREATE TABLE staff_sessions (
	token VARCHAR(64) NOT NULL,
	staff_id INTEGER NOT NULL,
	expires_at DATETIME NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (token),
	FOREIGN KEY(staff_id) REFERENCES staff (id)
)""",
    "stock_batches": """
CREATE TABLE stock_batches (
	id INTEGER NOT NULL,
	medicine_id INTEGER NOT NULL,
	batch_number VARCHAR(64) NOT NULL,
	expiry_date DATE NOT NULL,
	quantity INTEGER NOT NULL,
	cost_price NUMERIC(10, 2),
	selling_price NUMERIC(10, 2),
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(medicine_id) REFERENCES medicines (id)
)""",
    "prescriptions": """
CREATE TABLE prescriptions (
	id INTEGER NOT NULL,
	pharmacy_id INTEGER NOT NULL,
	patient_id INTEGER NOT NULL,
	doctor_name VARCHAR(255),
	complaint VARCHAR(500),
	diagnosis VARCHAR(500),
	notes TEXT,
	status VARCHAR(20) NOT NULL,
	prescribed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	dispensed_at DATETIME,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(pharmacy_id) REFERENCES pharmacies (id),
	FOREIGN KEY(patient_id) REFERENCES patients (id)
)""",
    "prescription_items": """
CREATE TABLE prescription_items (
	id INTEGER NOT NULL,
	prescription_id INTEGER NOT NULL,
	medicine_id INTEGER NOT NULL,
	medicine_name VARCHAR(255),
	medicine_salt VARCHAR(255),
	medicine_company VARCHAR(255),
	dosage VARCHAR(100),
	frequency VARCHAR(100),
	duration_days INTEGER,
	quantity INTEGER NOT NULL,
	instructions VARCHAR(500),
	PRIMARY KEY (id),
	FOREIGN KEY(prescription_id) REFERENCES prescriptions (id),
	FOREIGN KEY(medicine_id) REFERENCES medicines (id)
)""",
    "sales": """
CREATE TABLE sales (
	id INTEGER NOT NULL,
	pharmacy_id INTEGER NOT NULL,
	invoice_number VARCHAR(32),
	patient_id INTEGER,
	prescription_id INTEGER,
	staff_id INTEGER,
	customer_name VARCHAR(255),
	customer_phone VARCHAR(20),
	subtotal NUMERIC(12, 2) NOT NULL,
	discount_percent NUMERIC(5, 2) NOT NULL,
	discount_amount NUMERIC(12, 2) NOT NULL,
	tax_percent NUMERIC(5, 2) NOT NULL,
	tax_amount NUMERIC(12, 2) NOT NULL,
	total NUMERIC(12, 2) NOT NULL,
	payment_method VARCHAR(20) NOT NULL,
	amount_paid NUMERIC(12, 2) NOT NULL,
	change_due NUMERIC(12, 2) NOT NULL,
	notes VARCHAR(500),
	status VARCHAR(20) NOT NULL,
	voided_at DATETIME,
	void_reason VARCHAR(255),
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(pharmacy_id) REFERENCES pharmacies (id),
	FOREIGN KEY(patient_id) REFERENCES patients (id),
	FOREIGN KEY(prescription_id) REFERENCES prescriptions (id),
	FOREIGN KEY(staff_id) REFERENCES staff (id)
)""",
    "sale_items": """
CREATE TABLE sale_items (
	id INTEGER NOT NULL,
	sale_id INTEGER NOT NULL,
	medicine_id INTEGER NOT NULL,
	medicine_name VARCHAR(255) NOT NULL,
	quantity INTEGER NOT NULL,
	unit_price NUMERIC(10, 2) NOT NULL,
	line_total NUMERIC(12, 2) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(sale_id) REFERENCES sales (id),
	FOREIGN KEY(medicine_id) REFERENCES medicines (id)
)""",
    "sale_allocations": """
CREATE TABLE sale_allocations (
	id INTEGER NOT NULL,
	sale_item_id INTEGER NOT NULL,
	batch_id INTEGER NOT NULL,
	batch_number VARCHAR(64),
	expiry_date DATE,
	quantity INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(sale_item_id) REFERENCES sale_items (id),
	FOREIGN KEY(batch_id) REFERENCES stock_batches (id)
)""",
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_pharmacies_id ON pharmacies (id)",
    "CREATE INDEX IF NOT EXISTS ix_staff_pharmacy_id ON staff (pharmacy_id)",
    "CREATE INDEX IF NOT EXISTS ix_staff_id ON staff (id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_staff_username ON staff (username)",
    "CREATE INDEX IF NOT EXISTS ix_medicines_id ON medicines (id)",
    "CREATE INDEX IF NOT EXISTS ix_medicines_name ON medicines (name)",
    "CREATE INDEX IF NOT EXISTS ix_medicines_pharmacy_id ON medicines (pharmacy_id)",
    "CREATE INDEX IF NOT EXISTS ix_patients_id ON patients (id)",
    "CREATE INDEX IF NOT EXISTS ix_patients_phone ON patients (phone)",
    "CREATE INDEX IF NOT EXISTS ix_patients_pharmacy_id ON patients (pharmacy_id)",
    "CREATE INDEX IF NOT EXISTS ix_staff_sessions_staff_id ON staff_sessions (staff_id)",
    "CREATE INDEX IF NOT EXISTS ix_stock_batches_id ON stock_batches (id)",
    "CREATE INDEX IF NOT EXISTS ix_stock_batches_medicine_id ON stock_batches (medicine_id)",
    "CREATE INDEX IF NOT EXISTS ix_prescriptions_pharmacy_id ON prescriptions (pharmacy_id)",
    "CREATE INDEX IF NOT EXISTS ix_prescriptions_patient_id ON prescriptions (patient_id)",
    "CREATE INDEX IF NOT EXISTS ix_prescriptions_id ON prescriptions (id)",
    "CREATE INDEX IF NOT EXISTS ix_prescription_items_id ON prescription_items (id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_pharmacy_id ON sales (pharmacy_id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_prescription_id ON sales (prescription_id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_id ON sales (id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_created_at ON sales (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_sales_patient_id ON sales (patient_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_sales_invoice_number ON sales (invoice_number)",
    "CREATE INDEX IF NOT EXISTS ix_sale_items_sale_id ON sale_items (sale_id)",
    "CREATE INDEX IF NOT EXISTS ix_sale_items_id ON sale_items (id)",
    "CREATE INDEX IF NOT EXISTS ix_sale_allocations_id ON sale_allocations (id)",
    "CREATE INDEX IF NOT EXISTS ix_sale_allocations_sale_item_id ON sale_allocations (sale_item_id)",
]

# Columns the pre-Alembic startup added with ALTER TABLE to files created before them.
LEGACY_COLUMNS = {
    "medicines": {
        "salt": "VARCHAR(255)",
        "pack_size": "VARCHAR(80)",
        "rack_location": "VARCHAR(80)",
        "barcode": "VARCHAR(64)",
        "requires_prescription": "BOOLEAN DEFAULT 0",
        "notes": "TEXT",
    },
    "prescriptions": {"complaint": "VARCHAR(500)"},
    "prescription_items": {
        "medicine_name": "VARCHAR(255)",
        "medicine_salt": "VARCHAR(255)",
        "medicine_company": "VARCHAR(255)",
    },
}


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())

    for name, ddl in TABLES.items():
        if name not in existing:
            op.execute(ddl)

    inspector = inspect(bind)
    for table, columns in LEGACY_COLUMNS.items():
        present = {column["name"] for column in inspector.get_columns(table)}
        for column, ddl in columns.items():
            if column not in present:
                op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    for statement in INDEXES:
        op.execute(statement)

    # One-time data fixes. The old startup ran these on every launch.
    op.execute("UPDATE medicines SET salt = generic_name WHERE salt IS NULL AND generic_name IS NOT NULL")
    op.execute(
        "UPDATE prescription_items SET medicine_name = ("
        "SELECT name FROM medicines WHERE medicines.id = prescription_items.medicine_id"
        ") WHERE medicine_name IS NULL"
    )
    op.execute(
        "UPDATE prescription_items SET medicine_salt = ("
        "SELECT COALESCE(salt, generic_name) FROM medicines WHERE medicines.id = prescription_items.medicine_id"
        ") WHERE medicine_salt IS NULL"
    )
    op.execute(
        "UPDATE prescription_items SET medicine_company = ("
        "SELECT manufacturer FROM medicines WHERE medicines.id = prescription_items.medicine_id"
        ") WHERE medicine_company IS NULL"
    )


def downgrade() -> None:
    raise NotImplementedError("The baseline cannot be downgraded. Restore a backup instead.")
