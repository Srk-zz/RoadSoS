from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr
from jinja2 import Environment, FileSystemLoader
import datetime
import os

app = FastAPI(title="Road SOS — Email Dispatcher", version="1.0.0")

# Setup Jinja2 for HTML templates
template_env = Environment(loader=FileSystemLoader("templates"))

class EmailRequest(BaseModel):
    incident_id: str
    to: EmailStr
    template_name: str
    context: dict

@app.get("/health")
async def health():
    return {"service": "email_service", "status": "ok", "port": 8085}

@app.post("/send", status_code=202)
async def send_email(request: EmailRequest):
    """
    Receives email requests from other microservices.
    In a real scenario, this connects to AWS SES, SendGrid, or an SMTP server.
    """
    try:
        # 1. Load the requested template (e.g., ambulance_alert.html)
        template = template_env.get_template(f"{request.template_name}.html")
        
        # 2. Render HTML with the context provided (Patient name, GPS, etc.)
        html_content = template.render(**request.context, timestamp=datetime.datetime.now())
        
        # 3. MOCK SEND: In production, use a library like 'emails' or 'aiosmtplib'
        print(f"--- SENDING EMAIL ---")
        print(f"To: {request.to}")
        print(f"Subject: EMERGENCY ALERT - {request.incident_id}")
        print(f"Content Preview: {html_content[:100]}...")
        print(f"----------------------")
        
        return {"success": True, "message": "Email queued for delivery"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8085)