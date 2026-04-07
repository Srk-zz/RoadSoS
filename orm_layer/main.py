from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, JSON, DateTime, Integer
from sqlalchemy.orm import sessionmaker, declarative_base
import datetime
import uuid
import os

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:password@db/roadsos")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

app = FastAPI(title="Road SOS — ORM Data Layer", version="1.0.0")

# --- SQLAlchemy Model ---
class IncidentModel(Base):
    __tablename__ = "incidents"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(50), nullable=False)
    service_type = Column(String(20), nullable=False) # e.g., 'ambulance'
    location = Column(JSON, nullable=False)
    details = Column(JSON, nullable=True)
    notes = Column(String(500), nullable=True)
    status = Column(String(20), default="created")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Create tables on startup
Base.metadata.create_all(bind=engine)

# --- Pydantic Schemas for Internal API ---
class IncidentCreate(BaseModel):
    user_id: str
    service_type: str
    location: dict
    details: dict | None = None
    notes: str | None = None

# --- Endpoints ---

@app.get("/health")
async def health():
    return {"service": "orm_layer", "status": "ok", "port": 8086}

@app.post("/incidents", status_code=status.HTTP_201_CREATED)
async def create_incident(incident: IncidentCreate):
    db = SessionLocal()
    try:
        new_incident = IncidentModel(
            user_id=incident.user_id,
            service_type=incident.service_type,
            location=incident.location,
            details=incident.details,
            notes=incident.notes
        )
        db.add(new_incident)
        db.commit()
        db.refresh(new_incident)
        return {"id": new_incident.id, "status": new_incident.status}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8086)