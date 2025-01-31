import configparser

from flask import Flask
import logging
import os
import sys
import json
from flask_cors import CORS

import context
from notifications.email_sender import EmailSettings, EmailSender, EmailSenderMock
from notifications.notifier import Notifier
from pages import pages_blueprint
from services.licco import licco_ws_blueprint
from dal.licco import initialize_collections

__author__ = 'mshankar@slac.stanford.edu'

# Initialize application.
app = Flask("licco")
CORS(app, supports_credentials=True)
# Set the expiration for static files
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300

app.secret_key = "A secret key for licco"
app.debug = json.loads(os.environ.get("DEBUG", "false").lower())
app.config["TEMPLATES_AUTO_RELOAD"] = app.debug

app.config["NOTIFICATIONS"] = {"service_url": "http://localhost:3000"}
send_smtp_emails = os.environ.get("LICCO_SEND_EMAILS", False)

# read credentials file for notifications module
credentials_file = os.environ.get("LICCO_CREDENTIALS_FILE", "./credentials.ini")
if not os.path.exists(credentials_file):
    print(f"'credentials.ini' file was not found (path: {credentials_file}), email user notifications are disabled")
    app.config["NOTIFICATIONS"]["email"] = {
        "development_mode": not send_smtp_emails
    }
else:
    config = configparser.ConfigParser()
    config.read(credentials_file)
    app.config["NOTIFICATIONS"]["email"] = {
        "url": config["email"]["url"],
        "port": config["email"]["port"],
        "user": config["email"]["user"],
        "password": config["email"]["password"],
        "username_to_email_service": config["email"]["username_to_email_service"],
        "development_mode": send_smtp_emails,
    }

root = logging.getLogger()
root.setLevel(logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO")))
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
root.addHandler(ch)

# Register routes.
app.register_blueprint(pages_blueprint, url_prefix="")
app.register_blueprint(licco_ws_blueprint, url_prefix="/ws")


def create_notifier(app: Flask) -> Notifier:
    notifications_config = app.config["NOTIFICATIONS"]
    if not notifications_config:
        return Notifier("", EmailSenderMock())

    email_sender = EmailSenderMock()
    email_config = notifications_config["email"]
    if email_config and not email_config["development_mode"]:
        email_sender = EmailSender(EmailSettings(email_config["url"], email_config["port"],
                                                 email_config["user"], email_config["password"],
                                                 email_config["username_to_email_service"]))
    service_url = notifications_config["service_url"]
    return Notifier(service_url, email_sender)


context.notifier = create_notifier(app)

initialize_collections()


if __name__ == '__main__':
    print("Please use gunicorn for development as well.")
    sys.exit(-1)
