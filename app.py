import os, re, sqlite3, time
from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session, g, abort

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

DB_PATH = os.path.join(os.path.dirname(__file__), "db.sqlite3")

# ---------- DB ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
    """)
    db.commit()

# ---------- Seguridad básica ----------
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{8,32}$")
EMAIL_RE    = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[A-Za-z]{2,}$")

def valid_username(u): return bool(USERNAME_RE.fullmatch(u))
def valid_email(e):    return bool(EMAIL_RE.fullmatch(e.strip()))

# CSRF helpers
import secrets
def new_csrf():
    token = secrets.token_urlsafe(32)
    session["csrf_token"] = token
    return token

def check_csrf(token):
    return token and session.get("csrf_token") and token == session["csrf_token"]

# Rate limiting simple (IP → ventanita 60s, máx 20 req)
RATE = {}
def rate_limited(ip, key="submit", limit=20, window=60):
    now = time.time()
    bucket = RATE.setdefault((ip, key), [])
    # purga
    RATE[(ip, key)] = [t for t in bucket if now - t < window]
    if len(RATE[(ip, key)]) >= limit:
        return True
    RATE[(ip, key)].append(now)
    return False

# Security headers
@app.after_request
def set_secure_headers(resp):
    resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; form-action 'self'"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp

# ---------- Rutas ----------
@app.route("/", methods=["GET"])
def home():
    init_db()
    token = new_csrf()
    return render_template("index.html", csrf_token=token)

@app.route("/submit", methods=["POST"])
def submit():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if rate_limited(ip):
        abort(429, description="Demasiadas solicitudes, intenta más tarde.")

    csrf_token = request.form.get("csrf_token", "")
    if not check_csrf(csrf_token):
        abort(403, description="CSRF no válido.")

    username = (request.form.get("username") or "").strip()
    email    = (request.form.get("email") or "").strip()

    # Validación servidor
    errors = []
    if not valid_username(username):
        errors.append("Usuario debe tener 8-32 caracteres (letras, números, . _ -).")
    if not valid_email(email):
        errors.append("Email no es válido.")

    if errors:
        for e in errors: flash(e, "error")
        # reemitir nuevo token
        session.pop("csrf_token", None)
        return redirect(url_for("home"))

    # Inserción segura (parametrizada)
    db = get_db()
    db.execute("INSERT INTO users(username, email, created_at) VALUES(?,?,?)",
               (username, email, int(time.time())))
    db.commit()

    flash("¡Registro exitoso!", "ok")
    session.pop("csrf_token", None)
    return redirect(url_for("home"))

# Healthcheck (para Render/Railway)
@app.route("/healthz")
def healthz():
    return "ok", 200

if __name__ == "__main__":
    with app.app_context():
        init_db()            # ← ahora sí dentro del contexto
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

