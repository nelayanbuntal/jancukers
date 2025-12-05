"""
Enhanced Database Module
=========================
Production-grade database with connection pooling and better error handling
"""

import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
import config

# Import logger
try:
    from logger import logger, log_error_with_context
except ImportError:
    # Fallback if logger not available yet
    class FallbackLogger:
        def info(self, msg, **kwargs): print(f"ℹ️ {msg}")
        def warning(self, msg, **kwargs): print(f"⚠️ {msg}")
        def error(self, msg, **kwargs): print(f"❌ {msg}")
        def debug(self, msg, **kwargs): pass
    logger = FallbackLogger()
    def log_error_with_context(e, ctx, **kwargs): print(f"❌ Error in {ctx}: {e}")

# ==========================================
# CONNECTION POOL
# ==========================================
class ConnectionPool:
    """Thread-safe connection pool for SQLite"""
    
    def __init__(self, database, max_connections=10):
        self.database = database
        self.max_connections = max_connections
        self.connections = []
        self.lock = threading.Lock()
        self._local = threading.local()
    
    def get_connection(self):
        """Get a connection from pool"""
        # Return thread-local connection if exists
        if hasattr(self._local, 'conn') and self._local.conn:
            return self._local.conn
        
        with self.lock:
            if self.connections:
                conn = self.connections.pop()
            else:
                conn = sqlite3.connect(
                    self.database,
                    timeout=config.DB_TIMEOUT,
                    check_same_thread=False
                )
                conn.row_factory = sqlite3.Row
                # Enable WAL mode for better concurrency
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            
            self._local.conn = conn
            return conn
    
    def return_connection(self, conn):
        """Return connection to pool"""
        if conn:
            with self.lock:
                if len(self.connections) < self.max_connections:
                    self.connections.append(conn)
                else:
                    conn.close()
    
    def close_all(self):
        """Close all connections"""
        with self.lock:
            for conn in self.connections:
                try:
                    conn.close()
                except:
                    pass
            self.connections.clear()

# Global connection pool
_pool = None

def get_pool():
    """Get or create connection pool"""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(config.DB_FILE)
    return _pool

# ==========================================
# CONTEXT MANAGER FOR TRANSACTIONS
# ==========================================
@contextmanager
def get_db_connection(commit=True):
    """
    Context manager for database connections with automatic retry
    
    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(...)
    """
    pool = get_pool()
    conn = None
    retry_count = 0
    max_retries = config.DB_MAX_RETRY_ATTEMPTS
    
    while retry_count < max_retries:
        try:
            conn = pool.get_connection()
            yield conn
            
            if commit:
                conn.commit()
            break
            
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                retry_count += 1
                if retry_count < max_retries:
                    logger.warning(f"Database locked, retry {retry_count}/{max_retries}")
                    time.sleep(config.DB_RETRY_DELAY * retry_count)
                    if conn:
                        try:
                            conn.rollback()
                        except:
                            pass
                    continue
                else:
                    logger.error(f"Database locked after {max_retries} retries")
                    raise
            else:
                raise
        
        except Exception as e:
            if conn and commit:
                try:
                    conn.rollback()
                except:
                    pass
            raise
        
        finally:
            if conn:
                pool.return_connection(conn)

