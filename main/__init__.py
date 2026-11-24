"""Initialize the website for local development or Vercel."""
import os
import secrets

from algosdk.v2client.algod import AlgodClient
from flask import Flask
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import NullPool

from constants import ALGOD_TOKEN, ALGOD_SERVER_ADDRESS

app = Flask(__name__)
on_vercel = os.environ.get("VERCEL") == "1"
database_url = os.environ.get("DATABASE_URL")
secret_key = os.environ.get("SECRET_KEY")

if on_vercel and (not database_url or not secret_key):
    raise RuntimeError("Set DATABASE_URL and SECRET_KEY in the Vercel project environment.")

# Neon supplies a standard PostgreSQL URL; explicitly select the installed driver.
if database_url:
    if database_url.startswith(("postgres://", "postgresql://")):
        database_url = "postgresql+psycopg://" + database_url.split("://", 1)[1]
    if on_vercel and not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError("Vercel requires a hosted PostgreSQL DATABASE_URL.")

app.config.update(
    SECRET_KEY=secret_key or secrets.token_hex(32),
    SQLALCHEMY_DATABASE_URI=database_url or "sqlite:///main.db",
    SESSION_COOKIE_SECURE=on_vercel,
    REMEMBER_COOKIE_SECURE=on_vercel,
    SESSION_COOKIE_SAMESITE="Lax",
    # Vercel can stop execution after a response. Finish purchases before responding.
    BLOCKCHAIN_INLINE=on_vercel,
)
if database_url and database_url.startswith("postgresql+"):
    # Neon handles pooling; avoid retaining stale connections between invocations.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"poolclass": NullPool}

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# Constructing the client makes no network request, so pages can start independently.
algo_client = AlgodClient(ALGOD_TOKEN, ALGOD_SERVER_ADDRESS)

from main import routes, filters  # noqa: E402,F401

# Bootstrap a new database without deleting or reseeding existing records.
with app.app_context():
    db.create_all()
