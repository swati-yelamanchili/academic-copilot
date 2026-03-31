import os
import traceback
import json
from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth

from calendar_sync import (
    add_event,
    delete_event,
    event_needs_update,
    find_event,
    get_service,
    update_event,
)
from db import (
    get_all_assignments,
    init_db,
    init_user_db,
    insert_assignment,
    mark_inactive,
    mark_synced,
    save_pdf_url,
    get_user_credentials,
    save_user_credentials,
    get_primary_user_credentials,
    save_google_token,
)
from parser import (
    build_assignment_dedupe_key,
    build_assignment_identity_key,
    extract_assignments,
)
from scraper import get_dashboard_data
from utils import (
    encrypt,
    decrypt,
    urgency_score,
    estimate_effort,
    priority_score
)

from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv(dotenv_path=".env")

# ── Startup env-var check (Checklist #7) ─────────────────────────────
_required_env = ["SECRET_KEY", "DATABASE_URL", "ENCRYPTION_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]
for _var in _required_env:
    _val = os.getenv(_var)
    if _val:
        print(f"[STARTUP] ✅ {_var} is set ({len(_val)} chars)")
    else:
        print(f"[STARTUP] ❌ {_var} is MISSING!")

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.getenv("SECRET_KEY")
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
)

CORS(app, supports_credentials=True, origins=[
    r"chrome-extension://.*",
    "https://academicopilot.onrender.com",
])
print("[STARTUP] CORS configured for chrome-extension://* and academicopilot.onrender.com")
oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

init_user_db()


def persist_assignments(assignments):
    print(f"[PIPELINE] Persisting {len(assignments)} assignments to DB...")
    init_db()
    deduped_assignments = {}

    for assignment in assignments:
        deadline = assignment.get("deadline") or assignment.get("datetime")
        if not deadline:
            print(f"[PIPELINE]   Skipping assignment with no deadline: {assignment.get('title')}")
            continue

        identity_key = assignment.get("identity_key") or build_assignment_identity_key(
            assignment.get("source_url"),
            assignment.get("raw_title"),
            assignment.get("title"),
            assignment.get("course"),
        )
        dedupe_key = assignment.get("dedupe_key") or build_assignment_dedupe_key(
            assignment.get("raw_title"),
            assignment.get("title"),
            assignment.get("course"),
            deadline,
        )
        assignment["identity_key"] = identity_key
        assignment["dedupe_key"] = dedupe_key
        assignment["id"] = identity_key
        deduped_assignments[identity_key] = assignment

    print(f"[PIPELINE] After dedup: {len(deduped_assignments)} unique assignments")
    saved_assignments = []
    for assignment in deduped_assignments.values():
        saved_assignments.append(insert_assignment(assignment))

    print(f"[PIPELINE] Persisted {len(saved_assignments)} assignments to DB")
    return saved_assignments


def _assignment_id(assignment):
    return assignment.get("id") or assignment.get("identity_key") or build_assignment_identity_key(
        assignment.get("source_url"),
        assignment.get("raw_title"),
        assignment.get("title"),
        assignment.get("course"),
    )


def _deactivate_removed_assignments(service, current_assignment_ids):
    stale_tasks = [
        task
        for task in get_all_assignments(active_only=True)
        if task["id"] not in current_assignment_ids
    ]

    removed_tasks = []
    for task in stale_tasks:
        try:
            event = find_event(service, task)
            if event:
                delete_event(service, event.get("id"))
            mark_inactive(task["id"])
            removed_tasks.append(task)
        except Exception:
            print(f"Error deactivating task {task.get('id')}: {traceback.format_exc()}")

    return removed_tasks


def sync_assignments(assignments):
    current_assignment_ids = {_assignment_id(assignment) for assignment in assignments}

    try:
        service = get_service()
    except RuntimeError as e:
        print(f"Google Calendar unavailable: {e}")
        # Return without syncing to calendar — assignments are still saved to DB
        return {
            "added": [],
            "updated": [],
            "removed": [],
            "unchanged": [],
        }

    removed_tasks = _deactivate_removed_assignments(service, current_assignment_ids)
    current_tasks = [
        task
        for task in get_all_assignments(active_only=True)
        if task["id"] in current_assignment_ids
    ]

    added_tasks = []
    updated_tasks = []
    unchanged_tasks = []

    for task in current_tasks:
        try:
            existing_event = find_event(service, task)
            if not existing_event:
                created_event = add_event(service, task)
                mark_synced(task["id"], created_event.get("id"))
                added_tasks.append(task)
                continue

            if event_needs_update(task, existing_event):
                updated_event = update_event(service, existing_event["id"], task)
                mark_synced(task["id"], updated_event.get("id"))
                updated_tasks.append(task)
                continue

            mark_synced(task["id"], existing_event.get("id"))
            unchanged_tasks.append(task)
        except Exception:
            print(f"Error syncing task {task.get('id')}: {traceback.format_exc()}")

    return {
        "added": added_tasks,
        "updated": updated_tasks,
        "removed": removed_tasks,
        "unchanged": unchanged_tasks,
    }


