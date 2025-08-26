import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from dotenv import load_dotenv

# --- Email (SMTP) ---
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "slamy-dev-secret")

DB_PATH = os.environ.get("DB_PATH", "leads.db")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# SMTP config
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASS = os.environ.get("EMAIL_PASS", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "SLAMY")
EMAIL_USE_TLS = (os.environ.get("EMAIL_USE_TLS", "true").lower() != "false")

# ---------------- DB helpers ----------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def column_exists(conn, table, column):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # base table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
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
    # defensive migration for older versions missing columns
    try:
        if not column_exists(conn, "leads", "phone"):
            cur.execute("ALTER TABLE leads ADD COLUMN phone TEXT")
        if not column_exists(conn, "leads", "marketing_opt_in"):
            cur.execute("ALTER TABLE leads ADD COLUMN marketing_opt_in BOOLEAN")
        if not column_exists(conn, "leads", "utm_source"):
            cur.execute("ALTER TABLE leads ADD COLUMN utm_source TEXT")
        if not column_exists(conn, "leads", "utm_medium"):
            cur.execute("ALTER TABLE leads ADD COLUMN utm_medium TEXT")
        if not column_exists(conn, "leads", "utm_campaign"):
            cur.execute("ALTER TABLE leads ADD COLUMN utm_campaign TEXT")
        if not column_exists(conn, "leads", "utm_content"):
            cur.execute("ALTER TABLE leads ADD COLUMN utm_content TEXT")
        if not column_exists(conn, "leads", "user_agent"):
            cur.execute("ALTER TABLE leads ADD COLUMN user_agent TEXT")
        if not column_exists(conn, "leads", "ip"):
            cur.execute("ALTER TABLE leads ADD COLUMN ip TEXT")
    except Exception:
        pass

    conn.commit()
    conn.close()

init_db()

# ---------------- Email helpers ----------------
def send_email(to_addr: str, subject: str, body: str):
    """Send a plain-text email via SMTP using env configuration."""
    if not (EMAIL_HOST and EMAIL_PORT and EMAIL_USER and EMAIL_PASS and to_addr):
        print("Email not sent: SMTP env variables missing.")
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["From"] = formataddr((str(Header(EMAIL_FROM_NAME, "utf-8")), EMAIL_USER))
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=15) as server:
            if EMAIL_USE_TLS:
                server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
    except Exception as e:
        print("Email error:", e)

# ---------------- Data helpers ----------------
def save_lead(data):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO leads (
            created_at, name, email, phone, topic, notes, promo_code, consent, marketing_opt_in,
            utm_source, utm_medium, utm_campaign, utm_content, user_agent, ip
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.utcnow().isoformat(),
            data.get("name","").strip(),
            data.get("email","").strip().lower(),
            data.get("phone","").strip(),
            data.get("topic","").strip(),
            data.get("notes","").strip(),
            data.get("promo_code","").strip(),
            1 if data.get("consent") else 0,
            1 if data.get("marketing_opt_in") else 0,
            data.get("utm_source"),
            data.get("utm_medium"),
            data.get("utm_campaign"),
            data.get("utm_content"),
            data.get("user_agent",""),
            data.get("ip",""),
        )
    )
    conn.commit()
    conn.close()

# ---------------- Routes ----------------
@app.get("/")
def home():
    return redirect(url_for("free_lesson"))

@app.route("/darmowa-lekcja", methods=["GET", "POST"])
def free_lesson():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip()
        phone = request.form.get("phone","").strip()
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
            # repopulate form
            prefill = dict(request.form)
            return render_template("form.html", prefill=prefill)

        # Save & notify
        data = {
            "name": name,
            "email": email,
            "phone": phone,
            "topic": topic,
            "notes": notes,
            "promo_code": promo_code,
            "consent": consent,
            "marketing_opt_in": marketing_opt_in,
            "utm_source": request.args.get("utm_source"),
            "utm_medium": request.args.get("utm_medium"),
            "utm_campaign": request.args.get("utm_campaign"),
            "utm_content": request.args.get("utm_content"),
            "user_agent": request.headers.get("User-Agent",""),
            "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        }
        save_lead(data)

        # Email to admin
        admin_body = (
            "SLAMY – nowy lead na darmową lekcję\n\n"
            f"Imię: {name}\n"
            f"E-mail: {email}\n"
            f"Telefon: {phone or '-'}\n"
            f"Temat/pasja: {topic or '-'}\n"
            f"Notatki: {notes or '-'}\n"
            f"Kod: {promo_code or '-'}\n"
            f"UTM: {data.get('utm_source')}/{data.get('utm_medium')}/{data.get('utm_campaign')}/{data.get('utm_content')}\n"
            f"UA: {data.get('user_agent','')}\n"
            f"IP: {data.get('ip','')}\n"
            f"Data: {datetime.utcnow().isoformat()} UTC\n"
        )
        if ADMIN_EMAIL:
            send_email(ADMIN_EMAIL, "SLAMY – nowy lead (darmowa lekcja)", admin_body)

        # Email to client
        client_body = (
            f"Cześć {name},\n\n"
            "Dziękujemy za zaufanie i zapisanie się na darmową lekcję 30 minut w SLAMY! 🚀\n\n"
            "W ciągu 24h skontaktujemy się z Tobą z propozycją terminu oraz lektora, "
            "który najlepiej pasuje do Twoich pasji.\n\n"
            "Jeżeli chcesz przyspieszyć kontakt, odpowiedz na tego maila i podaj preferowane terminy.\n\n"
            "Do zobaczenia w SLAMY!\nZespół SLAMY\n"
        )
        if email:
            send_email(email, "Dziękujemy za zaufanie – SLAMY darmowa lekcja", client_body)

        return redirect(url_for("thanks"))

    # GET
    prefill = {
        "promo_code": request.args.get("code","SLAMY30")
    }
    return render_template("form.html", prefill=prefill)

@app.get("/dziekujemy")
def thanks():
    return render_template("thanks.html")

# ---------------- Admin (light) ----------------
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
    cur.execute("""
        SELECT id, created_at, name, email, phone, topic, promo_code, marketing_opt_in
        FROM leads
        ORDER BY id DESC
        LIMIT 200
    """)
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
    headers = [d[0] for d in cur.description] if cur.description else []
    conn.close()

    import csv
    from io import StringIO
    sio = StringIO()
    writer = csv.writer(sio)
    writer.writerow(headers)
    for r in rows:
        if isinstance(r, sqlite3.Row):
            writer.writerow([r[h] for h in headers])
        else:
            writer.writerow(r)
    csv_data = sio.getvalue()
    return Response(
        csv_data,
        headers={
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": "attachment; filename=slamy_leads.csv",
        },
    )

if __name__ == "__main__":
    # Local test run
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
