from typing import Optional, List
from pydantic import BaseModel

class BelgoItemProcess(BaseModel):
    bd_id: int
    transport: str
    center: str
    freto_lot: str
    levo_lot: Optional[str] = None
    nf: str
    submotive: str
    cte_value: str
    contract_value: str
    driver_value: str
    freto_cte: str
    freto_serie: str
    levo_cte: Optional[str] = None
    levo_serie: Optional[str] = None
    n_incidents: int
    incident_id: str