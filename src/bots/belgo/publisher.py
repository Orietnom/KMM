"""Entrypoint compatível do producer BELGO.

O agendador continua executando ``python -m src.bots.belgo.publisher``, enquanto
o ciclo de vida agora é gerenciado pelo ergon-framework.
"""

from src.bots.belgo.tasks.publisher.config import run

if __name__ == "__main__":
    run()
