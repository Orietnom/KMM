from typing import Optional, List
from pydantic import BaseModel

class JMNItemProcess(BaseModel):
    license_plate: str
    driver_name: str
    tbe: str
    nature: str
    operation: str
    route: str
    card: str
    sender: str
    recipient: str
    contract_value: str
    bd_id: int
    management: str
    contract: Optional[str] = None

class JMNItems(BaseModel):
    items: List[JMNItemProcess]
