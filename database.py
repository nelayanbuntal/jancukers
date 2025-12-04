import sqlite3
import threading
from datetime import datetime
from contextlib import contextmanager

DB_FILE = "bot_database.db"
db_lock = threading.RLock()  # Gunakan RLock agar bisa reentrant

@contextmanager
def get_db():
    """Context manager untuk koneksi database thread-safe"""
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

# ==========================================
# DATABASE INITIALIZATION
# ==========================================

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
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_redeems_user ON redeems(user_id)')

        conn.commit()
        print("✅ Database initialized successfully")

# ==========================================
# USER OPERATIONS
# ==========================================

def get_or_create_user(user_id: int):
    """Ambil user atau buat jika belum ada"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()

        if not user:
            cursor.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
            conn.commit()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()

        return dict(user)

def get_balance(user_id: int) -> int:
    """Ambil saldo user"""
    user = get_or_create_user(user_id)
    return user['balance']

def add_balance(user_id: int, amount: int) -> int:
    """Tambah saldo user (atomik)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET balance = balance + ?,
                total_topup = total_topup + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (amount, amount, user_id))
        conn.commit()

        # Ambil saldo baru langsung tanpa nested get_db()
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()['balance']

def deduct_balance(user_id: int, amount: int) -> bool:
    """Kurangi saldo user (atomik) - return True jika berhasil"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()

        if not row or row['balance'] < amount:
            return False

        cursor.execute('''
            UPDATE users
            SET balance = balance - ?,
                total_redeem = total_redeem + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (amount, user_id))
        conn.commit()

        return True

# ==========================================
# TOPUP OPERATIONS
# ==========================================

def create_topup(user_id: int, amount: int, order_id: str) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO topups (user_id, amount, order_id)
            VALUES (?, ?, ?)
        ''', (user_id, amount, order_id))
        conn.commit()
        return cursor.lastrowid

def update_topup_status(order_id: str, status: str, midtrans_data: str = None):
    with get_db() as conn:
        cursor = conn.cursor()
        if midtrans_data:
            cursor.execute('''
                UPDATE topups
                SET status = ?, midtrans_data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
            ''', (status, midtrans_data, order_id))
        else:
            cursor.execute('''
                UPDATE topups
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
            ''', (status, order_id))
        conn.commit()

def get_topup_by_order_id(order_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM topups WHERE order_id = ?', (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_topup_history(user_id: int, limit: int = 10):
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

def create_redeem(user_id: int, code: str, region: str, android_version: str, cost: int = 0) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO redeems (user_id, code, region, android_version, cost, status)
            VALUES (?, ?, ?, ?, ?, 'queued')
        ''', (user_id, code, region, android_version, cost))
        conn.commit()
        return cursor.lastrowid

def update_redeem_status(redeem_id: int, status: str, logs: str = None):
    with get_db() as conn:
        cursor = conn.cursor()
        if logs:
            cursor.execute('''
                UPDATE redeems
                SET status = ?, logs = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, logs, redeem_id))
        else:
            cursor.execute('''
                UPDATE redeems
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, redeem_id))
        conn.commit()

def get_user_redeem_history(user_id: int, limit: int = 10):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM redeems
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]

def get_redeem_queue_count() -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM redeems
            WHERE status IN ('queued', 'processing')
        ''')
        return cursor.fetchone()['count']

# ==========================================
# STATISTICS
# ==========================================

def get_user_stats(user_id: int):
    user = get_or_create_user(user_id)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM redeems
            WHERE user_id = ? AND status = 'success'
        ''', (user_id,))
        success_count = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count
            FROM redeems
            WHERE user_id = ? AND status IN ('invalid', 'error')
        ''', (user_id,))
        failed_count = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COALESCE(SUM(cost), 0) as total
            FROM redeems
            WHERE user_id = ? AND status = 'success'
        ''', (user_id,))
        total_spent = cursor.fetchone()['total']

    return {
        'balance': user['balance'],
        'total_topup': user['total_topup'],
        'total_redeem': user['total_redeem'],
        'success_redeem': success_count,
        'failed_redeem': failed_count,
        'total_spent': total_spent
    }

