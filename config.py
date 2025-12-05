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
# SUPABASE CONFIG (NEW)
# ==========================================
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')  # Use service_role key

# Database mode selection
USE_SUPABASE = os.getenv('USE_SUPABASE', 'True').lower() == 'true'

# Legacy SQLite config (for backward compatibility)
DB_FILE = os.getenv('DB_FILE', 'bot_database.db')
DB_MAX_RETRY_ATTEMPTS = int(os.getenv('DB_MAX_RETRY_ATTEMPTS', '5'))
DB_RETRY_DELAY = float(os.getenv('DB_RETRY_DELAY', '0.1'))
DB_TIMEOUT = int(os.getenv('DB_TIMEOUT', '30'))

# ==========================================
# MIDTRANS CONFIG
# ==========================================
MIDTRANS_SERVER_KEY = os.getenv('MIDTRANS_SERVER_KEY', 'YOUR_MIDTRANS_SERVER_KEY')
MIDTRANS_IS_PRODUCTION = os.getenv('MIDTRANS_IS_PRODUCTION', 'False').lower() == 'true'

# Webhook config
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'http://localhost:8000/webhook/midtrans')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8000'))

# ==========================================
# REDEEM CONFIG
# ==========================================
MAX_LOGIN_WORKERS = int(os.getenv('MAX_LOGIN_WORKERS', '3'))
REDEEM_COST_PER_CODE = int(os.getenv('REDEEM_COST_PER_CODE', '1000'))
MIN_TOPUP_AMOUNT = int(os.getenv('MIN_TOPUP_AMOUNT', '1000'))
MAX_CODES_PER_UPLOAD = int(os.getenv('MAX_CODES_PER_UPLOAD', '100'))

# ==========================================
# REDEEM CORE CONFIG
# ==========================================

# Retry configuration
MAX_LOGIN_RETRY = int(os.getenv('MAX_LOGIN_RETRY', '3'))
MAX_REDEEM_RETRY_PER_REGION = int(os.getenv('MAX_REDEEM_RETRY_PER_REGION', '2'))
MAX_SELENIUM_RETRY = int(os.getenv('MAX_SELENIUM_RETRY', '3'))
MAX_REGION_CYCLES = int(os.getenv('MAX_REGION_CYCLES', '10'))

# Timeout configuration (in seconds)
LOGIN_PAGE_TIMEOUT = int(os.getenv('LOGIN_PAGE_TIMEOUT', '30'))
ELEMENT_WAIT_TIMEOUT = int(os.getenv('ELEMENT_WAIT_TIMEOUT', '15'))
API_REQUEST_TIMEOUT = int(os.getenv('API_REQUEST_TIMEOUT', '20'))
MAX_CODE_PROCESSING_TIME = int(os.getenv('MAX_CODE_PROCESSING_TIME', '300'))
MAX_SESSION_TIME = int(os.getenv('MAX_SESSION_TIME', '1800'))

# Progress update interval (in seconds)
PROGRESS_UPDATE_INTERVAL = int(os.getenv('PROGRESS_UPDATE_INTERVAL', '3'))

# Speed Mode
SPEED_MODE = os.getenv('SPEED_MODE', 'True').lower() == 'true'

# Security settings
ENABLE_SENSITIVE_DATA_MASKING = os.getenv('ENABLE_SENSITIVE_DATA_MASKING', 'True').lower() == 'true'
MASK_SHOW_CHARACTERS = int(os.getenv('MASK_SHOW_CHARACTERS', '4'))

# Feature flags
ENABLE_CANCELLATION = os.getenv('ENABLE_CANCELLATION', 'True').lower() == 'true'
ENABLE_AUTO_RETRY = os.getenv('ENABLE_AUTO_RETRY', 'True').lower() == 'true'
ENABLE_PROGRESS_TRACKING = os.getenv('ENABLE_PROGRESS_TRACKING', 'True').lower() == 'true'

# Region configuration
SUPPORTED_REGIONS = {
    'hk2': {'idc_code': 'HKXC_IDC_01', 'name': 'Hong Kong 2'},
    'hk': {'idc_code': 'HK_IDC_01', 'name': 'Hong Kong'},
    'th': {'idc_code': 'TH_IDC_01', 'name': 'Thailand'},
    'sg': {'idc_code': 'SG_IDC_03', 'name': 'Singapore'},
    'tw': {'idc_code': 'TW_IDC_04', 'name': 'Taiwan'},
    'us': {'idc_code': 'US_IDC_01', 'name': 'United States'}
}

