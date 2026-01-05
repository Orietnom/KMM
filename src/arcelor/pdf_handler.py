import pdfplumber
import re

def read_pdf(arquivo):

    with pdfplumber.open(arquivo) as pdf:
        pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    maior = 0
    index = 0

    price_num = re.findall(r"(?:VALOR A RECEBER\n*)([0-9][.0-9]+,[0-9]{2})", pdf_text)

    cte_number = re.findall(r"(?:DATA./.HORA\n*)([0-9]+)", pdf_text)

    serie = re.findall(r"(?:DATA./.HORA\n*[0-9]+.)([0-9]{1})", pdf_text)

    for i, item in enumerate(price_num):
        valor = item.replace(".", '')
        valor = valor.replace(",", '.')
        valor = float(valor)
        if valor >= maior:
            maior = valor
            index = i

    cte_value = cte_number[index]
    cte_serie =  serie[index]
    return cte_value, cte_serie
