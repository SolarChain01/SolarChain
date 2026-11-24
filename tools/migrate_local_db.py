"""
One-time copy of the local SQLite data (instance/main.db) into the hosted database (Neon).

The hosted database starts empty, so accounts created locally (and their listings and
trade history) don't exist in production until they're copied. Passwords are stored as
bcrypt hashes and are copied unchanged, so the same passwords keep working.

Usage (from the repository root):
    # 1. Make the Neon connection string available, e.g. via the Vercel CLI:
    #      vercel env pull .env.local          (or export DATABASE_URL=... yourself)
    # 2. Preview (writes nothing):
    python tools/migrate_local_db.py --env-file .env.local
    # 3. Copy for real:
    python tools/migrate_local_db.py --env-file .env.local --apply

Safe to re-run: users already present with the same password hash, and listings / trades
already copied, are skipped. A username that exists in the target with a DIFFERENT password
is never overwritten; it's reported and that user's listings/trades are skipped.
"""
import argparse
import datetime
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "instance" / "main.db"


def read_env_file(path: Path) -> dict:
    """Minimal KEY=VALUE parser (handles quotes, ignores comments) for `vercel env pull` files."""
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().removeprefix("export ").strip()] = value.strip().strip('"').strip("'")
    return values


def describe_target(url: str) -> str:
    """Database URL without credentials, safe to print."""
    parts = urlsplit(url)
    if parts.scheme.startswith("sqlite"):
        return url
    return f"{parts.scheme}://{parts.hostname}{parts.path}"


def load_source(source: Path) -> dict:
    con = sqlite3.connect(f"file:{source}?mode=ro", uri=True)  # read-only: never touch the local DB
    con.row_factory = sqlite3.Row
    rows = {t: [dict(r) for r in con.execute(f'SELECT * FROM "{t}" ORDER BY id')]
            for t in ("user", "sell_order", "transaction_history")}
    con.close()
    return rows


def parse_date(value):
    if isinstance(value, datetime.datetime):
        return value
    return datetime.datetime.fromisoformat(str(value))


def migrate(source_rows: dict, db, models, apply: bool, log=print) -> dict:
    """Copy users, sell orders and trade history into `db`. Returns counts per category."""
    User, SellOrder, TransactionHistory = models
    stats = {k: 0 for k in ("users_added", "users_existing", "users_conflict",
                            "orders_added", "orders_skipped", "trades_added", "trades_skipped")}
    id_map = {}  # local user id -> target user id

    # ---- users (matched by username) ----
    for u in source_rows["user"]:
        existing = User.query.filter_by(username=u["username"]).first()
        if existing is not None:
            if existing.password == u["password"]:
                id_map[u["id"]] = existing.id
                stats["users_existing"] += 1
                log(f"  = user {u['username']!r}: already in target")
            else:
                stats["users_conflict"] += 1
                log(f"  ! user {u['username']!r}: a DIFFERENT account with this name exists in the target; "
                    "skipped (not overwritten), along with its listings and trades")
            continue
        new = User(username=u["username"], password=u["password"],
                   image_file=u.get("image_file") or "profile.jpg",
                   units=u.get("units") or 0, seller_rep=u.get("seller_rep") or 0,
                   wallet_public_key=u.get("wallet_public_key"))
        db.session.add(new)
        db.session.flush()  # get the target-assigned id
        id_map[u["id"]] = new.id
        stats["users_added"] += 1
        log(f"  + user {u['username']!r}")

    # ---- open sell orders (local user_id was stored as text) ----
    for o in source_rows["sell_order"]:
        try:
            owner = id_map.get(int(o["user_id"]))
        except (TypeError, ValueError):
            owner = None
        if owner is None:
            stats["orders_skipped"] += 1
            log(f"  - listing #{o['id']}: owner not migrated, skipped")
            continue
        key = dict(user_id=owner, units=o["units"], price=o["price"], status=o.get("status") or 0)
        if SellOrder.query.filter_by(**key).first():
            stats["orders_skipped"] += 1
            continue
        db.session.add(SellOrder(**key, buyer_id=o.get("buyer_id")))
        stats["orders_added"] += 1

    # ---- trade history ----
    for t in source_rows["transaction_history"]:
        seller, buyer = id_map.get(t["seller_id"]), id_map.get(t["buyer_id"])
        if seller is None or buyer is None:
            stats["trades_skipped"] += 1
            log(f"  - trade #{t['id']}: buyer or seller not migrated, skipped")
            continue
        key = dict(seller_id=seller, buyer_id=buyer, units=t["units"], price=t["price"], date=parse_date(t["date"]))
        if TransactionHistory.query.filter_by(**key).first():
            stats["trades_skipped"] += 1
            continue
        db.session.add(TransactionHistory(**key, seller_username=t["seller_username"]))
        stats["trades_added"] += 1

    if apply:
        db.session.commit()
    else:
        db.session.rollback()
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="local SQLite file (default: instance/main.db)")
    parser.add_argument("--env-file", type=Path, help="file containing DATABASE_URL (e.g. from `vercel env pull`)")
    parser.add_argument("--apply", action="store_true", help="actually write; without it this is a dry run")
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if args.env_file:
        url = read_env_file(args.env_file).get("DATABASE_URL") or url
    if not url:
        sys.exit("DATABASE_URL is not set. Export it or pass --env-file (see the docstring).")
    if not args.source.exists():
        sys.exit(f"Source database not found: {args.source}")
    if url.startswith("sqlite") and Path(url.split("///", 1)[-1]).resolve() == args.source.resolve():
        sys.exit("Target is the same file as the source; refusing.")

    # The app reads DATABASE_URL at import time; it also creates any missing tables in the target.
    os.environ["DATABASE_URL"] = url
    sys.path.insert(0, str(ROOT))
    from main import app, db
    from main.models import SellOrder, TransactionHistory, User

    rows = load_source(args.source)
    print(f"Source : {args.source} ({len(rows['user'])} users, {len(rows['sell_order'])} listings, "
          f"{len(rows['transaction_history'])} trades)")
    print(f"Target : {describe_target(url)}")
    print(f"Mode   : {'APPLY (writing)' if args.apply else 'DRY RUN (nothing is written)'}\n")

    with app.app_context():
        stats = migrate(rows, db, (User, SellOrder, TransactionHistory), apply=args.apply)

    print("\nSummary:", ", ".join(f"{k}={v}" for k, v in stats.items()))
    if not args.apply:
        print("Dry run only. Re-run with --apply to copy the data.")
    return stats


if __name__ == "__main__":
    main()
