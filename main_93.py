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

            if ((datetime.now().hour == 7 and last_exec != 7) or
                    (datetime.now().hour == 8 and last_exec != 8) or
                    (datetime.now().hour == 10 and last_exec != 10) or
                    (datetime.now().hour == 18 and last_exec != 18) or
                    (datetime.now().hour == 20 and last_exec != 20) or
                    (datetime.now().hour == 21 and last_exec != 21)):

                last_exec = datetime.now().hour
                logger.info(f"Iniciando automação - Belgo")
                email_handler.send_email(
                    to='lucas.leite@ergondata.com.br',
                    subject="Automações Freto",
                    body=f"Foi iniciado a automação Belgo"
                )
                subprocess.run(
                    ["uv", "run", "-m", f"src.bots.belgo.publisher"],
                    cwd=ROOT_DIR,
                    check=True
                )
                subprocess.run(
                    ["uv", "run", "-m", f"src.bots.belgo.worker"],
                    cwd=ROOT_DIR,
                    check=True
                )
                email_handler.send_email(
                    to='lucas.leite@ergondata.com.br',
                    subject="Automações Freto",
                    body=f"Foi finalizado a automação Belgo"
                )

            resultados = email_handler.read_emails(max_results=10, not_set_read=['arcelor', 'jmendes'])
            if not resultados:
                logger.debug("Sem novos emails")
                time.sleep(60)
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

                    if "arcelor" in resultado['subject']:
                        email_handler.send_email(
                            to='suporte@ergondata.com.br',
                            subject="arcelor",
                            body=f"."
                        )
                    if "jjmendes" in resultado['subject'] or 'jmendes' in resultado['subject']:
                        email_handler.send_email(
                            to='suporte@ergondata.com.br',
                            subject="jmendes",
                            body=f"."
                        )

                    if 'belgo' in resultado['subject']:
                        bot = 'belgo'

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
            time.sleep(60)  # evita loop insano em caso de erro repetido

        finally:
            time.sleep(1)