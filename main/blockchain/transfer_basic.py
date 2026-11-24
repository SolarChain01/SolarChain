import algokit_utils
from algokit_utils import OnSchemaBreak, \
    OnUpdate, transfer, TransferParameters, TransferAssetParameters, get_account_from_mnemonic, Account
from algosdk.transaction import SuggestedParams
from algosdk.v2client.indexer import IndexerClient

from SolarChain.projects.SolarChain.smart_contracts.artifacts.unit_transfer.asset_purchase_client import \
    AssetPurchaseClient
from constants import LOCAL_NET, INDEXER_TOKEN, INDEXER_ADDRESS
from main import algo_client
from account_constants import ACCOUNTS_LOCAL, ACCOUNTS_TEST_NET, ASSET_ID_TEST_NET, \
    ASSET_ID_LOCAL_NET

FEES = 1_000
PRICE = 2_000

def begin_transaction(units: int):
    """Run the on-chain purchase. Raises if any step fails so the caller can report it."""
    try:
        __begin_transaction__(units)
    except Exception as e:
        print("Failed to begin transaction:", e)
        raise

def __begin_transaction__(units: int):
    if LOCAL_NET:
        acc1: Account = get_account_from_mnemonic(ACCOUNTS_LOCAL[0])
        acc2: Account = get_account_from_mnemonic(ACCOUNTS_LOCAL[1])
    else:
        acc1: Account = get_account_from_mnemonic(ACCOUNTS_TEST_NET[0])
        acc2: Account = get_account_from_mnemonic(ACCOUNTS_TEST_NET[1])

    params: SuggestedParams = algo_client.suggested_params()
    params.min_fee = 0
    params.flat_fee = True
    created_asset = ASSET_ID_TEST_NET if not LOCAL_NET else ASSET_ID_LOCAL_NET

    app_indexer_client: IndexerClient = IndexerClient(indexer_address=INDEXER_ADDRESS, indexer_token=INDEXER_TOKEN)
    app_client = AssetPurchaseClient(
        algod_client=algo_client,
        creator=acc1,
        indexer_client=app_indexer_client
    )

    app_client.deploy(
        on_schema_break=OnSchemaBreak.AppendApp,
        on_update=OnUpdate.AppendApp,
    )

    transfer(
        algo_client,
        TransferParameters(
            from_account=acc2,
            to_address=app_client.app_address,
            micro_algos=(FEES + PRICE) * units,
        )
    )

    app_client.contract(seller=acc1.address, buyer=acc2.address, price=PRICE, qty=units, asset=created_asset)
    app_client.asset_opt_in(asset=created_asset)

    algokit_utils.transfer_asset(
        algo_client,
        TransferAssetParameters(
            from_account=acc1,
            to_address=app_client.app_address,
            asset_id=created_asset,
            amount=units
        )
    )

    app_client.begin_transfer(asset=created_asset, seller=acc1.address, buyer=acc2.address, price=PRICE, qty=units)
