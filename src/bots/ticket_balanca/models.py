from pydantic import BaseModel, field_validator, field_serializer
from typing import Union, Optional

from datetime import datetime


class Ticket(BaseModel):
    ticket_number: int
    plate: str
    client_name: str
    material: str
    emitting_date: datetime
    status: str
    gross_weight: str
    tare_weight: str
    net_weight: str
    ton_weight: str
    destiny: str
    origin: str
    operator: str
    shipping_company: str
    cancel_date: Optional[datetime]  # Optional[str]
    cancel_motive: Union[int, str]

    @field_validator("emitting_date", "cancel_date", mode='before')
    def parse_date(cls, v):
        if not v:
            return v
        v_formated = datetime.fromisoformat(v.split('.', 1)[0])
        return v_formated
        # return v_formated.strftime("%d/%m/%Y %H:%M")

    @field_validator("plate", mode='before')
    def parse_plate(cls, v):
        return v.replace("-", "")

    @field_validator("ton_weight", mode="before")
    @classmethod
    def parse_weight(cls, v):
        s = v.replace(",", "").replace(".", ",")
        return s
