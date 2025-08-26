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
    # defensive migration
    try:
        if not column_exists(conn, "leads", "phone"):
            cur.execute("ALTER TABLE leads ADD COLUMN phone TEXT")
        for col in ["marketing_opt_in","utm_source","utm_medium","utm_campaign","utm_content","user_agent","ip"]:
            if not column_exists(conn, "leads", col):
                cur.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT")
    except Exception:
        pass

    conn.commit()
    conn.close()

init_db()

# ---------------- Email helpers ----------------
def send_email(to_addr: str, subject: str, body: str, is_html: bool=False):
    """Send an email via SMTP using env configuration."""
    if not (EMAIL_HOST and EMAIL_PORT and EMAIL_USER and EMAIL_PASS and to_addr):
        print("Email not sent: SMTP env variables missing.")
        return

    subtype = "html" if is_html else "plain"
    msg = MIMEText(body, subtype, "utf-8")
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
        topic_custom = request.form.get("topic_custom","").strip()
        if topic == "__other" and topic_custom:
            topic = topic_custom
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

        # Email to admin (plain text)
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
            send_email(ADMIN_EMAIL, "SLAMY – nowy lead (darmowa lekcja)", admin_body, is_html=False)

        # Email to client (HTML, brand)
        logo_url = os.environ.get("PUBLIC_LOGO_URL", "https://slamy.online/logo.svg")
        safe_topic_html = f"Zainteresowanie: <strong>{topic}</strong>." if topic else ""
        client_body_html = f"""
<!doctype html>
<html lang='pl'>
  <head>
    <meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Dziękujemy – SLAMY</title>
    <style>
      .preheader {{ display:none!important; visibility:hidden; opacity:0; color:transparent; height:0; width:0; overflow:hidden; }}
      @media (prefers-color-scheme: dark) {{
        .card {{ background:#121212 !important; color:#EAEAEA !important; }}
        .muted {{ color:#A9A9A9 !important; }}
      }}
    </style>
  </head>
  <body style="margin:0;background:#f4f6fb;font-family:Inter,Segoe UI,Roboto,Arial,sans-serif;color:#111;">
    <div class="preheader">Twoja darmowa lekcja 30 min w SLAMY – wkrótce odezwiemy się z terminem.</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6fb;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellpadding="0" cellspacing="0" class="card" style="background:#ffffff;border-radius:12px;overflow:hidden;">
            <tr>
              <td style="background:linear-gradient(135deg,#1B1464,#6C2BD9);padding:18px 22px;">
                <table width="100%" role="presentation">
                  <tr>
                    <td align="left">
                      <img src="{logo_url}" alt="SLAMY" height="28" style="display:block;border:0;outline:none;">
                    </td>
                    <td align="right" style="font-size:12px;color:#ffffff99;">Darmowa lekcja 30 min</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 24px 8px 24px;">
                <h1 style="margin:0 0 8px 0;font-size:20px;line-height:1.3;">Dziękujemy za zaufanie, {name}!</h1>
                <p style="margin:0 0 12px 0;line-height:1.6;">
                  Zgłoszenie na <strong>darmową lekcję 30&nbsp;min</strong> w SLAMY już do nas dotarło. ✨
                </p>
                <p style="margin:0 0 12px 0;line-height:1.6;">{safe_topic_html}</p>
                <p style="margin:0 0 16px 0;line-height:1.6;">
                  W ciągu <strong>24h</strong> skontaktujemy się z Tobą z propozycją terminu i lektora dobranego do Twoich pasji.
                </p>
                <table role="presentation" cellpadding="0" cellspacing="0" style="margin:10px 0 18px 0;">
                  <tr>
                    <td align="center" bgcolor="#1B1464" style="border-radius:10px;">
                      <a href="mailto:kontakt@slamy.online?subject=SLAMY%20-%20Propozycja%20terminu%20lekcji"
                         style="display:inline-block;padding:12px 18px;color:#fff;text-decoration:none;font-weight:600;border-radius:10px;">
                        Przyspiesz kontakt – odpisz teraz
                      </a>
                    </td>
                  </tr>
                </table>
                <p style="margin:0 0 6px 0;line-height:1.6;">
                  Jeśli wolisz telefon, daj znać w odpowiedzi – oddzwonimy.
                </p>
                <hr style="border:none;border-top:1px solid #E9ECF4;margin:18px 0;">
                <p class="muted" style="margin:0;color:#6B7280;font-size:12px;line-height:1.5;">
                  W SLAMY uczysz się <em>przez swoje pasje</em> z lektorem, który je podziela. To najszybszy sposób, by zacząć mówić swobodnie.
                </p>
              </td>
            </tr>
            <tr>
              <td style="background:#f7f7fb;padding:14px 24px;color:#6B7280;font-size:12px;line-height:1.4;">
                Ten e-mail został wysłany po wypełnieniu formularza na stronie SLAMY.
                Jeśli to nie Ty – napisz do nas: <a href="mailto:kontakt@slamy.online" style="color:#6C2BD9;text-decoration:none;">kontakt@slamy.online</a>.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
        if email:
            send_email(email, "Dziękujemy za zaufanie – SLAMY darmowa lekcja", client_body_html, is_html=True)

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
