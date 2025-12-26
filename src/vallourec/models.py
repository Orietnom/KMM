from typing import Optional, List
from pydantic import BaseModel

class VallourecItemProcess(BaseModel):
    license_plate: str
    driver_name: str
    tbe: str
    nature: str
    operation: str
    route: str
    card: str
    sender: str
    recipient: str
    weight: str

class JMNItems(BaseModel):
    items: List[VallourecItemProcess]
