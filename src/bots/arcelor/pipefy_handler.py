import requests
from typing import Literal
from src.shared.logger import logger
from dotenv import load_dotenv
import os
load_dotenv()

class API:

    def __init__(self):
        self.url: str = 'https://api.pipefy.com/graphql'
        self.headers: dict = {
            'Authorization': f'Bearer {os.getenv("PIPEFY_TOKEN")}',
            'Content-Type': 'application/json'
        }
        self.log = logger.bind(service='arcelor')


    def _get_phase_id(self):

        """
        Consulta o pipe de acordo com o ID. ID fica no final do URL
        :return:
        """

        self.log.debug("Obtendo id da phase")
        query = '{pipe(id: 303452077) {organizationId id name phases {id name}}}'

        response = requests.post(self.url, json={'query': query}, headers=self.headers)

        if response.status_code == 200:
            dados_pipe = response.json()
            phase_id = {i['name']: i['id'] for i in dados_pipe['data']['pipe']['phases']}
            self.log.debug(f"Id => {phase_id}")
            return phase_id
        else:
            self.log.erro(f"Erro: {response.status_code}")

    def _get_card_ids(self):

        """
            Obtém os ids dos card de acordo com o id da phase
        :return:
        """
        self.log.debug("Obtendo id dos cards")
        query = "{phase(id: 322131287) {id name cards {edges {node {id title}}}}}"

        response = requests.post(self.url, json={"query": query}, headers=self.headers)

        if response.status_code == 200:
            card_ids = response.json()
            if card_ids.get('data').get('phase'):
                card_ids = card_ids['data']['phase']['cards']['edges']
                self.log.debug(f"Quantidade de cards {len(card_ids)}")
                return card_ids
            else:
                return None
        else:
            self.log.erro(f'Erro: {response.status_code}')

    def _get_data(self, id: str):

        self.log.debug("Obtendo dados dos cards")
        query = f'{{card(id: {id}) {{fields {{name value}} title done id updated_at}}}}'
        response = requests.post(self.url, json={'query': query}, headers=self.headers)

        if response.status_code == 200:
            data_card = response.json()
            data_card = data_card['data']['card']['fields']

            new_data_card = API._format_data(data=data_card)
            self.log.debug(f"Dado do card => {new_data_card}")
            return new_data_card
        else:
            self.log.erro(f"Erro: {response.status_code}")
            return None

    @staticmethod
    def _format_data(data: list) -> dict:

        keys = [
            'Transporte',
            'Unidade',
            'Filial emitida Freto',
            'Série Cte',
            'Motivo',
            'Valor aprovado - CTe',
            'Valor a pagar - Contrato',
        ]

        first_change = [value for value in data if value['name'] in keys]
        new_data_card = {item['name']: item['value'] for item in first_change}

        if len(new_data_card) != 7:
            return {}

        for key in new_data_card.keys():
            if key not in keys:
                return {}

        new_data_card['Valor a pagar (Contrato)'] = new_data_card.pop('Valor a pagar - Contrato')
        new_data_card['Valor aprovado emissão (CTe)'] = new_data_card.pop('Valor aprovado - CTe')
        new_data_card['Valor a pagar (Contrato)'] = float(new_data_card['Valor a pagar (Contrato)'].replace(',', ''))
        new_data_card['Valor aprovado emissão (CTe)'] = float(
            new_data_card['Valor aprovado emissão (CTe)'].replace(',', ''))
        new_data_card['Filial'] = new_data_card.pop('Filial emitida Freto')
        new_data_card['Série CTe'] = new_data_card.pop('Série Cte')

        return new_data_card

    def move_card(
            self,
            phase: Literal[
                'Fila Automação',
                'Portal Freto',
                'CTe Freto',
                'CTe Levo',
                'Contrato',
                'Quitação de Contrato',
                'Liberar'
            ],
            card_id: str
    ):

        actual_phase = self._get_card_phase(card_id)
        self.log.debug(f"Movendo card de phase. Atual {actual_phase} para {phase}")
        if phase == actual_phase:
            return

        phase_id = self._get_phase_id()
        id = phase_id[phase]

        query = f"mutation {{moveCardToPhase(input: {{card_id: {card_id}, destination_phase_id: {id}}}) {{card " \
                f"{{id current_phase {{name}}}}}}}}"
        response = requests.post(self.url, json={'query': query}, headers=self.headers)

        if response.status_code == 200:
            dados = response.json()
            self.log.debug("Card movido")
        else:
            self.log.erro(f"Erro: {response.status_code}")
            return None

    def get_card_data(self) -> list:

        card_data = []
        card_ids = self._get_card_ids()
        if not card_ids:
            return []
        for id in card_ids:
            data = self._get_data(id['node']['id'])
            if len(data) != 7:
                continue
            else:
                data['card id'] = id['node']['id']
                card_data.append(data)
        return card_data

    def _get_card_phase(self, card_id: str):
        query = f"""
        {{
          card(id: {card_id}) {{
            id
            title
            current_phase {{
              id
              name
            }}
          }}
        }}
        """

        response = requests.post(self.url, json={'query': query}, headers=self.headers)

        if response.status_code == 200:
            data = response.json()
            phase = data['data']['card']['current_phase']
            return phase['name']
        else:
            self.log.erro(f"Erro: {response.status_code}")
