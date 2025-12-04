import requests
import base64
import json
import hashlib
from datetime import datetime, timedelta

class MidtransPayment:
    """
    Midtrans Payment Gateway Integration
    Dokumentasi: https://docs.midtrans.com/reference/createtransaction
    """

    def __init__(self, server_key: str, is_production: bool = False):
        """
        Args:
            server_key: Server Key dari Midtrans Dashboard
            is_production: True untuk production, False untuk sandbox
        """
        self.server_key = server_key
        self.is_production = is_production

        # Base URL
        if is_production:
            self.base_url = "https://api.midtrans.com/v2"
        else:
            self.base_url = "https://api.sandbox.midtrans.com/v2"

        # Basic auth header
        auth_string = f"{server_key}:"
        auth_bytes = auth_string.encode('ascii')
        base64_bytes = base64.b64encode(auth_bytes)
        base64_auth = base64_bytes.decode('ascii')

        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Basic {base64_auth}'
        }

    def create_qris_transaction(self, order_id: str, amount: int, customer_details: dict = None):
        """
        Buat transaksi QRIS

        Args:
            order_id: Unique order ID (max 50 chars, alphanumeric + - _ ~)
            amount: Jumlah dalam Rupiah (integer)
            customer_details: Dict dengan key: first_name, email, phone (opsional)

        Returns:
            dict: Response dari Midtrans atau None jika error

        Example Response:
        {
            "status_code": "201",
            "status_message": "QRIS transaction is created",
            "transaction_id": "...",
            "order_id": "TOPUP-123-...",
            "gross_amount": "10000.00",
            "payment_type": "qris",
            "transaction_time": "2024-12-03 12:00:00",
            "transaction_status": "pending",
            "fraud_status": "accept",
            "actions": [
                {
                    "name": "generate-qr-code",
                    "method": "GET",
                    "url": "https://api.sandbox.midtrans.com/v2/qris/..."
                }
            ]
        }
        """
        url = f"{self.base_url}/charge"

        # Default customer details jika tidak diberikan
        if not customer_details:
            customer_details = {
                "first_name": "Discord User",
                "email": "user@discord.bot",
                "phone": "08123456789"
            }

        payload = {
            "payment_type": "qris",
            "transaction_details": {
                "order_id": order_id,
                "gross_amount": amount
            },
            "customer_details": customer_details,
            "qris": {
                "acquirer": "gopay"  # bisa juga "airpay shopee"
            }
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)

            if response.status_code in [200, 201]:
                return response.json()
            else:
                print(f"❌ Midtrans Error: {response.status_code}")
                print(f"Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Exception saat create transaction: {e}")
            return None

    def check_transaction_status(self, order_id: str):
        """
        Cek status transaksi

        Args:
            order_id: Order ID yang ingin dicek

        Returns:
            dict: Status transaksi atau None jika error

        Example Response:
        {
            "status_code": "200",
            "status_message": "Success, transaction found",
            "transaction_id": "...",
            "order_id": "TOPUP-123-...",
            "gross_amount": "10000.00",
            "payment_type": "qris",
            "transaction_time": "2024-12-03 12:00:00",
            "transaction_status": "settlement",  # pending/settlement/cancel/deny/expire
            "fraud_status": "accept",
            "currency": "IDR"
        }
        """
        url = f"{self.base_url}/{order_id}/status"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Status check error: {response.status_code}")
                print(f"Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Exception saat check status: {e}")
            return None

    def cancel_transaction(self, order_id: str):
        """
        Cancel transaksi yang masih pending

        Args:
            order_id: Order ID yang ingin dicancel

        Returns:
            dict: Response atau None jika error
        """
        url = f"{self.base_url}/{order_id}/cancel"

        try:
            response = requests.post(url, headers=self.headers, timeout=30)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Cancel error: {response.status_code}")
                print(f"Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Exception saat cancel: {e}")
            return None

    def expire_transaction(self, order_id: str):
        """
        Expire transaksi yang masih pending

        Args:
            order_id: Order ID yang ingin di-expire

        Returns:
            dict: Response atau None jika error
        """
        url = f"{self.base_url}/{order_id}/expire"

        try:
            response = requests.post(url, headers=self.headers, timeout=30)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Expire error: {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Exception saat expire: {e}")
            return None

# ==========================================
# WEBHOOK HANDLER
# ==========================================

def verify_signature(order_id: str, status_code: str, gross_amount: str, server_key: str, signature_key: str) -> bool:
    """
    Verifikasi signature dari Midtrans webhook untuk keamanan

    Args:
        order_id: Order ID dari notification
        status_code: Status code dari notification (200, 201, dll)
        gross_amount: Gross amount dari notification
        server_key: Server key Midtrans Anda
        signature_key: Signature key dari notification payload

    Returns:
        bool: True jika signature valid, False jika invalid

    Formula: SHA512(order_id+status_code+gross_amount+ServerKey)
    """
    # Buat hash string
    hash_string = f"{order_id}{status_code}{gross_amount}{server_key}"

    # Generate SHA512 hash
    hash_result = hashlib.sha512(hash_string.encode()).hexdigest()

    # Compare
    return hash_result == signature_key

def parse_webhook_notification(notification_json: dict, server_key: str):
    """
    Parse notifikasi webhook dari Midtrans

    Args:
        notification_json: Dict dari request body webhook
        server_key: Server key untuk verifikasi signature

    Returns:
        dict: Data yang sudah diparse dengan status yang jelas

    Example notification_json:
    {
        "transaction_time": "2024-12-03 12:00:00",
        "transaction_status": "settlement",
        "transaction_id": "...",
        "status_message": "midtrans payment notification",
        "status_code": "200",
        "signature_key": "...",
        "payment_type": "qris",
        "order_id": "TOPUP-123-...",
        "merchant_id": "...",
        "gross_amount": "10000.00",
        "fraud_status": "accept",
        "currency": "IDR"
    }
    """
    # Extract fields
    order_id = notification_json.get('order_id')
    transaction_status = notification_json.get('transaction_status')
    fraud_status = notification_json.get('fraud_status')
    status_code = notification_json.get('status_code')
    gross_amount = notification_json.get('gross_amount')
    signature_key = notification_json.get('signature_key')

    # Verifikasi signature
    is_valid = verify_signature(
        order_id=order_id,
        status_code=status_code,
        gross_amount=gross_amount,
        server_key=server_key,
        signature_key=signature_key
    )

    if not is_valid:
        return {
            'valid': False,
            'error': 'Invalid signature - possible security breach!'
        }

    # Tentukan status final berdasarkan transaction_status
    # Reference: https://docs.midtrans.com/docs/http-notification-webhooks
    final_status = 'pending'

    if transaction_status == 'capture':
        # Untuk credit card
        if fraud_status == 'accept':
            final_status = 'success'
        else:
            final_status = 'failed'

    elif transaction_status == 'settlement':
        # Pembayaran berhasil (non-credit card)
        final_status = 'success'

    elif transaction_status in ['cancel', 'deny', 'expire']:
        # Pembayaran gagal/dibatalkan
        final_status = 'failed'

    elif transaction_status == 'pending':
        # Masih menunggu pembayaran
        final_status = 'pending'

    return {
        'valid': True,
        'order_id': order_id,
        'status': final_status,
        'transaction_status': transaction_status,
        'fraud_status': fraud_status,
        'gross_amount': gross_amount,
        'payment_type': notification_json.get('payment_type'),
        'transaction_id': notification_json.get('transaction_id'),
        'raw_data': notification_json
    }

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def generate_order_id(user_id: int) -> str:
    """
    Generate unique order ID untuk Midtrans
    Format: TOPUP-{user_id}-{timestamp}

    Args:
        user_id: Discord user ID

    Returns:
        str: Unique order ID
    """
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"TOPUP-{user_id}-{timestamp}"

def format_rupiah(amount: int) -> str:
    """
    Format integer ke format Rupiah

    Args:
        amount: Jumlah dalam integer

    Returns:
        str: Format "Rp 10.000"
    """
    return f"Rp {amount:,}".replace(',', '.')

def parse_rupiah(text: str) -> int:
    """
    Parse text Rupiah ke integer

    Args:
        text: Text seperti "Rp 10.000" atau "10000"

    Returns:
        int: Jumlah dalam integer
    """
    # Remove Rp, spaces, dots
    clean = text.replace('Rp', '').replace(' ', '').replace('.', '').replace(',', '')
    return int(clean)

# ==========================================
# TRANSACTION STATUS MAPPING
# ==========================================

STATUS_MAPPING = {
    'pending': {
        'emoji': '⏳',
        'description': 'Menunggu pembayaran',
        'color': 0xf39c12  # Orange
    },
    'success': {
        'emoji': '✅',
        'description': 'Pembayaran berhasil',
        'color': 0x00ff00  # Green
    },
    'failed': {
        'emoji': '❌',
        'description': 'Pembayaran gagal/dibatalkan',
        'color': 0xe74c3c  # Red
    },
    'expired': {
        'emoji': '⌛',
        'description': 'Transaksi kadaluarsa',
        'color': 0x95a5a6  # Gray
    }
}

def get_status_info(status: str) -> dict:
    """
    Ambil info status (emoji, description, color) untuk embed Discord

    Args:
        status: Status transaksi (pending/success/failed/expired)

    Returns:
        dict: Status info
    """
    return STATUS_MAPPING.get(status, {
        'emoji': '❓',
        'description': 'Status tidak diketahui',
        'color': 0x95a5a6
    })
