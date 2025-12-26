import re
from typing import Optional


def find_management(management: str, lotation: str) -> str:
    if not lotation:
        raise "Não foi enviado qual a Lotação da Fretolog"
    lotation = lotation.lower().lstrip()
    management = management.lower().lstrip()

    if 'freto' in management:
        center = re.findall(r'^\w+',lotation)[0]
        if 'mg' in center:
            return 'FRETO LOG - MG'
        elif 'rj' in center:
            return 'FRETO LOG - FILIAL RJ'
        else:
            return 'FRETO LOG - MATRIZ'
    
    else:
        if 'rj' in lotation or 'sp' in lotation:
            return 'LEVO LOG - MATRIZ SP'
        elif 'mg' in lotation:
            return 'LEVO LOG - FILIAL MG'
        else:
            raise f"Falha ao encontrar a filial para {lotation}"