-- ==========================================
-- SUPABASE DATABASE SETUP
-- ==========================================
-- Run this SQL in your Supabase SQL Editor
-- Dashboard > SQL Editor > New Query

-- Enable UUID extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- USERS TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    balance INTEGER NOT NULL DEFAULT 0,
    total_topup INTEGER NOT NULL DEFAULT 0,
    total_spent INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_users_updated_at ON users(updated_at);

-- Add trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ==========================================
-- TOPUPS TABLE
-- ==========================================
CREATE TABLE IF NOT EXISTS topups (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    amount INTEGER NOT NULL,
    order_id TEXT UNIQUE NOT NULL,
    payment_type TEXT DEFAULT 'qris',
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed', 'expired')),
    midtrans_data TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_topups_user_id ON topups(user_id);
CREATE INDEX IF NOT EXISTS idx_topups_order_id ON topups(order_id);
CREATE INDEX IF NOT EXISTS idx_topups_status ON topups(status);
CREATE INDEX IF NOT EXISTS idx_topups_created_at ON topups(created_at);

-- Add trigger for updated_at
CREATE TRIGGER update_topups_updated_at BEFORE UPDATE ON topups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ==========================================
-- REDEEMS TABLE (FIXED SCHEMA)
-- ==========================================
CREATE TABLE IF NOT EXISTS redeems (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    code_count INTEGER NOT NULL DEFAULT 0,
    total_cost INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_redeems_user_id ON redeems(user_id);
CREATE INDEX IF NOT EXISTS idx_redeems_status ON redeems(status);
CREATE INDEX IF NOT EXISTS idx_redeems_created_at ON redeems(created_at);

-- ==========================================
-- ROW LEVEL SECURITY (RLS) - FIXED
-- ==========================================
-- IMPORTANT: We disable RLS because we're using service_role key
-- Service role should have full access without RLS restrictions

-- Disable RLS on all tables (service_role bypasses RLS anyway)
ALTER TABLE users DISABLE ROW LEVEL SECURITY;
ALTER TABLE topups DISABLE ROW LEVEL SECURITY;
ALTER TABLE redeems DISABLE ROW LEVEL SECURITY;

-- Drop any existing policies (in case they exist)
DROP POLICY IF EXISTS "Service role can do everything on users" ON users;
DROP POLICY IF EXISTS "Service role can do everything on topups" ON topups;
DROP POLICY IF EXISTS "Service role can do everything on redeems" ON redeems;
DROP POLICY IF EXISTS "Enable all for service role on users" ON users;
DROP POLICY IF EXISTS "Enable all for service role on topups" ON topups;
DROP POLICY IF EXISTS "Enable all for service role on redeems" ON redeems;

-- Alternative: If you MUST use RLS, create proper policies
-- Uncomment ONLY if you need RLS enabled:

/*
-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE topups ENABLE ROW LEVEL SECURITY;
ALTER TABLE redeems ENABLE ROW LEVEL SECURITY;

-- Create permissive policies for authenticated role (service_role)
CREATE POLICY "Enable all for authenticated on users" ON users
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Enable all for authenticated on topups" ON topups
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Enable all for authenticated on redeems" ON redeems
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);
*/

-- ==========================================
-- FUNCTIONS FOR STATISTICS
-- ==========================================

-- Function to get user statistics
CREATE OR REPLACE FUNCTION get_user_stats(p_user_id BIGINT)
RETURNS TABLE (
    balance INTEGER,
    total_topup INTEGER,
    total_spent INTEGER,
    total_redeem BIGINT,
    success_redeem BIGINT,
    failed_redeem BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COALESCE(u.balance, 0) as balance,
        COALESCE(u.total_topup, 0) as total_topup,
        COALESCE(u.total_spent, 0) as total_spent,
        COALESCE(COUNT(r.id), 0) as total_redeem,
        COALESCE(SUM(r.success_count), 0) as success_redeem,
        COALESCE(SUM(r.failed_count), 0) as failed_redeem
    FROM users u
    LEFT JOIN redeems r ON u.user_id = r.user_id AND r.status = 'completed'
    WHERE u.user_id = p_user_id
    GROUP BY u.user_id, u.balance, u.total_topup, u.total_spent;
END;
$$ LANGUAGE plpgsql;

-- Function to get database statistics
CREATE OR REPLACE FUNCTION get_database_stats()
RETURNS TABLE (
    total_users BIGINT,
    total_balance BIGINT,
    successful_topups BIGINT,
    total_topup_amount BIGINT,
    successful_redeems BIGINT,
    failed_redeems BIGINT,
    pending_redeems BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        (SELECT COUNT(*) FROM users)::BIGINT as total_users,
        (SELECT COALESCE(SUM(balance), 0) FROM users)::BIGINT as total_balance,
        (SELECT COUNT(*) FROM topups WHERE status = 'success')::BIGINT as successful_topups,
        (SELECT COALESCE(SUM(amount), 0) FROM topups WHERE status = 'success')::BIGINT as total_topup_amount,
        (SELECT COALESCE(SUM(success_count), 0) FROM redeems)::BIGINT as successful_redeems,
        (SELECT COALESCE(SUM(failed_count), 0) FROM redeems)::BIGINT as failed_redeems,
        (SELECT COUNT(*) FROM redeems WHERE status = 'pending')::BIGINT as pending_redeems;
END;
$$ LANGUAGE plpgsql;

-- ==========================================
-- CLEANUP FUNCTION
-- ==========================================
CREATE OR REPLACE FUNCTION cleanup_old_records()
RETURNS void AS $$
BEGIN
    -- Delete old failed topups (>30 days)
    DELETE FROM topups 
    WHERE status = 'failed' 
    AND created_at < NOW() - INTERVAL '30 days';
    
    -- Delete old completed redeems (>90 days)
    DELETE FROM redeems 
    WHERE status = 'completed' 
    AND completed_at < NOW() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql;

-- ==========================================
-- INITIAL DATA (OPTIONAL)
-- ==========================================
-- Uncomment if you want to add test data

-- INSERT INTO users (user_id, balance, total_topup, total_spent) VALUES
-- (999999, 0, 0, 0);

-- ==========================================
-- VERIFICATION QUERIES
-- ==========================================
-- Run these to verify your setup

-- Check tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('users', 'topups', 'redeems');

-- Check indexes
SELECT indexname, tablename 
FROM pg_indexes 
WHERE schemaname = 'public' 
AND tablename IN ('users', 'topups', 'redeems');

-- Test statistics function
SELECT * FROM get_database_stats();

-- ==========================================
-- NOTES
-- ==========================================
-- 1. Save your Supabase URL and service_role key
-- 2. Add them to your .env file:
--    SUPABASE_URL=https://your-project.supabase.co
--    SUPABASE_KEY=your-service-role-key
-- 3. Never commit your service_role key to version control!
-- 4. Use service_role key (not anon key) for server-side operations
-- 5. RLS is enabled but service_role bypasses it automatically