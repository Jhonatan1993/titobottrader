import sys
import os
import socket
from dashboard.web_dashboard import app, ENGINE

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def main():
    default_port = 5050
    selected_port = 5055 if is_port_in_use(default_port) else default_port
    port = int(os.environ.get("PORT", selected_port))
    print("=========================================================")
    print("🚀 INICIANDO TITOBOTTRADER - AGENTE DE TRADING AUTOMATIZADO")
    print("📈 Mercados: AAPL, TSLA, NVDA, MSFT, AMZN, GOOGL, BTC")
    print("🛡️ Gestión de Riesgo: Stop-Loss Automático & Take-Profit")
    print(f"🌐 Terminal en Vivo: http://127.0.0.1:{port}")
    print("=========================================================")
    
    # Iniciar servidor web Flask
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    main()
