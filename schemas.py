from typing import Optional, Literal, Union
from pydantic import BaseModel, Field, field_validator


def _clean_number(
    value: Union[str, float, int, None]
) -> Optional[Union[str, float]]:
    """
    Minimal, safe normalization for numeric-like values.

    - Trims whitespace
    - Removes commas
    - Attempts float conversion
    - Preserves non-numeric strings without raising
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    cleaned = value.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return cleaned


# ==================================================
# RAW LLM OUTPUT (UNTRUSTED)
# ==================================================

class RawLLMExtraction(BaseModel):
    """
    Raw extraction coming directly from the LLM.

    Design contract:
    - NO inference
    - NO defaults
    - NO business logic
    - Maximum tolerance for imperfect output
    """

    origin_port: Optional[str] = Field(
        default=None,
        description="Origin port text exactly as mentioned in the email"
    )

    destination_port: Optional[str] = Field(
        default=None,
        description="Destination port text exactly as mentioned in the email"
    )

    incoterm: Optional[str] = Field(
        default=None,
        description="Incoterm explicitly mentioned, if any"
    )

    cargo_weight_kg: Optional[Union[str, float]] = Field(
        default=None,
        description="Cargo weight as extracted (string or number)"
    )

    cargo_cbm: Optional[Union[str, float]] = Field(
        default=None,
        description="Cargo volume as extracted (string or number)"
    )

    is_dangerous: Optional[bool] = Field(
        default=None,
        description="Dangerous goods flag if explicitly indicated"
    )

    @field_validator("cargo_weight_kg", "cargo_cbm", mode="before")
    @classmethod
    def normalize_numeric_fields(
        cls,
        value: Union[str, float, int, None],
    ) -> Optional[Union[str, float]]:
        return _clean_number(value)


# ==================================================
# FINAL NORMALIZED OUTPUT (EVALUATED)
# ==================================================

class FinalExtraction(BaseModel):
    """
    Final normalized extraction after:
    - deterministic Python logic
    - reference resolution
    - business rules

    This model is STRICT and evaluation-facing.
    """

    model_config = {
        "extra": "forbid",
        "validate_assignment": True,
    }

    id: str = Field(
        description="Unique identifier for the processed email"
    )

    product_line: Optional[
        Literal["pl_sea_import_lcl", "pl_sea_export_lcl"]
    ] = Field(
        default=None,
        description="Resolved product line"
    )

    origin_port_code: Optional[str] = Field(
        default=None,
        description="Standardized origin port code"
    )

    origin_port_name: Optional[str] = Field(
        default=None,
        description="Resolved origin port name"
    )

    destination_port_code: Optional[str] = Field(
        default=None,
        description="Standardized destination port code"
    )

    destination_port_name: Optional[str] = Field(
        default=None,
        description="Resolved destination port name"
    )

    incoterm: Optional[str] = Field(
        default=None,
        description="Normalized incoterm (uppercase)"
    )

    cargo_weight_kg: Optional[float] = Field(
        default=None,
        description="Normalized cargo weight in kilograms"
    )

    cargo_cbm: Optional[float] = Field(
        default=None,
        description="Normalized cargo volume in cubic meters"
    )

    is_dangerous: Optional[bool] = Field(
        default=None,
        description="Final dangerous goods flag"
    )

    @field_validator("incoterm", mode="before")
    @classmethod
    def normalize_incoterm(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if isinstance(value, str) else value