# ==========================================
# DATABASE INITIALIZATION
# ==========================================
def init_database():
    """Initialize database tables"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER DEFAULT 0,
                    total_topup INTEGER DEFAULT 0,
                    total_spent INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Topup transactions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS topups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    order_id TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Redeem history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS redeems (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    code_count INTEGER NOT NULL,
                    total_cost INTEGER NOT NULL,
                    success_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Create indexes for better performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_topups_user_id 
                ON topups(user_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_topups_order_id 
                ON topups(order_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_redeems_user_id 
                ON redeems(user_id)
            ''')
            
            logger.info("✅ Database initialized successfully")
            
    except Exception as e:
        log_error_with_context(e, "init_database")
        raise

# ==========================================
# USER OPERATIONS
# ==========================================
def get_balance(user_id):
    """Get user balance"""
    try:
        with get_db_connection(commit=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return row['balance']
            else:
                # Create new user
                cursor.execute(
                    "INSERT INTO users (user_id, balance) VALUES (?, 0)",
                    (user_id,)
                )
                conn.commit()
                logger.info(f"Created new user: {user_id}", user_id=user_id)
                return 0
                
    except Exception as e:
        log_error_with_context(e, "get_balance", user_id=user_id)
        return 0

def add_balance(user_id, amount):
    """Add balance to user"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Ensure user exists
            cursor.execute(
                "INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)",
                (user_id,)
            )
            
            # Update balance and totals
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ?,
                    total_topup = total_topup + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (amount, amount, user_id))
            
            # Get new balance
            cursor.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            new_balance = row['balance'] if row else 0
            
            logger.info(f"Added Rp {amount:,} to user. New balance: Rp {new_balance:,}", user_id=user_id)
            return new_balance
            
    except Exception as e:
        log_error_with_context(e, "add_balance", user_id=user_id)
        raise

def deduct_balance(user_id, amount):
    """Deduct balance from user"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check current balance
            cursor.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                logger.warning(f"User not found for deduction", user_id=user_id)
                return False
            
            current_balance = row['balance']
            
            if current_balance < amount:
                logger.warning(f"Insufficient balance. Need: Rp {amount:,}, Have: Rp {current_balance:,}", user_id=user_id)
                return False
            
            # Deduct balance
            cursor.execute('''
                UPDATE users 
                SET balance = balance - ?,
                    total_spent = total_spent + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (amount, amount, user_id))
            
            new_balance = current_balance - amount
            logger.info(f"Deducted Rp {amount:,}. New balance: Rp {new_balance:,}", user_id=user_id)
            return True
            
    except Exception as e:
        log_error_with_context(e, "deduct_balance", user_id=user_id)
        return False

# ==========================================
# TOPUP OPERATIONS
# ==========================================
def create_topup(user_id, amount, order_id):
    """Create topup transaction"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Ensure user exists
            cursor.execute(
                "INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)",
                (user_id,)
            )
            
            # Create topup record
            cursor.execute('''
                INSERT INTO topups (user_id, amount, order_id, status)
                VALUES (?, ?, ?, 'pending')
            ''', (user_id, amount, order_id))
            
            logger.info(f"Created topup: {order_id} | Rp {amount:,}", user_id=user_id)
            return True
            
    except sqlite3.IntegrityError:
        logger.warning(f"Duplicate order_id: {order_id}", user_id=user_id)
        return False
    except Exception as e:
        log_error_with_context(e, "create_topup", user_id=user_id)
        return False

