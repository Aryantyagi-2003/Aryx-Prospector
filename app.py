"""
Aryx Prospector - web app.

Flask backend that lets you upload ANY CSV, map its columns (business name,
website URL, optional status), filter rows, scrape each site for an email
address, and download a clean results CSV.

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

# In-memory job store. Fine for a single-user local tool.
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


@app.route("/")
def index():
    return render_template("index.html")


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

    if df.empty or len(df.columns) == 0:
        os.remove(path)
        return jsonify({"error": "CSV has no columns."}), 400

    preview = df.head(4).fillna("").to_dict(orient="records")

    return jsonify({
        "upload_id": upload_id,
        "columns": list(df.columns),
        "row_count": len(df),
        "preview": preview,
    })


@app.route("/api/column-values", methods=["POST"])
def column_values():
    data = request.get_json(force=True)
    upload_id = data.get("upload_id")
    column = data.get("column")
    path = os.path.join(UPLOAD_DIR, f"{upload_id}.csv")
    if not upload_id or not os.path.isfile(path):
        return jsonify({"error": "Unknown upload_id."}), 404

    df = pd.read_csv(path, dtype=str)
    if column not in df.columns:
        return jsonify({"error": "Unknown column."}), 400

    series = df[column].fillna("").astype(str).str.strip()
    has_blank = series.eq("").any()
    values = sorted({v for v in series if v}, key=str.lower)

    return jsonify({"values": values, "has_blank": bool(has_blank)})


def _run_job(job_id, path, name_col, url_col, status_col, included_statuses, include_blank_status):
    job = JOBS[job_id]
    try:
        df = pd.read_csv(path, dtype=str)

        website = df[url_col].fillna("").astype(str).str.strip()
        has_website = website.ne("") & website.str.lower().ne("no website")

        if status_col and status_col in df.columns:
            status = df[status_col].fillna("").astype(str).str.strip().str.lower()
            is_blank_status = status.eq("")
            included_lower = {s.lower() for s in (included_statuses or [])}
            is_included_value = status.isin(included_lower)
            status_ok = is_included_value | (is_blank_status & include_blank_status)
        else:
            status_ok = pd.Series(True, index=df.index)

        eligible = df[has_website & status_ok].copy()

        job["total"] = len(eligible)
        job["state"] = "running"

        results = []
        for i in range(len(eligible)):
            if job.get("cancelled"):
                job["state"] = "cancelled"
                return

            business_name = eligible.iloc[i][name_col]
            url = normalize_url(eligible.iloc[i][url_col])

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


@app.route("/api/start", methods=["POST"])
def start():
    data = request.get_json(force=True)
    upload_id = data.get("upload_id")
    name_col = data.get("name_col")
    url_col = data.get("url_col")
    status_col = data.get("status_col") or None
    included_statuses = data.get("included_statuses") or []
    include_blank_status = bool(data.get("include_blank_status", True))

    path = os.path.join(UPLOAD_DIR, f"{upload_id}.csv")
    if not upload_id or not os.path.isfile(path):
        return jsonify({"error": "Unknown upload_id."}), 404
    if not name_col or not url_col:
        return jsonify({"error": "name_col and url_col are required."}), 400

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

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, path, name_col, url_col, status_col, included_statuses, include_blank_status),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


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
