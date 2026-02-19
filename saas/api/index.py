import base64
import io
import os
import uuid
from contextlib import contextmanager
from typing import Optional  # type: ignore

import psycopg2  # type: ignore
from fastapi import FastAPI, Depends, HTTPException  # type: ignore
from fastapi.responses import StreamingResponse  # type: ignore
from pydantic import BaseModel  # type: ignore
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials  # type: ignore
from openai import OpenAI  # type: ignore
from pypdf import PdfReader  # type: ignore

app = FastAPI()

# Postgres: use POSTGRES_URL or DATABASE_URL
def _get_postgres_url() -> Optional[str]:
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

def ensure_history_table(conn) -> None:
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

def save_history_entry(conn, user_id: str, patient_name: str, date_of_visit: str, summary: str) -> str:
    ensure_history_table(conn)
    entry_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO consultation_history (id, user_id, patient_name, date_of_visit, summary) VALUES (%s, %s, %s, %s, %s)",
            (entry_id, user_id, patient_name, date_of_visit, summary),
        )
    return entry_id

def list_history_for_user(conn, user_id: str, limit: int = 50):
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
clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
clerk_guard = ClerkHTTPBearer(clerk_config)


class Visit(BaseModel):
    patient_name: str
    date_of_visit: str
    notes: Optional[str] = None
    file_base64: Optional[str] = None
    file_mime: Optional[str] = None


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


def extract_text_from_pdf(b64: str) -> str:
    raw = base64.b64decode(b64)
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text_from_image(client: OpenAI, b64: str, mime: str = "image/jpeg") -> str:
    """Use OpenAI vision to extract text from an image (e.g. photo of notes)."""
    data_url = f"data:{mime};base64,{b64}"
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract all text visible in this image. If it contains handwritten or typed medical or consultation notes, transcribe them exactly. Return only the extracted text, no commentary.",
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        max_tokens=4096,
    )
    return (resp.choices[0].message.content or "").strip()


def resolve_notes(visit: Visit, client: OpenAI) -> str:
    """Combine form notes with text extracted from optional PDF/image file."""
    parts = []
    if visit.notes and visit.notes.strip():
        parts.append(visit.notes.strip())
    if visit.file_base64 and visit.file_mime:
        if "pdf" in (visit.file_mime or "").lower():
            parts.append(extract_text_from_pdf(visit.file_base64))
        elif "image" in (visit.file_mime or "").lower():
            parts.append(extract_text_from_image(client, visit.file_base64, visit.file_mime or "image/jpeg"))
    if not parts:
        raise ValueError("Provide either consultation notes (text) or a PDF/image file.")
    return "\n\n--- From file ---\n\n".join(parts) if len(parts) > 1 else parts[0]


def user_prompt_for(patient_name: str, date_of_visit: str, notes_text: str) -> str:
    return f"""Create the summary, next steps and draft email for:
Patient Name: {patient_name}
Date of Visit: {date_of_visit}
Notes:
{notes_text}"""


def is_premium(creds: HTTPAuthorizationCredentials) -> bool:
    """Check if user has premium_subscription from Clerk JWT 'pla' claim (e.g. u:premium_subscription)."""
    pla = creds.decoded.get("pla") or ""
    return "premium_subscription" in pla


@app.post("/api")
def consultation_summary(
    visit: Visit,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded["sub"]  # Available for tracking/auditing
    client = OpenAI()

    try:
        notes_text = resolve_notes(visit, client)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    model = "gpt-5" if is_premium(creds) else "gpt-4o-mini"

    user_prompt = user_prompt_for(visit.patient_name, visit.date_of_visit, notes_text)

    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    stream = client.chat.completions.create(
        model=model,
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
def create_history_entry(
    body: HistoryEntryCreate,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    """Save a consultation summary to Postgres (call after stream completes)."""
    user_id = creds.decoded["sub"]
    try:
        with get_db() as conn:
            entry_id = save_history_entry(
                conn, user_id, body.patient_name, body.date_of_visit, body.summary
            )
        return {"id": entry_id, "ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history")
def get_history(creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    """List current user's consultation history from Postgres."""
    user_id = creds.decoded["sub"]
    try:
        with get_db() as conn:
            entries = list_history_for_user(conn, user_id)
        return {"history": entries}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))