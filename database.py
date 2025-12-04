import sqlite3
import threading
import time
from datetime import datetime
from contextlib import contextmanager
from functools import wraps

DB_FILE = "bot_database.db"
db_lock = threading.RLock()

# ==========================================
# RETRY DECORATOR
# ==========================================

def retry_on_database_lock(max_attempts=5, delay=0.1):
    """Decorator untuk retry operasi database saat terjadi lock"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_attempts - 1:
                        time.sleep(delay * (attempt + 1))  # Exponential backoff
                        continue
                    raise
                except Exception as e:
                    raise
            return None
        return wrapper
    return decorator

@contextmanager
def get_db():
    """Context manager untuk koneksi database thread-safe dengan timeout"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging untuk concurrency
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

# ==========================================
# DATABASE INITIALIZATION
# ==========================================

@retry_on_database_lock()
def init_database():
    """Inisialisasi database dan tabel"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Tabel users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                total_topup INTEGER NOT NULL DEFAULT 0,
                total_spent INTEGER NOT NULL DEFAULT 0,
                total_redeem INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabel topups
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS topups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                order_id TEXT UNIQUE NOT NULL,
                payment_type TEXT DEFAULT 'qris',
                status TEXT CHECK(status IN ('pending', 'success', 'failed', 'expired')) DEFAULT 'pending',
                midtrans_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        # Tabel redeems
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS redeems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                region TEXT,
                android_version TEXT,
                status TEXT CHECK(status IN ('queued', 'processing', 'success', 'invalid', 'error')) DEFAULT 'queued',
                cost INTEGER NOT NULL DEFAULT 0,
                logs TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        # Index untuk performa
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_topups_user ON topups(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_topups_order ON topups(order_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_topups_status ON topups(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_redeems_user ON redeems(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_redeems_status ON redeems(status)')

        print("✅ Database berhasil diinisialisasi")

# ==========================================
# USER OPERATIONS
# ==========================================

@retry_on_database_lock()
def get_or_create_user(user_id: int):
    """Ambil user atau buat jika belum ada"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()

        if not user:
            cursor.execute(
                'INSERT OR IGNORE INTO users (user_id) VALUES (?)', 
                (user_id,)
            )
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()

        return dict(user) if user else None

@retry_on_database_lock()
def get_balance(user_id: int) -> int:
    """Ambil saldo user"""
    user = get_or_create_user(user_id)
    return user['balance'] if user else 0

@retry_on_database_lock()
def add_balance(user_id: int, amount: int) -> int:
    """Tambah saldo user (atomik dengan transaction)"""
    if amount <= 0:
        raise ValueError("Amount harus positif")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Gunakan transaction eksplisit
        cursor.execute('BEGIN IMMEDIATE')
        
        try:
            # Pastikan user ada
            get_or_create_user(user_id)
            
            # Update balance
            cursor.execute('''
                UPDATE users
                SET balance = balance + ?,
                    total_topup = total_topup + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (amount, amount, user_id))
            
            # Ambil saldo baru
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            conn.commit()
            return result['balance'] if result else 0
            
        except Exception as e:
            conn.rollback()
            raise

@retry_on_database_lock()
def deduct_balance(user_id: int, amount: int) -> bool:
    """Kurangi saldo user (atomik dengan check) - return True jika berhasil"""
    if amount <= 0:
        return False
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Gunakan transaction eksplisit
        cursor.execute('BEGIN IMMEDIATE')
        
        try:
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()

            if not row or row['balance'] < amount:
                conn.rollback()
                return False

            cursor.execute('''
                UPDATE users
                SET balance = balance - ?,
                    total_spent = total_spent + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND balance >= ?
            ''', (amount, amount, user_id, amount))
            
            # Verify update berhasil
            if cursor.rowcount == 0:
                conn.rollback()
                return False
            
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            raise

# ==========================================
# TOPUP OPERATIONS
# ==========================================

@retry_on_database_lock()
def create_topup(user_id: int, amount: int, order_id: str) -> int:
    """Buat record topup baru"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Pastikan user ada
        get_or_create_user(user_id)
        
        cursor.execute('''
            INSERT INTO topups (user_id, amount, order_id)
            VALUES (?, ?, ?)
        ''', (user_id, amount, order_id))
        
        return cursor.lastrowid

@retry_on_database_lock()
def update_topup_status(order_id: str, status: str, midtrans_data: str = None):
    """Update status topup"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        if midtrans_data:
            cursor.execute('''
                UPDATE topups
                SET status = ?, 
                    midtrans_data = ?, 
                    updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
            ''', (status, midtrans_data, order_id))
        else:
            cursor.execute('''
                UPDATE topups
                SET status = ?, 
                    updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
            ''', (status, order_id))

@retry_on_database_lock()
def get_topup_by_order_id(order_id: str):
    """Ambil topup berdasarkan order ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM topups WHERE order_id = ?', (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

@retry_on_database_lock()
def get_user_topup_history(user_id: int, limit: int = 10):
    """Ambil history topup user"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM topups
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]

# ==========================================
# REDEEM OPERATIONS
# ==========================================

@retry_on_database_lock()
def create_redeem(user_id: int, code: str, region: str, android_version: str, cost: int = 0) -> int:
    """Buat record redeem baru"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO redeems (user_id, code, region, android_version, cost, status)
            VALUES (?, ?, ?, ?, ?, 'queued')
        ''', (user_id, code, region, android_version, cost))
        return cursor.lastrowid

