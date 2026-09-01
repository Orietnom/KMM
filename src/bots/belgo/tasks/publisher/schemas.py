from __future__ import annotations

import json
import os
from datetime import date as Date
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CaptureRoute(str, Enum):
    PROCESSABLE = "processable"
    PENDING = "pending"


class BelgoIncident(BaseModel):
    id: str
    center: str | None = None
    transport: str | None = None
    subreason: str | None = None
    cte_attempt: str | None = None
    cte_value: str | None = None
    contract_value: str | None = None
    driver_value: float | None = None
    nf: str | None = None
    cte_levolog_code: str | None = None
    cte_fretolog_code: str | None = None
    serie_levolog: str | None = None
    serie_fretolog: str | None = None
    date: Date | None = None
    case_date: Date | None = None
    freto_lot: str | None = None
    levo_lot: str | None = None
    number_of_incidents: int | None = None
    pf: bool | None = None
    incident_status: bool | None = None
    error_reasons: list[str] = Field(default_factory=list)

    @field_validator("date", "case_date", mode="before")
    @classmethod
    def normalize_date(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, Date):
            return value
        date_part = str(value).strip().split()[0]
        if "/" in date_part:
            day, month, year = (int(part) for part in date_part.split("/"))
            return Date(year, month, day)
        return Date.fromisoformat(date_part)

    @property
    def route(self) -> CaptureRoute:
        return CaptureRoute.PENDING if self.error_reasons else CaptureRoute.PROCESSABLE

    def validate_processable(self) -> None:
        required = {
            "center": self.center,
            "transport": self.transport,
            "subreason": self.subreason,
            "cte_value": self.cte_value,
            "contract_value": self.contract_value,
            "driver_value": self.driver_value,
            "nf": self.nf,
            "cte_fretolog_code": self.cte_fretolog_code,
            "serie_fretolog": self.serie_fretolog,
            "date": self.date,
            "freto_lot": self.freto_lot,
            "number_of_incidents": self.number_of_incidents,
        }
        missing = [name for name, value in required.items() if value in (None, "")]
        if missing:
            raise ValueError(f"Incidente {self.id} incompleto: {', '.join(missing)}")

    def to_sql_record(self) -> dict[str, Any]:
        self.validate_processable()
        return {
            "VALOR_CTE": self.cte_value,
            "VALOR_CONTRATO": self.contract_value,
            "VALOR_MOTORISTA": self.driver_value,
            "NOTA_FISCAL": self.nf,
            "ID_INCIDENTE": self.id,
            "FILIAL": self.center,
            "TRANSPORTE": self.transport,
            "SUBMOTIVO": self.subreason,
            "CTE_LEVOLOG": self.cte_levolog_code,
            "CTE_FRETOLOG": self.cte_fretolog_code,
            "SERIE_LEVOLOG": self.serie_levolog,
            "SERIE_FRETOLOG": self.serie_fretolog,
            "DATA_NOTA": self.date,
            "LOTACAO_FRETOLOG": self.freto_lot,
            "LOTACAO_LEVOLOG": self.levo_lot,
            "N_INCIDENTES": self.number_of_incidents,
            "STATUS_": "Pendente",
        }

    def card_title(self) -> str:
        transport = f" - Transporte {self.transport}" if self.transport else ""
        return f"BELGO #{self.id}{transport}"

    def to_card_fields(self) -> dict[str, Any]:
        values = {
            "incident_id": self.id,
            "transport": self.transport,
            "branch": self.center,
            "subreason": self.subreason,
            "case_date": self.case_date.isoformat() if self.case_date else None,
            "cte_value": float(self.cte_value) if self.cte_value is not None else None,
            "contract_value": float(self.contract_value) if self.contract_value is not None else None,
            "driver_value": self.driver_value,
            "invoice": self.nf,
            "fretolog_cte": self.cte_fretolog_code,
            "fretolog_series": self.serie_fretolog,
            "levolog_cte": self.cte_levolog_code,
            "levolog_series": self.serie_levolog,
            "invoice_date": self.date.isoformat() if self.date else None,
            "fretolog_location": self.freto_lot,
            "levolog_location": self.levo_lot,
            "incident_count": self.number_of_incidents,
            "incident_status": self.incident_status,
        }
        field_map = platform_field_map()
        allowed_fields = (
            GLOBAL_WORKFLOW_FIELD_KEYS
            if self.route is CaptureRoute.PENDING
            else ALL_PROCESSABLE_FIELD_KEYS
        )
        return {
            field_map[logical_name]: value
            for logical_name, value in values.items()
            if logical_name in allowed_fields and value not in (None, "")
        }