# Android version configuration
SUPPORTED_ANDROID_VERSIONS = {
    '10.0': 'Android 10',
    '15.0': 'Android 15',
    '8.1': 'Android 8.1',
    '12.0': 'Android 12'
}

# Android number mapping
ANDROID_NUMBER_MAP = {
    '1': '8.1',
    '2': '10.0',
    '3': '12.0',
    '4': '15.0'
}

# Region select options with emojis
REGION_SELECT_OPTIONS = [
    {'value': 'hk2', 'label': 'Hong Kong 2', 'emoji': '🇭🇰', 'description': 'HKXC_IDC_01'},
    {'value': 'hk', 'label': 'Hong Kong', 'emoji': '🇭🇰', 'description': 'HK_IDC_01'},
    {'value': 'th', 'label': 'Thailand', 'emoji': '🇹🇭', 'description': 'TH_IDC_01'},
    {'value': 'sg', 'label': 'Singapore', 'emoji': '🇸🇬', 'description': 'SG_IDC_03'},
    {'value': 'tw', 'label': 'Taiwan', 'emoji': '🇹🇼', 'description': 'TW_IDC_04'},
    {'value': 'us', 'label': 'United States', 'emoji': '🇺🇸', 'description': 'US_IDC_01'}
]

# Default region and android
DEFAULT_REGION = os.getenv('DEFAULT_REGION', 'hk sg tw')
DEFAULT_ANDROID_VERSION = os.getenv('DEFAULT_ANDROID_VERSION', '10.0')

# ==========================================
# TIMEZONE UTILITIES (WIB - Indonesia)
# ==========================================
from datetime import timezone, timedelta

WIB = timezone(timedelta(hours=7))

def get_wib_time():
    """Get current datetime in WIB timezone"""
    from datetime import datetime
    return datetime.now(WIB)

def format_wib_datetime(dt=None, include_seconds=False):
    """Format datetime as WIB string"""
    from datetime import datetime
    if dt is None:
        dt = get_wib_time()
    
    if include_seconds:
        return dt.strftime('%d/%m/%Y %H:%M:%S WIB')
    else:
        return dt.strftime('%d/%m/%Y %H:%M WIB')

def format_wib_time_only(dt=None):
    """Format time only (HH:MM WIB)"""
    from datetime import datetime
    if dt is None:
        dt = get_wib_time()
    return dt.strftime('%H:%M WIB')

# ==========================================
# AUTO-CLOSE CHANNEL CONFIGURATION
# ==========================================
AUTO_CLOSE_AFTER_COMPLETION = int(os.getenv('AUTO_CLOSE_AFTER_COMPLETION', '7200'))
AUTO_CLOSE_AFTER_INACTIVITY = int(os.getenv('AUTO_CLOSE_AFTER_INACTIVITY', '7200'))
AUTO_CLOSE_WARNING_BEFORE = int(os.getenv('AUTO_CLOSE_WARNING_BEFORE', '600'))
AUTO_CLOSE_CHECK_INTERVAL = int(os.getenv('AUTO_CLOSE_CHECK_INTERVAL', '300'))

# ==========================================
# LOGGING CONFIG
# ==========================================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_TO_FILE = os.getenv('LOG_TO_FILE', 'True').lower() == 'true'
LOG_FILE = os.getenv('LOG_FILE', 'bot.log')
LOG_MAX_SIZE = int(os.getenv('LOG_MAX_SIZE', '10485760'))
LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))
LOG_FORMAT = os.getenv('LOG_FORMAT', '%(asctime)s | %(levelname)-8s | %(message)s')
LOG_DATE_FORMAT = os.getenv('LOG_DATE_FORMAT', '%Y-%m-%d %H:%M:%S')

# ==========================================
# CLOUDEMULATOR CONFIG
# ==========================================
CLOUDEMULATOR_SECRET_KEY = "2018red8688RendfingerSxxd"

# ==========================================
# VALIDATION & HELPER FUNCTIONS
# ==========================================

