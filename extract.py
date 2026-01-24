from __future__ import annotations
import json
import os
import re
import time
from typing import Optional, List, Dict, Tuple, Any, Literal
from dotenv import load_dotenv
from groq import Groq
from schemas import RawLLMExtraction, FinalExtraction
from prompts import PROMPT_V3

load_dotenv()

# ENV & CONFIG
EMAILS_PATH: str = "emails_input.json"
PORT_CODES_PATH: str = "port_codes_reference.json"
OUTPUT_PATH: str = "output3.json"
MODEL_NAME: str = "llama-3.3-70b-versatile"

GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
if GROQ_API_KEY is None:
    raise RuntimeError("GROQ_API_KEY not set")
client: Groq = Groq(api_key=GROQ_API_KEY)


# IO HELPERS
def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


emails: List[Dict[str, str]] = load_json(EMAILS_PATH)
port_codes: List[Dict[str, str]] = load_json(PORT_CODES_PATH)


# UTILS
def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


def clean_number(value: str | float | None) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    cleaned = value.replace(",", "").strip()
    return float(cleaned) if cleaned else None


# LLM CALL (RETRY SAFE)
def call_llm(
    subject: str,
    body: str,
    retries: int = 3,
) -> Optional[Dict[str, Any]]:
    prompt = PROMPT_V3.format(subject=subject, body=body)

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )

            content: str | None = response.choices[0].message.content
            if not content:
                raise ValueError("Empty LLM response")

            return json.loads(strip_code_fences(content))

        except Exception as exc:
            print(f"LLM error (attempt {attempt + 1}): {exc}")
            time.sleep(2 ** attempt)

    return None


# PORT RESOLUTION
def resolve_exact_port(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not raw:
        return None, None

    norm = raw.lower().strip()

    for port in port_codes:
        if norm == port["name"].lower():
            return port["code"], port["name"]

    return None, None


def resolve_origin(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not raw:
        return None, None

    text = raw.lower()

    # Explicit business rule
    if all(k in text for k in ("jed", "dam", "ruh")):
        return "SAJED", "Jeddah / Dammam / Riyadh"

    return resolve_exact_port(raw)


def resolve_destination(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    return resolve_exact_port(raw)


# PRODUCT LINE
InternalProductLine = Literal[
    "pl_sea_import_lcl",
    "pl_sea_export_lcl",
]


def resolve_product_line(
    subject: str,
    origin_code: Optional[str],
) -> InternalProductLine:
    subj = subject.lower()

    if "export" in subj:
        return "pl_sea_export_lcl"

    if "import" in subj:
        return "pl_sea_import_lcl"

    if origin_code and origin_code.startswith("IN"):
        return "pl_sea_export_lcl"

    return "pl_sea_import_lcl"


# REVENUE TON HANDLING
def resolve_weight_cbm_from_revenue_ton(
    body: str,
    weight: Optional[float],
    cbm: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    """
    Fallback logic:
    If both weight and CBM are missing, attempt to derive them from
    Revenue Ton (RT) mentioned in the email body.

    In LCL freight:
    - 1 RT = 1 CBM
    """
    if weight is not None or cbm is not None:
        return weight, cbm

    match = re.search(r"([\d.]+)\s*rt", body, re.IGNORECASE)
    if not match:
        return None, None

    revenue_ton = float(match.group(1))

    cbm_val = revenue_ton
    kg_val = revenue_ton * (1147 if revenue_ton < 1 else 1000)

    return kg_val, cbm_val


# EMAIL PROCESSING
def process_email(email: Dict[str, str]) -> FinalExtraction:
    llm_out = call_llm(email["subject"], email["body"])
    if llm_out is None:
        return FinalExtraction(id=email["id"])

    raw = RawLLMExtraction(**llm_out)

    origin_code, origin_name = resolve_origin(raw.origin_port)
    dest_code, dest_name = resolve_destination(raw.destination_port)

    product_line = resolve_product_line(email["subject"], origin_code)

    incoterm = raw.incoterm if raw.incoterm else "FOB"

    weight = clean_number(raw.cargo_weight_kg)
    cbm = clean_number(raw.cargo_cbm)

    weight, cbm = resolve_weight_cbm_from_revenue_ton(email["body"], weight, cbm)

    return FinalExtraction(
        id=email["id"],
        product_line=product_line,
        origin_port_code=origin_code,
        origin_port_name=origin_name,
        destination_port_code=dest_code,
        destination_port_name=dest_name,
        incoterm=incoterm,
        cargo_weight_kg=weight,
        cargo_cbm=cbm,
        is_dangerous=raw.is_dangerous is True,
    )


# MAIN
def main() -> None:
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            results: List[Dict[str, Any]] = json.load(f)
    else:
        results = []

    for email in emails:
        extraction = process_email(email)
        results.append(extraction.model_dump())

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        print(f"Processed {email['id']}")

    print(f"Extraction completed → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()