class BelgoPortalResult(BaseModel):
    processable: list[BelgoIncident] = Field(default_factory=list)
    pending: list[BelgoIncident] = Field(default_factory=list)

    @property
    def all(self) -> list[BelgoIncident]:
        return [*self.processable, *self.pending]


DEFAULT_PLATFORM_FIELD_MAP = {
    "incident_id": "ID",
    "transport": "Transporte",
    "subreason": "Submotivo",
    "case_date": "Data Caso",
    "cte_value": "Valor CT-e",
    "contract_value": "Valor Contrato",
    "driver_value": "Valor Motorista",
    "invoice": "Nota Fiscal",
    "branch": "Filial",
    "levolog_cte": "N CT-e Levolog",
    "fretolog_cte": "N CT-e Fretolog",
    "levolog_series": "Série CT-e Levolog",
    "fretolog_series": "Série CT-e Fretolog",
    "invoice_date": "Data Nota",
    "fretolog_location": "Lotação Fretolog",
    "levolog_location": "Lotação Levolog",
    "incident_count": "N Incidentes",
    "incident_status": "Status do Incidente",
}

GLOBAL_WORKFLOW_FIELD_KEYS = frozenset({
    "incident_id",
    "transport",
    "subreason",
    "case_date",
})

PROCESSABLE_PHASE_FIELD_KEYS = frozenset(DEFAULT_PLATFORM_FIELD_MAP) - GLOBAL_WORKFLOW_FIELD_KEYS
ALL_PROCESSABLE_FIELD_KEYS = GLOBAL_WORKFLOW_FIELD_KEYS | PROCESSABLE_PHASE_FIELD_KEYS

WORKFLOW_TO_SOURCE_FIELD: dict[str, str | None] = {
    "ID": "ID_INCIDENTE",
    "Transporte": "TRANSPORTE",
    "Submotivo": "SUBMOTIVO",
    "Data Caso": None,
    "Valor CT-e": "VALOR_CTE",
    "Valor Contrato": "VALOR_CONTRATO",
    "Valor Motorista": "VALOR_MOTORISTA",
    "Nota Fiscal": "NOTA_FISCAL",
    "Filial": "FILIAL",
    "N CT-e Levolog": "CTE_LEVOLOG",
    "N CT-e Fretolog": "CTE_FRETOLOG",
    "Série CT-e Levolog": "SERIE_LEVOLOG",
    "Série CT-e Fretolog": "SERIE_FRETOLOG",
    "Data Nota": "DATA_NOTA",
    "Lotação Fretolog": "LOTACAO_FRETOLOG",
    "Lotação Levolog": "LOTACAO_LEVOLOG",
    "N Incidentes": "N_INCIDENTES",
    "Status do Incidente": None,
    "N CT-e Complementar Fretolog": None,
    "Valor Complementar Fretolog": None,
    "N CT-e Complementar Levolog": None,
    "Valor Complementar Levolog": None,
    "N Contrato": None,
    "XML": None,
}


def platform_field_map() -> dict[str, str]:
    raw = os.getenv("BELGO_PLATFORM_FIELD_MAP", "").strip()
    if not raw:
        return DEFAULT_PLATFORM_FIELD_MAP
    overrides = json.loads(raw)
    if not isinstance(overrides, dict):
        raise TypeError("BELGO_PLATFORM_FIELD_MAP deve ser um objeto JSON")
    result = {**DEFAULT_PLATFORM_FIELD_MAP, **{str(key): str(value) for key, value in overrides.items()}}
    missing = set(DEFAULT_PLATFORM_FIELD_MAP) - set(result)
    if missing:
        raise ValueError(f"Mapeamento Platform incompleto: {sorted(missing)}")
    return result