def validate_config():
    """Validasi konfigurasi penting"""
    errors = []
    warnings = []

    # Check Discord Token
    if DISCORD_TOKEN == 'YOUR_DISCORD_BOT_TOKEN':
        errors.append("❌ DISCORD_TOKEN belum di-set di .env")

    # Check Midtrans Key
    if MIDTRANS_SERVER_KEY == 'YOUR_MIDTRANS_SERVER_KEY':
        errors.append("❌ MIDTRANS_SERVER_KEY belum di-set di .env")

    # Check Supabase (if enabled)
    if USE_SUPABASE:
        if not SUPABASE_URL or SUPABASE_URL == '':
            errors.append("❌ SUPABASE_URL belum di-set di .env")
        if not SUPABASE_KEY or SUPABASE_KEY == '':
            errors.append("❌ SUPABASE_KEY belum di-set di .env")
    else:
        warnings.append("⚠️ Menggunakan SQLite (USE_SUPABASE=False)")

    # Check Public Channel ID
    if PUBLIC_CHANNEL_ID == 0:
        errors.append("⚠️ PUBLIC_CHANNEL_ID tidak valid")

    # Check Workers
    if MAX_LOGIN_WORKERS < 1 or MAX_LOGIN_WORKERS > 10:
        warnings.append("⚠️ MAX_LOGIN_WORKERS harus antara 1-10")

    # Check Costs
    if REDEEM_COST_PER_CODE < 0:
        warnings.append("⚠️ REDEEM_COST_PER_CODE harus positif")

    if MIN_TOPUP_AMOUNT < 1000:
        warnings.append("⚠️ MIN_TOPUP_AMOUNT minimal 1000")

    # Check Retry Configuration
    if MAX_LOGIN_RETRY < 1 or MAX_LOGIN_RETRY > 10:
        warnings.append("⚠️ MAX_LOGIN_RETRY sebaiknya antara 1-10")
    
    if MAX_REDEEM_RETRY_PER_REGION < 1 or MAX_REDEEM_RETRY_PER_REGION > 5:
        warnings.append("⚠️ MAX_REDEEM_RETRY_PER_REGION sebaiknya antara 1-5")

    # Check Timeouts
    if LOGIN_PAGE_TIMEOUT < 10 or LOGIN_PAGE_TIMEOUT > 120:
        warnings.append("⚠️ LOGIN_PAGE_TIMEOUT sebaiknya antara 10-120 detik")
    
    if MAX_SESSION_TIME < 600 or MAX_SESSION_TIME > 7200:
        warnings.append("⚠️ MAX_SESSION_TIME sebaiknya antara 10-120 menit")

    # Check Database Config
    if not USE_SUPABASE and DB_TIMEOUT < 10:
        warnings.append("⚠️ DB_TIMEOUT sebaiknya minimal 10 detik")

    # Check Logging Config
    if LOG_LEVEL not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
        warnings.append(f"⚠️ LOG_LEVEL tidak valid: {LOG_LEVEL}, default ke INFO")

    # Print errors and warnings
    if errors or warnings:
        print("\n" + "="*50)
        print("⚠️ KONFIGURASI:")
        print("="*50)
        
        for error in errors:
            print(error)
        
        for warning in warnings:
            print(warning)
        
        print("="*50 + "\n")

        if any("❌" in e for e in errors):
            print("🛑 Bot tidak bisa jalan! Perbaiki .env terlebih dahulu.\n")
            return False

    return True

