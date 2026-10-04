import os
import re
import json
import sqlite3
import datetime
from typing import Dict, List, Any, Optional
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "users.db"))
CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "broker_config.json"))

def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or ""
    if not url and os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                url = cfg.get("database_url", "")
        except Exception:
            pass
    if url and url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url.strip()

def is_using_postgres() -> bool:
    return bool(get_database_url() and HAS_PSYCOPG2)

class PostgresCursorWrapper:
    def __init__(self, cur):
        self.cur = cur
        self.lastrowid = None

    def execute(self, query: str, params: Any = None):
        clean_query = re.sub(r'\?', '%s', query)
        # Si es un INSERT sin RETURNING en users, capturamos el ID insertado
        if re.search(r'^\s*INSERT\s+INTO\s+users\b', clean_query, re.IGNORECASE) and 'RETURNING' not in clean_query.upper():
            clean_query += " RETURNING id"
            self.cur.execute(clean_query, tuple(params) if params else None)
            res = self.cur.fetchone()
            if res:
                self.lastrowid = res.get("id") if isinstance(res, dict) else res[0]
            return self
        
        self.cur.execute(clean_query, tuple(params) if params else None)
        return self

    def fetchone(self):
        row = self.cur.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        rows = self.cur.fetchall()
        return [dict(r) for r in rows] if rows else []

class PostgresConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        return PostgresCursorWrapper(self.conn.cursor(cursor_factory=RealDictCursor))

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

class SQLiteConnectionWrapper:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def cursor(self):
        return self.conn.cursor()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

def get_db():
    db_url = get_database_url()
    if db_url and HAS_PSYCOPG2:
        try:
            pg_conn = psycopg2.connect(db_url, connect_timeout=5)
            return PostgresConnectionWrapper(pg_conn)
        except Exception as e:
            print(f"[AUTH] ⚠️ Error conectando a PostgreSQL ({e}). Usando SQLite local de contingencia.")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return SQLiteConnectionWrapper(DB_PATH)

def _migrate_sqlite_to_postgres(pg_conn):
    if not os.path.exists(DB_PATH):
        return False
    try:
        sqlite_conn = sqlite3.connect(DB_PATH)
        sqlite_conn.row_factory = sqlite3.Row
        cur_sq = sqlite_conn.cursor()
        cur_sq.execute("SELECT * FROM users")
        rows = cur_sq.fetchall()
        if not rows:
            sqlite_conn.close()
            return False
        cur_pg = pg_conn.cursor()
        for r in rows:
            u = dict(r)
            cur_pg.execute("""
                INSERT INTO users (username, password_hash, full_name, email, role, status, plan, expires_at, notes, created_at, last_login)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (username) DO NOTHING
            """, (
                u["username"], u["password_hash"], u["full_name"], u.get("email", ""),
                u.get("role", "user"), u.get("status", "active"), u.get("plan", "Mensual VIP"),
                u.get("expires_at", ""), u.get("notes", ""), u.get("created_at", ""), u.get("last_login")
            ))
        sqlite_conn.close()
        print(f"[AUTH] 🚀 Migrados {len(rows)} usuarios desde SQLite local a PostgreSQL Cloud con éxito!")
        return True
    except Exception as e:
        print(f"[AUTH] Error en auto-migración SQLite -> Postgres: {e}")
        return False

def _create_initial_admin(cur):
    default_pwd = generate_password_hash("admin123")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO users (username, password_hash, full_name, email, role, status, plan, expires_at, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "admin",
        default_pwd,
        "Super Administrador",
        "admin@titobottrader.tech",
        "admin",
        "active",
        "Vitalicio / Owner",
        "2099-12-31",
        "Cuenta principal de administración del sistema",
        now
    ))
    print("[AUTH] 👑 Administrador maestro inicial creado: Usuario: admin / Clave: admin123")

