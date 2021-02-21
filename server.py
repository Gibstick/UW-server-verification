import logging
import os
import random
import sys
import time
import uuid

from flask import Flask, abort, redirect, url_for, render_template, request
from sqlitedict import SqliteDict

import db
from config import settings
import mailer

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
app = Flask(__name__)
app.name = "AndrewWeb"

smtp_host = settings.server.smtp_host
smtp_port = settings.server.smtp_port
smtp_user = settings.server.smtp_user
smtp_pass = settings.server.smtp_pass
smtp_from_addr = settings.server.smtp_from_addr
allowed_domain = settings.server.allowed_domain

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
    app.logger.info(f"Using {mail} for mail")

@app.route("/start/<uuid>/email", methods=["POST", "GET"])
def start(uuid):
    session = db.session(uuid)
    if session is None:
        abort(404)

    # If the user has entered an email ready, take them to the code
    # verification form.
    if session.state == db.SessionState.WAITING_ON_CODE:
        return redirect(url_for("verify_get", uuid=uuid), code=303)

    if request.method == "POST":
        email_addr = request.form["email"]
        if not email_addr.endswith(allowed_domain):
            # TODO: error feedback
            return redirect(url_for("start", uuid=uuid), code=303)

        app.logger.info(f"User {session.discord_name} with id {session.user_id} sent an email")
        mail.send(email_addr, session.verification_code, session.discord_name)
        db.set_email_sent(uuid)
        return redirect(url_for("verify_get", uuid=uuid), code=303)

    else:
        return render_template("start.html")


@app.route("/verify/<uuid>", methods=["POST"])
def verify_post(uuid):
    # Post-Redirect-Get pattern
    attempted_code = request.form["verification"]
    verification_result = db.verify(uuid, attempted_code)

    if verification_result is True:
        return redirect(url_for("success"), code=303)
    elif verification_result == 0:
        # TODO: give 400 error? But who cares
        return redirect(url_for("failure"), code=303)
    else:
        return redirect(url_for("verify_get", uuid=uuid), code=303)


@app.route("/verify/<uuid>", methods=["GET"])
def verify_get(uuid):
    remaining_attempts = db.peek_attempts(uuid)

    if remaining_attempts is None:
        abort(404)

    assert (remaining_attempts > 0)

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
    app.logger.setLevel(logging.DEBUG)

    session_id = db._new_fake_session()
    app.logger.debug(f"http://localhost:5000/start/{session_id}/email")

    app.run(debug=True)
