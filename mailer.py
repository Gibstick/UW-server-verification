import logging
import smtplib
import ssl
from email.message import EmailMessage


def _generate_message(to_addr, from_addr, code, name):
    msg = EmailMessage()
    body = (f"Your verification code is {code}.", )
    msg.set_content("\n".join(body))
    msg['Subject'] = "Email Verification Code from AndrewBot"
    msg['From'] = from_addr
    msg['To'] = to_addr
    return msg


class SMTPMailer(object):
    """A Mailer sends out emails."""
    __slots__ = ["host", "port", "username", "password", "from_addr", "logger"]

    def __init__(self, host, port, username, password, from_addr):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.logger = logging.getLogger(__name__)

    def send(self, to_addr, code, name):
        msg = _generate_message(to_addr, self.from_addr, code, name)
        # TODO: configurable TLS vs STARTTLS
        self.logger.info("Connecting to SMTP")
        context = ssl.create_default_context()
        server = smtplib.SMTP(self.host, self.port)
        server.starttls(context=context)
        self.logger.info("Logging in to SMTP")
        server.login(self.username, self.password)
        self.logger.info("Sending real email")
        server.send_message(msg)
        server.quit()


class PrintMailer(object):
    """A mailer that just prints things instead of sending for real."""
    __slots__ = ["logger"]

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send(self, to_addr, code, name):
        msg = _generate_message(to_addr, "test@example.com", code, name)
        self.logger.info("Sending fake email")
        self.logger.info(msg)
