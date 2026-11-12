from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

if settings.database_url.startswith("sqlite"):
    data_dir = Path(__file__).resolve().parents[2] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "pharmacy.db"
    database_url = f"sqlite:///{db_path}"
    connect_args = {"check_same_thread": False}
else:
    database_url = settings.database_url
    connect_args = {}

engine = create_engine(database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


MEDICINE_COLUMN_DDL = {
    "salt": "VARCHAR(255)",
    "pack_size": "VARCHAR(80)",
    "rack_location": "VARCHAR(80)",
    "barcode": "VARCHAR(64)",
    "requires_prescription": "BOOLEAN DEFAULT 0",
    "notes": "TEXT",
}


def _add_columns(connection, inspector, table: str, columns: dict[str, str]) -> None:
    if table not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns(table)}
    for name, ddl in columns.items():
        if name not in existing:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def ensure_schema() -> None:
    """Create tables, then add columns on databases created before later catalog fields."""
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    with engine.begin() as connection:
        _add_columns(connection, inspector, "medicines", MEDICINE_COLUMN_DDL)
        _add_columns(connection, inspector, "prescriptions", {"complaint": "VARCHAR(500)"})
        _add_columns(
            connection,
            inspector,
            "prescription_items",
            {
                "medicine_name": "VARCHAR(255)",
                "medicine_salt": "VARCHAR(255)",
                "medicine_company": "VARCHAR(255)",
            },
        )
        if "medicines" in inspector.get_table_names():
            connection.execute(
                text(
                    "UPDATE medicines SET salt = generic_name "
                    "WHERE salt IS NULL AND generic_name IS NOT NULL"
                )
            )
        if "prescription_items" in inspector.get_table_names():
            connection.execute(
                text(
                    "UPDATE prescription_items SET medicine_name = ("
                    "SELECT name FROM medicines WHERE medicines.id = prescription_items.medicine_id"
                    ") WHERE medicine_name IS NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE prescription_items SET medicine_salt = ("
                    "SELECT COALESCE(salt, generic_name) FROM medicines "
                    "WHERE medicines.id = prescription_items.medicine_id"
                    ") WHERE medicine_salt IS NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE prescription_items SET medicine_company = ("
                    "SELECT manufacturer FROM medicines WHERE medicines.id = prescription_items.medicine_id"
                    ") WHERE medicine_company IS NULL"
                )
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
