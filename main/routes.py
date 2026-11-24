"""
This module defines the Flask application routes, utility functions, and views for the core functionality.
It includes user authentication, rendering templates, handling user actions like buying/selling units, and
managing transaction history. This module integrates Flask, Flask-Login, SQLAlchemy, and forms for a complete web experience.
"""

import datetime  # Used for timestamping transactions
import threading
import uuid
from typing import List  # Type hint for a list return type

from flask import flash, redirect, render_template, url_for, request  # Flask utilities for routing and responses
from flask_login import login_required, login_user, current_user, logout_user  # Session management
from sqlalchemy import or_  # SQLAlchemy operator for OR conditions

from Arduino import arduiino_util
from constants import BATTERY_CAPACITY, NETWORK_NAME
from main import app, bcrypt, db, algo_client
from main.blockchain.receipts import explorer_address_url, is_valid_address, send_trade_receipts
from main.blockchain.transfer_basic import begin_transaction
from main.forms import LoginForm, PurchaseForm, RegistrationForm, SellOrderForm  # WTForms for handling forms
from main.models import SellOrder, TransactionHistory, TransactionProgress, User, get_sellers  # Database models and utility function


@app.context_processor
def inject_constants():
    """Make app-wide constants available in every template."""
    return {"BATTERY_CAPACITY": BATTERY_CAPACITY}


@app.route('/layout')
def layout():
    """
    Render the base layout template for testing purposes.
    """
    return render_template("layout.html")


@app.route('/')
@app.route('/home')
def home():
    """
    Render the home page. Redirects to login if the user is not authenticated.
    Displays user's current unit usage and dashboard information.
    """
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    return render_template("index.html", **get_dashboard_context())


def get_dashboard_context():
    """
    Collect everything the dashboard shows for the current user: battery state,
    the user's own listings, trading totals, recent activity and a market snapshot.
    """
    capacity = BATTERY_CAPACITY
    units = current_user.units or 0

    # The user's own open sell orders
    my_orders = list(get_user_sell_orders())
    listed_units = sum(o.units for o in my_orders)

    # Trading history: CREDIT = user bought, DEBIT = user sold
    history = get_transaction_history(current_user.id)
    bought = [h['row'] for h in history if h['type'] == "CREDIT"]
    sold = [h['row'] for h in history if h['type'] == "DEBIT"]

    # Live market: other users' orders whose seller can still deliver
    market = [m for m in get_sell_orders() if m['status'] == 0]
    market.sort(key=lambda m: m['order'].price)

    return {
        "capacity": capacity,
        "units": units,
        "battery_pct": min(units_used(units, capacity), 100),
        "free_space": max(capacity - units, 0),
        "listed_units": listed_units,
        "sellable_units": max(units - listed_units, 0),
        "my_order_count": len(my_orders),
        "stats": {
            "units_bought": sum(r.units for r in bought),
            "spent": sum(r.price for r in bought),
            "units_sold": sum(r.units for r in sold),
            "earned": sum(r.price for r in sold),
            "trades": len(history),
        },
        "recent_activity": history[:5],
        "market_offers": market[:4],
        "market_offer_count": len(market),
        "market_units": sum(m['order'].units for m in market),
        "best_price": market[0]['order'].price if market else None,
        "wallet_connected": bool(current_user.wallet_public_key),
    }


def units_used(current, total: int = BATTERY_CAPACITY):
    """
    Calculate the percentage of units used by the user.

    Args:
        current (int): Current units of the user.
        total (int): Total units available. Defaults to 36.

    Returns:
        int: Percentage of units used.
    """
    proportion = current / total
    return int(proportion * 100)


@app.route('/transactions')
def transactions():
    """
    Render the transactions page, showing the transaction history for the current user.
    Redirects to login if the user is not authenticated.
    """
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    return render_template("transaction.html", history=get_transaction_history(current_user.id))


