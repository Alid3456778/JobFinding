import os
import threading
import time

import requests
from flask import Flask, jsonify, render_template, request

from job_automation import JobScraper

app = Flask(__name__)

_self_ping_started = False
_self_ping_lock = threading.Lock()
HARDCODED_RENDER_URL = "https://jobfinding-kvbr.onrender.com"


def parse_int(value, default, minimum=None, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default

    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def get_self_ping_url():
    base_url = (
        os.environ.get("SELF_PING_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("APP_BASE_URL")
        or HARDCODED_RENDER_URL
    )
    if not base_url:
        return None
    normalized = base_url.rstrip("/")
    if normalized.endswith("/health"):
        return normalized
    return f"{normalized}/health"


def self_ping_worker():
    ping_url = get_self_ping_url()
    interval_seconds = parse_int(os.environ.get("SELF_PING_INTERVAL", 600), 600, minimum=60)
    if not ping_url:
        return

    time.sleep(15)
    while True:
        try:
            response = requests.get(ping_url, timeout=10)
            print(f"Self ping -> {response.status_code} {ping_url}")
        except requests.RequestException as exc:
            print(f"Self ping failed: {exc}")
        time.sleep(interval_seconds)


def start_self_ping():
    global _self_ping_started
    if os.environ.get("DISABLE_SELF_PING", "").lower() in {"1", "true", "yes"}:
        return

    if os.environ.get("RENDER", "").lower() not in {"1", "true", "yes"} and not os.environ.get("SELF_PING_URL"):
        return

    if not get_self_ping_url():
        return

    with _self_ping_lock:
        if _self_ping_started:
            return
        thread = threading.Thread(target=self_ping_worker, daemon=True, name="render-self-ping")
        thread.start()
        _self_ping_started = True


@app.before_request
def ensure_background_jobs():
    start_self_ping()


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/", methods=["GET", "POST"])
def index():
    jobs = []
    message = ""
    form_data = {
        "title": "",
        "location": "",
        "max_results": 10,
        "latest_days": 7,
    }
    platform_statuses = []

    if request.method == "POST":
        form_data["title"] = request.form.get("title", "").strip()
        form_data["location"] = request.form.get("location", "").strip()
        form_data["max_results"] = parse_int(request.form.get("max_results"), 10, minimum=1, maximum=50)
        form_data["latest_days"] = parse_int(request.form.get("latest_days"), 7, minimum=0, maximum=365)

        if form_data["title"] and form_data["location"]:
            scraper = JobScraper()
            all_jobs = scraper.scrape_all_sites(
                form_data["title"],
                form_data["location"],
                form_data["max_results"],
            )
            filtered_jobs = scraper.filter_latest_jobs(all_jobs, form_data["latest_days"])
            jobs = filtered_jobs if filtered_jobs else all_jobs
            platform_statuses = scraper.last_run_statuses

            message = (
                f"Found {len(jobs)} jobs for '{form_data['title']}' in "
                f"'{form_data['location']}' across all active platforms"
            )
        else:
            message = "Please enter both a job title and location."

    return render_template(
        "index.html",
        jobs=jobs,
        message=message,
        form_data=form_data,
        platform_statuses=platform_statuses,
        ping_url=get_self_ping_url(),
    )


if __name__ == "__main__":
    start_self_ping()
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
