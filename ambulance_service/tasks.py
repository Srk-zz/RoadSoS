import os
import httpx
from celery import Celery
import logging

# Setup basic logging to see worker activity in Docker logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. Initialize Celery
# The broker URL points to the 'redis' service name defined in docker-compose
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
EMAIL_SERVICE_URL = os.getenv("EMAIL_SERVICE_URL", "http://email-service:8085")

celery_app = Celery(
    "ambulance_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Optional configuration for reliability
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_acks_late=True,          # Task is acknowledged only after execution
    worker_prefetch_multiplier=1  # One task at a time per worker for reliability
)

@celery_app.task(
    bind=True, 
    max_retries=5, 
    default_retry_delay=60,
    name="tasks.send_ambulance_alert_email"
)
def send_ambulance_alert_email(self, incident_id, patient_name, lat, lng):
    """
    Background task to notify the Email Service about a new Ambulance SOS.
    Retries automatically if the Email Service is temporarily unreachable.
    """
    logger.info(f"Processing background email alert for Incident: {incident_id}")

    email_payload = {
        "incident_id": incident_id,
        "to": "ambulance.dispatch@mock.roadsos.in",
        "template_name": "ambulance_alert",
        "context": {
            "incident_id": incident_id,
            "patient_name": patient_name,
            "lat": lat,
            "lng": lng
        }
    }

    try:
        # Use a synchronous httpx client inside the Celery worker
        with httpx.Client(timeout=10.0) as client:
            response = client.post(f"{EMAIL_SERVICE_URL}/send", json=email_payload)
            response.raise_for_status()
            
            logger.info(f"Successfully dispatched email alert for {incident_id}")
            return {"status": "sent", "incident_id": incident_id}

    except httpx.HTTPStatusError as exc:
        logger.error(f"Email service returned error {exc.response.status_code} for {incident_id}")
        # Retry if it's a server error (5xx)
        if exc.response.status_code >= 500:
            raise self.retry(exc=exc)
        return {"status": "failed", "reason": "Client error at email service"}

    except Exception as exc:
        logger.error(f"Network error connecting to email service: {str(exc)}")
        # Retry for network timeouts or connection refused
        raise self.retry(exc=exc)