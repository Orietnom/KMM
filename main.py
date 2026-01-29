from pathlib import Path
from src.shared import email_handler
from src.shared.logger import logger
import subprocess
import os
from dotenv import load_dotenv
load_dotenv()

ROOT_DIR = Path.cwd()
if __name__ == '__main__':
    logger.info("Iniciando trigger")
    while True:
        resultados = email_handler.read_emails(max_results=10)
        if not resultados:
            logger.debug("Sem novos emails")
        else:
            for resultado in resultados:
                if resultado['subject'] not in ['jmendes', 'jjmendes', 'arcelor', 'belgo']:
                    logger.error("Assunto não contem o nome da automação a ser executada")
                    email_handler.send_email(
                        to=resultado['from'],
                        subject="Falha ao iniciar a automação",
                        body=f"Assunto não contém a automação a ser executada. {resultado}"
                    )
                    continue

                bot = resultado['subject']
                if 'jjmendes' in bot:
                    bot = 'jmendes'

                logger.info(f"Iniciando automação - {bot}")

                subprocess.run(
                    ["uv", "run", f"src/bots/{bot}/publisher.py"],
                    cwd=ROOT_DIR,
                    check=True
                )
                subprocess.run(
                    ["uv", "run", f"src/bots/{bot}/worker.py"],
                    cwd=ROOT_DIR,
                    check=True
                )
                logger.info(f"Fim da automação {bot}")

    logger.info("Trigger finalizado")