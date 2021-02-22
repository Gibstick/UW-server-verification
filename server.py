import logging
import os
import random
import sys
import time
import uuid
from typing import Union

from flask import Flask, abort, redirect, url_for, render_template, request
from flask.logging import create_logger
from sqlitedict import SqliteDict
from werkzeug.routing import BaseConverter, ValidationError

import db
from config import settings
import mailer

# TODO: refactor to  use application factory pattern
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
app = Flask(__name__)
logger = create_logger(app)

smtp_host: str = settings.server.smtp_host
smtp_port: int = settings.server.smtp_port
smtp_user: str = settings.server.smtp_user
smtp_pass: str = settings.server.smtp_pass
smtp_from_addr: str = settings.server.smtp_from_addr
allowed_domain: str = settings.server.allowed_domain

expiry_seconds: int = settings.common.expiry_s
database_file: int = settings.common.database_file

sm = db.SessionManager(expiry_seconds, database_file)

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

with app.app_context():
    logger.info("Using %s for mail" % mail)


def redirect_to_verify(user_id: int, secondary_id: uuid.UUID):
    """Return a 303 redirect to the verification page."""
    return redirect(url_for("verify_get",
                            user_id=user_id,
                            secondary_id=secondary_id),
                    code=303)


@app.route("/start/<int:user_id>/<uuid:secondary_id>", methods=["POST", "GET"])
def start(user_id: int, secondary_id: uuid.UUID):
    session = sm.session(user_id, secondary_id)
    if session is None:
        abort(404)

    # If the user has entered an email ready, take them to the code
    # verification form.
    if session.state == db.SessionState.WAITING_ON_CODE:
        return redirect_to_verify(user_id, secondary_id)

    if session.state == db.SessionState.VERIFIED:
        return redirect(url_for("success"), code=303)

    if request.method == "POST":
        email_addr = request.form["email"]
        if not email_addr.endswith(allowed_domain):
            # TODO: error feedback
            return redirect(url_for("start",
                                    user_id=user_id,
                                    secondary_id=secondary_id),
                            code=303)

        logger.info(
            f"User {session.discord_name} with id {session.user_id} sent an email"
        )
        mail.send(email_addr, session.verification_code, session.discord_name)
        sm.set_email_sent(user_id, secondary_id)
        return redirect_to_verify(user_id, secondary_id)
    else:
        return render_template("start.html")


@app.route("/verify/<int:user_id>/<uuid:secondary_id>", methods=["POST"])
def verify_post(user_id: int, secondary_id: uuid.UUID):
    # Post-Redirect-Get pattern
    attempted_code: str = request.form["verification"]
    verification_result = sm.verify(user_id, secondary_id, attempted_code)

    if verification_result is True:
        return redirect(url_for("success"), code=303)
    elif verification_result == 0:
        # TODO: give 400 error? But who cares
        return redirect(url_for("failure"), code=303)
    else:
        return redirect_to_verify(user_id, secondary_id)


@app.route("/verify/<int:user_id>/<uuid:secondary_id>", methods=["GET"])
def verify_get(user_id: int, secondary_id: uuid.UUID):
    session = sm.session(user_id, secondary_id)
    if session is None:
        abort(404)

    remaining_attempts = session.remaining_attempts
    if remaining_attempts is None:
        abort(404)

    assert remaining_attempts >= 0

    return render_template(
        "verify.html",
        remaining_attempts=remaining_attempts,
    ), 200


@app.route("/success")
def success():
    return render_template("passed_verification.html")


@app.route("/failure")
def failure():
    return render_template("failed_verification.html")


@app.route("/")
def root():
    return render_template("index.html")


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    logging.getLogger("sqlitedict").setLevel(logging.WARNING)
    logger.setLevel(logging.DEBUG)

    session_uuid = sm._new_fake()
    logger.debug(f"http://localhost:5000/start/0/{session_uuid}")

    app.run(debug=True)
