"""
Supabase Database Module
=========================
Production-grade database with Supabase PostgreSQL
"""

import os
from supabase import create_client, Client
from datetime import datetime
import config
from functools import wraps
import time

# Import logger
try:
    from logger import logger, log_error_with_context
except ImportError:
    class FallbackLogger:
        def info(self, msg, **kwargs): print(f"ℹ️ {msg}")
        def warning(self, msg, **kwargs): print(f"⚠️ {msg}")
        def error(self, msg, **kwargs): print(f"❌ {msg}")
        def debug(self, msg, **kwargs): pass
    logger = FallbackLogger()
    def log_error_with_context(e, ctx, **kwargs): print(f"❌ Error in {ctx}: {e}")

# ==========================================
# ERROR HANDLING HELPERS
# ==========================================

def is_rls_error(error):
    """Check if error is RLS policy error"""
    error_str = str(error).lower()
    return (
        'row-level security' in error_str or 
        '42501' in error_str or
        'rls' in error_str
    )

def handle_supabase_error(error, context="database operation"):
    """Handle Supabase errors with helpful messages"""
    error_dict = error if isinstance(error, dict) else {'message': str(error)}
    error_msg = error_dict.get('message', str(error))
    error_code = error_dict.get('code', '')
    
    if is_rls_error(error) or error_code == '42501':
        logger.error(f"❌ RLS POLICY ERROR in {context}")
        logger.error("=" * 70)
        logger.error("QUICK FIX: Run this SQL in Supabase SQL Editor:")
        logger.error("")
        logger.error("  ALTER TABLE users DISABLE ROW LEVEL SECURITY;")
        logger.error("  ALTER TABLE topups DISABLE ROW LEVEL SECURITY;")
        logger.error("  ALTER TABLE redeems DISABLE ROW LEVEL SECURITY;")
        logger.error("")
        logger.error("OR run the complete fix: fix_rls_security.sql")
        logger.error("=" * 70)
        raise Exception(f"RLS Policy Error - Please disable RLS or fix policies. See logs above.")
    else:
        logger.error(f"Database error in {context}: {error_msg}")
        raise

# ==========================================
# SUPABASE CLIENT
# ==========================================
_supabase_client: Client = None

def get_supabase_client() -> Client:
    """Get or create Supabase client"""
    global _supabase_client
    
    if _supabase_client is None:
        try:
            url = config.SUPABASE_URL
            key = config.SUPABASE_KEY
            
            if not url or not key:
                raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in config")
            
            _supabase_client = create_client(url, key)
            logger.info("✅ Supabase client initialized")
            
            # Test connection and check RLS
            try:
                test = _supabase_client.table('users').select('user_id').limit(1).execute()
                logger.info("✅ Supabase connection tested successfully")
            except Exception as test_error:
                error_msg = str(test_error)
                if 'row-level security' in error_msg.lower() or '42501' in error_msg:
                    logger.error("❌ RLS POLICY ERROR DETECTED!")
                    logger.error("Run this SQL in Supabase SQL Editor:")
                    logger.error("=" * 60)
                    logger.error("ALTER TABLE users DISABLE ROW LEVEL SECURITY;")
                    logger.error("ALTER TABLE topups DISABLE ROW LEVEL SECURITY;")
                    logger.error("ALTER TABLE redeems DISABLE ROW LEVEL SECURITY;")
                    logger.error("=" * 60)
                    logger.error("Or run: fix_rls_security.sql")
                    raise Exception(f"RLS Policy Error: {error_msg}\n\nPlease run fix_rls_security.sql in Supabase SQL Editor")
                raise
            
        except Exception as e:
            logger.error(f"Failed to initialize Supabase: {e}")
            raise
    
    return _supabase_client

