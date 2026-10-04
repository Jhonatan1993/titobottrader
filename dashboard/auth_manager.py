import os
import sqlite3
import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "users.db"))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_auth_db():
    """Inicializa la base de datos de usuarios y crea el admin maestro por defecto si no existe."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT,
                role TEXT NOT NULL DEFAULT 'user', -- 'admin' o 'user'
                status TEXT NOT NULL DEFAULT 'active', -- 'active', 'restricted', 'suspended'
                plan TEXT DEFAULT 'Mensual VIP',
                expires_at TEXT, -- YYYY-MM-DD
                notes TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        """)
        
        # Verificar si existe al menos un admin
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'admin'")
        admin_count = cur.fetchone()["cnt"]
        
        if admin_count == 0:
            # Crear administrador inicial por defecto
            default_pwd = generate_password_hash("admin123")
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO users (username, password_hash, full_name, email, role, status, plan, expires_at, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "admin",
                default_pwd,
                "Super Administrador",
                "admin@trading.ai",
                "admin",
                "active",
                "Vitalicio / Owner",
                "2099-12-31",
                "Cuenta principal de administración del sistema",
                now
            ))
            conn.commit()
            print("[AUTH] 👑 Administrador maestro inicial creado: Usuario: admin / Clave: admin123")

def authenticate(username, password):
    """
    Autentica un usuario verificando credenciales y estado de cuenta.
    Retorna (user_dict, error_code).
    error_code puede ser:
      - None (éxito)
      - 'INVALID_CREDENTIALS'
      - 'ACCOUNT_RESTRICTED' (por falta de pago)
      - 'ACCOUNT_SUSPENDED'
    """
    if not username or not password:
        return None, "INVALID_CREDENTIALS"
        
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
        row = cur.fetchone()
        if not row:
            return None, "INVALID_CREDENTIALS"
            
        user = dict(row)
        if not check_password_hash(user["password_hash"], password):
            return None, "INVALID_CREDENTIALS"
            
        # Verificar estado de la cuenta
        if user["status"] == "restricted":
            return user, "ACCOUNT_RESTRICTED"
        if user["status"] == "suspended":
            return user, "ACCOUNT_SUSPENDED"
            
        # Registrar último acceso
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user["id"]))
        conn.commit()
        
        user["last_login"] = now
        user.pop("password_hash", None)
        return user, None

def get_user_by_id(user_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        if row:
            u = dict(row)
            u.pop("password_hash", None)
            return u
    return None

def get_user_by_username(username):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
        row = cur.fetchone()
        if row:
            u = dict(row)
            u.pop("password_hash", None)
            return u
    return None

def list_users(search=None, status_filter=None):
    with get_db() as conn:
        cur = conn.cursor()
        query = "SELECT id, username, full_name, email, role, status, plan, expires_at, notes, created_at, last_login FROM users WHERE 1=1"
        params = []
        
        if search:
            query += " AND (username LIKE ? OR full_name LIKE ? OR email LIKE ?)"
            s = f"%{search.strip()}%"
            params.extend([s, s, s])
            
        if status_filter and status_filter != "all":
            query += " AND status = ?"
            params.append(status_filter)
            
        query += " ORDER BY id DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]

import re
from dashboard.security_guard import log_security_event

def validate_username(username: str) -> bool:
    """Valida que el usuario tenga entre 3 y 30 caracteres alfanuméricos, guiones o puntos."""
    if not username or len(username) < 3 or len(username) > 30:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_.-]+$', username))

