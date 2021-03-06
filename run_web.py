#!/usr/bin/env python3
import logging
import sys
from typing import Union

from gevent.pywsgi import WSGIServer

from config import settings
import db
import mailer
import server

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    logging.getLogger("sqlitedict").setLevel(logging.WARNING)

    smtp_host: str = settings.server.smtp_host
    smtp_port: int = settings.server.smtp_port
    smtp_user: str = settings.server.smtp_user
    smtp_pass: str = settings.server.smtp_pass
    smtp_from_addr: str = settings.server.smtp_from_addr
    allowed_domain: str = settings.server.allowed_domain

    mail: Union[mailer.SMTPMailer, mailer.PrintMailer]
    if not smtp_host:
        mail = mailer.PrintMailer()
    else:
        mail = mailer.SMTPMailer(
            host=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_pass,
            from_addr=smtp_from_addr,
        )

    expiry_seconds: int = settings.common.expiry_s
    database_file: int = settings.common.database_file
    sm = db.SessionManager(expiry_seconds, database_file)

    app = server.create_app(
        session_manager=sm,
        mail=mail,
        allowed_domain=allowed_domain,
    )
    http_server = WSGIServer(('', 5000), app)
    http_server.serve_forever()
