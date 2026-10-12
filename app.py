import os
import secrets
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask, abort, flash, redirect, render_template, request,
    send_file, session, url_for
)
from werkzeug.utils import secure_filename

from meesho_qr_generator import (
    extract_pdf_orders,
    match_with_csv,
    create_printable_pdf,
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB per request
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "true").lower() == "true"

# Required environment variables: APP_USERNAME, APP_PASSWORD, SECRET_KEY.
# Do not hardcode production credentials in this file.
APP_USERNAME = os.environ.get("APP_USERNAME", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

if not app.config["SECRET_KEY"]:
    # Allows local development only. Set a long random SECRET_KEY in production.
    app.config["SECRET_KEY"] = secrets.token_hex(32)
    app.config["SESSION_COOKIE_SECURE"] = False


def login_is_configured():
    return bool(APP_USERNAME and APP_PASSWORD)


def require_login():
    if session.get("logged_in") is not True:
        return redirect(url_for("login", next=request.path))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if not login_is_configured():
        return render_template("setup_error.html"), 500

    if session.get("logged_in") is True:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        username_ok = secrets.compare_digest(username, APP_USERNAME)
        password_ok = secrets.compare_digest(password, APP_PASSWORD)

        if username_ok and password_ok:
            session.clear()
            session["logged_in"] = True
            session["jobs"] = []
            next_url = request.args.get("next", "")
            # Only allow local relative paths to avoid open redirects.
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("index"))

        flash("Incorrect username or password.", "error")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET", "POST"])
def index():
    auth = require_login()
    if auth:
        return auth

    stats = None
    downloads = None

    if request.method == "POST":
        pdf_file = request.files.get("pdf_file")
        csv_file = request.files.get("csv_file")

        if not pdf_file or not pdf_file.filename:
            flash("Please upload the Meesho shipping-label PDF.", "error")
        elif not csv_file or not csv_file.filename:
            flash("Please upload the Meesho orders CSV.", "error")
        elif Path(pdf_file.filename).suffix.lower() != ".pdf":
            flash("The shipping-label file must be a PDF.", "error")
        elif Path(csv_file.filename).suffix.lower() != ".csv":
            flash("The orders file must be a CSV.", "error")
        else:
            job_id = uuid4().hex
            pdf_path = UPLOAD_DIR / f"{job_id}_{secure_filename(pdf_file.filename)}"
            csv_path = UPLOAD_DIR / f"{job_id}_{secure_filename(csv_file.filename)}"
            output_pdf = OUTPUT_DIR / f"{job_id}_printable_qr.pdf"
            output_excel = OUTPUT_DIR / f"{job_id}_match_report.xlsx"

            try:
                pdf_file.save(pdf_path)
                csv_file.save(csv_path)

                records = extract_pdf_orders(pdf_path)
                if not records:
                    raise ValueError("No pages were found in the uploaded PDF.")

                results = match_with_csv(records, csv_path)
                create_printable_pdf(results, output_pdf)
                results.to_excel(output_excel, index=False, engine="openpyxl")

                total = len(results)
                matched_count = int(
                    results["Match Result"].astype(str).str.startswith("MATCHED").sum()
                )
                stats = {
                    "total": int(total),
                    "awb": int(results["AWB"].astype(str).str.strip().ne("").sum()),
                    "suborders": int(
                        results["Sub Order No"].astype(str).str.strip().ne("").sum()
                    ),
                    "packets": int(
                        results["Packet Id"].astype(str).str.strip().ne("").sum()
                    ),
                    "matched": matched_count,
                    "unmatched": int(total - matched_count),
                }

                # Limit each login session to its most recent 20 downloadable jobs.
                jobs = session.get("jobs", [])
                jobs.append(job_id)
                session["jobs"] = jobs[-20:]
                downloads = {
                    "pdf": url_for("download_file", job_id=job_id, kind="pdf"),
                    "excel": url_for("download_file", job_id=job_id, kind="excel"),
                }

            except Exception as exc:
                app.logger.exception("QR generation failed")
                flash(f"Could not process files: {exc}", "error")
            finally:
                pdf_path.unlink(missing_ok=True)
                csv_path.unlink(missing_ok=True)

    return render_template(
        "index.html", stats=stats, downloads=downloads
    )


@app.route("/download/<job_id>/<kind>")
def download_file(job_id, kind):
    auth = require_login()
    if auth:
        return auth

    if not job_id.isalnum() or job_id not in session.get("jobs", []):
        abort(404)

    file_map = {
        "pdf": (
            OUTPUT_DIR / f"{job_id}_printable_qr.pdf",
            "meesho_awb_packet_qr_printable.pdf",
        ),
        "excel": (
            OUTPUT_DIR / f"{job_id}_match_report.xlsx",
            "meesho_awb_packet_qr_match_report.xlsx",
        ),
    }
    if kind not in file_map:
        abort(404)

    path, download_name = file_map[kind]
    if not path.is_file():
        flash(
            "This report is no longer available on the server. "
            "Generate it again and download it promptly.",
            "error",
        )
        return redirect(url_for("index"))

    return send_file(path, as_attachment=True, download_name=download_name)


@app.errorhandler(413)
def file_too_large(_error):
    flash("Files are too large. Maximum combined upload size is 100 MB.", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
