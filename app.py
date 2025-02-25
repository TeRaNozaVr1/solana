from fastapi import FastAPI, HTTPException
import time
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.publickey import PublicKey
from solana.system_program import TransferParams, transfer
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from spl.token.instructions import transfer_checked, get_associated_token_address
from spl.token.constants import TOKEN_PROGRAM_ID
import base58
import os

# ------------------- НАЛАШТУВАННЯ -------------------
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
TOKEN_RECEIVER = "4ofLfgCmaJYC233vTGv78WFD4AfezzcMiViu26dF3cVU"  # Гаманець для отримання платежів
SPL_TOKEN_MINT = "3EwV6VTHYHrkrZ3UJcRRAxnuHiaeb8EntqX85Khj98Zo"  # Адреса SPL-токена
SPL_RATE = 0.00048  # Обмінний курс

# Завантаження приватного ключа для підпису транзакцій
PRIVATE_KEY_BASE58 = os.getenv("PRIVATE_KEY")  # Завантажуємо з .env або Render
PRIVATE_KEY_BYTES = base58.b58decode(PRIVATE_KEY_BASE58)
TOKEN_SENDER_KEYPAIR = Keypair.from_bytes(PRIVATE_KEY_BYTES)

client = Client(SOLANA_RPC_URL)
app = FastAPI()

# ------------------- ФУНКЦІЇ -------------------
def check_transaction(tx_signature):
    """Перевіряє, чи транзакція була підтверджена."""
    for _ in range(10):  # Чекати 20 сек (10 спроб по 2 сек)
        tx_info = client.get_transaction(tx_signature, commitment="confirmed")
        if tx_info["result"]:
            return tx_info["result"]
        time.sleep(2)
    return None

def send_spl_tokens(receiver_wallet, amount):
    """Відправка SPL-токенів після підтвердження платежу."""
    sender_wallet = TOKEN_SENDER_KEYPAIR.public_key
    receiver_wallet = PublicKey(receiver_wallet)
    mint_address = PublicKey(SPL_TOKEN_MINT)

    # Отримуємо ATA (Associated Token Account)
    receiver_ata = get_associated_token_address(receiver_wallet, mint_address)
    
    # Створюємо транзакцію
    transaction = Transaction()
    transaction.add(
        transfer_checked(
            source=sender_wallet,
            dest=receiver_ata,
            owner=sender_wallet,
            mint=mint_address,
            amount=int(amount * (10 ** 6)),  # Кількість токенів (з урахуванням десяткових)
            decimals=6,  # Десяткові для SPL
            program_id=TOKEN_PROGRAM_ID
        )
    )

    # Відправляємо транзакцію
    tx_signature = client.send_transaction(transaction, TOKEN_SENDER_KEYPAIR, opts=TxOpts(skip_preflight=True))
    return tx_signature

# ------------------- API -------------------
@app.get("/check_payment/{tx_signature}")
async def check_payment(tx_signature: str):
    """Перевіряє оплату і видає SPL-токени."""
    tx_data = check_transaction(tx_signature)
    if not tx_data:
        raise HTTPException(status_code=400, detail="Транзакція не знайдена або не підтверджена.")

    sender = tx_data["transaction"]["message"]["accountKeys"][0]
    amount = tx_data["meta"]["postBalances"][0] - tx_data["meta"]["preBalances"][0]

    # Конвертація в SPL-токени
    spl_amount = amount * SPL_RATE

    # Відправка SPL-токенів
    spl_tx = send_spl_tokens(sender, spl_amount)

    return {
        "status": "success",
        "sender": sender,
        "amount_received": amount,
        "spl_sent": spl_amount,
        "spl_tx_signature": spl_tx
    }