import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials
from openai import OpenAI

app = FastAPI()

# Add CORS middleware (allows frontend to call backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Clerk authentication setup
clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
clerk_guard = ClerkHTTPBearer(clerk_config)

def _get_postgres_url():
    return os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")

@contextmanager
def get_db():
    url = _get_postgres_url()
    if not url:
        raise HTTPException(status_code=503, detail="Database not configured (set POSTGRES_URL or DATABASE_URL)")
    conn = psycopg2.connect(url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def ensure_history_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS consultation_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                patient_name TEXT NOT NULL,
                date_of_visit DATE NOT NULL,
                summary TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)

def save_history_entry(conn, user_id, patient_name, date_of_visit, summary):
    ensure_history_table(conn)
    entry_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO consultation_history (id, user_id, patient_name, date_of_visit, summary) VALUES (%s, %s, %s, %s, %s)",
            (entry_id, user_id, patient_name, date_of_visit, summary),
        )
    return entry_id

def list_history_for_user(conn, user_id, limit=50):
    ensure_history_table(conn)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, patient_name, date_of_visit, summary, created_at
               FROM consultation_history WHERE user_id = %s ORDER BY created_at DESC LIMIT %s""",
            (user_id, limit),
        )
        rows = cur.fetchall()
    return [
        {"id": str(r[0]), "patient_name": r[1], "date_of_visit": str(r[2]), "summary": r[3], "created_at": r[4].isoformat()}
        for r in rows
    ]

class Visit(BaseModel):
    patient_name: str
    date_of_visit: str
    notes: str

class HistoryEntryCreate(BaseModel):
    patient_name: str
    date_of_visit: str
    summary: str

system_prompt = """
You are provided with notes written by a doctor from a patient's visit.
Your job is to summarize the visit for the doctor and provide an email.
Reply with exactly three sections with the headings:
### Summary of visit for the doctor's records
### Next steps for the doctor
### Draft of email to patient in patient-friendly language
"""

def user_prompt_for(visit: Visit) -> str:
    return f"""Create the summary, next steps and draft email for:
Patient Name: {visit.patient_name}
Date of Visit: {visit.date_of_visit}
Notes:
{visit.notes}"""

@app.post("/api/consultation")
def consultation_summary(
    visit: Visit,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded["sub"]
    client = OpenAI()
    
    user_prompt = user_prompt_for(visit)
    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    stream = client.chat.completions.create(
        model="gpt-5-nano",
        messages=prompt,
        stream=True,
    )
    
    def event_stream():
        for chunk in stream:
            text = chunk.choices[0].delta.content
            if text:
                lines = text.split("\n")
                for line in lines[:-1]:
                    yield f"data: {line}\n\n"
                    yield "data:  \n"
                yield f"data: {lines[-1]}\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/api/history")
def create_history_entry(body: HistoryEntryCreate, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded["sub"]
    try:
        with get_db() as conn:
            entry_id = save_history_entry(conn, user_id, body.patient_name, body.date_of_visit, body.summary)
        return {"id": entry_id, "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
def get_history(creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded["sub"]
    try:
        with get_db() as conn:
            entries = list_history_for_user(conn, user_id)
        return {"history": entries}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    """Health check endpoint for AWS App Runner"""
    return {"status": "healthy"}

# Serve static files (our Next.js export) - MUST BE LAST!
static_path = Path("static")
if static_path.exists():
    # Serve index.html for the root path
    @app.get("/")
    async def serve_root():
        return FileResponse(static_path / "index.html")
    
    # Mount static files for all other routes
    app.mount("/", StaticFiles(directory="static", html=True), name="static")