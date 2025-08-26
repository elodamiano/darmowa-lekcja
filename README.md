
# SLAMY – Darmowa lekcja (30 min)

Minimalna aplikacja Flask do zbierania leadów na darmową lekcję 30 minut (kod: `SLAMY30`).

## Funkcje
- Formularz pod `/darmowa-lekcja` (imię, e-mail, temat/pasja, notatki, kod, zgody).
- Zapisy do SQLite (`leads.db`).
- Prosty panel `/admin` (hasło przez zmienną `ADMIN_PASSWORD`) + eksport CSV.
- Opcjonalne powiadomienie na Telegram (zmienne `TELEGRAM_BOT_TOKEN` i `TELEGRAM_CHAT_ID`).

## Uruchomienie lokalne
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app.py
python app.py
# otwórz http://localhost:5000/darmowa-lekcja
```

## Deploy na Render.com
1. Stwórz **New Web Service** → połącz repo lub wgraj kod.
2. **Runtime:** Python 3.11+
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `gunicorn app:app`
5. **Environment Variables:**
   - `SECRET_KEY` – dowolny losowy string
   - `ADMIN_PASSWORD` – hasło do panelu admin
   - `DB_PATH` – `leads.db` (domyślnie)
   - *(opcjonalnie)* `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
6. Po wdrożeniu, Twoje URL-e:
   - `/darmowa-lekcja` – formularz
   - `/dziekujemy` – potwierdzenie
   - `/admin` – panel (wymaga hasła)
   - `/admin/export.csv` – eksport CSV (po zalogowaniu)

## UTM tracking
Aplikacja automatycznie zapisuje parametry `utm_source`, `utm_medium`, `utm_campaign`, `utm_content` z query stringa, dzięki czemu łatwo ocenisz skuteczność reklam.

## Uwaga prawna
Tekst zgód/RODO jest skrócony – dostosuj go do swoich dokumentów prawnych. Podlinkuj własny Regulamin i Politykę prywatności w `templates/base.html`.
