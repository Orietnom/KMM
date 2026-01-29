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
def read_emails(max_results=100):
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(USER, APP_PASSWORD)
    imap.select("INBOX")

    today = datetime.now().strftime("%d-%b-%Y")

    status, messages = imap.search(
        None,
        f'(UNSEEN SINCE {today})'
    )
    email_ids = messages[0].split()

    resultados = []

    for eid in email_ids[:max_results]:
        _, msg_data = imap.fetch(eid, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        if "freto" in msg['From'].lower():
            resultados.append({
                "from": msg["From"].lower(),
                "subject": msg["Subject"].lower(),
                "date": msg["Date"]
            })
            # imap.store(eid, '+FLAGS', '\\Seen')

    imap.logout()
    return resultados
