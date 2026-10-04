import os
import time
import secrets
import logging
import datetime
from collections import defaultdict
from typing import Tuple, Optional

# Ruta de almacenamiento de secretos y auditoría
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
SECRET_FILE = os.path.join(DATA_DIR, ".session_secret")
AUDIT_LOG_FILE = os.path.join(DATA_DIR, "security_audit.log")

# ==================== GESTOR DE LLAVE DE SESIÓN SEGURA ====================
def get_secure_session_key() -> str:
    """
    Retorna la llave secreta para cookies de sesión.
    Si existe variable de entorno FLASK_SECRET_KEY, la utiliza.
    De lo contrario, genera y persiste una llave criptográfica aleatoria de 256 bits (64 hex chars).
    """
    env_key = os.environ.get("FLASK_SECRET_KEY")
    if env_key and len(env_key.strip()) >= 32:
        return env_key.strip()
        
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SECRET_FILE):
        try:
            with open(SECRET_FILE, "r") as f:
                saved = f.read().strip()
                if len(saved) >= 32:
                    return saved
        except Exception:
            pass
            
    # Generar nueva llave criptográfica segura
    new_secret = secrets.token_hex(32)
    try:
        with open(SECRET_FILE, "w") as f:
            f.write(new_secret)
        os.chmod(SECRET_FILE, 0o600) # Solo lectura/escritura para el dueño
    except Exception as e:
        print(f"[SECURITY] Advertencia guardando .session_secret: {e}")
    return new_secret


# ==================== RATE LIMITER ANTIFUERZA BRUTA ====================
class SecurityRateLimiter:
    """
    Rate Limiter en memoria con ventana deslizante para mitigar ataques de fuerza bruta en el Login.
    Bloquea temporalmente IPs y usuarios tras 5 intentos fallidos dentro de una ventana de 5 minutos.
    """
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, lockout_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        # Estructura: key -> [timestamp, timestamp, ...]
        self.failed_attempts = defaultdict(list)
        # Estructura: key -> lockout_expiry_timestamp
        self.lockouts = {}

    def _clean_old(self, key: str, now: float):
        self.failed_attempts[key] = [t for t in self.failed_attempts[key] if now - t < self.window_seconds]

    def is_locked(self, ip: str, username: str = "") -> Tuple[bool, int]:
        now = time.time()
        # Verificar bloqueo por IP (excluyendo loopback para evitar DoS local)
        if ip and ip not in ("127.0.0.1", "::1", "localhost") and ip in self.lockouts:
            if now < self.lockouts[ip]:
                return True, int(self.lockouts[ip] - now)
            else:
                del self.lockouts[ip]
                
        # Verificar bloqueo por Usuario (aplica siempre, incluso en localhost)
        if username and username in self.lockouts:
            if now < self.lockouts[username]:
                return True, int(self.lockouts[username] - now)
            else:
                del self.lockouts[username]
                
        return False, 0

    def record_failure(self, ip: str, username: str = "") -> Tuple[bool, int]:
        now = time.time()
        locked = False
        max_lock = 0
        for key in (ip, username):
            if not key:
                continue
            # No bloquear IP loopback a nivel de IP global
            if key in ("127.0.0.1", "::1", "localhost"):
                continue
            self._clean_old(key, now)
            self.failed_attempts[key].append(now)
            if len(self.failed_attempts[key]) >= self.max_attempts:
                self.lockouts[key] = now + self.lockout_seconds
                self.failed_attempts[key].clear()
                locked = True
                max_lock = self.lockout_seconds
        # Siempre registrar fallo por usuario
        if username:
            self._clean_old(username, now)
            self.failed_attempts[username].append(now)
            if len(self.failed_attempts[username]) >= self.max_attempts:
                self.lockouts[username] = now + self.lockout_seconds
                self.failed_attempts[username].clear()
                locked = True
                max_lock = self.lockout_seconds
        return locked, max_lock

    def record_success(self, ip: str, username: str = ""):
        now = time.time()
        for key in (ip, username):
            if key in self.failed_attempts:
                self.failed_attempts[key].clear()
            if key in self.lockouts and now >= self.lockouts[key]:
                del self.lockouts[key]


RATE_LIMITER = SecurityRateLimiter(max_attempts=5, window_seconds=300, lockout_seconds=900)


# ==================== LOG DE AUDITORÍA DE SEGURIDAD ====================
audit_logger = logging.getLogger("TitoBotSecurityAudit")
audit_logger.setLevel(logging.INFO)
if not audit_logger.handlers:
    os.makedirs(DATA_DIR, exist_ok=True)
    file_handler = logging.FileHandler(AUDIT_LOG_FILE, encoding="utf-8")
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    audit_logger.addHandler(file_handler)

def log_security_event(event_type: str, details: str, ip: str = "UNKNOWN", username: str = "ANONYMOUS"):
    """Registra eventos críticos de seguridad para trazabilidad y auditoría forense."""
    msg = f"EVENT={event_type} | USER={username} | IP={ip} | {details}"
    audit_logger.info(msg)


# ==================== ENMASCARAMIENTO DE SECRETOS ====================
def mask_secret(secret: Optional[str]) -> str:
    """Enmascara llaves y secretos para que nunca viajen en texto plano a vistas de usuario."""
    if not secret:
        return ""
    s = str(secret).strip()
    if len(s) <= 8:
        return "********"
    return f"{s[:4]}...{s[-4:]}"


# ==================== BLINDAJE DE PERMISOS DE ARCHIVOS ====================
def harden_data_files():
    """
    Aplica permisos restrictivos (POSIX chmod 0700 en directorios y 0600 en archivos sensibles)
    para evitar que otros usuarios o procesos del sistema puedan leer llaves o bases de datos.
    """
    if os.name != 'posix':
        return
    try:
        if os.path.exists(DATA_DIR):
            os.chmod(DATA_DIR, 0o700)
        for sensitive_name in (".session_secret", "users.db", "broker_config.json", "security_audit.log"):
            fpath = os.path.join(DATA_DIR, sensitive_name)
            if os.path.exists(fpath):
                os.chmod(fpath, 0o600)
    except Exception as e:
        audit_logger.warning(f"No se pudieron ajustar permisos POSIX estrictos: {e}")

