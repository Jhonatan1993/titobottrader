"""Isolated administrative app for the read-only Telegram monitor.

Importing this module does not start or import the trading engine.
"""
import datetime
import os
from pathlib import Path

from flask import Flask, g, jsonify, redirect, request
from itsdangerous import BadSignature
from werkzeug.middleware.proxy_fix import ProxyFix

from .auth_manager import get_user_by_id
from .security_guard import SECRET_FILE
from .telegram_monitor_web import telegram_monitor_web


def _main_session_secret():
    """Read the existing dashboard secret without generating or changing it."""
    env_key = os.environ.get("FLASK_SECRET_KEY", "").strip()
    if len(env_key) >= 32:
        return env_key
    try:
        key = Path(SECRET_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        raise RuntimeError("Dashboard session key is unavailable") from None
    if len(key) < 32:
        raise RuntimeError("Dashboard session key is invalid")
    return key


def create_app(secret_key=None, main_session_key=None):
    secret = secret_key or os.environ.get("TELEGRAM_ADMIN_SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("TELEGRAM_ADMIN_SECRET_KEY must contain at least 32 characters")

    main_key = main_session_key if main_session_key is not None else _main_session_secret()
    if len(main_key) < 32:
        raise RuntimeError("Dashboard session key is invalid")

    app = Flask(__name__)
    app.secret_key = secret
    app.config.update(
        SESSION_COOKIE_NAME="titobot_telegram_admin",
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        MAX_CONTENT_LENGTH=8192,
    )

    # Flask's session serializer must match the main dashboard's defaults.
    # Never use this verifier to issue or modify the main dashboard cookie.
    main_app = Flask("titobot_main_session_verifier")
    main_app.secret_key = main_key
    main_app.permanent_session_lifetime = datetime.timedelta(days=7)
    serializer = main_app.session_interface.get_signing_serializer(main_app)

    # The application must bind only to loopback behind a trusted proxy that
    # replaces X-Forwarded-Proto.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
    app.register_blueprint(telegram_monitor_web)

    @app.before_request
    def identify_user():
        if not request.is_secure:
            return "HTTPS requerido", 403
        if request.endpoint == "static":
            return None

        cookie = request.cookies.get("session", "")
        try:
            data = serializer.loads(cookie, max_age=7 * 24 * 60 * 60)
            user_id = data.get("user_id") if isinstance(data, dict) else None
        except (BadSignature, TypeError, ValueError):
            user_id = None

        if not user_id:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Inicia sesión en TitoBot."}), 401
            return redirect("/login")
        try:
            user = get_user_by_id(user_id)
        except Exception:
            return "No se pudo verificar la cuenta", 503
        if not user or user.get("role") != "admin" or user.get("status") != "active":
            return "Acceso denegado", 403
        g.current_user = user
        return None

    @app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        return response

    @app.get("/telegram-admin/login")
    def old_login():
        return redirect("/admin/telegram")

    return app
