import json
import logging
import re
from pathlib import Path
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from config import (
    DEBUG_AI_JSON_DIR,
    FIELD_NAMES,
    GEMINI_API_KEY,
    GEMINI_MAX_RETRIES,
    GEMINI_MODEL_CANDIDATES,
)

_client = None

def get_client():
    global _client
    if not GEMINI_API_KEY:
        return None
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client

def has_gemini_client():
    return bool(GEMINI_API_KEY)

def sanitize_error_text(text):
    return re.sub(r"AIza[0-9A-Za-z_-]+", "AIza...REDACTED", str(text))

# Kept your original filename logic so main.py doesn't break!
def extract_filename_reference(filename):
    stem = Path(filename).stem.upper()
    patterns = [
        r"\bW3-C\d{9}-[A-Z0-9]{2}\b",
        r"\bC\d{4}-\d{3}-[A-Z0-9]+-[A-Z0-9]{2}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, stem)
        if not match:
            continue
        drawing_number = match.group(0)
        revision = drawing_number.rsplit("-", 1)[-1]
        return drawing_number, revision
    return "", ""

def empty_ai_data():
    return {field: "" for field in FIELD_NAMES}

# --- 1. NEW: PYDANTIC SCHEMA (The JSON Blueprint) ---
class TitleBlockSchema(BaseModel):
    Company_Name: str = Field(alias="Company Name", default="")
    Part_Name: str = Field(alias="Part Name", default="")
    Material: str = Field(alias="Material", default="")
    Drawing_Number: str = Field(alias="Drawing Number", default="")
    Revision: str = Field(alias="Revision", default="")

# --- 2. NEW: TENACITY (Automatic Math-Based Retries) ---
@retry(
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(GEMINI_MAX_RETRIES),
    retry=retry_if_exception_type(Exception),
    reraise=True
)
def fetch_ai_extraction(messy_text: str, filename_reference: str):
    client = get_client()
    if client is None:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    # We deleted 80% of your prompt because the Schema handles the rules now!
    prompt = f"""
    Extract title block data from this engineering drawing OCR text.
    Do not translate technical values. Preserve exact text.
    Filename clues (Strongest hint for Drawing Number/Revision): {filename_reference}

    OCR TEXT:
    {messy_text}
    """

    model_name = next(
        (model for model in GEMINI_MODEL_CANDIDATES if str(model or "").strip()),
        "gemini-2.5-flash",
    )

    # --- 3. NEW: STRUCTURED OUTPUTS ---
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TitleBlockSchema, # Forces Gemini to output perfect JSON
            temperature=0.1,
        ),
    )
    return response.text

# --- 4. THE MAIN FUNCTION (Called by main.py) ---
def get_structured_data_with_retries(messy_text, filename):
    filename_drawing_number, filename_revision = extract_filename_reference(filename)
    filename_reference = "None found"
    
    if filename_drawing_number:
        filename_reference = f"Drawing Number: {filename_drawing_number}\nRevision: {filename_revision}"

    try:
        # Call the auto-retrying AI function
        raw_response_text = fetch_ai_extraction(messy_text, filename_reference)

        # Parse the guaranteed JSON using Pydantic
        parsed_data = TitleBlockSchema.model_validate_json(raw_response_text)

        # Convert back to the exact dictionary format your exporter expects
        data = {
            "Company Name": parsed_data.Company_Name,
            "Part Name": parsed_data.Part_Name,
            "Material": parsed_data.Material,
            "Drawing Number": parsed_data.Drawing_Number,
            "Revision": parsed_data.Revision
        }
        return (data, raw_response_text), None

    except Exception as exc:
        logging.error(f"AI extraction permanently failed for {filename}: {exc}")
        return (empty_ai_data(), ""), sanitize_error_text(exc)

# Kept your original debugging function!
def save_ai_debug(stem, data, raw_ai_text, error=None):
    payload = {
        "parsed": data,
        "raw_response": raw_ai_text,
        "error": sanitize_error_text(error) if error else None,
    }
    (DEBUG_AI_JSON_DIR / f"{stem}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
