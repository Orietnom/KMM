from pathlib import Path
from src.shared import email_handler
from src.shared.logger import logger
import subprocess
import os
from dotenv import load_dotenv
from datetime import datetime
import time
load_dotenv()

ROOT_DIR = Path.cwd()
if __name__ == '__main__':
    logger.info("Iniciando trigger")
    last_exec = None
    while True:
        try:

            if ((datetime.now().hour == 3 and last_exec != 3) or
                    (datetime.now().hour == 14 and last_exec != 14) or
                    (datetime.now().hour == 16 and last_exec != 16)):

                last_exec = datetime.now().hour
                logger.info(f"Iniciando automação - Arcelor")
                email_handler.send_email(
                    to='lucas.leite@ergondata.com.br',
                    subject="Automações Freto",
                    body=f"Foi iniciado a automação Arcelor"
                )
                subprocess.run(
                    ["uv", "run", "-m", f"src.bots.arcelor.publisher"],
                    cwd=ROOT_DIR,
                    check=True
                )
                subprocess.run(
                    ["uv", "run", "-m", f"src.bots.arcelor.worker"],
                    cwd=ROOT_DIR,
                    check=True
                )
                email_handler.send_email(
                    to='lucas.leite@ergondata.com.br',
                    subject="Automações Freto",
                    body=f"Foi finalizado a automação arcelor"
                )

            resultados = email_handler.read_emails(max_results=10)
            if not resultados:
                logger.debug("Sem novos emails")
                time.sleep(30)
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

                    if "belgo" in resultado['subject']:
                        email_handler.send_email(
                            to='suporte@ergondata.com.br',
                            subject="belgo",
                            body=f"."
                        )
                        
                    bot = resultado['subject']
                    if 'jjmendes' in bot:
                        bot = 'jmendes'

                    logger.info(f"Iniciando automação - {bot}")
                    email_handler.send_email(
                        to='lucas.leite@ergondata.com.br',
                        subject="Automações Freto",
                        body=f"Foi iniciado a automação {bot}"
                    )
                    try:
                        subprocess.run(
                            ["uv", "run", "-m", f"src.bots.{bot}.publisher"],
                            cwd=ROOT_DIR,
                            check=True
                        )
                        subprocess.run(
                            ["uv", "run", "-m", f"src.bots.{bot}.worker"],
                            cwd=ROOT_DIR,
                            check=True
                        )
                        logger.info(f"Fim da automação {bot}")
                    except Exception as e:
                        logger.exception(f"Falha ao executar o bot {bot}. {e}")
                    finally:
                        email_handler.send_email(
                            to='lucas.leite@ergondata.com.br',
                            subject="Automações Freto",
                            body=f"Foi finalizado a automação {bot}"
                        )
        except Exception as e:
            logger.exception(f"Erro no trigger (vai continuar rodando): {e}")
            time.sleep(30)  # evita loop insano em caso de erro repetido

        finally:
            time.sleep(1)  # dá um respiro pro CPU