def run_pipeline(username=None, password=None):
    print(f"[PIPELINE] ===== run_pipeline START (user={username}) =====")
    try:
        print("[PIPELINE] Step 1/4: Fetching dashboard from Moodle...")
        html, pdf_map = get_dashboard_data(username=username, password=password)
        print(f"[PIPELINE] Step 1/4: Got HTML ({len(html)} chars), {len(pdf_map)} PDF links")
    except RuntimeError as e:
        print(f"[PIPELINE] Step 1/4: FAILED — {e}")
        return {
            "added": 0,
            "updated": 0,
            "removed": 0,
            "unchanged": 0,
        }

    print("[PIPELINE] Step 2/4: Parsing assignments from HTML...")
    assignments = extract_assignments(html)
    print(f"[PIPELINE] Step 2/4: Parsed {len(assignments)} assignments")

    print("[PIPELINE] Step 3/4: Persisting to database...")
    saved_assignments = persist_assignments(assignments)

    for assignment in saved_assignments:
        url = pdf_map.get(assignment.get("source_url"))
        if url:
            save_pdf_url(assignment["id"], url)

    print("[PIPELINE] Step 4/4: Syncing to Google Calendar...")
    result = sync_assignments(saved_assignments)

    summary = {
        "added": len(result["added"]),
        "updated": len(result["updated"]),
        "removed": len(result["removed"]),
        "unchanged": len(result["unchanged"]),
    }
    print(f"[PIPELINE] ===== run_pipeline DONE: {summary} =====")
    return summary


def _serialize_assignment(row):
    datetime_value = row.get("datetime")
    if not datetime_value:
        return None

    urgency = urgency_score(row["datetime"])
    effort = estimate_effort(row["title"])
    overdue = urgency == 5

    return {
        "title": row["title"],
        "course": row.get("course"),
        "datetime": datetime_value,
        "urgency": urgency,
        "effort": effort,
        "priority": priority_score(urgency, effort, overdue),
    }


def _ranked_assignments():
    items = []
    for row in get_all_assignments(active_only=True):
        item = _serialize_assignment(row)
        if item is not None:
            items.append(item)

    items.sort(key=lambda item: item["priority"], reverse=True)
    return items


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login")
def login():
    nonce = os.urandom(16).hex()
    session["nonce"] = nonce

    return google.authorize_redirect(
        url_for("callback", _external=True),
        nonce=nonce
    )


@app.route("/callback")
def callback():
    token = google.authorize_access_token()
    user = google.parse_id_token(
        token,
        nonce=session.get("nonce")
    )

    session["user"] = user
    return redirect("/setup")


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if "user" not in session:
        return redirect("/")

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        encrypted_password = encrypt(password)
        save_user_credentials(
            email=session["user"]["email"],
            moodle_user=username,
            moodle_pass=encrypted_password
        )

        # Immediately run the pipeline after saving credentials
        try:
            run_pipeline(username, password)
        except Exception as e:
            print(f"Initial sync after setup failed: {e}")

        return render_template("success.html")

    return render_template("setup.html")


@app.route("/api/get-credentials")
def get_credentials():
    print("[API] Request received: /api/get-credentials")
    username, _ = get_primary_user_credentials()

    if not username:
        print("[API] No credentials found → 404")
        return jsonify({"error": "not setup"}), 404

    print(f"[API] Credentials found for user: {username}")
    return jsonify({
        "username": username,
        "password": "***"
    })


@app.route("/api/health")
def health():
    print("[API] Request received: /api/health")
    return jsonify({"status": "ok"})


@app.route("/api/assignments")
def get_assignments():
    print("[API] Request received: /api/assignments")
    items = _ranked_assignments()
    print(f"[API] Returning {len(items)} ranked assignments")
    return jsonify(items)


