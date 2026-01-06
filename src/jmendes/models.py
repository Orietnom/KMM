from typing import Optional, List
from pydantic import BaseModel

class JMNItemProcess(BaseModel):
    placa: str
    nome_motorista: str
    tbe: str
    natureza: str
    operacao: str
    rota: str
    cartao: str
    remetente: str
    destinatario: str
    peso: str

class JMNItems(BaseModel):
    items: List[JMNItemProcess]
