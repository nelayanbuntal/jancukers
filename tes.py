import hashlib
import json
import requests

# ==========================
# CONFIG
# ==========================

WEBHOOK_URL = "http://localhost:8000/webhook/midtrans"

# Data test
order_id = "TOPUP-1384584067319730226-20251204125129"
status_code = "200"
gross_amount = "1000000"   # harus string, bukan integer
transaction_status = "settlement"
server_key = "Mid-server-EGnfraulRARFfZbhT86J5zxi"  # isi server key sandbox kamu


# ==========================
# SIGNATURE GENERATOR
# ==========================

def generate_signature(order_id, status_code, gross_amount, server_key):
    raw = f"{order_id}{status_code}{gross_amount}{server_key}"
    signature = hashlib.sha512(raw.encode()).hexdigest()
    return signature


# ==========================
# SEND WEBHOOK
# ==========================

def send_webhook():
    signature_key = generate_signature(order_id, status_code, gross_amount, server_key)

    payload = {
        "order_id": order_id,
        "status_code": status_code,
        "gross_amount": gross_amount,
        "transaction_status": transaction_status,
        "signature_key": signature_key,
        "payment_type": "qris",
        "fraud_status": "accept",
        "transaction_id": "TEST-TX-123456"
    }

    print("📤 Sending webhook to:", WEBHOOK_URL)
    print("📦 Payload:")
    print(json.dumps(payload, indent=4))

    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)

        print("\n📥 Response:")
        print("Status:", response.status_code)
        print("Body:", response.text)

    except Exception as e:
        print("❌ Error sending webhook:", e)


if __name__ == "__main__":
    send_webhook()
