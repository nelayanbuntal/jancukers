"""
Test script untuk validasi Midtrans integration
Jalankan: python test_midtrans.py
"""

import sys
from payment_gateway import MidtransPayment, generate_order_id, format_rupiah
import config

def test_connection():
    """Test koneksi ke Midtrans API"""
    print("=" * 50)
    print("🧪 TEST 1: Koneksi Midtrans")
    print("=" * 50)

    try:
        midtrans = MidtransPayment(
            server_key=config.MIDTRANS_SERVER_KEY,
            is_production=config.MIDTRANS_IS_PRODUCTION
        )

        env = "PRODUCTION" if config.MIDTRANS_IS_PRODUCTION else "SANDBOX"
        print(f"✅ Midtrans client initialized")
        print(f"   Environment: {env}")
        print(f"   Base URL: {midtrans.base_url}")

        return midtrans

    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_create_qris(midtrans):
    """Test pembuatan transaksi QRIS"""
    print("\n" + "=" * 50)
    print("🧪 TEST 2: Create QRIS Transaction")
    print("=" * 50)

    try:
        # Generate order ID test
        order_id = generate_order_id(999999)
        print(f"📋 Order ID: {order_id}")

        # Create transaction
        amount = 10000
        print(f"💰 Amount: {format_rupiah(amount)}")
        print("⏳ Creating transaction...")

        customer = {
            "first_name": "Test User",
            "email": "test@example.com",
            "phone": "08123456789"
        }

        transaction = midtrans.create_qris_transaction(
            order_id=order_id,
            amount=amount,
            customer_details=customer
        )

        if not transaction:
            print("❌ Failed to create transaction")
            return None

        print("✅ Transaction created successfully!")
        print(f"   Status: {transaction.get('transaction_status')}")
        print(f"   Order ID: {transaction.get('order_id')}")

        # Check QR URL
        actions = transaction.get('actions', [])
        if actions:
            qr_url = actions[0].get('url', '')
            print(f"   QR URL: {qr_url[:50]}...")

        return order_id

    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_check_status(midtrans, order_id):
    """Test check transaction status"""
    print("\n" + "=" * 50)
    print("🧪 TEST 3: Check Transaction Status")
    print("=" * 50)

    try:
        if not order_id:
            print("⚠️ Skipped - No order ID from previous test")
            return

        print(f"📋 Checking status for: {order_id}")
        print("⏳ Fetching status...")

        status = midtrans.check_transaction_status(order_id)

        if not status:
            print("❌ Failed to check status")
            return

        print("✅ Status retrieved successfully!")
        print(f"   Transaction Status: {status.get('transaction_status')}")
        print(f"   Order ID: {status.get('order_id')}")
        gross_amount_str = status.get('gross_amount', '0')
        gross_amount = int(float(gross_amount_str))  # ubah string ke float dulu, baru ke int
        print(f"   Gross Amount: {format_rupiah(gross_amount)}")

        print(f"   Payment Type: {status.get('payment_type')}")

    except Exception as e:
        print(f"❌ Error: {e}")

def test_database():
    """Test database operations"""
    print("\n" + "=" * 50)
    print("🧪 TEST 4: Database Operations")
    print("=" * 50)

    try:
        from database import init_database, get_balance, add_balance, deduct_balance

        print("⏳ Initializing database...")
        init_database()
        print("✅ Database initialized")

        # Test user operations
        test_user_id = 999999
        print(f"\n📊 Testing with user ID: {test_user_id}")

        # Get initial balance
        balance = get_balance(test_user_id)
        print(f"   Initial balance: {format_rupiah(balance)}")

        # Add balance
        print("   Adding Rp 10,000...")
        new_balance = add_balance(test_user_id, 10000)
        print(f"   New balance: {format_rupiah(new_balance)}")

        # Deduct balance
        print("   Deducting Rp 5,000...")
        success = deduct_balance(test_user_id, 5000)
        if success:
            final_balance = get_balance(test_user_id)
            print(f"   Final balance: {format_rupiah(final_balance)}")
        else:
            print("   ❌ Failed to deduct balance")

        print("\n✅ All database operations successful!")

    except Exception as e:
        print(f"❌ Error: {e}")

def test_config():
    """Test configuration"""
    print("\n" + "=" * 50)
    print("🧪 TEST 5: Configuration Check")
    print("=" * 50)

    checks = {
        "Discord Token": config.DISCORD_TOKEN != 'YOUR_DISCORD_BOT_TOKEN',
        "Midtrans Key": config.MIDTRANS_SERVER_KEY != 'YOUR_MIDTRANS_SERVER_KEY',
        "Public Channel ID": config.PUBLIC_CHANNEL_ID > 0,
    }

    all_ok = True
    for check_name, check_result in checks.items():
        status = "✅" if check_result else "❌"
        print(f"{status} {check_name}: {'OK' if check_result else 'NOT SET'}")
        if not check_result:
            all_ok = False

    if all_ok:
        print("\n✅ All configuration OK!")
    else:
        print("\n⚠️ Please update your .env file with correct values!")

def main():
    """Run all tests"""
    print("\n")
    print("=" * 50)
    print("🚀 MIDTRANS & DATABASE TEST SUITE")
    print("=" * 50)
    print()

    # Test 1: Connection
    midtrans = test_connection()
    if not midtrans:
        print("\n❌ Cannot proceed without Midtrans connection")
        sys.exit(1)

    # Test 2: Create QRIS
    order_id = test_create_qris(midtrans)

    # Test 3: Check Status
    test_check_status(midtrans, order_id)

    # Test 4: Database
    test_database()

    # Test 5: Config
    test_config()

    # Summary
    print("\n" + "=" * 50)
    print("✅ TEST SUITE COMPLETED")
    print("=" * 50)
    print()
    print("Next steps:")
    print("1. Check Midtrans Dashboard for test transaction")
    print("2. Setup webhook URL in Midtrans Dashboard")
    print("3. Run: python bot.py")
    print()

if __name__ == "__main__":
    main()
