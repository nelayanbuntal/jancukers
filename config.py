import os
from dotenv import load_dotenv

# Load environment variables dari file .env
load_dotenv()

# ==========================================
# DISCORD CONFIG
# ==========================================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', 'YOUR_DISCORD_BOT_TOKEN')
ADMIN_ROLE_NAME = os.getenv('ADMIN_ROLE_NAME', 'Admin')
PUBLIC_CHANNEL_ID = int(os.getenv('PUBLIC_CHANNEL_ID', '1443997759479877683'))

# ==========================================
# MIDTRANS CONFIG
# ==========================================
MIDTRANS_SERVER_KEY = os.getenv('MIDTRANS_SERVER_KEY', 'YOUR_MIDTRANS_SERVER_KEY')
MIDTRANS_IS_PRODUCTION = os.getenv('MIDTRANS_IS_PRODUCTION', 'False').lower() == 'true'

# Webhook config (untuk production, gunakan ngrok atau domain publik)
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'http://localhost:8000/webhook/midtrans')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8000'))

# ==========================================
# REDEEM CONFIG
# ==========================================
MAX_LOGIN_WORKERS = int(os.getenv('MAX_LOGIN_WORKERS', '3'))
REDEEM_COST_PER_CODE = int(os.getenv('REDEEM_COST_PER_CODE', '1000'))  # Biaya per kode dalam Rupiah
MIN_TOPUP_AMOUNT = int(os.getenv('MIN_TOPUP_AMOUNT', '1000'))
MAX_CODES_PER_UPLOAD = int(os.getenv('MAX_CODES_PER_UPLOAD', '100'))  # Maksimal kode per upload

# ==========================================
# DATABASE CONFIG
# ==========================================
DB_FILE = os.getenv('DB_FILE', 'bot_database.db')

# ==========================================
# CLOUDEMULATOR CONFIG (SECRET KEY)
# ==========================================
CLOUDEMULATOR_SECRET_KEY = "2018red8688RendfingerSxxd"

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def validate_config():
    """
    Validasi konfigurasi penting
    Dipanggil saat bot startup
    """
    errors = []

    # Check Discord Token
    if DISCORD_TOKEN == 'YOUR_DISCORD_BOT_TOKEN':
        errors.append("❌ DISCORD_TOKEN belum di-set di .env")

    # Check Midtrans Key
    if MIDTRANS_SERVER_KEY == 'YOUR_MIDTRANS_SERVER_KEY':
        errors.append("❌ MIDTRANS_SERVER_KEY belum di-set di .env")

    # Check Public Channel ID
    if PUBLIC_CHANNEL_ID == 0:
        errors.append("⚠️ PUBLIC_CHANNEL_ID tidak valid")

    # Check Workers
    if MAX_LOGIN_WORKERS < 1 or MAX_LOGIN_WORKERS > 10:
        errors.append("⚠️ MAX_LOGIN_WORKERS harus antara 1-10")

    # Check Costs
    if REDEEM_COST_PER_CODE < 0:
        errors.append("⚠️ REDEEM_COST_PER_CODE harus positif")

    if MIN_TOPUP_AMOUNT < 1000:
        errors.append("⚠️ MIN_TOPUP_AMOUNT minimal 1000")

    if errors:
        print("\n" + "="*50)
        print("⚠️ PERINGATAN KONFIGURASI:")
        print("="*50)
        for error in errors:
            print(error)
        print("="*50 + "\n")

        # Critical errors yang harus diperbaiki
        if any("❌" in e for e in errors):
            print("🛑 Bot tidak bisa jalan! Perbaiki .env terlebih dahulu.\n")
            return False

    return True

def print_config():
    """Print konfigurasi saat startup (untuk debugging)"""
    print("\n" + "="*50)
    print("⚙️ KONFIGURASI BOT")
    print("="*50)
    print(f"Discord Token: {'✅ Set' if DISCORD_TOKEN != 'YOUR_DISCORD_BOT_TOKEN' else '❌ Not Set'}")
    print(f"Admin Role: {ADMIN_ROLE_NAME}")
    print(f"Public Channel ID: {PUBLIC_CHANNEL_ID}")
    print(f"\nMidtrans Server Key: {'✅ Set' if MIDTRANS_SERVER_KEY != 'YOUR_MIDTRANS_SERVER_KEY' else '❌ Not Set'}")
    print(f"Midtrans Environment: {'🔴 PRODUCTION' if MIDTRANS_IS_PRODUCTION else '🟡 SANDBOX'}")
    print(f"Webhook Port: {WEBHOOK_PORT}")
    print(f"\nMax Login Workers: {MAX_LOGIN_WORKERS}")
    print(f"Redeem Cost Per Code: Rp {REDEEM_COST_PER_CODE:,}")
    print(f"Min Topup Amount: Rp {MIN_TOPUP_AMOUNT:,}")
    print(f"\nDatabase: {DB_FILE}")
    print("="*50 + "\n")
