from typing import Optional, List
from pydantic import BaseModel

class ArcelorItemProcess(BaseModel):
    cte_fretolog: str
    serie_fretolog: str
    cte_levolog: Optional[str] = None
    serie_levolog: Optional[str] = None
    transport: str
    driver_name: str
    cte_value: str
    contract_value: str
    center: str
    card_id: str
    bd_id: int
    complement_cte_fretolog: Optional[str] = None
    complement_cte_levolog: Optional[str] = None
    contract: Optional[str] = None

