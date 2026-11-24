"""Deployment smoke tests: no real accounts, database, or blockchain calls."""
import os
from unittest.mock import Mock, patch

import pytest


@pytest.fixture()
def website():
    with patch.dict(os.environ, {"DATABASE_URL": "sqlite://", "SECRET_KEY": "test-only", "VERCEL": "0"}):
        import main
    main.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, BLOCKCHAIN_INLINE=True)
    with main.app.app_context():
        assert str(main.db.engine.url) == "sqlite://"
        main.db.drop_all()
        main.db.create_all()
    yield main
    with main.app.app_context():
        main.db.session.remove()
        main.db.drop_all()


def test_register_login_and_pages(website):
    client = website.app.test_client()
    assert client.get("/login").status_code == 200
    response = client.post("/register", data={
        "username": "demo", "password": "testing123", "confirm_password": "testing123"
    })
    assert response.status_code == 302
    assert client.post("/login", data={"username": "demo", "password": "testing123"}).status_code == 302
    for path in ("/home", "/buyer_page", "/seller_page", "/account", "/account_wallet",
                 "/transactions", "/about", "/static/style.css"):
        assert client.get(path).status_code == 200, path


@pytest.mark.parametrize("outcome", ["success", "blockchain_error", "receipt_error"])
def test_checkout_persists_result_and_limits_receipt_access(website, monkeypatch, outcome):
    from main import routes
    from main.models import SellOrder, TransactionHistory, TransactionProgress, User

    with website.app.app_context():
        seller = User(username="seller", password="seller-hash", units=10, wallet_public_key="SELLER")
        buyer = User(username="buyer", password="buyer-hash", units=2, wallet_public_key="BUYER")
        outsider = User(username="outsider", password="outsider-hash", units=1)
        website.db.session.add_all([seller, buyer, outsider])
        website.db.session.flush()
        order = SellOrder(user_id=seller.id, units=5, price=4.5)
        website.db.session.add(order)
        website.db.session.commit()
        buyer_id, outsider_id, order_id = buyer.id, outsider.id, order.id
    chain = Mock(side_effect=RuntimeError("simulated node failure") if outcome == "blockchain_error" else None)
    receipt_sender = Mock(
        return_value=[{"address": "BUYER", "txid": "buyer-receipt", "url": "/buyer"},
                      {"address": "SELLER", "txid": "seller-receipt", "url": "/seller"}],
        side_effect=RuntimeError("simulated receipt failure") if outcome == "receipt_error" else None,
    )
    monkeypatch.setattr(routes, "begin_transaction", chain)
    monkeypatch.setattr(routes, "send_trade_receipts", receipt_sender)
    monkeypatch.setattr(routes.arduiino_util, "initiate_transfer", Mock())
    thread = Mock(side_effect=AssertionError("Vercel checkout must finish before the response"))
    monkeypatch.setattr(routes.threading, "Thread", thread)

    client = website.app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(buyer_id)
        session["_fresh"] = True
    response = client.post(f"/checkout_page?order_id={order_id}", data={"units": 2})
    assert response.status_code == 302
    tx_id = response.location.rsplit("/", 1)[-1]
    with website.app.app_context():
        website.db.session.remove()
        progress = website.db.session.get(TransactionProgress, tx_id)
        expected_status = progress.status
        assert expected_status == ("error" if outcome == "blockchain_error" else "done")
        assert progress.receipt_error == (outcome == "receipt_error")
        assert website.db.session.get(User, buyer_id).units == 4
        assert TransactionHistory.query.count() == 1
    assert client.get(response.location).status_code == 200
    status = client.get(f"/transaction_status/{tx_id}").get_json()
    assert status["status"] == expected_status
    assert len(status["receipts"]) == (1 if outcome == "success" else 0)
    with client.session_transaction() as session:
        session["_user_id"] = str(outsider_id)
    assert client.get(f"/transaction_status/{tx_id}").get_json()["status"] == "unknown"
    thread.assert_not_called()
    chain.assert_called_once_with(2)


def test_postgres_schema_and_config(website):
    """Compile schema and exercise Vercel startup without connecting to a real DB."""
    import subprocess
    import sys
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable
    from main.models import SellOrder, User

    assert type(SellOrder.__table__.c.user_id.type) is type(User.__table__.c.id.type)
    for table in website.db.metadata.sorted_tables:
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))

    environment = dict(os.environ, VERCEL="1", SECRET_KEY="test-only",
                       DATABASE_URL="postgresql://test:test@localhost/test?sslmode=require")
    code = """
from unittest.mock import patch
from sqlalchemy.pool import NullPool
with patch("flask_sqlalchemy.SQLAlchemy.create_all"):
    import main
assert main.app.config["BLOCKCHAIN_INLINE"]
assert main.app.config["SESSION_COOKIE_SECURE"]
with main.app.app_context():
    assert main.db.engine.url.drivername == "postgresql+psycopg"
    assert isinstance(main.db.engine.pool, NullPool)
    assert main.db.engine.url.query["sslmode"] == "require"
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], env=environment,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_vercel_requires_persistent_config():
    import subprocess
    import sys

    environment = dict(os.environ, VERCEL="1")
    environment.pop("DATABASE_URL", None)
    environment.pop("SECRET_KEY", None)
    result = subprocess.run([sys.executable, "-B", "-c", "import main"],
                            env=environment, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Set DATABASE_URL and SECRET_KEY" in result.stderr


def test_vercel_entrypoint_loads_without_shadowing_package():
    """Load the configured file under its module name, as Vercel does."""
    import subprocess
    import sys

    environment = dict(os.environ, VERCEL="0", SECRET_KEY="test-only", DATABASE_URL="sqlite://")
    code = """
import importlib.util
import json
import sys
from pathlib import Path
from flask import Flask

entrypoint = Path(next(iter(json.loads(Path("vercel.json").read_text())["functions"])))
spec = importlib.util.spec_from_file_location(entrypoint.stem, entrypoint.resolve())
module = importlib.util.module_from_spec(spec)
sys.modules[entrypoint.stem] = module
spec.loader.exec_module(module)
assert isinstance(module.app, Flask)
import main
assert hasattr(main, "__path__"), "main must resolve to the package, not the entrypoint"
assert module.app is main.app
client = module.app.test_client()
assert client.get("/").status_code == 302
assert client.get("/login").status_code == 200
"""
    result = subprocess.run([sys.executable, "-B", "-c", code], env=environment,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
