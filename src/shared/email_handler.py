import smtplib
from email.message import EmailMessage
import imaplib
import email


# ===== ENVIAR EMAIL =====
def enviar_email_multiplos_smtp(user, app_password, to, subject, body):
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(user, app_password)
        smtp.send_message(msg)


# ===== LER NÃO LIDOS =====
def listar_nao_lidos_imap(user, app_password, max_results=10):
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(user, app_password)
    imap.select("INBOX")

    status, messages = imap.search(None, "UNSEEN")
    email_ids = messages[0].split()

    resultados = []

    for eid in email_ids[:max_results]:
        _, msg_data = imap.fetch(eid, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        resultados.append({
            "from": msg["From"],
            "subject": msg["Subject"],
            "date": msg["Date"]
        })

    imap.logout()
    return resultados


# ===== EXEMPLO =====
if __name__ == "__main__":
    USER = "suporte@ergondata.com"
    APP_PASSWORD = "Ergon@123"  # senha de app gerada

    # Ler não lidos
    nao_lidos = listar_nao_lidos_imap(USER, APP_PASSWORD)
    print("Não lidos:")
    for e in nao_lidos:
        print(e)

    # Enviar
    # enviar_email_multiplos_smtp(
    #     USER,
    #     APP_PASSWORD,
    #     ["dest1@email.com", "dest2@email.com"],
    #     "Teste Gmail",
    #     "Se chegou, o robô trabalhou bonito 😎"
    # )