def update_topup_status(order_id, status):
    """Update topup status"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE topups 
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
            ''', (status, order_id))
            
            if cursor.rowcount > 0:
                logger.info(f"Updated topup status: {order_id} → {status}")
                return True
            else:
                logger.warning(f"Topup not found: {order_id}")
                return False
                
    except Exception as e:
        log_error_with_context(e, "update_topup_status")
        return False

def get_topup_by_order_id(order_id):
    """Get topup by order_id"""
    try:
        with get_db_connection(commit=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM topups WHERE order_id = ?",
                (order_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
            
    except Exception as e:
        log_error_with_context(e, "get_topup_by_order_id")
        return None

# ==========================================
# REDEEM OPERATIONS
# ==========================================
def create_redeem(user_id, code_count, total_cost):
    """Create redeem record"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO redeems (user_id, code_count, total_cost, status)
                VALUES (?, ?, ?, 'pending')
            ''', (user_id, code_count, total_cost))
            
            redeem_id = cursor.lastrowid
            logger.info(f"Created redeem: ID={redeem_id} | Codes={code_count} | Cost=Rp {total_cost:,}", user_id=user_id)
            return redeem_id
            
    except Exception as e:
        log_error_with_context(e, "create_redeem", user_id=user_id)
        return None

def update_redeem_result(redeem_id, success_count, failed_count, status='completed'):
    """Update redeem result"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE redeems 
                SET success_count = ?,
                    failed_count = ?,
                    status = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (success_count, failed_count, status, redeem_id))
            
            logger.info(f"Updated redeem: ID={redeem_id} | Success={success_count} | Failed={failed_count}")
            return True
            
    except Exception as e:
        log_error_with_context(e, "update_redeem_result")
        return False

# ==========================================
# STATISTICS
# ==========================================
def get_user_stats(user_id):
    """Get user statistics"""
    try:
        with get_db_connection(commit=False) as conn:
            cursor = conn.cursor()
            
            # Get user data
            cursor.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            user_row = cursor.fetchone()
            
            if not user_row:
                return {
                    'balance': 0,
                    'total_topup': 0,
                    'total_spent': 0,
                    'total_redeem': 0,
                    'success_redeem': 0,
                    'failed_redeem': 0
                }
            
            # Get redeem stats
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_redeem,
                    SUM(success_count) as success_redeem,
                    SUM(failed_count) as failed_redeem
                FROM redeems 
                WHERE user_id = ? AND status = 'completed'
            ''', (user_id,))
            redeem_row = cursor.fetchone()
            
            return {
                'balance': user_row['balance'],
                'total_topup': user_row['total_topup'],
                'total_spent': user_row['total_spent'],
                'total_redeem': redeem_row['total_redeem'] or 0,
                'success_redeem': redeem_row['success_redeem'] or 0,
                'failed_redeem': redeem_row['failed_redeem'] or 0
            }
            
    except Exception as e:
        log_error_with_context(e, "get_user_stats", user_id=user_id)
        return {
            'balance': 0,
            'total_topup': 0,
            'total_spent': 0,
            'total_redeem': 0,
            'success_redeem': 0,
            'failed_redeem': 0
        }

def get_database_stats():
    """Get overall database statistics"""
    try:
        with get_db_connection(commit=False) as conn:
            cursor = conn.cursor()
            
            # Total users
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']
            
            # Total balance
            cursor.execute("SELECT SUM(balance) as total FROM users")
            total_balance = cursor.fetchone()['total'] or 0
            
            # Topup stats
            cursor.execute('''
                SELECT 
                    COUNT(*) as count,
                    SUM(amount) as total
                FROM topups 
                WHERE status = 'success'
            ''')
            topup_row = cursor.fetchone()
            
            # Redeem stats
            cursor.execute('''
                SELECT 
                    SUM(success_count) as success,
                    SUM(failed_count) as failed,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending
                FROM redeems
            ''')
            redeem_row = cursor.fetchone()
            
            return {
                'total_users': total_users,
                'total_balance': total_balance,
                'successful_topups': topup_row['count'] or 0,
                'total_topup_amount': topup_row['total'] or 0,
                'successful_redeems': redeem_row['success'] or 0,
                'failed_redeems': redeem_row['failed'] or 0,
                'pending_redeems': redeem_row['pending'] or 0
            }
            
    except Exception as e:
        log_error_with_context(e, "get_database_stats")
        return {
            'total_users': 0,
            'total_balance': 0,
            'successful_topups': 0,
            'total_topup_amount': 0,
            'successful_redeems': 0,
            'failed_redeems': 0,
            'pending_redeems': 0
        }

def get_redeem_queue_count():
    """Get count of pending redeems"""
    try:
        with get_db_connection(commit=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM redeems WHERE status = 'pending'"
            )
            return cursor.fetchone()['count']
    except:
        return 0

# ==========================================
# CLEANUP
# ==========================================
def cleanup_database():
    """Cleanup old records (optional, for maintenance)"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Delete old failed topups (>30 days)
            cursor.execute('''
                DELETE FROM topups 
                WHERE status = 'failed' 
                AND created_at < datetime('now', '-30 days')
            ''')
            deleted_topups = cursor.rowcount
            
            # Delete old completed redeems (>90 days)
            cursor.execute('''
                DELETE FROM redeems 
                WHERE status = 'completed' 
                AND completed_at < datetime('now', '-90 days')
            ''')
            deleted_redeems = cursor.rowcount
            
            logger.info(f"Cleanup: Deleted {deleted_topups} old topups, {deleted_redeems} old redeems")
            return True
            
    except Exception as e:
        log_error_with_context(e, "cleanup_database")
        return False