from flask import Flask, request, jsonify
import asyncio
import threading
import traceback
from payment_gateway import parse_webhook_notification, format_rupiah
from database import get_topup_by_order_id, update_topup_status, add_balance
import config
import discord

app = Flask(__name__)

# Reference ke bot Discord
discord_bot = None

def set_discord_bot(bot):
    """Set reference ke Discord bot untuk kirim notifikasi"""
    global discord_bot
    discord_bot = bot

@app.route('/webhook/midtrans', methods=['POST'])
def midtrans_webhook():
    """
    Endpoint untuk menerima notifikasi dari Midtrans
    URL ini harus didaftarkan di Midtrans Dashboard
    """
    try:
        notification = request.get_json()

        if not notification:
            print("⚠️ Webhook received with no JSON data")
            return jsonify({'status': 'error', 'message': 'No JSON data received'}), 400

        print(f"📥 Webhook received: {notification.get('order_id', 'unknown')}")

        # Parse dan validasi webhook
        parsed = parse_webhook_notification(notification, config.MIDTRANS_SERVER_KEY)

        if not parsed['valid']:
            print(f"❌ Invalid webhook: {parsed.get('error', 'unknown error')}")
            return jsonify({'status': 'error', 'message': parsed['error']}), 400

        order_id = parsed['order_id']
        status = parsed['status']
        transaction_status = parsed.get('transaction_status', 'unknown')

        print(f"✅ Valid webhook for {order_id}: {transaction_status} -> {status}")

        # Ambil data topup dari database
        topup = get_topup_by_order_id(order_id)

        if not topup:
            print(f"⚠️ Order {order_id} not found in database")
            return jsonify({'status': 'error', 'message': 'Order not found'}), 404

        # Check if already processed
        if topup['status'] == 'success' and status == 'success':
            print(f"ℹ️ Order {order_id} already processed successfully")
            return jsonify({'status': 'success', 'message': 'Already processed'}), 200

        # Update status di database
        try:
            update_topup_status(order_id, status, str(notification))
            print(f"✅ Database updated for {order_id}: {status}")
        except Exception as e:
            print(f"❌ Failed to update database: {e}")
            print(traceback.format_exc())
            return jsonify({'status': 'error', 'message': 'Database update failed'}), 500

        # Jika pembayaran sukses, tambah saldo user
        if status == 'success' and topup['status'] != 'success':
            user_id = topup['user_id']
            amount = topup['amount']

            try:
                # Tambah saldo
                new_balance = add_balance(user_id, amount)
                print(f"✅ Balance added: User {user_id} +{amount} (new: {new_balance})")

                # Kirim notifikasi ke user via DM (jika bot sudah ready)
                if discord_bot and discord_bot.is_ready():
                    try:
                        asyncio.run_coroutine_threadsafe(
                            send_payment_success_dm(user_id, amount, new_balance, order_id),
                            discord_bot.loop
                        )
                        print(f"✅ Notification sent to user {user_id}")
                    except Exception as e:
                        print(f"⚠️ Failed to send notification: {e}")
                else:
                    print(f"⚠️ Bot not ready, notification skipped for user {user_id}")

            except Exception as e:
                print(f"❌ Failed to add balance: {e}")
                print(traceback.format_exc())
                return jsonify({'status': 'error', 'message': 'Failed to add balance'}), 500

        elif status == 'failed':
            print(f"ℹ️ Payment failed for {order_id}")
            # Optional: Notify user about failed payment
            if discord_bot and discord_bot.is_ready():
                try:
                    asyncio.run_coroutine_threadsafe(
                        send_payment_failed_dm(topup['user_id'], order_id),
                        discord_bot.loop
                    )
                except:
                    pass

        elif status == 'expired':
            print(f"ℹ️ Payment expired for {order_id}")

        return jsonify({'status': 'success', 'message': 'Webhook processed'}), 200

    except Exception as e:
        print(f"❌ Critical webhook error: {e}")
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

