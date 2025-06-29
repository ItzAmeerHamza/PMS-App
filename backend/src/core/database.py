from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

# Use the constructed database URL if DATABASE_URL is not provided
database_url = settings.database_url if settings.database_url != "postgresql://postgres:password@localhost:5432/medical_app" else settings.database_url_constructed

engine = create_engine(database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 