@app.route("/api/sync", methods=["POST"])
def sync_now():
    print("[API] ===== Request received: POST /api/sync =====")

    data = request.get_json(force=True)
    html = data.get("html")
    pdf_map = data.get("pdf_map", {})

    if not html:
        print("[API] /api/sync → No HTML provided → 400")
        return jsonify({"error": "html is required"}), 400

    print(f"[API] /api/sync → Got HTML ({len(html)} chars), {len(pdf_map)} PDF links from extension")

    # ── Diagnostic: inspect what the parser will see ──
    from bs4 import BeautifulSoup as _BS
    _soup = _BS(html, "html.parser")
    _event_items = _soup.select('[data-region="event-list-item"]')
    _timeline = _soup.select('section.block_timeline, [data-region="event-list-container"], [data-region="event-list-wrapper"]')
    _login_form = _soup.select('input[name="username"], input[type="email"]')
    _all_data_regions = list(set(el.get("data-region") for el in _soup.select("[data-region]")))
    print(f"[DEBUG] event-list-items: {len(_event_items)}, timeline sections: {len(_timeline)}, login forms: {len(_login_form)}")
    print(f"[DEBUG] HTML title: {_soup.title.string if _soup.title else 'N/A'}")
    print(f"[DEBUG] All data-region values found: {_all_data_regions[:30]}")
    if _soup.body:
        _body_text = _soup.body.get_text(" ", strip=True)[:500]
        print(f"[DEBUG] Body text preview: {_body_text}")

    try:
        print("[PIPELINE] Step 1: Parsing assignments from HTML...")
        assignments = extract_assignments(html)
        print(f"[PIPELINE] Step 1: Parsed {len(assignments)} assignments")

        print("[PIPELINE] Step 2: Persisting to database...")
        saved_assignments = persist_assignments(assignments)

        for assignment in saved_assignments:
            url = pdf_map.get(assignment.get("source_url"))
            if url:
                save_pdf_url(assignment["id"], url)

        print("[PIPELINE] Step 3: Syncing to Google Calendar...")
        result = sync_assignments(saved_assignments)

        response = {
            "status": "updated",
            "added": len(result["added"]),
            "updated": len(result["updated"]),
            "removed": len(result["removed"]),
            "unchanged": len(result["unchanged"]),
        }
        print(f"[API] /api/sync → Response: {response}")
        return jsonify(response)
    except Exception as e:
        print(f"[API] /api/sync → FAILED: {e}")
        traceback.print_exc()
        return jsonify({"error": "sync_failed", "message": str(e)}), 500



@app.route("/api/next")
def next_task():
    print("[API] Request received: /api/next")
    rows = get_all_assignments(active_only=True)
    print(f"[API] /api/next → {len(rows)} active assignments in DB")
    result = []
    
    for r in rows:
        item = {
            "id": r["id"],
            "title": r["title"],
            "course": r["course"],
            "datetime": r["datetime"],
            "urgency": urgency_score(r["datetime"]),
            "effort": estimate_effort(r["title"]),
            "pdf_url": r.get("pdf_url"),
            "source_url": r.get("source_url"),
        }
        item["priority"] = priority_score(item["urgency"], item["effort"], overdue=(item["urgency"] == 5))
        result.append(item)

    if not result:
        print("[API] /api/next → No tasks, returning null")
        return jsonify(None)

    result.sort(key=lambda x: x["priority"], reverse=True)
    print(f"[API] /api/next → Top task: {result[0].get('title')} (priority={result[0].get('priority')})")
    return jsonify(result[0])


@app.route("/api/done", methods=["POST"])
def mark_done():
    task_id = request.args.get("task_id")
    print(f"[API] Request received: /api/done (task_id={task_id})")
    if not task_id:
        print("[API] /api/done → Missing task_id → 400")
        return jsonify({"error": "task_id is required"}), 400
    mark_inactive(task_id)
    print(f"[API] /api/done → Task {task_id} marked inactive")
    return jsonify({"status": "ok"})


@app.route("/api/cookies")
def get_cookies():
    print("[API] Request received: /api/cookies")
    if os.path.exists("state.json"):
        with open("state.json", "r") as f:
            state = json.load(f)
            cookies = state.get("cookies", [])
            print(f"[API] /api/cookies → Returning {len(cookies)} cookies from state.json")
            return jsonify({"cookies": cookies})
    print("[API] /api/cookies → No state.json found, returning empty")
    return jsonify({"cookies": []})


@app.route("/api/upload-token", methods=["POST"])
def upload_token():
    """Upload a locally-generated token.json so the server can use it for Calendar sync."""
    data = request.get_json(force=True)
    token_json = data.get("token")
    if not token_json:
        return jsonify({"error": "No token provided"}), 400
    save_google_token(token_json if isinstance(token_json, str) else json.dumps(token_json))
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
