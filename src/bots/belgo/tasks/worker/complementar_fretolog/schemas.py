from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator


REQUIRED_CARD_FIELDS = frozenset({
    "ID",
    "Filial",
    "Lotação Fretolog",
    "N CT-e Fretolog",
    "Série CT-e Fretolog",
    "Valor CT-e",
    "N Incidentes",
})

RESULT_CARD_FIELDS = frozenset({
    "Valor Complementar Fretolog",
    "N CT-e Complementar Fretolog",
})


def platform_field_values(payload: dict[str, Any]) -> dict[str, Any]:
    raw_values = payload.get("field_values") or payload.get("fields") or {}
    if isinstance(raw_values, dict):
        return {
            str(name): value.get("value") if isinstance(value, dict) and "value" in value else value
            for name, value in raw_values.items()
        }

    values: dict[str, Any] = {}
    for entry in raw_values if isinstance(raw_values, list) else []:
        if not isinstance(entry, dict):
            continue
        field = entry.get("field")
        field = field if isinstance(field, dict) else {}
        name = entry.get("field_name") or entry.get("name") or field.get("name")
        if name:
            values[str(name)] = entry.get("value")
    return values


class FretologComplementInput(BaseModel):
    incident_id: str
    center: str
    freto_lot: str
    freto_cte: str
    freto_serie: str
    cte_value: float
    number_of_incidents: int
    complement_cte: str | None = None
    complement_value: float | None = None

    @field_validator(
        "incident_id",
        "center",
        "freto_lot",
        "freto_cte",
        "freto_serie",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        if value is None or not str(value).strip():
            raise ValueError("campo obrigatório ausente")
        return str(value).strip()

    @field_validator("complement_cte", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None or not str(value).strip():
            return None
        return str(value).strip()

    @classmethod
    def from_platform_payload(cls, payload: dict[str, Any]) -> FretologComplementInput:
        values = platform_field_values(payload)
        return cls.model_validate({
            "incident_id": values.get("ID"),
            "center": values.get("Filial"),
            "freto_lot": values.get("Lotação Fretolog"),
            "freto_cte": values.get("N CT-e Fretolog"),
            "freto_serie": values.get("Série CT-e Fretolog"),
            "cte_value": values.get("Valor CT-e"),
            "number_of_incidents": values.get("N Incidentes"),
            "complement_cte": values.get("N CT-e Complementar Fretolog"),
            "complement_value": values.get("Valor Complementar Fretolog"),
        })


class FretologComplementResult(BaseModel):
    cte_number: str
    net_value: float
    resumed_from_sql: bool = False
