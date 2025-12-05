"""
Enhanced Logging System
========================
Production-grade logging with rotation and structured output
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
import traceback
import config

# ==========================================
# LOG LEVELS
# ==========================================
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# ==========================================
# CUSTOM FORMATTER
# ==========================================
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        if hasattr(record, 'user_id'):
            record.msg = f"[User:{record.user_id}] {record.msg}"
        
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        
        return super().format(record)

# ==========================================
# LOGGER SETUP
# ==========================================
class Logger:
    """Enhanced logger with rotation and structured output"""
    
    def __init__(self, name='BotLogger'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(LOG_LEVELS.get(config.LOG_LEVEL, logging.INFO))
        
        # Prevent duplicate handlers
        if self.logger.handlers:
            return
        
        # Console handler with colors
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_formatter = ColoredFormatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler with rotation (if enabled)
        if config.LOG_TO_FILE:
            try:
                os.makedirs('logs', exist_ok=True)
                file_handler = RotatingFileHandler(
                    f'logs/{config.LOG_FILE}',
                    maxBytes=config.LOG_MAX_SIZE,
                    backupCount=5,
                    encoding='utf-8'
                )
                file_handler.setLevel(logging.DEBUG)
                file_formatter = logging.Formatter(
                    '%(asctime)s | %(levelname)-8s | %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                file_handler.setFormatter(file_formatter)
                self.logger.addHandler(file_handler)
            except Exception as e:
                print(f"⚠️ Failed to setup file logging: {e}")
    
    def debug(self, msg, user_id=None):
        """Log debug message"""
        extra = {'user_id': user_id} if user_id else {}
        self.logger.debug(msg, extra=extra)
    
    def info(self, msg, user_id=None):
        """Log info message"""
        extra = {'user_id': user_id} if user_id else {}
        self.logger.info(msg, extra=extra)
    
    def warning(self, msg, user_id=None):
        """Log warning message"""
        extra = {'user_id': user_id} if user_id else {}
        self.logger.warning(msg, extra=extra)
    
    def error(self, msg, user_id=None, exc_info=False):
        """Log error message"""
        extra = {'user_id': user_id} if user_id else {}
        self.logger.error(msg, extra=extra, exc_info=exc_info)
    
    def critical(self, msg, user_id=None, exc_info=False):
        """Log critical message"""
        extra = {'user_id': user_id} if user_id else {}
        self.logger.critical(msg, extra=extra, exc_info=exc_info)
    
    def exception(self, msg, user_id=None):
        """Log exception with traceback"""
        extra = {'user_id': user_id} if user_id else {}
        self.logger.exception(msg, extra=extra)
    
    def log_api_call(self, endpoint, status_code, response_time, user_id=None):
        """Log API call details"""
        msg = f"API Call: {endpoint} | Status: {status_code} | Time: {response_time:.2f}s"
        if status_code >= 500:
            self.error(msg, user_id=user_id)
        elif status_code >= 400:
            self.warning(msg, user_id=user_id)
        else:
            self.info(msg, user_id=user_id)
    
    def log_redeem_attempt(self, code, region, attempt, result, user_id=None):
        """Log redeem attempt"""
        masked_code = code[:4] + "****" + code[-4:] if len(code) > 8 else "****"
        msg = f"Redeem: {masked_code} | Region: {region} | Attempt: {attempt} | Result: {result}"
        
        if result == "success":
            self.info(msg, user_id=user_id)
        elif result == "invalid":
            self.warning(msg, user_id=user_id)
        else:
            self.debug(msg, user_id=user_id)
    
    def log_login_attempt(self, email, success, user_id=None):
        """Log login attempt"""
        masked_email = email.split('@')[0][:3] + "****@" + email.split('@')[1]
        msg = f"Login: {masked_email} | Success: {success}"
        
        if success:
            self.info(msg, user_id=user_id)
        else:
            self.error(msg, user_id=user_id)
    
    def log_payment(self, amount, order_id, status, user_id=None):
        """Log payment transaction"""
        msg = f"Payment: {order_id} | Amount: Rp {amount:,} | Status: {status}"
        
        if status == "success":
            self.info(msg, user_id=user_id)
        elif status == "failed":
            self.error(msg, user_id=user_id)
        else:
            self.debug(msg, user_id=user_id)

# ==========================================
# ERROR CATEGORIES
# ==========================================
class ErrorCategory:
    """Error categories for better UX"""
    
    # User-facing error messages
    LOGIN_FAILED = {
        'title': '🔐 Login Gagal',
        'description': 'Tidak dapat masuk ke akun CloudEmulator Anda.',
        'causes': [
            'Email atau password salah',
            'Akun terkunci sementara',
            'Koneksi internet bermasalah'
        ],
        'solutions': [
            'Periksa kembali email dan password',
            'Coba login manual di website CloudEmulator',
            'Tunggu 5-10 menit lalu coba lagi'
        ]
    }
    
    NETWORK_ERROR = {
        'title': '🌐 Koneksi Bermasalah',
        'description': 'Gagal terhubung ke server CloudEmulator.',
        'causes': [
            'Koneksi internet tidak stabil',
            'Server CloudEmulator sedang sibuk',
            'Firewall memblokir koneksi'
        ],
        'solutions': [
            'Periksa koneksi internet Anda',
            'Tunggu beberapa menit lalu coba lagi',
            'Hubungi admin jika masalah berlanjut'
        ]
    }
    
    INVALID_CODE = {
        'title': '❌ Kode Tidak Valid',
        'description': 'Kode redeem tidak dapat digunakan.',
        'causes': [
            'Kode sudah pernah digunakan',
            'Format kode salah',
            'Kode sudah expired'
        ],
        'solutions': [
            'Periksa kembali format kode',
            'Gunakan kode yang belum terpakai',
            'Hubungi penyedia kode untuk kode baru'
        ]
    }
    
    INSUFFICIENT_BALANCE = {
        'title': '💳 Saldo Tidak Cukup',
        'description': 'Saldo Anda tidak mencukupi untuk proses ini.',
        'causes': [
            'Biaya redeem melebihi saldo',
            'Saldo belum ter-update'
        ],
        'solutions': [
            'Top up saldo terlebih dahulu',
            'Kurangi jumlah kode yang diproses',
            'Cek saldo dengan tombol Info Saldo'
        ]
    }
    
    FILE_ERROR = {
        'title': '📁 File Bermasalah',
        'description': 'Tidak dapat membaca file kode.',
        'causes': [
            'Format file bukan .txt',
            'File kosong',
            'Encoding file salah'
        ],
        'solutions': [
            'Pastikan file berformat .txt',
            'Periksa isi file (min 1 kode)',
            'Simpan ulang file dengan encoding UTF-8'
        ]
    }
    
    TIMEOUT = {
        'title': '⏱️ Waktu Habis',
        'description': 'Proses melebihi batas waktu yang ditentukan.',
        'causes': [
            'Terlalu banyak kode diproses',
            'Server CloudEmulator lambat',
            'Koneksi tidak stabil'
        ],
        'solutions': [
            'Kurangi jumlah kode per batch',
            'Coba lagi saat server lebih lancar',
            'Hubungi admin untuk bantuan'
        ]
    }
    
    SYSTEM_ERROR = {
        'title': '⚙️ Kesalahan Sistem',
        'description': 'Terjadi kesalahan internal pada bot.',
        'causes': [
            'Bug pada sistem',
            'Resource server penuh',
            'Konfigurasi bermasalah'
        ],
        'solutions': [
            'Coba lagi dalam beberapa menit',
            'Hubungi admin dengan detail error',
            'Gunakan tombol 🆘 untuk laporan'
        ]
    }
    
    @staticmethod
    def format_error(category):
        """Format error category to Discord embed fields"""
        return {
            'title': category['title'],
            'description': category['description'],
            'causes': '\n'.join([f"• {c}" for c in category['causes']]),
            'solutions': '\n'.join([f"• {s}" for s in category['solutions']])
        }

# ==========================================
# GLOBAL LOGGER INSTANCE
# ==========================================
logger = Logger('BotRedeem')

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def log_startup():
    """Log startup message"""
    logger.info("="*60)
    logger.info("🚀 Bot Starting Up")
    logger.info(f"📅 Time: {config.format_wib_datetime()}")
    logger.info(f"⚙️ Workers: {config.MAX_LOGIN_WORKERS}")
    logger.info(f"💰 Cost per Code: Rp {config.REDEEM_COST_PER_CODE:,}")
    logger.info(f"🌐 Environment: {'PRODUCTION' if config.MIDTRANS_IS_PRODUCTION else 'SANDBOX'}")
    logger.info("="*60)

def log_shutdown():
    """Log shutdown message"""
    logger.info("="*60)
    logger.info("👋 Bot Shutting Down")
    logger.info(f"📅 Time: {config.format_wib_datetime()}")
    logger.info("="*60)

def log_error_with_context(error, context, user_id=None):
    """Log error with additional context"""
    logger.error(f"Error in {context}: {str(error)}", user_id=user_id)
    logger.debug(f"Traceback: {traceback.format_exc()}", user_id=user_id)