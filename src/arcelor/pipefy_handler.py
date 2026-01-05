import requests
from typing import Literal


class API:
    url: str = 'https://api.pipefy.com/graphql'

    headers: dict = {
        'Authorization': 'Bearer eyJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJQaXBlZnkiLCJpYXQiOjE3MjkwOTc3MzYsImp0aSI6IjYyOTA5MTFkLThlN2UtNDllOS05MmM4LTVmNzhhNTAwOWJhNSIsInN1YiI6MzA1MDA4MDQ0LCJ1c2VyIjp7ImlkIjozMDUwMDgwNDQsImVtYWlsIjoibWF0aGV1cy5jZXJ2aUBlcmdvbmRhdGEuY29tLmJyIn19.g526cWsZ31a4eA_XSfQGpcnxjhZ_FDltvyAA_VL0PhRPZpcM0dGhxm5cPDqUNS7bPkYmBlUzi25Xeea6xHgSuQ',
        'Content-Type': 'application/json'
    }

    def __int__(self):
        pass

    def _get_phase_id(self):

        """
        Consulta o pipe de acordo com o ID. ID fica no final do URL
        :return:
        """

        query = '{pipe(id: 303452077) {organizationId id name phases {id name}}}'

        response = requests.post(self.url, json={'query': query}, headers=self.headers)

        if response.status_code == 200:
            dados_pipe = response.json()
            phase_id = {i['name']: i['id'] for i in dados_pipe['data']['pipe']['phases']}
            return phase_id
        else:
            print(f"Erro: {response.status_code}")

    def _get_card_ids(self):

        """
            Obtém os ids dos card de acordo com o id da phase
        :return:
        """

        query = "{phase(id: 322131287) {id name cards {edges {node {id title}}}}}"

        response = requests.post(self.url, json={"query": query}, headers=self.headers)

        if response.status_code == 200:
            card_ids = response.json()
            card_ids = card_ids['data']['phase']['cards']['edges']

            return card_ids
        else:
            print(f'Erro: {response.status_code}')

    def _get_data(self, id: str):

        query = f'{{card(id: {id}) {{fields {{name value}} title done id updated_at}}}}'
        response = requests.post(self.url, json={'query': query}, headers=self.headers)

        if response.status_code == 200:
            data_card = response.json()
            data_card = data_card['data']['card']['fields']

            new_data_card = API._format_data(data=data_card)

            return new_data_card
        else:
            print(f"Erro: {response.status_code}")
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

        id: str = ''

        phase_id = self._get_phase_id()
        id = phase_id[phase]

        query = f"mutation {{moveCardToPhase(input: {{card_id: {card_id}, destination_phase_id: {id}}}) {{card " \
                f"{{id current_phase {{name}}}}}}}}"
        response = requests.post(self.url, json={'query': query}, headers=self.headers)

        if response.status_code == 200:
            dados = response.json()
        else:
            print(f"Erro: {response.status_code}")
            return None

    def get_card_data(self) -> list:

        card_data = []
        card_ids = self._get_card_ids()
        for id in card_ids:
            data = self._get_data(id['node']['id'])
            if len(data) != 7:
                continue
            else:
                data['card id'] = id['node']['id']
                card_data.append(data)
        return card_data
