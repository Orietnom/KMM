from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


REQUIRED_PLATFORM_FIELDS = frozenset({"ID", "XML"})


class XMLDownloadInput(BaseModel):
    row_id: int
    incident_id: str
    center: str
    freto_lot: str
    complement_cte: str
    emitted_at: datetime | None = None

    @field_validator(
        "incident_id",
        "center",
        "freto_lot",
        "complement_cte",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        if value is None or not str(value).strip():
            raise ValueError("campo obrigatório ausente")
        return str(value).strip()

    @classmethod
    def from_sql_payload(cls, payload: dict[str, Any]) -> XMLDownloadInput:
        return cls.model_validate({
            "row_id": payload.get("ID"),
            "incident_id": payload.get("ID_INCIDENTE"),
            "center": payload.get("FILIAL"),
            "freto_lot": payload.get("LOTACAO_FRETOLOG"),
            "complement_cte": payload.get("CTE_FRETOLOG_COMPLEMENTAR"),
            "emitted_at": payload.get("DATA_EMISSAO_CTE_FRETO"),
        })


class XMLDownloadResult(BaseModel):
    filename: str
    uploaded: bool
