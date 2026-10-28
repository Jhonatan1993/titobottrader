import os
from dotenv import load_dotenv

load_dotenv()

from dashboard.web_dashboard import app, ENGINE

def main():
    port = int(os.environ.get("PORT", 5050))
    host = os.environ.get("HOST", "127.0.0.1")
    print("=========================================================")
    print("🚀 INICIANDO TITOBOTTRADER - AGENTE DE TRADING AUTOMATIZADO")
    print("📈 Mercados: AAPL, TSLA, NVDA, MSFT, AMZN, GOOGL, BTC")
    print("🛡️ Gestión de Riesgo: Stop-Loss Automático & Take-Profit")
    print(f"🌐 Terminal en Vivo: http://{host}:{port}")
    print("=========================================================")
    
    # Iniciar servidor web Flask
    app.run(host=host, port=port, debug=False)

if __name__ == "__main__":
    main()
