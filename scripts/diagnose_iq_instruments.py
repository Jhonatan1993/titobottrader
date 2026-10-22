#!/usr/bin/env python3
import sys
import os
import json
import time
import ssl
import websocket

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.broker_config import load_broker_config

def diagnose():
    cfg = load_broker_config()
    ssid = cfg.get("iqoption", {}).get("ssid", "")
    if not ssid:
        print("No SSID found in config.")
        return

    print(f"Connecting to IQ Option WS with SSID: {ssid[:10]}...")
    headers = [
        f"Cookie: ssid={ssid}",
        "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    ]
    ws = websocket.create_connection("wss://iqoption.com/echo/websocket", header=headers, timeout=10, sslopt={"cert_reqs": ssl.CERT_NONE})
    ws.send(json.dumps({"name": "ssid", "msg": ssid}))
    ws.send(json.dumps({"name": "setOptions", "msg": {"sendResults": True}}))

    real_balance_id = None
    currency = "COP"
    balance = 0.0
    start = time.time()
    
    # Read profile & balances
    while time.time() - start < 4:
        raw = ws.recv()
        if not raw:
            continue
        try:
            d = json.loads(raw)
            if d.get("name") == "profile":
                msg = d.get("msg", {})
                for b in msg.get("balances", []):
                    if b.get("type") == 1: # Real
                        real_balance_id = b.get("id")
                        balance = b.get("amount", 0.0)
                        currency = b.get("currency", "COP")
                        print(f"✅ Real Balance ID: {real_balance_id} | Balance: {balance:,.2f} {currency}")
                        break
        except Exception:
            pass

    if not real_balance_id:
        print("❌ Could not get real balance ID.")
        ws.close()
        return

    # Check active open assets for Turbo and Binary
    # Try placing an order on EURJPY (active 4), EURUSD (active 1), USDCHF-OTC (78), EURUSD-OTC (76)
    test_candidates = [
        {"name": "EURUSD-OTC", "active_id": 76, "type": 3},
        {"name": "USDCHF-OTC", "active_id": 78, "type": 3},
        {"name": "EURJPY-OTC", "active_id": 79, "type": 3},
        {"name": "EURJPY-Blitz", "active_id": 4, "type": 3},
        {"name": "AUDUSD", "active_id": 99, "type": 3},
        {"name": "EURGBP", "active_id": 2, "type": 3},
        {"name": "USDCHF-OTC-Bin", "active_id": 78, "type": 1},
        {"name": "EURUSD-OTC-Bin", "active_id": 76, "type": 1},
    ]

    for cand in test_candidates:
        print(f"\n🔍 Testing asset: {cand['name']} (ID: {cand['active_id']}, Option Type: {cand['type']})...")
        now = time.time()
        rem = int(now) % 60
        add = (60 - rem) if rem <= 30 else (120 - rem)
        exp = int(now) + add

        req_id = f"test_{int(now*1000)}"
        payload = {
            "name": "sendMessage",
            "request_id": req_id,
            "msg": {
                "name": "binary-options.open-option",
                "version": "1.0",
                "body": {
                    "active_id": cand["active_id"],
                    "direction": "call",
                    "expired": exp,
                    "option_type_id": cand["type"],
                    "price": 2000.0 if currency == "COP" else 1.0,
                    "user_balance_id": real_balance_id
                }
            }
        }
        ws.send(json.dumps(payload))
        
        # Read response
        t0 = time.time()
        while time.time() - t0 < 3.5:
            r = ws.recv()
            if not r:
                continue
            try:
                data = json.loads(r)
                m_name = data.get("name")
                req = data.get("request_id")
                if req == req_id or m_name in ["option-opened", "option", "option-rejected", "rejected"]:
                    print(f"📩 RESPONSE FOR {cand['name']}: {json.dumps(data)}")
                    if data.get("name") in ["option-opened", "option"] or (isinstance(data.get("msg"), dict) and "id" in data.get("msg")):
                        print(f"🎉 SUCCESS! ORDER OPENED ON {cand['name']}! Order ID: {data.get('msg', {}).get('id')}")
                        ws.close()
                        return
                    break
            except Exception:
                pass

    ws.close()

if __name__ == "__main__":
    diagnose()