@retry_on_database_lock()
def update_redeem_status(redeem_id: int, status: str, logs: str = None):
    """Update status redeem"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        if logs:
            cursor.execute('''
                UPDATE redeems
                SET status = ?, 
                    logs = ?, 
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, logs, redeem_id))
        else:
            cursor.execute('''
                UPDATE redeems
                SET status = ?, 
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, redeem_id))

@retry_on_database_lock()
def get_user_redeem_history(user_id: int, limit: int = 10):
    """Ambil history redeem user"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM redeems
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]

@retry_on_database_lock()
def get_redeem_queue_count() -> int:
    """Hitung jumlah redeem dalam antrian"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM redeems
            WHERE status IN ('queued', 'processing')
        ''')
        result = cursor.fetchone()
        return result['count'] if result else 0

# ==========================================
# STATISTICS
# ==========================================

@retry_on_database_lock()
def get_user_stats(user_id: int):
    """Ambil statistik lengkap user"""
    user = get_or_create_user(user_id)
    
    if not user:
        return {
            'balance': 0,
            'total_topup': 0,
            'total_spent': 0,
            'total_redeem': 0,
            'success_redeem': 0,
            'failed_redeem': 0
        }
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Success count
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM redeems
            WHERE user_id = ? AND status = 'success'
        ''', (user_id,))
        success_count = cursor.fetchone()['count']

        # Failed count
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM redeems
            WHERE user_id = ? AND status IN ('invalid', 'error')
        ''', (user_id,))
        failed_count = cursor.fetchone()['count']

    return {
        'balance': user['balance'],
        'total_topup': user['total_topup'],
        'total_spent': user['total_spent'],
        'total_redeem': user['total_redeem'],
        'success_redeem': success_count,
        'failed_redeem': failed_count
    }

# ==========================================
# MAINTENANCE & CLEANUP
# ==========================================

@retry_on_database_lock()
def cleanup_old_pending_topups(days=1):
    """Cleanup topup pending yang sudah kadaluarsa"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE topups
            SET status = 'expired',
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'pending'
            AND datetime(created_at) < datetime('now', '-' || ? || ' days')
        ''', (days,))
        
        return cursor.rowcount

@retry_on_database_lock()
def get_database_stats():
    """Ambil statistik database untuk monitoring"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        stats = {}
        
        # Total users
        cursor.execute('SELECT COUNT(*) as count FROM users')
        stats['total_users'] = cursor.fetchone()['count']
        
        # Total balance in system
        cursor.execute('SELECT COALESCE(SUM(balance), 0) as total FROM users')
        stats['total_balance'] = cursor.fetchone()['total']
        
        # Topup stats
        cursor.execute('''
            SELECT 
                COUNT(*) as count,
                COALESCE(SUM(amount), 0) as total
            FROM topups 
            WHERE status = 'success'
        ''')
        row = cursor.fetchone()
        stats['successful_topups'] = row['count']
        stats['total_topup_amount'] = row['total']
        
        # Redeem stats
        cursor.execute('SELECT COUNT(*) as count FROM redeems WHERE status = "success"')
        stats['successful_redeems'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM redeems WHERE status IN ("invalid", "error")')
        stats['failed_redeems'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM redeems WHERE status IN ("queued", "processing")')
        stats['pending_redeems'] = cursor.fetchone()['count']
        
        return stats