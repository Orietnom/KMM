from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator


REQUIRED_PLATFORM_FIELDS = frozenset({
    "ID",
    "Valor Complementar Fretolog",
    "N CT-e Complementar Fretolog",
})


class FretologComplementInput(BaseModel):
    row_id: int
    incident_id: str
    center: str
    freto_lot: str
    freto_cte: str
    freto_serie: str
    cte_value: float
    number_of_incidents: int
    complement_cte: str | None = None

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
    def from_sql_payload(cls, payload: dict[str, Any]) -> FretologComplementInput:
        return cls.model_validate({
            "row_id": payload.get("ID"),
            "incident_id": payload.get("ID_INCIDENTE"),
            "center": payload.get("FILIAL"),
            "freto_lot": payload.get("LOTACAO_FRETOLOG"),
            "freto_cte": payload.get("CTE_FRETOLOG"),
            "freto_serie": payload.get("SERIE_FRETOLOG"),
            "cte_value": payload.get("VALOR_CTE"),
            "number_of_incidents": payload.get("N_INCIDENTES"),
            "complement_cte": payload.get("CTE_FRETOLOG_COMPLEMENTAR"),
        })


class FretologComplementResult(BaseModel):
    cte_number: str
    net_value: float | None = None
    resumed_from_sql: bool = False
