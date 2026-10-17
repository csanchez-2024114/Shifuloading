"""Envío de correo por SMTP (recuperación de contraseña, PASSWORD_RESET_ENABLED). Nunca registra el contenido del
correo, la contraseña SMTP ni el destinatario."""
import smtplib
from email.message import EmailMessage

from assistant.config import Settings


class SmtpMailer:
    def __init__(self, settings: Settings):
        self.s = settings

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.s.smtp_from, to, subject
        msg.set_content(body)
        ssl = self.s.smtp_port == 465  # SMTPS; en los demás puertos, STARTTLS si SMTP_STARTTLS=1
        with (smtplib.SMTP_SSL if ssl else smtplib.SMTP)(self.s.smtp_host, self.s.smtp_port, timeout=20) as smtp:
            if not ssl and self.s.smtp_starttls:
                smtp.starttls()
            if self.s.smtp_user:
                smtp.login(self.s.smtp_user, self.s.smtp_password)
            smtp.send_message(msg)
