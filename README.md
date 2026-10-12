# PRESTYLE Meesho QR Generator

Flask web app that accepts a Meesho shipping-label PDF and orders CSV, matches sub-order IDs to packet IDs, and generates a printable PDF plus an Excel report.

## Run locally (Windows)

```bat
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
set APP_USERNAME=admin
set APP_PASSWORD=choose-a-long-password
set COOKIE_SECURE=false
python app.py
```

Open http://127.0.0.1:5000

## Deploy to Render

1. Push this project to a GitHub repository.
2. In Render, create a Web Service from that repository, or use the included `render.yaml`.
3. Set environment variables:
   - `APP_USERNAME`: your chosen login username
   - `APP_PASSWORD`: a strong, unique password
   - `SECRET_KEY`: a long random secret (Render can generate one)
   - `COOKIE_SECURE`: `true`
4. Build command: `pip install -r requirements.txt`
5. Start command: `gunicorn app:app`

Never commit credentials or real order files to GitHub.

## Important storage note

This version stores generated reports in the instance's local `outputs/` directory. On free ephemeral hosting, reports can disappear when the service restarts or redeploys. Download reports immediately and keep local copies. For durable server-side storage, configure a persistent disk or object storage.

## CSV requirements

The CSV must include columns named exactly `Sub Order No` and `Packet Id`. `Reason for Credit Entry` is optional.
