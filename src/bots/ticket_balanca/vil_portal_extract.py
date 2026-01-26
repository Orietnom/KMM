from playwright.sync_api import Playwright
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Any, Tuple, Iterable

from src.shared.logger import logger
from models import Ticket

import email_handler
import pandas as pd
import win32com.client as win32
import os
import time
import requests


load_dotenv()


class ExtractVilPortal:
    output_path = Path.cwd() / 'output'

    def __init__(self, p: Playwright):
        self.p = p
        self._playwright_setup()
        self.config = vault.get_secret("ticketBalancaConfig")
        self.makedirs()

    def makedirs(self):
        self.output_path.mkdir(exist_ok=True)

    def _playwright_setup(self):

        self.browser = self.p.chromium.launch(headless=False)
        self.context = self.browser.new_context(storage_state=None, accept_downloads=True)

        self.context.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
        })

        self.page = self.context.new_page()

    def _restart_browser(self, timeout):
        self.page.close()
        time.sleep(timeout)
        self._playwright_setup()

    def login(self, tries: int = 3, lazy: int = 5):

        logger.info(f"Realizando login no portal Vil: {self.config['Home']}")
        for login_try in range(tries):
            try:
                self.page.goto(self.config['Home'], timeout=120000)
                self.page.fill('id=Username', value=self.config['Login'])
                self.page.fill('id=Password', value=self.config['Senha'])

                self.page.locator("[name=button]").click()
                time.sleep(5)
                confirm_login = self.page.get_by_text("Balanças")
                if confirm_login.count():
                    logger.success("Login realizado com sucesso")
                    break
                else:
                    raise Exception
            except Exception:
                screenshot_file = self.output_path / f"{datetime.now().strftime('%d%m%Y_%H-%M-%S')}.png"
                self.page.screenshot(type='png', path=screenshot_file)
                if login_try < 2:
                    logger.warning(f'Falha ao logar. Tentativa {login_try + 1}')
                    self._restart_browser(lazy)
                    continue
                else:
                    raise Exception("Falha ao logar após 3 tentativas")

    def get_tickets(self):
        logger.info("Obtendo os dados")
        self.page.goto(self.config['Ticket URL'], timeout=120000)
        time.sleep(10)

        init_date = (datetime.now() - timedelta(days=1)).strftime("%m/%d/%Y")
        final_date = datetime.now().strftime("%m/%d/%Y")
        bearer_token = self.page.evaluate("() => window.localStorage.getItem('access_token')")
        offset: int = 0

        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "pt-BR,pt;q=0.9",
            "authorization": f"Bearer {bearer_token}",
            "content-type": "application/json",
            "idempresa": self.config['ID Empresa'],
            "origin": "https://vil.vallourec.com.br",
            "referer": "https://vil.vallourec.com.br/vil/ui/dashboard/balancas/consultaTicketsPesagemTransportadora",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
        }

        tickets: list = []
        while True:

            json_body = {
                "IdClientes": [],
                "IdMateriais": [],
                "IdDestinos": [],
                "Periodo": {
                    "DataInicial": f"{init_date}, 12:00:00 AM",
                    "DataFinal": f"{final_date}, 11:59:59 PM"
                },
                "Limit": 40,
                "Offset": offset
            }

            response = requests.post(self.config['Request URL'], headers=headers, json=json_body)
            try:
                response.raise_for_status()
                total = response.json()['Value']['Total']
                json_response = response.json()['Value']['Collection']
                tickets.extend(json_response)

                if (offset + 40) >= total:
                    break
                else:
                    offset += 40

            except requests.RequestException as err:
                logger.error(f"Falha HTTP: {err}")
                raise

        logger.success(f"Existem {len(tickets)} tickets.")
        return tickets

    @staticmethod
    def normalized_tickets(tickets: list):
        normalized_tickets: list = []
        for ticket in tickets:
            normalized_ticket = Ticket(
                ticket_number=ticket['NumeroTicket'],
                emitting_date=ticket['DataEmissao'],
                cancel_date=None if ticket['DataCancelamento'] == '0001-01-01T00:00:00' else ticket['DataCancelamento'],
                plate=ticket['PlacaVeiculo'],
                client_name=ticket['NomeCliente'],
                material=ticket['NomeMaterial'],
                destiny=ticket['NomeDestino'],
                shipping_company=ticket['NomeTransportadora'],
                origin=ticket['Origem'],
                operator=str(ticket['OperadorBalanca']),
                gross_weight=str(ticket['PesoBruto']),
                ton_weight=str(round(ticket['PesoLiquido'] / 1000, 2)),
                tare_weight=str(ticket['PesoTara']),
                net_weight=str(ticket['PesoLiquido']),
                status=ticket['Status'],
                cancel_motive=ticket['MotivoCancelamento']
            )
            normalized_tickets.append(normalized_ticket)

        return normalized_tickets

    def append_new_rows_with_win32(self, df: pd.DataFrame, sheet_name: str):
        """
        Abre o arquivo Excel, lê os tickets já existentes e anexa só as linhas de df
        cujo 'Tíquete' ainda não estejam na planilha.
        """
        excel = None
        wb = None
        try:
            # inicializa Excel isolado (DispatchEx evita reaproveitar instância existente)
            excel = win32.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False

            logger.info("Abrindo workbook: {}", self.config['Caminho Sharepoint Atual'])
            wb = excel.Workbooks.Open(self.config['Caminho Sharepoint Atual'])
            # wb = excel.Workbooks.Open(r"C:\Users\rpa.belgo\OneDrive - FRETO SOLUCOES E TECNOLOGIA S.A\Arquivos de YASMIN ISIS FELIPE DE OLIVEIRA - Vallourec\VALLOUREC YAS ATUAL - Copy.xlsm")
            try:
                ws = wb.Worksheets(sheet_name)
            except Exception:
                raise KeyError(
                    f"Planilha '{sheet_name}' não encontrada no arquivo {self.config['Caminho Sharepoint Atual']}.")

            # --- Lê cabeçalhos da primeira linha ---
            headers: List[str] = []
            col = 1
            while True:
                val = ws.Cells(1, col).Value
                if val is None:
                    break
                headers.append(str(val))
                col += 1

            # mapa nome -> índice 1-based
            header_map: Dict[str, int] = {h: i + 1 for i, h in enumerate(headers)}

            # Recomputar last_row de forma robusta
            used = ws.UsedRange
            used_first_row = used.Row
            used_row_count = used.Rows.Count
            last_row = used_first_row + used_row_count - 1
            date_headers = ["DatadeEmissão", "Datacancelamento"]  # ajuste para seus nomes reais
            for h in date_headers:
                idx = header_map.get(h)
                if idx:
                    ws.Columns(idx).NumberFormat = "[$-pt-BR]dd/mm/aaaa;@"

            # --- Coleta tickets existentes ---
            idx_ticket = header_map.get('Tíquete')
            if idx_ticket is None:
                raise KeyError("Coluna 'Tíquete' não encontrada e não foi possível criar automaticamente.")

            existing_tickets = set()
            # leitura segura: some times UsedRange inclui linhas vazias, então percorre até last_row
            for row in range(2, last_row + 1):
                cell_val = ws.Cells(row, idx_ticket).Value
                if cell_val is not None:
                    existing_tickets.add(str(cell_val).replace(".0", "").strip())

            # --- Prepara linhas novas ---
            rows_to_write_map: List[Dict[str, Any]] = []
            for _, row in df.iterrows():
                ticket = row.get('Tíquete', None)
                if pd.isna(ticket):
                    logger.debug("Pulando linha com Tíquete NaN")
                    continue
                ticket_norm = str(ticket).strip()
                if ticket_norm in existing_tickets:
                    continue
                prepared_map = {}
                for col_name in headers:  # escreve seguindo a ordem dos headers da planilha
                    # preferir o valor do df quando existir, caso contrário string vazia
                    if col_name in df.columns:
                        val = row.get(col_name)
                        prepared_map[col_name] = "" if pd.isna(val) else val
                    else:
                        # se coluna não estiver no df, tenta pegar do col_order (caso nome diferente)
                        prepared_map[col_name] = ""
                # sempre garantir que 'Tíquete' esteja preenchido coerentemente
                prepared_map['Tíquete'] = ticket_norm
                rows_to_write_map.append(prepared_map)

            if not rows_to_write_map:
                logger.info("Nenhuma nova linha encontrada — nada para adicionar.")
                return 0

            # --- Monta matriz (2D) alinhada com a ordem 'headers' para escrita em bloco ---
            data_matrix: List[Tuple] = []
            for m in rows_to_write_map:
                row_tuple = tuple(m.get(col_name, "") for col_name in headers)
                data_matrix.append(row_tuple)

            safe_block = _sanitize_block(data_matrix)
            # escreve em bloco: determina faixa de destino
            start_row = last_row + 1
            end_row = start_row + len(data_matrix) - 1
            end_col = len(headers)

            logger.info("Escrevendo {} linhas (linhas {} até {}) e {} colunas...", len(data_matrix), start_row, end_row,
                        end_col)

            # Converte para tupla de tuplas (requisito do COM)
            block = tuple(tuple(r) for r in data_matrix)

            # Define Range e atribui Value em bloco
            top_left = ws.Cells(start_row, 1)
            bottom_right = ws.Cells(end_row, end_col)
            write_range = ws.Range(top_left, bottom_right)
            write_range.Value = safe_block

            # Salva e loga sucesso
            wb.Save()
            written = len(data_matrix)

            # Mensagem no nível success se disponível

            logger.success(f"{written} linhas adicionadas com sucesso.")

            return written

        except Exception as exc:
            logger.error("Erro ao gravar no Excel: {}", exc)
            raise
        finally:
            # garante fechamento do workbook e do Excel para evitar processos zumbis
            try:
                if wb is not None:
                    wb.Close(SaveChanges=True)
            except Exception:
                logger.error("Falha ao fechar workbook (já pode ter sido fechado).")
            try:
                if excel is not None:
                    excel.Quit()
            except Exception:
                logger.error("Falha ao finalizar Excel.")

    def create_excel(self, tickets):
        logger.info("Adicionando apenas linhas novas à planilha com win32.")

        df = pd.DataFrame([ticket.model_dump() for ticket in tickets])

        df.rename(columns={
            'ticket_number': 'Tíquete',
            'plate': 'Placa',
            'client_name': 'T',
            'material': 'Material',
            'operator': 'Operador',
            'emitting_date': 'DatadeEmissão',
            'cancel_date': 'Data cancelamento',
            'destiny': 'Destino',
            'shipping_company': 'Transportadora',
            'origin': 'Origem',
            'gross_weight': 'PesoBruto',
            'tare_weight': 'PesoTara',
            'net_weight': 'PesoLiquido',
            'status': 'Status',
            'cancel_motive': 'Motivo do Cancelamento',
            'ton_weight': 'Peso Ton'
        }, inplace=True)

        result = self.append_new_rows_with_win32(
            df=df,
            sheet_name="Base VIL Ticket's oficial"
        )
        if not result:
            return
        df.sort_values(by="DatadeEmissão", ascending=True, inplace=True, ignore_index=True)
        logger.success("Linhas novas adicionadas com sucesso.")

    def run(self):
        try:
            logger.info("{0}\n{1}   Start of automation.\n{1}   {0}".format('=' * 20, '\t' * 8))
            self.login()
            tickets = self.get_tickets()
            normalized_tickets = self.normalized_tickets(tickets)
            self.create_excel(normalized_tickets)
            email_handler.send_email(
                subject="RPA - Ticket Balança",
                body="A automação Ticket Balança finalizou com sucesso"
            )
        except KeyError as e:
            logger.exception(e)
            email_handler.send_email(
                subject="RPA - Ticket Balança",
                body="A automação Ticket Balança Falhou"
            )
            raise
        except Exception as e:
            logger.exception(e)
            email_handler.send_email(
                subject="RPA - Ticket Balança",
                body="A automação Ticket Balança Falhou"
            )
            raise
        finally:
            self.context.close()
            self.browser.close()
            logger.info("{0}\n{1}    End of automation.\n{1}   {0}".format('=' * 20, '\t' * 8))



from zoneinfo import ZoneInfo
TZ = ZoneInfo("America/Sao_Paulo")

def to_excel_compatible(v: Any):
    # pandas Timestamp -> datetime (sem tz)
    if isinstance(v, pd.Timestamp):
        ts: pd.Timestamp = v
        if ts.tzinfo is None:
            return ts.to_pydatetime()
        else:
            return ts.tz_convert(TZ).tz_localize(None).to_pydatetime()
    # datetime -> datetime (sem tz)
    if isinstance(v, datetime):
        if v.tzinfo is not None:
            return v.astimezone(TZ).replace(tzinfo=None)
        return v
    # NaT/NaN -> None
    if v is pd.NaT or (isinstance(v, float) and pd.isna(v)):
        return None
    return v

def _sanitize_block(block: Iterable[Iterable[Any]]) -> List[List[Any]]:
    # COM prefere lista de listas
    return [[to_excel_compatible(v) for v in row] for row in block]