@app.route('/about')
def about():
    """
    Render the about page with static information about the application.
    """
    return render_template("about.html")


@app.route('/account')
def account():
    """
    Render the account page to display user-specific details.
    """
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    return render_template("account_info.html")

@app.route('/update_account', methods=['GET', 'POST'])
@login_required
def update_account():
    """Change the current user's username (2-20 characters, must be unique)."""
    if request.method == 'POST':
        new_username = (request.form.get('username') or '').strip()
        if not 2 <= len(new_username) <= 20:
            flash('Username must be between 2 and 20 characters.', 'error')
        elif new_username == current_user.username:
            flash('That is already your username.', 'info')
        elif User.query.filter_by(username=new_username).first():
            flash('That username is already taken, please choose another.', 'error')
        else:
            current_user.username = new_username
            db.session.commit()
            flash("Profile updated successfully!", "success")
    return redirect(url_for('account'))  # Redirect to the same page after updating


@app.route('/update_wallet', methods=['POST'])
@login_required
def update_wallet():
    """
    Link or unlink the user's Algorand wallet (e.g. Pera Wallet) by its public address.
    Only the public address is stored; recovery phrases are rejected and never saved or logged.
    """
    if request.form.get("action") == "unlink":
        current_user.wallet_public_key = None
        db.session.commit()
        flash("Wallet unlinked. You'll no longer receive on-chain trade receipts.", "success")
        return redirect(url_for('account_wallet'))

    address = (request.form.get("wallet_key") or "").strip()
    if len(address.split()) >= 12:
        # Looks like a 25-word recovery passphrase: refuse it and don't echo it back.
        flash("That looks like a recovery passphrase, so it was NOT saved. Only paste your public "
              "wallet address. Never share your passphrase with anyone.", "danger")
    elif not is_valid_address(address):
        flash("That isn't a valid Algorand address. It should be 58 characters, "
              "letters A-Z and digits 2-7.", "error")
    else:
        if algo_client is not None:
            try:
                algo_client.account_info(address)  # confirms the node accepts the address
            except Exception:
                flash(f"Couldn't reach the {NETWORK_NAME} node to check this address; "
                      "it was saved anyway.", "info")
        current_user.wallet_public_key = address
        db.session.commit()
        flash("Wallet linked! Your trades will now appear in your wallet's activity.", "success")
    return redirect(url_for('account_wallet'))


@app.route('/account_wallet')
def account_wallet():
    """
    Show the linked wallet (address, balance, explorer link) and the form to link one.
    """
    if not current_user.is_authenticated:
        return redirect(url_for("login"))

    wallet = None
    address = current_user.wallet_public_key
    if address:
        wallet = {"address": address, "explorer_url": explorer_address_url(address), "balance": None}
        if algo_client is not None:
            try:
                wallet["balance"] = algo_client.account_info(address).get("amount", 0) / 1_000_000
            except Exception:
                pass  # balance just shows as unavailable
    return render_template("account_wallet.html", title="Wallet", wallet=wallet, network=NETWORK_NAME)

