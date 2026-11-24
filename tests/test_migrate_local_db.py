"""The local-SQLite -> hosted-DB migration: accounts keep working, re-runs are no-ops, conflicts aren't overwritten."""
import datetime
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


@pytest.fixture()
def website():
    with patch.dict(os.environ, {"DATABASE_URL": "sqlite://", "SECRET_KEY": "test-only", "VERCEL": "0"}):
        import main
    main.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with main.app.app_context():
        main.db.drop_all()
        main.db.create_all()
    yield main
    with main.app.app_context():
        main.db.session.remove()
        main.db.drop_all()


@pytest.fixture()
def legacy_source(tmp_path, website):
    """A SQLite file shaped like the old local instance/main.db (sell_order.user_id is text)."""
    path = tmp_path / "main.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR(50), image_file VARCHAR(20),
                           password VARCHAR(60), units INTEGER, seller_rep INTEGER, wallet_public_key VARCHAR(100));
        CREATE TABLE sell_order (id INTEGER PRIMARY KEY, user_id VARCHAR(50), units INTEGER, price DOUBLE,
                                 status INTEGER, buyer_id VARCHAR(50));
        CREATE TABLE transaction_history (id INTEGER PRIMARY KEY, seller_id INTEGER, seller_username VARCHAR(50),
                                          buyer_id INTEGER, units INTEGER, price DOUBLE, date DATETIME);
    """)
    hash_abc = website.bcrypt.generate_password_hash("abc-pass").decode()
    hash_seller = website.bcrypt.generate_password_hash("seller-pass").decode()
    con.executemany("INSERT INTO user VALUES (?,?,?,?,?,?,?)", [
        (3, "abc", "profile.jpg", hash_abc, 36, 2, None),
        (5, "Seller", "profile.jpg", hash_seller, 22, 5, None),
    ])
    con.execute("INSERT INTO sell_order VALUES (2, '5', 2, 6.0, 0, NULL)")
    con.execute("INSERT INTO transaction_history VALUES (25, 3, 'abc', 5, 1, 45.0, ?)",
                (str(datetime.datetime(2026, 3, 11, 7, 33, 53, 123456)),))
    con.commit()
    con.close()
    return path


def run(website, source, apply):
    import migrate_local_db as m
    from main.models import SellOrder, TransactionHistory, User
    with website.app.app_context():
        return m.migrate(m.load_source(source), website.db, (User, SellOrder, TransactionHistory),
                         apply=apply, log=lambda *_: None)


def test_dry_run_writes_nothing(website, legacy_source):
    from main.models import User
    stats = run(website, legacy_source, apply=False)
    assert stats["users_added"] == 2
    with website.app.app_context():
        assert User.query.count() == 0


def test_migrated_accounts_can_log_in_and_rerun_is_a_noop(website, legacy_source):
    from main.models import SellOrder, TransactionHistory, User

    # Someone registered in pre-prod first, so target ids differ from local ids
    with website.app.app_context():
        website.db.session.add(User(username="early_bird", password="x-hash", units=1))
        website.db.session.commit()

    first = run(website, legacy_source, apply=True)
    assert (first["users_added"], first["orders_added"], first["trades_added"]) == (2, 1, 1)

    with website.app.app_context():
        abc, seller = User.query.filter_by(username="abc").one(), User.query.filter_by(username="Seller").one()
        order = SellOrder.query.one()
        trade = TransactionHistory.query.one()
        assert order.user_id == seller.id                     # text '5' remapped to the new integer id
        assert (trade.seller_id, trade.buyer_id) == (abc.id, seller.id)
        assert trade.date == datetime.datetime(2026, 3, 11, 7, 33, 53, 123456)

    client = website.app.test_client()
    assert client.post("/login", data={"username": "abc", "password": "abc-pass"}).status_code == 302
    assert client.get("/home").status_code == 200
    bad = website.app.test_client().post("/login", data={"username": "abc", "password": "wrong"})
    assert bad.status_code == 200 and b"Login Unsuccessful" in bad.data

    second = run(website, legacy_source, apply=True)
    assert (second["users_added"], second["orders_added"], second["trades_added"]) == (0, 0, 0)
    assert second["users_existing"] == 2


def test_existing_different_account_is_not_overwritten(website, legacy_source):
    from main.models import TransactionHistory, User
    with website.app.app_context():
        website.db.session.add(User(username="abc", password="someone-elses-hash", units=1))
        website.db.session.commit()

    stats = run(website, legacy_source, apply=True)
    assert stats["users_conflict"] == 1 and stats["users_added"] == 1
    with website.app.app_context():
        assert User.query.filter_by(username="abc").one().password == "someone-elses-hash"
        assert TransactionHistory.query.count() == 0  # trade involved the conflicting user
