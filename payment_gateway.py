import requests
import base64
import json
import hashlib
import time
from datetime import datetime, timedelta
from functools import wraps

# ==========================================
# RETRY DECORATOR
# ==========================================

def retry_api_call(max_attempts=3, delay=2, backoff=2):
    """Decorator untuk retry API calls dengan exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.Timeout:
                    if attempt < max_attempts - 1:
                        wait_time = delay * (backoff ** attempt)
                        print(f"⏳ Timeout, mencoba ulang dalam {wait_time}s... (percobaan {attempt + 1}/{max_attempts})")
                        time.sleep(wait_time)
                        continue
                    raise
                except requests.exceptions.ConnectionError:
                    if attempt < max_attempts - 1:
                        wait_time = delay * (backoff ** attempt)
                        print(f"🔌 Koneksi gagal, mencoba ulang dalam {wait_time}s... (percobaan {attempt + 1}/{max_attempts})")
                        time.sleep(wait_time)
                        continue
                    raise
                except requests.exceptions.RequestException as e:
                    if attempt < max_attempts - 1:
                        print(f"❌ Request error: {e}, mencoba ulang...")
                        time.sleep(delay * (backoff ** attempt))
                        continue
                    raise
            return None
        return wrapper
    return decorator

# ==========================================
# MIDTRANS PAYMENT CLASS
# ==========================================

class MidtransPayment:
    """
    Midtrans Payment Gateway Integration dengan error handling & retry logic
    Dokumentasi: https://docs.midtrans.com/reference/createtransaction
    """

    def __init__(self, server_key: str, is_production: bool = False):
        """
        Args:
            server_key: Server Key dari Midtrans Dashboard
            is_production: True untuk production, False untuk sandbox
        """
        if not server_key or server_key == 'YOUR_MIDTRANS_SERVER_KEY':
            raise ValueError("Server key Midtrans tidak valid")
        
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

    @retry_api_call(max_attempts=3, delay=2)
    def create_qris_transaction(self, order_id: str, amount: int, customer_details: dict = None):
        """
        Buat transaksi QRIS dengan retry logic

        Args:
            order_id: Unique order ID (max 50 chars, alphanumeric + - _ ~)
            amount: Jumlah dalam Rupiah (integer)
            customer_details: Dict dengan key: first_name, email, phone (opsional)

        Returns:
            dict: Response dari Midtrans atau None jika error
        """
        url = f"{self.base_url}/charge"

        # Validasi input
        if not order_id or len(order_id) > 50:
            raise ValueError("Order ID tidak valid (max 50 karakter)")
        
        if amount < 1000:
            raise ValueError("Amount minimal Rp 1.000")

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
                "acquirer": "gopay"
            }
        }

        try:
            response = requests.post(
                url, 
                headers=self.headers, 
                json=payload, 
                timeout=30
            )

            if response.status_code in [200, 201]:
                return response.json()
            elif response.status_code == 400:
                error_msg = response.json().get('error_messages', ['Unknown error'])[0]
                print(f"❌ Midtrans validation error: {error_msg}")
                return None
            elif response.status_code == 401:
                print(f"❌ Midtrans authentication error: Periksa server key")
                return None
            else:
                print(f"❌ Midtrans error: {response.status_code}")
                print(f"Response: {response.text}")
                return None

        except requests.exceptions.Timeout:
            print(f"⏳ Request timeout ke Midtrans")
            raise
        except Exception as e:
            print(f"❌ Exception saat create transaction: {e}")
            return None

    @retry_api_call(max_attempts=3, delay=1)
    def check_transaction_status(self, order_id: str):
        """
        Cek status transaksi dengan retry logic

        Args:
            order_id: Order ID yang ingin dicek

        Returns:
            dict: Status transaksi atau None jika error
        """
        url = f"{self.base_url}/{order_id}/status"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                print(f"❌ Transaksi tidak ditemukan: {order_id}")
                return None
            else:
                print(f"❌ Status check error: {response.status_code}")
                print(f"Response: {response.text}")
                return None

        except requests.exceptions.Timeout:
            print(f"⏳ Timeout saat check status")
            raise
        except Exception as e:
            print(f"❌ Exception saat check status: {e}")
            return None

    @retry_api_call(max_attempts=2, delay=1)
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

    @retry_api_call(max_attempts=2, delay=1)
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
    """
    # Buat hash string
    hash_string = f"{order_id}{status_code}{gross_amount}{server_key}"

    # Generate SHA512 hash
    hash_result = hashlib.sha512(hash_string.encode()).hexdigest()

    # Compare
    return hash_result == signature_key

def parse_webhook_notification(notification_json: dict, server_key: str):
    """
    Parse notifikasi webhook dari Midtrans dengan validasi ketat

    Args:
        notification_json: Dict dari request body webhook
        server_key: Server key untuk verifikasi signature

    Returns:
        dict: Data yang sudah diparse dengan status yang jelas
    """
    # Validasi required fields
    required_fields = ['order_id', 'transaction_status', 'status_code', 'gross_amount', 'signature_key']
    missing_fields = [field for field in required_fields if field not in notification_json]
    
    if missing_fields:
        return {
            'valid': False,
            'error': f'Missing required fields: {", ".join(missing_fields)}'
        }
    
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
            'error': 'Signature tidak valid - kemungkinan pelanggaran keamanan!'
        }

    # Tentukan status final berdasarkan transaction_status
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
    """
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"TOPUP-{user_id}-{timestamp}"

def format_rupiah(amount: int) -> str:
    """Format integer ke format Rupiah yang mudah dibaca"""
    return f"Rp {amount:,}".replace(',', '.')

def parse_rupiah(text: str) -> int:
    """Parse text Rupiah ke integer"""
    # Remove Rp, spaces, dots, commas
    clean = text.replace('Rp', '').replace(' ', '').replace('.', '').replace(',', '')
    try:
        return int(clean)
    except ValueError:
        return 0

# ==========================================
# STATUS INFO MAPPING
# ==========================================

STATUS_MAPPING = {
    'pending': {
        'emoji': '⏳',
        'title': 'Menunggu Pembayaran',
        'description': 'Silakan scan QR code untuk menyelesaikan pembayaran',
        'color': 0xf39c12  # Orange
    },
    'success': {
        'emoji': '✅',
        'title': 'Pembayaran Berhasil',
        'description': 'Saldo Anda telah ditambahkan',
        'color': 0x2ecc71  # Green
    },
    'failed': {
        'emoji': '❌',
        'title': 'Pembayaran Gagal',
        'description': 'Transaksi dibatalkan atau ditolak',
        'color': 0xe74c3c  # Red
    },
    'expired': {
        'emoji': '⌛',
        'title': 'Transaksi Kadaluarsa',
        'description': 'Waktu pembayaran telah habis',
        'color': 0x95a5a6  # Gray
    }
}

def get_status_info(status: str) -> dict:
    """
    Ambil info status untuk tampilan di Discord embed
    """
    return STATUS_MAPPING.get(status, {
        'emoji': '❓',
        'title': 'Status Tidak Diketahui',
        'description': 'Status transaksi tidak dapat ditentukan',
        'color': 0x95a5a6
    })