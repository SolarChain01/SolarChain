"""
On-chain trade receipts for linked wallets (e.g. Pera Wallet).

After a purchase, the platform account sends a 0-ALGO payment to the buyer's and the
seller's linked Algorand addresses. The transaction note describes the trade, so it shows
up in the user's wallet activity without them having to sign anything.
"""
from algosdk import encoding, transaction
from algokit_utils import get_account_from_mnemonic

from account_constants import ACCOUNTS_LOCAL, ACCOUNTS_TEST_NET
from constants import LOCAL_NET, PERA_EXPLORER_URL
from main import algo_client

NOTE_PREFIX = "SolarChain"


def is_valid_address(address: str | None) -> bool:
    """True if the string is a well-formed Algorand address (58 chars + checksum)."""
    return bool(address) and encoding.is_valid_address(address)


def explorer_tx_url(txid: str) -> str | None:
    return f"{PERA_EXPLORER_URL}/tx/{txid}" if PERA_EXPLORER_URL else None


def explorer_address_url(address: str) -> str | None:
    return f"{PERA_EXPLORER_URL}/address/{address}" if PERA_EXPLORER_URL else None


def _platform_account():
    """The platform account that pays the receipt fees."""
    return get_account_from_mnemonic(ACCOUNTS_LOCAL[0] if LOCAL_NET else ACCOUNTS_TEST_NET[0])


def send_trade_receipts(receipts: list[dict]) -> list[dict]:
    """
    Send a 0-ALGO receipt to each linked wallet.

    Args:
        receipts: [{"role": "buyer"|"seller", "address": str, "note": str}, ...].
                  Entries with a missing/invalid address are skipped.

    Returns:
        [{"role", "address", "txid", "url"}] for every confirmed receipt.
    """
    targets = [r for r in receipts if is_valid_address(r.get("address"))]
    if not targets or algo_client is None:
        return []

    sender = _platform_account()
    params = algo_client.suggested_params()

    signed, meta = [], []
    for r in targets:
        note = f"{NOTE_PREFIX}: {r['note']}".encode("utf-8")[:1000]  # note field max is 1 KB
        txn = transaction.PaymentTxn(sender=sender.address, sp=params, receiver=r["address"], amt=0, note=note)
        signed.append(txn.sign(sender.private_key))
        meta.append(r)

    sent = []
    for stxn, r in zip(signed, meta):
        txid = algo_client.send_transaction(stxn)
        transaction.wait_for_confirmation(algo_client, txid, 6)
        sent.append({"role": r["role"], "address": r["address"], "txid": txid, "url": explorer_tx_url(txid)})
    return sent