def print_config():
    """Print konfigurasi saat startup"""
    print("\n" + "="*50)
    print("⚙️ KONFIGURASI BOT v3.0 (SUPABASE)")
    print("="*50)
    
    # Discord Config
    print(f"\n📱 DISCORD:")
    print(f"  Token: {'✅ Set' if DISCORD_TOKEN != 'YOUR_DISCORD_BOT_TOKEN' else '❌ Not Set'}")
    print(f"  Admin Role: {ADMIN_ROLE_NAME}")
    print(f"  Public Channel ID: {PUBLIC_CHANNEL_ID}")
    
    # Database Config (NEW)
    print(f"\n💾 DATABASE:")
    print(f"  Mode: {'🟢 Supabase' if USE_SUPABASE else '🔵 SQLite'}")
    if USE_SUPABASE:
        print(f"  URL: {'✅ Set' if SUPABASE_URL else '❌ Not Set'}")
        print(f"  Key: {'✅ Set' if SUPABASE_KEY else '❌ Not Set'}")
    else:
        print(f"  File: {DB_FILE}")
        print(f"  Timeout: {DB_TIMEOUT}s")
    
    # Midtrans Config
    print(f"\n💳 MIDTRANS:")
    print(f"  Server Key: {'✅ Set' if MIDTRANS_SERVER_KEY != 'YOUR_MIDTRANS_SERVER_KEY' else '❌ Not Set'}")
    print(f"  Environment: {'🔴 PRODUCTION' if MIDTRANS_IS_PRODUCTION else '🟡 SANDBOX'}")
    print(f"  Webhook Port: {WEBHOOK_PORT}")
    
    # Redeem Config
    print(f"\n🎮 REDEEM:")
    print(f"  Max Workers: {MAX_LOGIN_WORKERS}")
    print(f"  Cost per Code: Rp {REDEEM_COST_PER_CODE:,}")
    print(f"  Min Topup: Rp {MIN_TOPUP_AMOUNT:,}")
    print(f"  Max Codes Upload: {MAX_CODES_PER_UPLOAD}")
    print(f"  Speed Mode: {'✅ Enabled' if SPEED_MODE else '❌ Disabled'}")
    
    # Retry Config
    print(f"\n🔄 RETRY:")
    print(f"  Login: {MAX_LOGIN_RETRY} attempts")
    print(f"  API per Region: {MAX_REDEEM_RETRY_PER_REGION} attempts")
    print(f"  Selenium: {MAX_SELENIUM_RETRY} attempts")
    
    # Timeout Config
    print(f"\n⏱️ TIMEOUTS:")
    print(f"  Login Page: {LOGIN_PAGE_TIMEOUT}s")
    print(f"  Element Wait: {ELEMENT_WAIT_TIMEOUT}s")
    print(f"  API Request: {API_REQUEST_TIMEOUT}s")
    
    # Regions
    print(f"\n🌍 REGIONS ({len(SUPPORTED_REGIONS)}):")
    for key, info in SUPPORTED_REGIONS.items():
        print(f"  {key.upper()}: {info['name']}")
    
    # Android Versions
    print(f"\n📱 ANDROID ({len(SUPPORTED_ANDROID_VERSIONS)}):")
    for version, name in SUPPORTED_ANDROID_VERSIONS.items():
        print(f"  {version}: {name}")
    
    # Security
    print(f"\n🔒 SECURITY:")
    print(f"  Data Masking: {'✅ Enabled' if ENABLE_SENSITIVE_DATA_MASKING else '❌ Disabled'}")
    print(f"  Mask Characters: {MASK_SHOW_CHARACTERS}")
    
    # Logging
    print(f"\n📝 LOGGING:")
    print(f"  Level: {LOG_LEVEL}")
    print(f"  To File: {'✅ Enabled' if LOG_TO_FILE else '❌ Disabled'}")
    if LOG_TO_FILE:
        print(f"  File: logs/{LOG_FILE}")
        print(f"  Max Size: {LOG_MAX_SIZE / 1024 / 1024:.1f}MB")
        print(f"  Backups: {LOG_BACKUP_COUNT}")
    
    print("="*50 + "\n")

def get_region_info(region_code):
    """Get region information by code"""
    return SUPPORTED_REGIONS.get(region_code.lower())

def get_android_name(version):
    """Get android version name"""
    return SUPPORTED_ANDROID_VERSIONS.get(version)

def get_android_version_from_number(number):
    """Convert number input to android version"""
    return ANDROID_NUMBER_MAP.get(str(number))

def is_valid_android_number(number):
    """Check if android number is valid"""
    return str(number) in ANDROID_NUMBER_MAP

def is_valid_region(region_code):
    """Check if region code is valid"""
    return region_code.lower() in SUPPORTED_REGIONS

def is_valid_android(version):
    """Check if android version is valid"""
    return version in SUPPORTED_ANDROID_VERSIONS

def get_all_region_codes():
    """Get list of all valid region codes"""
    return list(SUPPORTED_REGIONS.keys())

def get_all_android_versions():
    """Get list of all valid android versions"""
    return list(SUPPORTED_ANDROID_VERSIONS.keys())

def get_android_display_options():
    """Get formatted android options for display"""
    return " | ".join([f"{num}={ver}" for num, ver in ANDROID_NUMBER_MAP.items()])