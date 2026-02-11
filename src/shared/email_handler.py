import smtplib
from email.message import EmailMessage
import mimetypes
import imaplib
import email
import os
import subprocess
from pathlib import Path
from datetime import datetime
from src.shared.logger import logger

from dotenv import load_dotenv
load_dotenv()

USER = os.getenv("EMAIL_ERGON")
APP_PASSWORD = os.getenv("EMAIL_PASS_KEY")

# ===== ENVIAR EMAIL =====
def send_email(to, subject, body, attachment_path = None):
    msg = EmailMessage()
    msg["From"] = USER
    if isinstance(to, list):
        msg["To"] = ", ".join(to)
    elif isinstance(to, str):
        msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    if attachment_path:
        filename = os.path.basename(attachment_path)

        mime_type, _ = mimetypes.guess_type(attachment_path)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)

        with open(attachment_path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype=maintype,
                subtype=subtype,
                filename=filename
            )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(USER, APP_PASSWORD)
        smtp.send_message(msg)


# ===== LER NÃO LIDOS =====
def read_emails(not_set_read: list = [], max_results=100):
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(USER, APP_PASSWORD)
    imap.select("INBOX")

    today = datetime.now().strftime("%d-%b-%Y")

    status, messages = imap.search(
        None,
        f'(UNSEEN SINCE {today})'
    )

    if status != "OK" or not messages or not messages[0]:
        imap.logout()
        return []

    email_ids = messages[0].split()
    if not email_ids:
        imap.logout()
        logger.error(f"Falha ao ler o email. id do email {email_ids}")
        return []

    resultados = []

    for eid in email_ids[:max_results]:
        status_fetch, msg_data = imap.fetch(eid,"(BODY.PEEK[HEADER])")
        if status_fetch != "OK" or not msg_data or not msg_data[0]:
            logger.error(f"Falha ao ler o email. status fetch {status_fetch} msg_data {msg_data}")
            continue

        raw_email = msg_data[0][1]
        if not raw_email:
            logger.error(f"Falha ao ler o email. raw_email {raw_email}")
            continue
        msg = email.message_from_bytes(raw_email)

        if "freto" in msg["Subject"].lower() or "ergondata" in msg['From'].lower():
            if 'arcelor' in msg["Subject"].lower():
                bot = "arcelor"
            elif 'jmendes' in msg["Subject"].lower() or 'jjmendes' in msg["Subject"].lower():
                bot = "jmendes"
            elif 'belgo' in msg["Subject"].lower():
                bot = "belgo"
            else:
                imap.store(eid, '+FLAGS', '\\Seen')
                continue
            if bot not in not_set_read:
                resultados.append({
                    "from": msg["From"].lower(),
                    "subject": msg["Subject"].lower(),
                    "date": msg["Date"]
                })
                imap.store(eid, '+FLAGS', '\\Seen')

    imap.logout()
    return resultados