@app.route("/register", methods=['GET', 'POST'])
def register():
    """
    Handle user registration. Redirects authenticated users to the home page.
    On successful registration, hashes the password and stores the new user in the database.
    """
    if current_user.is_authenticated:
        return redirect(url_for("account"))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        user = User(username=form.username.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash(f'Account created for {form.username.data}!', 'success')
        return redirect(url_for('home'))
    return render_template('register.html', title='Register', form=form)


@app.route("/login", methods=['GET', 'POST'])
def login():
    """
    Handle user login. Redirects authenticated users to the home page.
    Validates user credentials and starts a session on successful login.
    """
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get("next")
            return redirect(next_page) if next_page else redirect(url_for('home'))
        flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html', title='Login', form=form)


@app.route("/seller_page", methods=['GET', 'POST'])
@login_required
def seller_page():
    """
    Display and handle actions on the seller page. Allows users to create sell orders.
    """
    form = SellOrderForm()
    if form.validate_on_submit():
        units, price = form.unit.data, round(form.price.data, 2)
        already_listed = sum(o.units for o in get_user_sell_orders())
        can_list = max((current_user.units or 0) - already_listed, 0)
        if units <= can_list:
            order = SellOrder(user_id=current_user.id, units=units, price=price)
            db.session.add(order)
            db.session.commit()
            flash(f"Listed {units} unit{'s' if units != 1 else ''} at \u20b9{price:,.2f} per unit.", "success")
            # Redirect after a successful POST so refreshing the page can't create a duplicate listing
            return redirect(url_for("seller_page"))
        flash(f"You can only list {can_list} more unit{'s' if can_list != 1 else ''} "
              "(stored units minus units already listed).", "error")

    sell_orders = get_user_sell_orders()
    return render_template("seller_page.html", title="Page", sell_orders=sell_orders, form=form)


@app.route("/buyer_page", methods=['GET', 'POST'])
@login_required
def buyer_page():
    """
    Display the buyer page with available sell orders from other users.
    """
    sell_orders = get_sell_orders()
    return render_template("buyer_page.html", title="Buy Units", sell_orders=sell_orders)


@app.route("/cancel_sell_order", methods=["GET", "POST"])
@login_required
def cancel_sell_order():
    """
    Cancel an existing sell order for the current user.
    """
    order_id = request.args.get("order_id")
    if order_id is None:
        return redirect(url_for("home"))

    # Only the owner can cancel their own listing
    order: SellOrder = SellOrder.query.filter_by(id=order_id, user_id=current_user.id).first()
    if order is None:
        flash("That listing doesn't exist or isn't yours.", "error")
        return redirect(url_for('seller_page'))
    db.session.delete(order)
    db.session.commit()
    flash(f"Listing #{order.id} cancelled.", "success")
    return redirect(url_for('seller_page'))


@app.route("/checkout_page", methods=["GET", "POST"])
@login_required
def checkout_page():
    """
    Handle the checkout process when a user purchases units from a seller.
    """
    order_id = request.args.get("order_id")
    if order_id is None:
        return redirect(url_for("home"))

    order: SellOrder = SellOrder.query.filter_by(id=order_id).first()
    seller: User = User.query.filter_by(id=order.user_id).first() if order else None

    if not order or not seller:
        flash("That offer is no longer available. It may have sold out or been cancelled.", "error")
        return redirect(url_for("buyer_page"))
    if seller.id == current_user.id:
        flash("You can't buy from your own listing.", "error")
        return redirect(url_for("buyer_page"))

    form = PurchaseForm()
    if form.validate_on_submit():
        if form.units.data <= order.units:
            total_price = order.price * form.units.data
            buyer: User = User.query.filter_by(id=current_user.id).first()
            units = form.units.data

            if seller.units >= units:
                if buyer.units + form.units.data <= BATTERY_CAPACITY:

                    tx_id = str(uuid.uuid4())
                    db.session.add(TransactionProgress(
                        id=tx_id, buyer_id=buyer.id, seller_id=seller.id
                    ))

                    buyer.units += units
                    order.units -= units
                    seller.units -= units

                    history = TransactionHistory(
                        seller_id=seller.id,
                        seller_username=seller.username,
                        buyer_id=buyer.id,
                        units=units,
                        price=total_price,
                        date=datetime.datetime.now()
                    )

                    db.session.add(history)

                    if order.units == 0:
                        db.session.delete(order)

                    db.session.commit()

                    # Plain values only: ORM objects must not cross into the worker thread
                    receipts = [
                        {"role": "buyer", "address": buyer.wallet_public_key,
                         "note": f"Bought {units} energy unit(s) from {seller.username} for Rs {total_price:,.2f}"},
                        {"role": "seller", "address": seller.wallet_public_key,
                         "note": f"Sold {units} energy unit(s) to {buyer.username} for Rs {total_price:,.2f}"},
                    ]
                    if app.config["BLOCKCHAIN_INLINE"]:
                        process_blockchain_transaction(tx_id, units, receipts)
                    else:
                        threading.Thread(
                            target=process_blockchain_transaction,
                            args=(tx_id, units, receipts),
                            daemon=True
                        ).start()

                    arduiino_util.initiate_transfer(units)

                    return redirect(url_for("transaction_processing", tx_id=tx_id))
                else:
                    flash(f"Purchase unsuccessful for {form.units.data} units. Your Battery is Full!")
            else:
                flash(f"Purchase unsuccessful for {form.units.data} units. Seller Does Not have these Units!", "error")
        else:
            flash('Units exceeded!', 'error')
    return render_template("checkout_page.html", title="Checkout", order=order, seller=seller, form=form)

def process_blockchain_transaction(tx_id, units, receipts):
    """
    Worker thread: run the on-chain purchase, then send receipts to linked wallets.
    The status only becomes "done" after the blockchain transaction has actually succeeded.
    """
    with app.app_context():
        progress = db.session.get(TransactionProgress, tx_id)
        if progress is None:
            return
        try:
            begin_transaction(units)
        except Exception as e:
            print("Blockchain transaction failed:", e)
            progress.status = "error"
            db.session.commit()
            return

        # Receipts are best-effort: a failure here doesn't undo a successful purchase
        try:
            progress.receipts = send_trade_receipts(receipts)
        except Exception as e:
            print("Sending wallet receipts failed:", e)
            progress.receipt_error = True

        progress.status = "done"
        db.session.commit()

@app.route("/transaction_processing/<tx_id>")
@login_required
def transaction_processing(tx_id):
    return render_template("transaction_processing.html", tx_id=tx_id)

@app.route("/transaction_status/<tx_id>")
@login_required
def transaction_status_api(tx_id):
    """Read shared status; receipt details are visible only to trade participants."""
    progress = db.session.get(TransactionProgress, tx_id)
    if progress is None or current_user.id not in (progress.buyer_id, progress.seller_id):
        return {"status": "unknown", "receipts": [], "receipt_error": False}
    receipts = [r for r in progress.receipts if r["address"] == current_user.wallet_public_key]
    return {"status": progress.status, "receipts": receipts, "receipt_error": progress.receipt_error}

def get_user_sell_orders():
    """
    Retrieve all sell orders created by the current user.

    Returns:
        List[SellOrder]: List of sell orders belonging to the current user.
    """
    qry = SellOrder.query.filter_by(user_id=current_user.id)
    return qry


def get_transaction_history(user_id):
    """
    Retrieve the transaction history for a given user.

    Args:
        user_id (int): ID of the user.

    Returns:
        List[dict]: List of transactions with type (CREDIT/DEBIT) and details.
    """
    history = []
    transacts = TransactionHistory.query.filter(or_(
        TransactionHistory.buyer_id == user_id,
        TransactionHistory.seller_id == user_id
    )).order_by(TransactionHistory.date.desc())
    for transact in transacts:
        history.append({
            'row': transact,
            'type': "CREDIT" if transact.buyer_id == user_id else "DEBIT"
        })
    return history


def get_sell_orders():
    """
    Retrieve all active sell orders from the database along with their sellers.

    Returns:
        List[dict]: List of orders and their respective seller details.
    """
    sell_orders = SellOrder.query.all()
    orders_with_seller = []
    for order in sell_orders:
        seller = User.query.filter_by(id=order.user_id).first()
        if seller.id == current_user.id:
            continue
        orders_with_seller.append({
            'order': order,
            'seller': seller,
            'status': int(order.units > seller.units)
        })
    return orders_with_seller


@app.route("/logout")
def logout():
    """
    Log the user out and redirect to the about page.
    """
    logout_user()
    return redirect(url_for("about"))
