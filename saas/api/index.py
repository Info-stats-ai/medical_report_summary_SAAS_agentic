import base64
import io
import os
from typing import Optional  # type: ignore

from fastapi import FastAPI, Depends, HTTPException  # type: ignore
from fastapi.responses import StreamingResponse  # type: ignore
from pydantic import BaseModel  # type: ignore
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials  # type: ignore
from openai import OpenAI  # type: ignore
from pypdf import PdfReader  # type: ignore

app = FastAPI()
clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
clerk_guard = ClerkHTTPBearer(clerk_config)


class Visit(BaseModel):
    patient_name: str
    date_of_visit: str
    notes: Optional[str] = None
    file_base64: Optional[str] = None
    file_mime: Optional[str] = None


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