def create_user(username, password, full_name, email="", role="user", status="active", plan="Mensual VIP", expires_at="", notes="", admin_user="admin"):
    username = (username or "").strip()
    if not username:
        return None, "El nombre de usuario es obligatorio"
    if not validate_username(username):
        return None, "El usuario solo puede contener letras, números, puntos o guiones (3-30 caracteres)"
    if not password or len(password) < 6:
        return None, "La contraseña debe tener al menos 6 caracteres por seguridad"
    if not full_name or len(full_name.strip()) < 2:
        return None, "El nombre completo es obligatorio (mínimo 2 caracteres)"
        
    full_name = full_name.strip()[:100]
    email = (email or "").strip()[:120]
    plan = (plan or "Mensual VIP").strip()[:50]
    notes = (notes or "").strip()[:500]
    
    pwd_hash = generate_password_hash(password)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not expires_at:
        # Por defecto 30 días si es mensual
        expires_at = (datetime.date.today() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        
    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO users (username, password_hash, full_name, email, role, status, plan, expires_at, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                username,
                pwd_hash,
                full_name,
                email,
                role if role in ("admin", "user") else "user",
                status if status in ("active", "restricted", "suspended") else "active",
                plan,
                expires_at,
                notes,
                now
            ))
            conn.commit()
            uid = cur.lastrowid
            log_security_event("USER_CREATED", f"Nuevo usuario ID={uid} '{username}' rol={role} plan={plan}", username=admin_user)
            return uid, None
        except sqlite3.IntegrityError:
            return None, f"El nombre de usuario '{username}' ya está registrado. Por favor elija otro."
        except Exception as e:
            return None, str(e)

def update_user(user_id, full_name, email, role, status, plan, expires_at, notes, admin_user="admin"):
    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE users
                SET full_name = ?, email = ?, role = ?, status = ?, plan = ?, expires_at = ?, notes = ?
                WHERE id = ?
            """, (
                (full_name or "").strip()[:100],
                (email or "").strip()[:120],
                role if role in ("admin", "user") else "user",
                status if status in ("active", "restricted", "suspended") else "active",
                (plan or "Mensual VIP").strip()[:50],
                expires_at,
                (notes or "").strip()[:500],
                user_id
            ))
            conn.commit()
            log_security_event("USER_UPDATED", f"Usuario ID={user_id} modificado: rol={role} estado={status} plan={plan}", username=admin_user)
            return True, None
        except Exception as e:
            return False, str(e)

def set_user_status(user_id, new_status, admin_user="admin"):
    """Permite restringir o reactivar la cuenta de un usuario rápidamente."""
    if new_status not in ("active", "restricted", "suspended"):
        return False, "Estado no válido"
    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id))
            conn.commit()
            action_tag = "USER_RESTRICTED_PAYMENT" if new_status == "restricted" else ("USER_ACTIVATED" if new_status == "active" else "USER_SUSPENDED")
            log_security_event(action_tag, f"Cambio de estado a '{new_status}' para usuario ID={user_id}", username=admin_user)
            return True, None
        except Exception as e:
            return False, str(e)

def change_user_password(user_id, new_password, admin_user="admin"):
    if not new_password or len(new_password) < 6:
        return False, "La nueva contraseña debe tener al menos 6 caracteres por seguridad"
    pwd_hash = generate_password_hash(new_password)
    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))
            conn.commit()
            log_security_event("PASSWORD_RESET", f"Contraseña restablecida para usuario ID={user_id}", username=admin_user)
            return True, None
        except Exception as e:
            return False, str(e)

def delete_user(user_id, requesting_admin_id, admin_user="admin"):
    if int(user_id) == int(requesting_admin_id):
        return False, "No puedes eliminar tu propia cuenta de administrador"
    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            log_security_event("USER_DELETED", f"Usuario ID={user_id} eliminado permanentemente", username=admin_user)
            return True, None
        except Exception as e:
            return False, str(e)

def get_auth_metrics():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as total FROM users")
        total = cur.fetchone()["total"]
        
        cur.execute("SELECT COUNT(*) as active FROM users WHERE status = 'active'")
        active = cur.fetchone()["active"]
        
        cur.execute("SELECT COUNT(*) as restricted FROM users WHERE status = 'restricted'")
        restricted = cur.fetchone()["restricted"]
        
        cur.execute("SELECT COUNT(*) as admins FROM users WHERE role = 'admin'")
        admins = cur.fetchone()["admins"]
        
        return {
            "total_users": total,
            "active_users": active,
            "restricted_users": restricted,
            "admin_users": admins
        }