async def send_payment_success_dm(user_id: int, amount: int, new_balance: int, order_id: str):
    """Kirim DM ke user saat payment berhasil"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            user = await discord_bot.fetch_user(user_id)

            if user:
                embed = discord.Embed(
                    title="✅ Pembayaran Berhasil!",
                    description=f"Top up sebesar **{format_rupiah(amount)}** telah berhasil diproses.",
                    color=0x2ecc71
                )
                embed.add_field(
                    name="🆔 Order ID",
                    value=f"`{order_id}`",
                    inline=False
                )
                embed.add_field(
                    name="💰 Jumlah Top Up",
                    value=format_rupiah(amount),
                    inline=True
                )
                embed.add_field(
                    name="💳 Saldo Baru",
                    value=format_rupiah(new_balance),
                    inline=True
                )
                embed.add_field(
                    name="💡 Langkah Selanjutnya",
                    value="Anda sudah bisa memulai redeem code! Kembali ke server dan klik tombol **🎮 Mulai Redeem**.",
                    inline=False
                )
                embed.set_footer(
                    text="Terima kasih telah melakukan top up!",
                    icon_url=discord_bot.user.display_avatar.url if discord_bot.user.display_avatar else None
                )

                await user.send(embed=embed)
                print(f"✅ Success notification sent to user {user_id}")
                return
                
        except discord.Forbidden:
            print(f"⚠️ Cannot send DM to user {user_id} (DM closed)")
            return  # Don't retry if DM is closed
            
        except discord.HTTPException as e:
            if attempt < max_retries - 1:
                print(f"⚠️ HTTP error sending DM (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            else:
                print(f"❌ Failed to send DM after {max_retries} attempts: {e}")
                
        except Exception as e:
            print(f"❌ Error sending success DM to user {user_id}: {e}")
            print(traceback.format_exc())
            return

async def send_payment_failed_dm(user_id: int, order_id: str):
    """Kirim DM ke user saat payment gagal"""
    try:
        user = await discord_bot.fetch_user(user_id)

        if user:
            embed = discord.Embed(
                title="❌ Pembayaran Gagal",
                description="Maaf, pembayaran Anda tidak dapat diproses.",
                color=0xe74c3c
            )
            embed.add_field(
                name="🆔 Order ID",
                value=f"`{order_id}`",
                inline=False
            )
            embed.add_field(
                name="💡 Apa yang harus dilakukan?",
                value="• Pastikan saldo e-wallet Anda mencukupi\n"
                      "• Coba lagi dengan membuat transaksi baru\n"
                      "• Hubungi admin jika masalah berlanjut",
                inline=False
            )
            embed.set_footer(text="Hubungi admin jika butuh bantuan")

            await user.send(embed=embed)
            
    except discord.Forbidden:
        print(f"⚠️ Cannot send DM to user {user_id} (DM closed)")
    except Exception as e:
        print(f"⚠️ Error sending failed DM to user {user_id}: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint untuk monitoring"""
    bot_status = "ready" if discord_bot and discord_bot.is_ready() else "not_ready"
    
    return jsonify({
        'status': 'healthy',
        'bot_status': bot_status,
        'webhook_enabled': True
    }), 200

@app.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint untuk debugging"""
    return jsonify({
        'message': 'Webhook server is running',
        'port': config.WEBHOOK_PORT,
        'bot_connected': discord_bot is not None,
        'bot_ready': discord_bot.is_ready() if discord_bot else False
    }), 200

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'status': 'error', 'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    print(f"❌ Internal server error: {error}")
    print(traceback.format_exc())
    return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

def run_webhook_server():
    """Jalankan webhook server di thread terpisah"""
    try:
        print(f"🚀 Starting webhook server on port {config.WEBHOOK_PORT}...")
        
        # Production-ready settings
        app.run(
            host='0.0.0.0',
            port=config.WEBHOOK_PORT,
            debug=False,
            use_reloader=False,
            threaded=True
        )
    except Exception as e:
        print(f"❌ Failed to start webhook server: {e}")
        print(traceback.format_exc())

def start_webhook_server():
    """Start webhook server di background thread"""
    try:
        webhook_thread = threading.Thread(target=run_webhook_server, daemon=True)
        webhook_thread.start()
        print(f"✅ Webhook server thread started on port {config.WEBHOOK_PORT}")
        
        # Note untuk deployment
        print(f"📝 Note: Untuk production, pastikan port {config.WEBHOOK_PORT} bisa diakses dari internet")
        print(f"📝 Daftarkan URL webhook di Midtrans Dashboard: http://your-domain:{config.WEBHOOK_PORT}/webhook/midtrans")
        
    except Exception as e:
        print(f"❌ Failed to start webhook thread: {e}")
        print(traceback.format_exc())