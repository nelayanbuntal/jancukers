from flask import Flask, request, jsonify
import asyncio
import threading
from payment_gateway import parse_webhook_notification
from database import get_topup_by_order_id, update_topup_status, add_balance, get_or_create_user
import config

app = Flask(__name__)

# Reference ke bot Discord (akan di-set dari bot.py)
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
            return jsonify({'status': 'error', 'message': 'No JSON data'}), 400

        # Parse dan validasi webhook
        parsed = parse_webhook_notification(notification, config.MIDTRANS_SERVER_KEY)

        if not parsed['valid']:
            return jsonify({'status': 'error', 'message': parsed['error']}), 400

        order_id = parsed['order_id']
        status = parsed['status']

        # Ambil data topup dari database
        topup = get_topup_by_order_id(order_id)

        if not topup:
            return jsonify({'status': 'error', 'message': 'Order not found'}), 404

        # Update status di database
        update_topup_status(order_id, status, str(notification))

        # Jika pembayaran sukses, tambah saldo user
        if status == 'success' and topup['status'] != 'success':  # cek agar tidak double credit
            user_id = topup['user_id']
            amount = topup['amount']

            # Tambah saldo
            new_balance = add_balance(user_id, amount)

            # Kirim notifikasi ke user via DM
            if discord_bot:
                asyncio.run_coroutine_threadsafe(
                    send_payment_success_dm(user_id, amount, new_balance, order_id),
                    discord_bot.loop
                )

            print(f"✅ Payment success: {order_id} - User {user_id} +Rp {amount:,}")

        return jsonify({'status': 'success'}), 200

    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

async def send_payment_success_dm(user_id: int, amount: int, new_balance: int, order_id: str):
    """Kirim DM ke user saat payment berhasil"""
    try:
        user = await discord_bot.fetch_user(user_id)

        if user:
            import discord
            embed = discord.Embed(
                title="✅ Pembayaran Berhasil!",
                description=f"Topup sebesar **Rp {amount:,}** telah berhasil diproses.",
                color=0x00ff00
            )
            embed.add_field(name="Order ID", value=order_id, inline=False)
            embed.add_field(name="Saldo Baru", value=f"Rp {new_balance:,}", inline=False)
            embed.set_footer(text="Terima kasih telah melakukan topup!")

            await user.send(embed=embed)
    except Exception as e:
        print(f"❌ Error sending DM: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

def run_webhook_server():
    """Jalankan webhook server di thread terpisah"""
    app.run(host='0.0.0.0', port=config.WEBHOOK_PORT, debug=False, use_reloader=False)

def start_webhook_server():
    """Start webhook server di background thread"""
    webhook_thread = threading.Thread(target=run_webhook_server, daemon=True)
    webhook_thread.start()
    print(f"✅ Webhook server started on port {config.WEBHOOK_PORT}")
