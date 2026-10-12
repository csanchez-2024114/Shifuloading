import os
import smtplib
import logging
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _smtp_from() -> str:
    return _env("SMTP_FROM_EMAIL", "")


def validate_smtp_config() -> None:
    """
    Verifica que las credenciales existan para no fallar silenciosamente.
    Variables requeridas: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM_EMAIL.
    """
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM_EMAIL"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise ValueError(f"Faltan variables de entorno SMTP: {', '.join(missing)}")


def _send_email_message(msg: EmailMessage) -> bool:
    """
    [ARQUITECTURA ENTERPRISE]: Motor centralizado de envío de correos.
    Evita la duplicación de código, maneja timeouts, puertos SSL/TLS y captura de errores.
    Retorna True si el envío fue exitoso, False en caso de error.
    """
    validate_smtp_config()
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        logger.info(f"[MAIL SUCCESS] Correo enviado correctamente a: {msg['To']}")
        return True
    except smtplib.SMTPException as e:
        logger.error(f"[ERROR CRÍTICO SMTP] Error de protocolo: {e}")
        return False
    except Exception as e:
        logger.error(f"[ERROR CRÍTICO SMTP] Fallo inesperado al enviar el correo: {e}")
        return False


def _smtp_send(msg: EmailMessage) -> None:
    if not _send_email_message(msg):
        raise RuntimeError("No se pudo enviar el correo SMTP.")


def send_smtp_email(
    to_email: str,
    subject: str,
    body: str,
    reply_to: str = "",
    from_name: str = "HyperShifu",
) -> bool:
    """Envio SMTP genérico en texto plano."""
    validate_smtp_config()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name.strip() or 'HyperShifu'} <{_smtp_from()}>"
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    return _send_email_message(msg)


def send_contact_email(full_name: str, email_address: str, message: str) -> bool:
    """
    Construye y envía el correo del formulario de contacto.
    """
    from_email = os.getenv("SMTP_FROM_EMAIL", "")
    to_email = os.getenv("CONTACT_TO_EMAIL") or from_email
    msg = EmailMessage()
    msg["Subject"] = "🚀 Nuevo mensaje desde la web: Hyper Shifu"
    msg["From"] = f"Contacto Web <{from_email}>"
    msg["To"] = to_email
    msg["Reply-To"] = email_address
    msg.set_content(
        f"Has recibido un nuevo mensaje desde el formulario de contacto de la web.\n\n👤 Nombre: {full_name}\n✉️ Email: {email_address}\n\n💬 Mensaje:\n{message}\n"
    )
    return _send_email_message(msg)


def send_password_reset_email(
    to_email: str, reset_link_or_token: str, user_name: str = ""
) -> bool:
    """
    Construye y envía el correo de recuperación de contraseña.

    Acepta tanto un enlace completo como un token legacy.
    """
    frontend_url = _env("FRONTEND_URL", "https://hypershifu.com").rstrip("/")
    reset_link = reset_link_or_token
    if "/" not in reset_link_or_token:
        reset_link = f"{frontend_url}/reset-password?token={reset_link_or_token}"
    greeting_name = (user_name or "").strip() or "hola"
    body = f"{greeting_name},\n\nRecibimos una solicitud para restablecer tu contraseña de Hyper Shifu.\nUsa el siguiente enlace para continuar:\n\n{reset_link}\n\nSi no solicitaste este cambio, puedes ignorar este correo."
    return send_smtp_email(
        to_email=to_email,
        subject="Recuperación de contraseña - Hyper Shifu",
        body=body,
        from_name="Hyper Shifu",
    )


def send_smtp_email_with_attachment(
    to_email: str,
    subject: str,
    body: str,
    attachment_bytes: bytes,
    attachment_name: str,
    reply_to: str = "",
    from_name: str = "HyperShifu",
) -> None:
    """Envio SMTP con adjunto para correos con documentos (facturas, etc)."""
    validate_smtp_config()
    smtp_user = _env("SMTP_USER", "")
    safe_from_name = from_name.strip() or "HyperShifu"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{safe_from_name} <{_smtp_from()}>"
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    msg.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="pdf",
        filename=attachment_name,
    )
    try:
        _smtp_send(msg)
        print(f"[MAIL SUCCESS] Correo SMTP con adjunto enviado a {to_email}")
    except smtplib.SMTPAuthenticationError as e:
        print(
            f"[ERROR SMTP AUTH] Error enviando correo SMTP: {e}. Verifica SMTP_USER/SMTP_PASS y que SMTP AUTH este habilitado para {smtp_user}."
        )
    except smtplib.SMTPException as e:
        print(f"[ERROR SMTP] Error enviando correo SMTP: {e}")
    except Exception as e:
        print(f"[ERROR SMTP] Fallo inesperado enviando correo SMTP: {e}")
