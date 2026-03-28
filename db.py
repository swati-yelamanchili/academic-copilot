import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from parser import build_assignment_dedupe_key, build_assignment_identity_key

load_dotenv()

def get_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set in .env")
    return psycopg2.connect(db_url)


def init_db():
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS assignments (
                id TEXT PRIMARY KEY,
                title TEXT,
                course TEXT,
                datetime TEXT,
                synced INTEGER DEFAULT 0,
                dedupe_key TEXT,
                raw_title TEXT,
                deadline TEXT,
                all_day INTEGER NOT NULL DEFAULT 0,
                calendar_event_id TEXT,
                identity_key TEXT UNIQUE,
                source_url TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                pdf_url TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_assignments_dedupe_key
            ON assignments(dedupe_key)
            """
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_assignment(assignment):
    deadline = assignment.get("deadline") or assignment.get("datetime")
    if not deadline:
        raise ValueError("assignment deadline is required before insert")

    source_url = assignment.get("source_url")
    identity_key = assignment.get("identity_key") or build_assignment_identity_key(
        source_url,
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
    legacy_identity_key = build_assignment_identity_key(
        None,
        assignment.get("raw_title"),
        assignment.get("title"),
        assignment.get("course"),
    )

    conn = get_connection()
    try:
        cur = conn.cursor()

        if source_url and identity_key != legacy_identity_key:
            cur.execute(
                """
                UPDATE assignments
                SET
                    id = %s,
                    identity_key = %s,
                    source_url = COALESCE(source_url, %s),
                    synced = 0
                WHERE identity_key = %s
                  AND (source_url IS NULL OR source_url = '')
                """,
                (identity_key, identity_key, source_url, legacy_identity_key),
            )

        cur.execute(
            """
            INSERT INTO assignments (
                id,
                identity_key,
                dedupe_key,
                title,
                raw_title,
                course,
                source_url,
                datetime,
                deadline,
                all_day,
                active,
                synced
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 0)
            ON CONFLICT(identity_key) DO UPDATE SET
                id = EXCLUDED.id,
                dedupe_key = EXCLUDED.dedupe_key,
                title = EXCLUDED.title,
                raw_title = EXCLUDED.raw_title,
                course = EXCLUDED.course,
                source_url = COALESCE(EXCLUDED.source_url, assignments.source_url),
                datetime = EXCLUDED.datetime,
                deadline = EXCLUDED.deadline,
                all_day = EXCLUDED.all_day,
                active = 1,
                synced = CASE
                    WHEN assignments.title != EXCLUDED.title
                      OR COALESCE(assignments.raw_title, '') != COALESCE(EXCLUDED.raw_title, '')
                      OR COALESCE(assignments.course, '') != COALESCE(EXCLUDED.course, '')
                      OR COALESCE(assignments.source_url, '') != COALESCE(COALESCE(EXCLUDED.source_url, assignments.source_url), '')
                      OR COALESCE(assignments.deadline, assignments.datetime, '') != COALESCE(EXCLUDED.deadline, '')
                      OR COALESCE(assignments.all_day, 0) != COALESCE(EXCLUDED.all_day, 0)
                      OR COALESCE(assignments.active, 1) != 1
                    THEN 0
                    ELSE assignments.synced
                END
            """,
            (
                identity_key,
                identity_key,
                dedupe_key,
                assignment["title"],
                assignment.get("raw_title"),
                assignment.get("course"),
                source_url,
                deadline,
                deadline,
                int(bool(assignment.get("all_day", False))),
            ),
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    assignment["id"] = identity_key
    assignment["identity_key"] = identity_key
    assignment["dedupe_key"] = dedupe_key
    return assignment


def get_all_assignments(active_only=False):
    init_db()
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        where_clause = "WHERE active = 1" if active_only else ""
        cur.execute(
            f"""
            SELECT
                id,
                identity_key,
                dedupe_key,
                title,
                raw_title,
                course,
                source_url,
                pdf_url,
                COALESCE(deadline, datetime) AS deadline,
                COALESCE(deadline, datetime) AS datetime,
                all_day,
                calendar_event_id,
                active,
                synced
            FROM assignments
            {where_clause}
            ORDER BY COALESCE(deadline, datetime)
            """
        )

        rows = []
        for row in cur.fetchall():
            assignment = dict(row)
            assignment["all_day"] = bool(assignment["all_day"])
            assignment["active"] = bool(assignment["active"])
            assignment["synced"] = bool(assignment["synced"])
            rows.append(assignment)

        return rows
    finally:
        conn.close()


def mark_synced(task_id, calendar_event_id=None):
    init_db()
    conn = get_connection()
    try:
        cur = conn.cursor()

        if calendar_event_id:
            cur.execute(
                """
                UPDATE assignments
                SET synced = 1, active = 1, calendar_event_id = %s
                WHERE id = %s
                """,
                (calendar_event_id, task_id),
            )
        else:
            cur.execute(
                "UPDATE assignments SET synced = 1, active = 1 WHERE id = %s",
                (task_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_inactive(task_id):
    init_db()
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE assignments
            SET active = 0, synced = 0, calendar_event_id = NULL
            WHERE id = %s
            """,
            (task_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_pdf_url(task_id, pdf_url):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE assignments SET pdf_url = %s WHERE id = %s",
            (pdf_url, task_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_user_db():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            moodle_user TEXT,
            moodle_pass BYTEA
        )
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_user_credentials(email, moodle_user, moodle_pass):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (email, moodle_user, moodle_pass)
            VALUES (%s, %s, %s)
            ON CONFLICT(email) DO UPDATE SET
                moodle_user = EXCLUDED.moodle_user,
                moodle_pass = EXCLUDED.moodle_pass
        """, (email, moodle_user, moodle_pass))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_primary_user_credentials():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT moodle_user, moodle_pass FROM users LIMIT 1")
        row = cur.fetchone()
        if row:
            # psycopg2 returns BYTEA as memoryview; convert to bytes for Fernet
            return row[0], bytes(row[1]) if row[1] else None
        return None, None
    finally:
        conn.close()


def get_user_credentials(email):
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT moodle_user, moodle_pass FROM users WHERE email=%s",
            (email,)
        )

        row = cur.fetchone()

        if row:
            # psycopg2 returns BYTEA as memoryview; convert to bytes for Fernet
            return row[0], bytes(row[1]) if row[1] else None

        return None, None
    finally:
        conn.close()

def init_config_db():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def save_google_token(token_json):
    init_config_db()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO system_config (key, value) VALUES ('google_token', %s)
            ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value
        """, (token_json,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_google_token():
    init_config_db()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM system_config WHERE key = 'google_token'")
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()