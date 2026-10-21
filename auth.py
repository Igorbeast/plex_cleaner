from datetime import timedelta
import hmac
import os
import secrets
import time

from flask import redirect, render_template_string, request, session
from werkzeug.security import check_password_hash, generate_password_hash

PAGE = """<!DOCTYPE html><html lang="nl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Plex Cleaner - Inloggen</title><style>
body{background:#0f1117;color:#f3f4f6;font-family:sans-serif;display:flex;
justify-content:center;align-items:center;height:100vh;margin:0}
form{background:#161922;border:1px solid #262b3d;border-radius:16px;padding:32px;width:300px}
h2{margin-top:0}h2 span{color:#e5a00d}
input{width:100%;box-sizing:border-box;margin:6px 0 14px;padding:10px;border-radius:8px;
border:1px solid #262b3d;background:#0f1117;color:#f3f4f6}
button{width:100%;padding:10px;border:0;border-radius:8px;background:#e5a00d;font-weight:600;cursor:pointer}
.err{color:#fca5a5}</style></head><body>
<form method="post"><h2>plex <span>Cleaner</span></h2>
{% if error %}<p class="err">{{ error }}</p>{% endif %}
<label>Gebruikersnaam</label><input name="username" autofocus autocomplete="username">
<label>Wachtwoord</label><input name="password" type="password" autocomplete="current-password">
<button type="submit">Inloggen</button></form></body></html>"""

MAX_FAILS, LOCK_SECONDS = 5, 300
_fails = {}  # shortcut: in-memory per IP, resets on restart


def init_auth(app):
    app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
    app.permanent_session_lifetime = timedelta(hours=8)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = False
    app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)

    @app.before_request
    def guard():
        if request.endpoint in ("login", "static") or session.get("user"):
            return None
        token = os.environ.get("SCAN_TOKEN", "")
        sent = request.headers.get("X-Scan-Token", "")
        if token and request.path == "/scan" and hmac.compare_digest(sent.encode(), token.encode()):
            return None
        return redirect("/login")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        ip, now = request.remote_addr, time.time()
        count, since = _fails.get(ip, (0, now))
        if now - since > LOCK_SECONDS:
            count, since = 0, now
        if count >= MAX_FAILS:
            return render_template_string(PAGE, error="Te veel pogingen, wacht 5 minuten."), 429
        if request.method == "POST":
            name = os.environ.get("APP_USERNAME", "")
            user_ok = bool(name) and hmac.compare_digest(request.form.get("username", "").encode(), name.encode())
            pw_hash = os.environ.get("APP_PASSWORD_HASH", "")
            pw_ok = bool(pw_hash) and check_password_hash(pw_hash, request.form.get("password", ""))
            if user_ok and pw_ok:
                _fails.pop(ip, None)
                app.logger.info("Login gelukt vanaf %s", ip)
                session.clear()
                session["user"] = 1
                session.permanent = True
                return redirect("/")
            _fails[ip] = (count + 1, since)
            app.logger.warning("Login mislukt vanaf %s", ip)
            return render_template_string(PAGE, error="Onjuiste gegevens."), 401
        return render_template_string(PAGE, error=None)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect("/login")


if __name__ == "__main__":
    import getpass

    user = input("Gebruikersnaam: ")
    pw = getpass.getpass("Wachtwoord: ")
    if pw != getpass.getpass("Nogmaals: "):
        raise SystemExit("Wachtwoorden verschillen")
    print("\n# plak deze regels in .env")
    print(f"APP_USERNAME={user}")
    print(f"APP_PASSWORD_HASH='{generate_password_hash(pw)}'")
    print(f"SECRET_KEY={secrets.token_hex(32)}")
    print(f"SCAN_TOKEN={secrets.token_hex(16)}")
