"""
Aryx Prospector - web app.

Flask backend: upload your CSV (columns "Business Name", "Website / URL",
and "Status"), it automatically filters for eligible rows, scrapes each
site for an email address, and gives you a clean results CSV to download.
No manual column mapping - the expected columns are fixed.

Run with:  python3 app.py
Then open: http://127.0.0.1:5000
"""

import os
import threading
import time
import uuid

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory

from scraper import normalize_url, scrape_email

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB upload cap

# Fixed column names - this is what your CSV is expected to contain.
NAME_COL = "Business Name"
URL_COL = "Website / URL"
STATUS_COL = "Status"

EXCLUDED_STATUSES = {"no deal", "awaiting response", "dead"}
INCLUDED_STATUS = "to contact"

# In-memory job store. Fine for a single-user local tool.
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


@app.route("/")
def index():
    return render_template("index.html")


def _filter_eligible(df: pd.DataFrame) -> pd.DataFrame:
    website = df[URL_COL].fillna("").astype(str).str.strip()
    has_website = website.ne("") & website.str.lower().ne("no website")

    status = df[STATUS_COL].fillna("").astype(str).str.strip().str.lower() if STATUS_COL in df.columns else pd.Series("", index=df.index)
    is_blank_status = status.eq("")
    is_to_contact = status.eq(INCLUDED_STATUS)
    is_excluded = status.isin(EXCLUDED_STATUSES)

    status_ok = (is_to_contact | is_blank_status) & ~is_excluded
    return df[has_website & status_ok].copy()


def _run_job(job_id, path):
    job = JOBS[job_id]
    try:
        df = pd.read_csv(path, dtype=str)
        eligible = _filter_eligible(df)

        job["total"] = len(eligible)
        job["state"] = "running"

        results = []
        for i in range(len(eligible)):
            if job.get("cancelled"):
                job["state"] = "cancelled"
                return

            business_name = eligible.iloc[i][NAME_COL]
            url = normalize_url(eligible.iloc[i][URL_COL])

            job["current"] = business_name
            email, error = scrape_email(url)

            results.append({"Business Name": business_name, "URL": url, "Email": email})
            job["processed"] = i + 1
            job["log"].append({
                "business": str(business_name),
                "url": url,
                "email": email,
                "error": error,
            })
            time.sleep(1)

        out_df = pd.DataFrame(results, columns=["Business Name", "URL", "Email"])
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(OUTPUT_DIR, f"{job_id}.csv")
        out_df.to_csv(out_path, index=False)

        job["found_count"] = sum(1 for r in results if r["Email"])
        job["state"] = "done"
    except Exception as exc:
        job["state"] = "error"
        job["error"] = str(exc)


@app.route("/api/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if file is None or file.filename == "":
        return jsonify({"error": "No file provided."}), 400
    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Please upload a .csv file."}), 400

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    upload_id = uuid.uuid4().hex
    path = os.path.join(UPLOAD_DIR, f"{upload_id}.csv")
    file.save(path)

    try:
        df = pd.read_csv(path, dtype=str)
    except Exception as exc:
        os.remove(path)
        return jsonify({"error": f"Could not parse CSV: {exc}"}), 400

    missing = [c for c in (NAME_COL, URL_COL) if c not in df.columns]
    if missing:
        os.remove(path)
        return jsonify({
            "error": (
                f"Missing required column(s): {', '.join(missing)}. "
                f"Your CSV has: {', '.join(df.columns)}"
            )
        }), 400

    # Kick off scraping immediately - no manual mapping step.
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "state": "starting",
            "processed": 0,
            "total": 0,
            "current": "",
            "log": [],
            "found_count": 0,
            "error": None,
            "cancelled": False,
        }

    thread = threading.Thread(target=_run_job, args=(job_id, path), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "row_count": len(df)})


@app.route("/api/progress/<job_id>")
def progress(job_id):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown job_id."}), 404
    return jsonify({
        "state": job["state"],
        "processed": job["processed"],
        "total": job["total"],
        "current": job["current"],
        "found_count": job["found_count"],
        "error": job["error"],
        "log_tail": job["log"][-10:],
    })


@app.route("/api/cancel/<job_id>", methods=["POST"])
def cancel(job_id):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown job_id."}), 404
    job["cancelled"] = True
    return jsonify({"ok": True})


@app.route("/api/download/<job_id>")
def download(job_id):
    filename = f"{job_id}.csv"
    if not os.path.isfile(os.path.join(OUTPUT_DIR, filename)):
        return jsonify({"error": "Result not ready."}), 404
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True,
                                download_name="Aryx_Prospector_Leads.csv")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
