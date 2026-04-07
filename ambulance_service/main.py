from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field
import httpx
import datetime
import os

# Import the background task
from tasks import send_ambulance_alert_email

app = FastAPI(
    title="Road SOS — Ambulance Service", 
    version="1.0.0",
    description="Microservice handling medical emergency requests on Port 8082"
)

# Configuration from Environment Variables (set in docker-compose.yml)
ORM_SERVICE_URL = os.getenv("ORM_SERVICE_URL", "http://orm-layer:8086")

# --- Pydantic Schemas (Aligned with road_sos_openapi.yaml) ---

class GpsLocation(BaseModel):
    lat: float = Field(..., ge=-90, le=90, example=13.0827)
    lng: float = Field(..., ge=-180, le=180, example=80.2707)
    accuracy_metres: float = Field(..., example=5.0)
    captured_at: datetime.datetime

class PatientDetails(BaseModel):
    name: str | None = Field(None, example="Arjun V")
    age: int | None = Field(None, ge=0, le=130, example=28)
    is_conscious: bool = Field(...)
    has_visible_bleeding: bool = Field(False)
    known_condition: str | None = Field(None, example="Diabetic")
    people_injured: int = Field(1, ge=1)

class AmbulanceRequest(BaseModel):
    user_id: str = Field(..., example="usr_01HZQ2")
    location: GpsLocation
    patient: PatientDetails
    additional_notes: str | None = None

# --- Endpoints ---

@app.get("/api/v1/ambulance/health")
async def health():
    """Service health check for Docker/Kubernetes liveness probes"""
    return {
        "service": "ambulance_service", 
        "status": "ok", 
        "port": 8082,
        "timestamp": datetime.datetime.now()
    }

@app.post("/api/v1/ambulance/request", status_code=status.HTTP_201_CREATED)
async def request_ambulance(payload: AmbulanceRequest, authorization: str = Header(None)):
    """
    Main SOS endpoint for Ambulance requests.
    1. Validates JWT (simulated)
    2. Persists data to ORM Layer (Synchronous)
    3. Triggers Email Alert via Celery/Redis (Asynchronous)
    """
    
    # 1. JWT Validation check (as required by specification)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Token is missing or has expired."
        )

    # 2. Persist to ORM Data Layer (Port 8086)
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            orm_payload = {
                "user_id": payload.user_id,
                "service_type": "ambulance",
                "location": payload.location.model_dump(),
                "details": payload.patient.model_dump(),
                "notes": payload.additional_notes
            }
            
            # Internal call to the shared data layer
            orm_resp = await client.post(f"{ORM_SERVICE_URL}/incidents", json=orm_payload)
            orm_resp.raise_for_status()
            incident_id = orm_resp.json().get("id")

        except httpx.HTTPStatusError:
            raise HTTPException(status_code=500, detail="ORM Layer: Failed to save incident")
        except Exception:
            raise HTTPException(status_code=503, detail="ORM Layer: Service Unavailable")

    # 3. Dispatch Background Alert via Celery & Redis
    # This does NOT wait for the email to send, keeping latency < 100ms
    send_ambulance_alert_email.delay(
        incident_id=incident_id,
        patient_name=payload.patient.name or "Unknown",
        lat=payload.location.lat,
        lng=payload.location.lng
    )

    # 4. Final Success Response
    return {
        "success": True,
        "incident_id": incident_id,
        "message": f"Ambulance requested successfully. Incident ID: {incident_id}"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)