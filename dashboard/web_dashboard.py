import os
import sys
import threading
import time
import datetime
import re
from flask import Flask, render_template, jsonify, request, Response, redirect, url_for, session, g
from functools import wraps

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from execution.trading_engine import RealTimeTradingEngine
from dashboard.auth_manager import (
    init_auth_db, authenticate, get_user_by_id, list_users,
    create_user, update_user, set_user_status, change_user_password,
    delete_user, get_auth_metrics, update_database_url
)

from dashboard.security_guard import (
    get_secure_session_key, RATE_LIMITER, log_security_event, mask_secret, harden_data_files
)

# Instancia global del motor de trading en tiempo real
ENGINE = RealTimeTradingEngine(max_open_positions=5)

# Inicializar base de datos de autenticación y blindar permisos de almacenamiento
init_auth_db()
harden_data_files()

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.secret_key = get_secure_session_key()
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=7)

def get_client_ip():
    """Obtiene la IP real del cliente considerando proxies inversos estándar."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"

@app.after_request
def add_security_headers(response):
    """Aplica cabeceras de seguridad HTTP de nivel bancario/institucional (OWASP Best Practices)."""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self';"
    )
    return response

@app.before_request
def check_authentication():
    client_ip = get_client_ip()
    
    # Rutas públicas sin autenticación requerida
    if request.path.startswith("/static") or request.path in ("/login", "/logout"):
        return None
        
    user_id = session.get("user_id")
    if not user_id:
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "UNAUTHORIZED", "redirect": "/login"}), 401
        return redirect(url_for("login"))
        
    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "UNAUTHORIZED", "redirect": "/login"}), 401
        return redirect(url_for("login"))
        
    # Restricción inmediata si el usuario no ha pagado o está suspendido
    if user.get("status") == "restricted":
        session.clear()
        log_security_event("SESSION_REVOKED_RESTRICTED", "Sesión revocada por cuenta en mora", ip=client_ip, username=user.get("username"))
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "ACCOUNT_RESTRICTED", "redirect": "/login?error=restricted"}), 403
        return redirect(url_for("login", error="restricted"))
        
    if user.get("status") == "suspended":
        session.clear()
        log_security_event("SESSION_REVOKED_SUSPENDED", "Sesión revocada por cuenta suspendida", ip=client_ip, username=user.get("username"))
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "ACCOUNT_SUSPENDED", "redirect": "/login?error=suspended"}), 403
        return redirect(url_for("login", error="suspended"))
        
    # Control de acceso exclusivo para el panel de administración y control financiero crítico
    admin_critical_routes = (
        "/admin",
        "/api/admin",
        "/api/control/get-broker-keys",
        "/api/control/set-broker-keys",
        "/api/control/add-broker",
        "/api/control/reset",
        "/api/control/emergency-close",
        "/api/control/switch-env",
        "/api/control/set-execution-environment",
        "/api/control/transfer-vault",
        "/api/control/set-target",
        "/api/control/set-mode",
        "/api/control/recalibrate",
        "/api/control/clear-cooldown",
        "/api/control/toggle",
        "/api/trade/",
        "/api/news/evaluate"
    )
    if any(request.path.startswith(prefix) for prefix in admin_critical_routes):
        if user.get("role") != "admin":
            log_security_event("UNAUTHORIZED_ADMIN_ACTION", f"Intento de acceso denegado a ruta admin: {request.path}", ip=client_ip, username=user.get("username"))
            if request.path.startswith("/api/"):
                return jsonify({
                    "success": False, 
                    "error": "FORBIDDEN", 
                    "message": "Operación protegida: Se requieren permisos de Administrador para modificar la operativa o ver credenciales"
                }), 403
            return redirect(url_for("login", error="admin_required"))
            
    g.current_user = user
    return None

@app.route("/login", methods=["GET", "POST"])
def login():
    client_ip = get_client_ip()
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        # 1. Protección contra Ataques de Fuerza Bruta / Credential Stuffing
        is_locked, remaining_sec = RATE_LIMITER.is_locked(client_ip, username)
        if is_locked:
            minutes = max(1, remaining_sec // 60)
            log_security_event("LOGIN_LOCKOUT_ATTEMPT", f"Intento rechazado por bloqueo temporal ({minutes}m)", ip=client_ip, username=username)
            return render_template("login.html", error="rate_limit", lockout_minutes=minutes)
            
        # 2. Autenticación Criptográfica
        user, err = authenticate(username, password)
        if user and not err:
            RATE_LIMITER.record_success(client_ip, username)
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["user_role"] = user["role"]
            session.permanent = True
            log_security_event("LOGIN_SUCCESS", f"Sesión iniciada rol={user['role']}", ip=client_ip, username=username)
            return redirect(url_for("index"))
            
        # Registrar intento fallido
        is_now_locked, lock_sec = RATE_LIMITER.record_failure(client_ip, username)
        log_security_event("LOGIN_FAILED", f"Intento fallido (motivo={err or 'INVALID'})", ip=client_ip, username=username)
        
        if is_now_locked:
            return render_template("login.html", error="rate_limit", lockout_minutes=max(1, lock_sec // 60))
            
        if err == "ACCOUNT_RESTRICTED":
            return redirect(url_for("login", error="restricted"))
        elif err == "ACCOUNT_SUSPENDED":
            return redirect(url_for("login", error="suspended"))
        else:
            return redirect(url_for("login", error="invalid"))
            
    error = request.args.get("error")
    msg = request.args.get("msg")
    return render_template("login.html", error=error, msg=msg)

@app.route("/logout")
def logout():
    u = session.get("username", "ANONYMOUS")
    log_security_event("LOGOUT", "Cierre de sesión", ip=get_client_ip(), username=u)
    session.clear()
    return redirect(url_for("login", msg="logged_out"))

@app.route("/admin")
def admin_panel():
    return render_template("admin.html", current_user=getattr(g, "current_user", {}))

# ==================== ENDPOINTS API DE ADMINISTRACIÓN ====================
@app.route("/api/admin/users", methods=["GET"])
def api_admin_list_users():
    status = request.args.get("status", "all")
    search = request.args.get("search", "")
    users = list_users(search=search, status_filter=status)
    metrics = get_auth_metrics()
    return jsonify({"success": True, "users": users, "metrics": metrics})

@app.route("/api/admin/users", methods=["POST"])
def api_admin_create_user():
    data = request.get_json(silent=True) or {}
    uid, err = create_user(
        username=data.get("username"),
        password=data.get("password"),
        full_name=data.get("full_name"),
        email=data.get("email", ""),
        role=data.get("role", "user"),
        status=data.get("status", "active"),
        plan=data.get("plan", "Mensual VIP"),
        expires_at=data.get("expires_at", ""),
        notes=data.get("notes", "")
    )
    if err:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "user_id": uid})

@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
def api_admin_update_user(user_id):
    data = request.get_json(silent=True) or {}
    ok, err = update_user(
        user_id=user_id,
        full_name=data.get("full_name", ""),
        email=data.get("email", ""),
        role=data.get("role", "user"),
        status=data.get("status", "active"),
        plan=data.get("plan", "Mensual VIP"),
        expires_at=data.get("expires_at", ""),
        notes=data.get("notes", "")
    )
    if not ok:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True})

@app.route("/api/admin/users/<int:user_id>/status", methods=["POST"])
def api_admin_set_status(user_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    ok, err = set_user_status(user_id, new_status)
    if not ok:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "status": new_status})

@app.route("/api/admin/users/<int:user_id>/password", methods=["POST"])
def api_admin_change_password(user_id):
    data = request.get_json(silent=True) or {}
    pwd = data.get("password") or data.get("new_password")
    ok, err = change_user_password(user_id, pwd)
    if not ok:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True})

@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
def api_admin_delete_user(user_id):
    current_admin_id = session.get("user_id")
    ok, err = delete_user(user_id, requesting_admin_id=current_admin_id)
    if not ok:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True})

@app.route("/api/admin/set-database-url", methods=["POST"])
def api_admin_set_database_url():
    data = request.get_json(silent=True) or {}
    db_url = data.get("database_url", "")
    res = update_database_url(db_url)
    if res.get("success"):
        return jsonify(res)
    return jsonify(res), 400

@app.route("/")
def index():
    return render_template("index.html", current_user=getattr(g, "current_user", {}))

@app.route("/api/state", methods=["GET"])
def get_state():
    return jsonify(ENGINE.get_full_state())

@app.route("/api/control/toggle", methods=["POST"])
def toggle_state():
    ENGINE.is_running = not ENGINE.is_running
    if ENGINE.is_running:
        if ENGINE.target_reached or ENGINE.loss_limit_reached:
            ENGINE.initial_balance = ENGINE.get_total_equity()
            ENGINE.target_reached = False
            ENGINE.loss_limit_reached = False
            ENGINE.agent._add_thought(f"🚀 Iniciando nueva sesión con capital base de ${ENGINE.initial_balance:,.2f} USD.", "INFO", icon="🎯")
        else:
            ENGINE.agent._add_thought("Estado del Agente cambiado a: OPERANDO EN VIVO", "INFO", icon="⚙️")
    else:
        ENGINE.agent._add_thought("Estado del Agente cambiado a: EN PAUSA", "INFO", icon="⏸️")
    return jsonify({"success": True, "is_running": ENGINE.is_running, "target_reached": ENGINE.target_reached})

@app.route("/api/control/emergency-close", methods=["POST"])
def emergency_close():
    ENGINE.emergency_close_all()
    return jsonify({"success": True})

@app.route("/api/control/reset", methods=["POST"])
def reset_account():
    ENGINE.reset_account()
    return jsonify({"success": True})

@app.route("/api/control/set-target", methods=["POST"])
def set_profit_target():
    data = request.get_json(silent=True) or {}
    target_amount = float(data.get("amount") or data.get("target") or 500.0)
    target_enabled = bool(data.get("enabled", True))
    
    raw_loss = data.get("max_loss")
    try:
        max_loss_amount = max(0.0, float(raw_loss)) if raw_loss is not None and str(raw_loss).strip() != "" else 0.0
    except (ValueError, TypeError):
        max_loss_amount = 0.0
        
    loss_enabled = bool(data.get("loss_enabled", True))
    broker = data.get("broker")
    
    ENGINE.set_risk_limits(target_amount, max_loss_amount, target_enabled, loss_enabled, broker)
    return jsonify({
        "success": True, 
        "target_amount": ENGINE.profit_target_amount, 
        "max_loss_amount": ENGINE.max_loss_amount,
        "profit_target_enabled": ENGINE.profit_target_enabled,
        "max_loss_enabled": ENGINE.max_loss_enabled
    })

@app.route("/api/control/set-mode", methods=["POST"])
def set_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "UNIFIED_TRADFI_CRYPTO")
    ENGINE.set_operating_mode(mode)
    return jsonify({"success": True, "mode": ENGINE.operating_mode})

@app.route("/api/control/set-active-broker", methods=["POST"])
def set_active_broker():
    data = request.get_json(silent=True) or {}
    broker = data.get("broker", "BINANCE")
    res = ENGINE.set_active_broker(broker)
    return jsonify(res)

@app.route("/api/control/clear-cooldown", methods=["POST"])
def clear_cooldown():
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol")
    ENGINE.clear_cooldown(symbol)
    return jsonify({"success": True, "symbol": symbol})

@app.route("/api/control/recalibrate", methods=["POST"])
def recalibrate():
    ENGINE.agent.update_learning_from_disk()
    return jsonify({"success": True, "learning": ENGINE.agent.learner.get_learning_summary()})

@app.route("/api/control/get-broker-keys", methods=["GET"])
def get_broker_keys():
    cfg = ENGINE.broker_config
    alpaca = cfg.get("alpaca", {})
    binance = cfg.get("binance", {})
    return jsonify({
        "alpaca_key": alpaca.get("api_key", ""),
        "alpaca_secret": alpaca.get("secret_key", ""),
        "binance_key": binance.get("api_key", ""),
        "binance_secret": binance.get("secret_key", "")
    })

@app.route("/api/control/set-broker-keys", methods=["POST"])
def set_broker_keys():
    data = request.get_json(silent=True) or {}
    alpaca_key = data.get("alpaca_key", "").strip()
    alpaca_secret = data.get("alpaca_secret", "").strip()
    binance_key = data.get("binance_key", "").strip()
    binance_secret = data.get("binance_secret", "").strip()
    
    ENGINE.update_broker_keys(alpaca_key, alpaca_secret, binance_key, binance_secret)
    return jsonify({"success": True})

@app.route("/api/control/add-broker", methods=["POST"])
def add_broker():
    data = request.get_json(silent=True) or {}
    broker_id = data.get("broker_type") or data.get("broker") or "BYBIT"
    api_key = data.get("api_key", "").strip()
    secret_key = data.get("secret_key", "").strip()
    initial_balance = float(data.get("initial_balance", 1000.0))
    res = ENGINE.add_broker(broker_id, api_key=api_key, secret_key=secret_key, initial_balance=initial_balance)
    return jsonify(res)

@app.route("/api/control/set-execution-environment", methods=["POST"])
def set_execution_environment():
    data = request.get_json(silent=True) or {}
    env = data.get("environment", "PAPER")
    paper_balance = data.get("paper_balance")
    broker = data.get("broker")
    res = ENGINE.set_execution_environment(env, paper_balance, broker)
    return jsonify(res)

@app.route("/api/control/transfer-vault", methods=["POST"])
def transfer_vault():
    data = request.get_json(silent=True) or {}
    broker = data.get("broker")
    amount = data.get("amount")
    if amount is not None and amount != "ALL":
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            amount = None
    else:
        amount = None
    res = ENGINE.transfer_vault_to_capital(broker, amount)
    return jsonify(res)

@app.route("/api/trade/sell", methods=["POST"])
def manual_sell():
    data = request.get_json(silent=True) or {}
    symbol = data.get("symbol")
    if not symbol:
        return jsonify({"success": False, "error": "Símbolo no proporcionado"}), 400
    
    result = ENGINE.close_position(symbol, reason="Venta manual autorizada por el usuario")
    if result:
        return jsonify({"success": True, "trade": result})
    return jsonify({"success": False, "error": "Posición no encontrada"}), 404

@app.route("/api/trade/harvest-vault", methods=["POST"])
def harvest_vault():
    data = request.get_json(silent=True) or {}
    broker = data.get("broker") or ENGINE.active_broker
    result = ENGINE.harvest_vault_profits(broker)
    return jsonify(result)

@app.route("/api/news/evaluate", methods=["POST"])
def evaluate_news():
    data = request.get_json(silent=True) or {}
    headline = data.get("headline", "").strip()
    if not headline:
        return jsonify({"success": False, "error": "Titular vacío"}), 400
    res = ENGINE.agent.sentiment_shield.add_headline(headline, source=data.get("source", "Usuario"))
    return jsonify({"success": True, "evaluation": res, "shield": ENGINE.agent.sentiment_shield.get_shield_summary()})

@app.route("/api/candles/<symbol>", methods=["GET"])
def get_symbol_candles(symbol: str):
    timeframe = request.args.get("timeframe", "1m")
    limit = int(request.args.get("limit", 100))
    candles_data = ENGINE.get_asset_candles(symbol, timeframe=timeframe, limit=limit)
    return jsonify(candles_data)

@app.route("/api/export/trades-csv", methods=["GET"])
def export_trades_csv():
    broker = request.args.get("broker")
    mode = request.args.get("mode", "complete")
    clean_broker = re.sub(r'[^a-zA-Z0-9_-]', '', broker or "TODOS").lower()
    clean_mode = re.sub(r'[^a-zA-Z0-9_-]', '', mode or "complete").lower()
    csv_data = ENGINE.journal.export_trades_csv(broker=broker, mode=clean_mode)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"historico_transacciones_{clean_broker}_{clean_mode}_{timestamp}.csv"
    
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/api/export/daily-summary", methods=["GET"])
def export_daily_summary():
    broker = request.args.get("broker")
    clean_broker = re.sub(r'[^a-zA-Z0-9_-]', '', broker or "ALL").upper()
    summary = ENGINE.journal.get_daily_summary(broker=broker)
    return jsonify({
        "success": True,
        "broker": clean_broker,
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_days": len(summary),
        "daily_history": summary
    })

@app.route("/api/export/trades-json", methods=["GET"])
def export_trades_json():
    import json
    broker = request.args.get("broker")
    clean_broker = re.sub(r'[^a-zA-Z0-9_-]', '', broker or "TODOS").lower()
    summary = ENGINE.journal.get_daily_summary(broker=broker)
    payload = {
        "metadata": {
            "title": "Histórico de Transacciones por Día",
            "broker": clean_broker.upper(),
            "exported_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_days": len(summary),
            "total_trades": sum(d["total_trades"] for d in summary)
        },
        "days": summary
    }
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"historico_transacciones_{clean_broker}_{timestamp}.json"
    
    return Response(
        json.dumps(payload, indent=2, ensure_ascii=False),
        mimetype="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/api/export/trades-xlsx", methods=["GET"])
def export_trades_xlsx():
    from trade_journal.report_exporter import generate_trades_xlsx
    broker = request.args.get("broker")
    clean_broker = re.sub(r'[^a-zA-Z0-9_-]', '', broker or "TODOS").lower()
    xlsx_bytes = generate_trades_xlsx(ENGINE.journal, broker=broker)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reporte_transacciones_{clean_broker}_{timestamp}.xlsx"
    
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/api/export/trades-pdf", methods=["GET"])
def export_trades_pdf():
    from trade_journal.report_exporter import generate_trades_pdf
    broker = request.args.get("broker")
    clean_broker = re.sub(r'[^a-zA-Z0-9_-]', '', broker or "TODOS").lower()
    pdf_bytes = generate_trades_pdf(ENGINE.journal, broker=broker)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reporte_transacciones_{clean_broker}_{timestamp}.pdf"
    
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

def start_trading_loop():
    """
    Bucle en segundo plano que ejecuta un ciclo de mercado y análisis de IA cada segundo.
    """
    while True:
        try:
            ENGINE.step()
        except Exception as e:
            print(f"Error en bucle de trading: {e}")
        time.sleep(1.2)

# Iniciar el hilo del motor de trading automáticamente al cargar el módulo
trading_thread = threading.Thread(target=start_trading_loop, daemon=True)
trading_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
