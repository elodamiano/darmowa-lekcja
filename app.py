
import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, Response
from dotenv import load_dotenv

# Optional notifications
try:
    import requests
except Exception:
    requests = None

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "slamy-dev-secret")

DB_PATH = os.environ.get("DB_PATH", "leads.db")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- DB helpers ---
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            topic TEXT,
            notes TEXT,
            promo_code TEXT,
            consent BOOLEAN,
            marketing_opt_in BOOLEAN,
            utm_source TEXT,
            utm_medium TEXT,
            utm_campaign TEXT,
            utm_content TEXT,
            user_agent TEXT,
            ip TEXT
        )
        """
    )
    conn.commit()
    conn.close()

init_db()

# --- Utils ---
def notify_telegram(text: str):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID and requests):
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

def save_lead(data):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO leads (created_at, name, email, topic, notes, promo_code, consent, marketing_opt_in,
                           utm_source, utm_medium, utm_campaign, utm_content, user_agent, ip)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.utcnow().isoformat(),
            data.get("name","").strip(),
            data.get("email","").strip().lower(),
            data.get("topic","").strip(),
            data.get("notes","").strip(),
            data.get("promo_code","").strip(),
            1 if data.get("consent") else 0,
            1 if data.get("marketing_opt_in") else 0,
            data.get("utm_source"),
            data.get("utm_medium"),
            data.get("utm_campaign"),
            data.get("utm_content"),
            request.headers.get("User-Agent",""),
            request.headers.get("X-Forwarded-For", request.remote_addr)
        )
    )
    conn.commit()
    conn.close()

# --- Routes ---
@app.get("/")
def home():
    return redirect(url_for("free_lesson"))

@app.route("/darmowa-lekcja", methods=["GET", "POST"])
def free_lesson():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip()
        topic = request.form.get("topic","").strip()
        notes = request.form.get("notes","").strip()
        promo_code = request.form.get("promo_code","").strip()
        consent = request.form.get("consent") == "on"
        marketing_opt_in = request.form.get("marketing_opt_in") == "on"

        # Basic validation
        errors = []
        if not name:
            errors.append("Podaj imię.")
        if not email or "@" not in email:
            errors.append("Podaj poprawny adres e-mail.")
        if not consent:
            errors.append("Musisz zaakceptować regulamin i politykę prywatności.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("form.html", prefill=request.form)

        # Save & notify
        data = {
            "name": name, "email": email, "topic": topic, "notes": notes,
            "promo_code": promo_code, "consent": consent, "marketing_opt_in": marketing_opt_in,
            "utm_source": request.args.get("utm_source"),
            "utm_medium": request.args.get("utm_medium"),
            "utm_campaign": request.args.get("utm_campaign"),
            "utm_content": request.args.get("utm_content"),
        }
        save_lead(data)

        notify_telegram(
            f"🆕 <b>SLAMY: nowy lead na darmową lekcję</b>\n"
            f"👤 {name}\n✉️ {email}\n🎯 Temat: {topic or '-'}\n📝 Notatki: {notes or '-'}\n🏷 Kod: {promo_code or '-'}"
        )

        return redirect(url_for("thanks"))

    # GET
    prefill = {
        "promo_code": request.args.get("code","SLAMY30")
    }
    return render_template("form.html", prefill=prefill)

@app.get("/dziekujemy")
def thanks():
    return render_template("thanks.html")

# --- Admin (very light) ---
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        pwd = request.form.get("password")
        if pwd == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        else:
            flash("Wrong password", "error")
            return render_template("login.html")

    if not session.get("admin"):
        return render_template("login.html")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, created_at, name, email, topic, promo_code, marketing_opt_in FROM leads ORDER BY id DESC LIMIT 200")
    rows = cur.fetchall()
    conn.close()
    return render_template("admin.html", leads=rows)

@app.get("/admin/export.csv")
def export_csv():
    if not session.get("admin"):
        return Response("Unauthorized", status=401)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    # Build CSV
    headers = [d[0] for d in cur.description] if cur.description else []
    import csv
    from io import StringIO
    sio = StringIO()
    writer = csv.writer(sio)
    # Write header
    writer.writerow(headers)
    for r in rows:
        writer.writerow([r[h] if isinstance(r, sqlite3.Row) else r for h in headers])
    csv_data = sio.getvalue()
    return Response(
        csv_data,
        headers={
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": "attachment; filename=slamy_leads.csv",
        },
    )

if __name__ == "__main__":
    # For local testing
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
