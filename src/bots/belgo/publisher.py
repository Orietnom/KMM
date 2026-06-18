from src.shared.db_handler.db_handler import DB
from src.bots.belgo.bba_portal import BelgoPortal
import pandas as pd

class Main:
    def __init__(self):
        self.db=DB()

    def get_incidents(self):
        incidents = self.db.get_data('complementar_belgo2', date_range=True)
        bba = BelgoPortal(itens_in_bd=incidents)
        new_incidents = bba.get_incidents_in_bba_portal()
        if not new_incidents:
            return
        df = pd.DataFrame(new_incidents)
        df = df.drop(columns=["pf", "incident_status"])
        df["date"] = pd.to_datetime(
            df["date"],
            format="%d/%m/%Y",
            errors="coerce"  # se vier inválido → vira NaT → depois vai como NULL
        ).dt.date
        df_renamed = df.rename(columns={
            "cte_value": "VALOR_CTE",
            "contract_value": "VALOR_CONTRATO",
            "driver_value": "VALOR_MOTORISTA",
            "nf": "NOTA_FISCAL",
            "id": "ID_INCIDENTE",
            "center": "FILIAL",
            "transport": "TRANSPORTE",
            "subreason": "SUBMOTIVO",
            "cte_levolog_code": "CTE_LEVOLOG",
            "cte_fretolog_code": "CTE_FRETOLOG",
            "serie_levolog": "SERIE_LEVOLOG",
            "serie_fretolog": "SERIE_FRETOLOG",
            "date": "DATA_NOTA",
            "freto_lot": "LOTACAO_FRETOLOG",
            "levo_lot": "LOTACAO_LEVOLOG",
            "number_of_incidents": "N_INCIDENTES"
        })
        df_renamed['STATUS_'] = "Pendente"
        self.db.insert_ignore_df(table='complementar_belgo2', df=df_renamed, unique_keys=['CTE_FRETOLOG'])

if __name__ == '__main__':
    main = Main()
    main.get_incidents()