def init_auth_db():
    """Inicializa la base de datos (PostgreSQL Cloud si está configurada, o SQLite local con tolerancia a fallos)."""
    db_url = get_database_url()
    if db_url and HAS_PSYCOPG2:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        full_name VARCHAR(100) NOT NULL,
                        email VARCHAR(120),
                        role VARCHAR(20) NOT NULL DEFAULT 'user',
                        status VARCHAR(20) NOT NULL DEFAULT 'active',
                        plan VARCHAR(50) DEFAULT 'Mensual VIP',
                        expires_at VARCHAR(20),
                        notes TEXT,
                        created_at VARCHAR(30) NOT NULL,
                        last_login VARCHAR(30)
                    );
                """)
                cur.execute("SELECT COUNT(*) as cnt FROM users")
                cnt = cur.fetchone()["cnt"]
                if cnt == 0:
                    migrated = _migrate_sqlite_to_postgres(conn)
                    if not migrated:
                        _create_initial_admin(cur)
                print("[AUTH] ☁️ Conectado y sincronizado a PostgreSQL Cloud (Supabase/Managed DB).")
                return
        except Exception as e:
            print(f"[AUTH] ⚠️ Error inicializando PostgreSQL: {e}. Usando SQLite local.")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                plan TEXT DEFAULT 'Mensual VIP',
                expires_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        """)
        cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'admin'")
        admin_count = cur.fetchone()["cnt"]
        if admin_count == 0:
            _create_initial_admin(cur)

def update_database_url(new_url: str) -> Dict[str, Any]:
    """Prueba y guarda una nueva URL de conexión PostgreSQL / Supabase, migrando los datos automáticamente."""
    clean_url = (new_url or "").strip()
    if clean_url.startswith("postgres://"):
        clean_url = "postgresql://" + clean_url[len("postgres://"):]
    
    if not clean_url:
        return {"success": False, "error": "URL de base de datos vacía."}
    
    if not HAS_PSYCOPG2:
        return {"success": False, "error": "Librería psycopg2 no disponible. Ejecute pip install psycopg2-binary."}
    
    try:
        test_conn = psycopg2.connect(clean_url, connect_timeout=5)
        wrapped = PostgresConnectionWrapper(test_conn)
        with wrapped as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name VARCHAR(100) NOT NULL,
                    email VARCHAR(120),
                    role VARCHAR(20) NOT NULL DEFAULT 'user',
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    plan VARCHAR(50) DEFAULT 'Mensual VIP',
                    expires_at VARCHAR(20),
                    notes TEXT,
                    created_at VARCHAR(30) NOT NULL,
                    last_login VARCHAR(30)
                );
            """)
            _migrate_sqlite_to_postgres(conn)
        
        # Guardar en broker_config.json
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        cfg = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["database_url"] = clean_url
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.environ["DATABASE_URL"] = clean_url
        return {"success": True, "message": "Conectado exitosamente a PostgreSQL Cloud. Todos los usuarios han sido sincronizados y asegurados."}
    except Exception as e:
        return {"success": False, "error": f"Error conectando a PostgreSQL: {str(e)}"}

def authenticate(username, password):
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
            
        if user["status"] == "restricted":
            return user, "ACCOUNT_RESTRICTED"
        if user["status"] == "suspended":
            return user, "ACCOUNT_SUSPENDED"
            
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

from dashboard.security_guard import log_security_event

def validate_username(username: str) -> bool:
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
            uid = getattr(cur, "lastrowid", None)
            log_security_event("USER_CREATED", f"Nuevo usuario ID={uid} '{username}' rol={role} plan={plan}", username=admin_user)
            return uid, None
        except Exception as e:
            err_str = str(e).lower()
            if "unique" in err_str or "duplicate" in err_str:
                return None, f"El nombre de usuario '{username}' ya está registrado. Por favor elija otro."
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
            "admin_users": admins,
            "storage_type": "PostgreSQL Cloud (Supabase)" if is_using_postgres() else "SQLite Local Persistente"
        }