# ==========================================
# RETRY DECORATOR
# ==========================================
def retry_db_operation(max_attempts=3, delay=1):
    """Decorator untuk retry database operations"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt < max_attempts - 1:
                        logger.warning(f"DB operation failed, retry {attempt + 1}/{max_attempts}: {e}")
                        time.sleep(delay * (attempt + 1))
                        continue
                    raise
            return None
        return wrapper
    return decorator

# ==========================================
# DATABASE INITIALIZATION
# ==========================================
def init_database():
    """Initialize database tables in Supabase (via SQL migration)"""
    try:
        supabase = get_supabase_client()
        
        # Test connection with simple query
        result = supabase.table('users').select("user_id").limit(1).execute()
        
        logger.info("✅ Supabase database initialized and connected")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        logger.info("Please run the SQL migration in Supabase SQL Editor:")
        logger.info("See: setup_supabase.sql")
        raise

# ==========================================
# USER OPERATIONS
# ==========================================
@retry_db_operation(max_attempts=3)
def get_balance(user_id: int) -> int:
    """Get user balance"""
    try:
        supabase = get_supabase_client()
        
        # Query user
        result = supabase.table('users').select('balance').eq('user_id', user_id).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]['balance']
        else:
            # Create new user
            try:
                supabase.table('users').insert({
                    'user_id': user_id,
                    'balance': 0,
                    'total_topup': 0,
                    'total_spent': 0
                }).execute()
                
                logger.info(f"Created new user: {user_id}", user_id=user_id)
                return 0
            except Exception as insert_error:
                # Check if it's RLS error
                if is_rls_error(insert_error):
                    handle_supabase_error(insert_error, "get_balance - insert new user")
                # If user already exists (race condition), get balance again
                result = supabase.table('users').select('balance').eq('user_id', user_id).execute()
                if result.data:
                    return result.data[0]['balance']
                raise
            
    except Exception as e:
        if is_rls_error(e):
            handle_supabase_error(e, "get_balance")
        log_error_with_context(e, "get_balance", user_id=user_id)
        return 0

@retry_db_operation(max_attempts=3)
def add_balance(user_id: int, amount: int) -> int:
    """Add balance to user"""
    try:
        supabase = get_supabase_client()
        
        # Get current balance
        current_balance = get_balance(user_id)
        
        # Update balance
        new_balance = current_balance + amount
        
        result = supabase.table('users').update({
            'balance': new_balance,
            'total_topup': supabase.table('users').select('total_topup').eq('user_id', user_id).execute().data[0]['total_topup'] + amount,
            'updated_at': datetime.utcnow().isoformat()
        }).eq('user_id', user_id).execute()
        
        logger.info(f"Added Rp {amount:,} to user. New balance: Rp {new_balance:,}", user_id=user_id)
        return new_balance
        
    except Exception as e:
        log_error_with_context(e, "add_balance", user_id=user_id)
        raise

@retry_db_operation(max_attempts=3)
def deduct_balance(user_id: int, amount: int) -> bool:
    """Deduct balance from user"""
    try:
        supabase = get_supabase_client()
        
        # Get current balance
        current_balance = get_balance(user_id)
        
        if current_balance < amount:
            logger.warning(f"Insufficient balance. Need: Rp {amount:,}, Have: Rp {current_balance:,}", user_id=user_id)
            return False
        
        # Update balance
        new_balance = current_balance - amount
        
        # Get current total_spent
        user_data = supabase.table('users').select('total_spent').eq('user_id', user_id).execute()
        current_spent = user_data.data[0]['total_spent'] if user_data.data else 0
        
        result = supabase.table('users').update({
            'balance': new_balance,
            'total_spent': current_spent + amount,
            'updated_at': datetime.utcnow().isoformat()
        }).eq('user_id', user_id).execute()
        
        logger.info(f"Deducted Rp {amount:,}. New balance: Rp {new_balance:,}", user_id=user_id)
        return True
        
    except Exception as e:
        log_error_with_context(e, "deduct_balance", user_id=user_id)
        return False

# ==========================================
# TOPUP OPERATIONS
# ==========================================
@retry_db_operation(max_attempts=3)
def create_topup(user_id: int, amount: int, order_id: str) -> bool:
    """Create topup transaction"""
    try:
        supabase = get_supabase_client()
        
        # Ensure user exists
        get_balance(user_id)
        
        # Create topup record
        result = supabase.table('topups').insert({
            'user_id': user_id,
            'amount': amount,
            'order_id': order_id,
            'status': 'pending',
            'payment_type': 'qris'
        }).execute()
        
        logger.info(f"Created topup: {order_id} | Rp {amount:,}", user_id=user_id)
        return True
        
    except Exception as e:
        # Check for RLS error
        if is_rls_error(e):
            handle_supabase_error(e, "create_topup")
        # Check for duplicate
        error_str = str(e).lower()
        if 'duplicate' in error_str or 'unique' in error_str:
            logger.warning(f"Duplicate order_id: {order_id}", user_id=user_id)
            return False
        log_error_with_context(e, "create_topup", user_id=user_id)
        return False

@retry_db_operation(max_attempts=3)
def update_topup_status(order_id: str, status: str, midtrans_data: str = None) -> bool:
    """Update topup status"""
    try:
        supabase = get_supabase_client()
        
        update_data = {
            'status': status,
            'updated_at': datetime.utcnow().isoformat()
        }
        
        if midtrans_data:
            update_data['midtrans_data'] = midtrans_data
        
        result = supabase.table('topups').update(update_data).eq('order_id', order_id).execute()
        
        if result.data:
            logger.info(f"Updated topup status: {order_id} → {status}")
            return True
        else:
            logger.warning(f"Topup not found: {order_id}")
            return False
            
    except Exception as e:
        log_error_with_context(e, "update_topup_status")
        return False

@retry_db_operation(max_attempts=3)
def get_topup_by_order_id(order_id: str) -> dict:
    """Get topup by order_id"""
    try:
        supabase = get_supabase_client()
        
        result = supabase.table('topups').select('*').eq('order_id', order_id).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
        
    except Exception as e:
        log_error_with_context(e, "get_topup_by_order_id")
        return None

# ==========================================
# REDEEM OPERATIONS
# ==========================================
@retry_db_operation(max_attempts=3)
def create_redeem(user_id: int, code_count: int, total_cost: int) -> int:
    """Create redeem record"""
    try:
        supabase = get_supabase_client()
        
        result = supabase.table('redeems').insert({
            'user_id': user_id,
            'code_count': code_count,
            'total_cost': total_cost,
            'status': 'pending',
            'success_count': 0,
            'failed_count': 0
        }).execute()
        
        if result.data:
            redeem_id = result.data[0]['id']
            logger.info(f"Created redeem: ID={redeem_id} | Codes={code_count} | Cost=Rp {total_cost:,}", user_id=user_id)
            return redeem_id
        
        return None
        
    except Exception as e:
        log_error_with_context(e, "create_redeem", user_id=user_id)
        return None

@retry_db_operation(max_attempts=3)
def update_redeem_result(redeem_id: int, success_count: int, failed_count: int, status: str = 'completed') -> bool:
    """Update redeem result"""
    try:
        supabase = get_supabase_client()
        
        result = supabase.table('redeems').update({
            'success_count': success_count,
            'failed_count': failed_count,
            'status': status,
            'completed_at': datetime.utcnow().isoformat()
        }).eq('id', redeem_id).execute()
        
        logger.info(f"Updated redeem: ID={redeem_id} | Success={success_count} | Failed={failed_count}")
        return True
        
    except Exception as e:
        log_error_with_context(e, "update_redeem_result")
        return False

# ==========================================
# STATISTICS
# ==========================================
@retry_db_operation(max_attempts=3)
def get_user_stats(user_id: int) -> dict:
    """Get user statistics"""
    try:
        supabase = get_supabase_client()
        
        # Get user data
        user_result = supabase.table('users').select('*').eq('user_id', user_id).execute()
        
        if not user_result.data:
            return {
                'balance': 0,
                'total_topup': 0,
                'total_spent': 0,
                'total_redeem': 0,
                'success_redeem': 0,
                'failed_redeem': 0
            }
        
        user_data = user_result.data[0]
        
        # Get redeem stats - FIXED: use correct column names
        redeem_result = supabase.table('redeems').select('*').eq('user_id', user_id).eq('status', 'completed').execute()
        
        total_redeem = len(redeem_result.data) if redeem_result.data else 0
        success_redeem = sum(r['success_count'] for r in redeem_result.data) if redeem_result.data else 0
        failed_redeem = sum(r['failed_count'] for r in redeem_result.data) if redeem_result.data else 0
        
        return {
            'balance': user_data.get('balance', 0),
            'total_topup': user_data.get('total_topup', 0),
            'total_spent': user_data.get('total_spent', 0),
            'total_redeem': total_redeem,
            'success_redeem': success_redeem,
            'failed_redeem': failed_redeem
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

@retry_db_operation(max_attempts=3)
def get_database_stats() -> dict:
    """Get overall database statistics"""
    try:
        supabase = get_supabase_client()
        
        # Total users
        users_result = supabase.table('users').select('user_id', count='exact').execute()
        total_users = users_result.count if hasattr(users_result, 'count') else 0
        
        # Total balance
        balance_result = supabase.table('users').select('balance').execute()
        total_balance = sum(u['balance'] for u in balance_result.data) if balance_result.data else 0
        
        # Topup stats
        topup_result = supabase.table('topups').select('*').eq('status', 'success').execute()
        successful_topups = len(topup_result.data) if topup_result.data else 0
        total_topup_amount = sum(t['amount'] for t in topup_result.data) if topup_result.data else 0
        
        # Redeem stats - FIXED: use correct column names
        redeem_result = supabase.table('redeems').select('*').execute()
        
        successful_redeems = sum(r['success_count'] for r in redeem_result.data) if redeem_result.data else 0
        failed_redeems = sum(r['failed_count'] for r in redeem_result.data) if redeem_result.data else 0
        pending_redeems = len([r for r in redeem_result.data if r['status'] == 'pending']) if redeem_result.data else 0
        
        return {
            'total_users': total_users,
            'total_balance': total_balance,
            'successful_topups': successful_topups,
            'total_topup_amount': total_topup_amount,
            'successful_redeems': successful_redeems,
            'failed_redeems': failed_redeems,
            'pending_redeems': pending_redeems
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

@retry_db_operation(max_attempts=3)
def get_redeem_queue_count() -> int:
    """Get count of pending redeems"""
    try:
        supabase = get_supabase_client()
        result = supabase.table('redeems').select('id', count='exact').eq('status', 'pending').execute()
        return result.count if hasattr(result, 'count') else 0
    except:
        return 0

# ==========================================
# CLEANUP
# ==========================================
@retry_db_operation(max_attempts=2)
def cleanup_database():
    """Cleanup old records (optional, for maintenance)"""
    try:
        supabase = get_supabase_client()
        
        # Delete old failed topups (>30 days)
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        
        result1 = supabase.table('topups').delete().eq('status', 'failed').lt('created_at', thirty_days_ago).execute()
        deleted_topups = len(result1.data) if result1.data else 0
        
        # Delete old completed redeems (>90 days)
        ninety_days_ago = (datetime.utcnow() - timedelta(days=90)).isoformat()
        
        result2 = supabase.table('redeems').delete().eq('status', 'completed').lt('completed_at', ninety_days_ago).execute()
        deleted_redeems = len(result2.data) if result2.data else 0
        
        logger.info(f"Cleanup: Deleted {deleted_topups} old topups, {deleted_redeems} old redeems")
        return True
        
    except Exception as e:
        log_error_with_context(e, "cleanup_database")
        return False

# ==========================================
# MIGRATION HELPER (SQLite to Supabase)
# ==========================================
def migrate_from_sqlite(sqlite_db_path: str = 'bot_database.db'):
    """
    Migrate data from SQLite to Supabase
    WARNING: Only run this once during migration!
    """
    import sqlite3
    
    try:
        logger.info("Starting migration from SQLite to Supabase...")
        
        # Connect to SQLite
        sqlite_conn = sqlite3.connect(sqlite_db_path)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()
        
        supabase = get_supabase_client()
        
        # Migrate users
        logger.info("Migrating users...")
        sqlite_cursor.execute("SELECT * FROM users")
        users = sqlite_cursor.fetchall()
        
        for user in users:
            try:
                supabase.table('users').insert({
                    'user_id': user['user_id'],
                    'balance': user['balance'],
                    'total_topup': user['total_topup'],
                    'total_spent': user.get('total_spent', 0),
                    'created_at': user['created_at'],
                    'updated_at': user['updated_at']
                }).execute()
            except Exception as e:
                if 'duplicate' not in str(e).lower():
                    logger.warning(f"Failed to migrate user {user['user_id']}: {e}")
        
        logger.info(f"Migrated {len(users)} users")
        
        # Migrate topups
        logger.info("Migrating topups...")
        sqlite_cursor.execute("SELECT * FROM topups")
        topups = sqlite_cursor.fetchall()
        
        for topup in topups:
            try:
                supabase.table('topups').insert({
                    'user_id': topup['user_id'],
                    'amount': topup['amount'],
                    'order_id': topup['order_id'],
                    'payment_type': topup.get('payment_type', 'qris'),
                    'status': topup['status'],
                    'midtrans_data': topup.get('midtrans_data'),
                    'created_at': topup['created_at'],
                    'updated_at': topup['updated_at']
                }).execute()
            except Exception as e:
                if 'duplicate' not in str(e).lower():
                    logger.warning(f"Failed to migrate topup {topup['order_id']}: {e}")
        
        logger.info(f"Migrated {len(topups)} topups")
        
        # Migrate redeems (if table exists and has correct schema)
        try:
            sqlite_cursor.execute("SELECT * FROM redeems")
            redeems = sqlite_cursor.fetchall()
            
            logger.info("Migrating redeems...")
            for redeem in redeems:
                try:
                    supabase.table('redeems').insert({
                        'user_id': redeem['user_id'],
                        'code_count': redeem.get('code_count', 0),
                        'total_cost': redeem.get('total_cost', 0),
                        'success_count': redeem.get('success_count', 0),
                        'failed_count': redeem.get('failed_count', 0),
                        'status': redeem['status'],
                        'created_at': redeem['created_at'],
                        'completed_at': redeem.get('completed_at')
                    }).execute()
                except Exception as e:
                    logger.warning(f"Failed to migrate redeem {redeem.get('id')}: {e}")
            
            logger.info(f"Migrated {len(redeems)} redeems")
        except:
            logger.warning("Could not migrate redeems table (might not exist or different schema)")
        
        sqlite_conn.close()
        logger.info("✅ Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise