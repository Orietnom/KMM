import re

def str_to_float(text: str) -> float:
    if not text:
        raise ValueError("Texto vazio")

    cleaned = re.sub(r"[^\d.,]", "", text)

    if not cleaned:
        raise ValueError("Nenhum número encontrado")

    if cleaned.count(",") == 1 and cleaned.rfind(",") > cleaned.rfind("."):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")

    return float(cleaned)