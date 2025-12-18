import re
from typing import Optional


def find_management(management: str, freto_lotation: Optional[str], levolog_lotation: Optional[str]) -> str:
    management = management.lower().lstrip()
        
    if 'freto' in management:
        if not freto_lotation:
            raise "Não foi enviado qual a Lotação da Fretolog"
        
        freto_lotation = freto_lotation.lower().lstrip()
        center = re.findall(r'^\w+',freto_lotation)[0]
        if 'mg' in center:
            return 'FRETO LOG - MG'
        elif 'rj' in center:
            vallue = 'FRETO LOG - FILIAL RJ'
        else:
            return 'FRETO LOG - MATRIZ'
    
    else:
        if not levolog_lotation:
            raise "Não foi enviado qual a Lotação da Levolog"
        
        levolog_lotation = levolog_lotation.lower().lstrip()
        if 'rj' in levolog_lotation or 'sp' in levolog_lotation:
            return 'LEVO LOG - MATRIZ SP'
        elif 'mg' in levolog_lotation:
            return 'LEVO LOG - FILIAL MG'
        else:
            raise f"Falha ao encontrar a filial para {levolog_lotation}"