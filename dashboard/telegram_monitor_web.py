"""Admin-only web interface for the independent Telegram monitor."""
import hmac
import secrets
import subprocess
from urllib.parse import urlsplit

from flask import Blueprint, current_app, g, jsonify, make_response, render_template, request, session

from . import telegram_monitor_config as config
from .auth_manager import authenticate
from .security_guard import RATE_LIMITER, log_security_event

telegram_monitor_web = Blueprint("telegram_monitor_web", __name__)


def _admin():
    user = getattr(g, "current_user", None)
    return user if isinstance(user, dict) and user.get("role") == "admin" and user.get("status") == "active" else None


def _guard(write=False):
    user = _admin()
    if not user:
        return jsonify({"error": "Acceso exclusivo para administradores."}), 403
    if not request.is_secure or not current_app.config.get("SESSION_COOKIE_SECURE"):
        return jsonify({"error": "Esta función requiere HTTPS y cookies de sesión seguras."}), 403
    if write:
        origin = request.headers.get("Origin", "")
        try:
            parsed = urlsplit(origin)
            valid_origin = (
                parsed.scheme == "https" and parsed.netloc == request.host
                and not parsed.path and not parsed.query and not parsed.fragment
            )
        except ValueError:
            valid_origin = False
        csrf = request.headers.get("X-CSRF-Token", "")
        expected = session.get("telegram_monitor_csrf", "")
        if not valid_origin or not csrf or not expected or not hmac.compare_digest(csrf, expected):
            return jsonify({"error": "Solicitud de origen no autorizado."}), 403
    return None


def _reauthenticate(user, password):
    ip = request.remote_addr or "unknown"
    username = user.get("username", "")
    locked, _ = RATE_LIMITER.is_locked(ip, username)
    if locked:
        return False
    try:
        verified, error = authenticate(username, password)
    except Exception:
        return False
    if error or not verified or verified.get("id") != user.get("id") or verified.get("role") != "admin":
        RATE_LIMITER.record_failure(ip, username)
        return False
    RATE_LIMITER.record_success(ip, username)
    return True


@telegram_monitor_web.get("/admin/telegram")
def page():
    denied = _guard()
    if denied:
        return denied
    csrf = secrets.token_urlsafe(32)
    session["telegram_monitor_csrf"] = csrf
    response = make_response(render_template("telegram_monitor.html", csrf_token=csrf))
    response.headers["Content-Security-Policy"] = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    return response


@telegram_monitor_web.get("/api/admin/telegram-monitor/status")
def status():
    denied = _guard()
    if denied:
        return denied
    try:
        result = subprocess.run(
            ["systemctl", "is-active", config.SERVICE],
            capture_output=True, text=True, timeout=5, check=False,
        )
        state = result.stdout.strip()
        if state not in {"active", "inactive", "failed", "activating", "deactivating"}:
            state = "unknown"
    except (OSError, subprocess.SubprocessError):
        state = "unknown"
    return jsonify({"configured": config.CONFIG_PATH.is_file() and not config.CONFIG_PATH.is_symlink(), "service": state})


@telegram_monitor_web.post("/api/admin/telegram-monitor/discover")
def discover():
    denied = _guard(write=True)
    if denied:
        return denied
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("password"), str) or not isinstance(data.get("token"), str):
        return jsonify({"error": "Completa el token y la contraseña."}), 400
    if len(data["password"]) > 1024 or len(data["token"]) > 256:
        return jsonify({"error": "Datos inválidos."}), 400
    if not _reauthenticate(_admin(), data["password"]):
        return jsonify({"error": "No se pudo verificar la contraseña o la cuenta está bloqueada."}), 403
    try:
        result = config.discover_chats(data["token"].strip())
        return jsonify(result)
    except config.ConfigurationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "No se pudo consultar Telegram."}), 500


@telegram_monitor_web.post("/api/admin/telegram-monitor/configure")
def configure():
    denied = _guard(write=True)
    if denied:
        return denied
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not all(isinstance(data.get(key), str) for key in ("password", "token", "chat_id")):
        return jsonify({"error": "Completa los datos de configuración."}), 400
    if len(data["password"]) > 1024 or len(data["token"]) > 256 or len(data["chat_id"]) > 20:
        return jsonify({"error": "Datos inválidos."}), 400
    user = _admin()
    if not _reauthenticate(user, data["password"]):
        return jsonify({"error": "No se pudo verificar la contraseña o la cuenta está bloqueada."}), 403
    try:
        config.configure(data["token"].strip(), data["chat_id"])
        log_security_event("TELEGRAM_MONITOR_CONFIGURED", "Configuración del monitor actualizada.", ip=request.remote_addr or "unknown", username=user["username"])
        return jsonify({"success": True, "message": "Telegram aceptó la prueba y se reinició el monitor. Confirma que el mensaje llegó a tu chat."})
    except config.ConfigurationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "No se pudo actualizar el monitor; revisa su estado."}), 500
