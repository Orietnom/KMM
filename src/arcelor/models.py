from typing import Optional, List
from pydantic import BaseModel

class ArcelorItemProcess(BaseModel):
    cte_fretolog: str
    serie_fretolog: str
    cte_levolog: Optional[str] = None
    serie_levolog: Optional[str] = None
    transport: str
    driver_name: str
    cte_value_fretolog: str
    cte_value_levolog: str
    contract_value: str
    center: str

class JMNItems(BaseModel):
    items: List[ArcelorItemProcess]
