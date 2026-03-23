import sqlite3

from parser import build_assignment_dedupe_key, build_assignment_identity_key

DB_PATH = "tasks.db"


def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assignments (
            id TEXT PRIMARY KEY,
            title TEXT,
            course TEXT,
            datetime TEXT,
            synced INTEGER DEFAULT 0
        )
        """
    )

    for statement in (
        "ALTER TABLE assignments ADD COLUMN dedupe_key TEXT",
        "ALTER TABLE assignments ADD COLUMN raw_title TEXT",
        "ALTER TABLE assignments ADD COLUMN deadline TEXT",
        "ALTER TABLE assignments ADD COLUMN all_day INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE assignments ADD COLUMN calendar_event_id TEXT",
        "ALTER TABLE assignments ADD COLUMN identity_key TEXT",
        "ALTER TABLE assignments ADD COLUMN source_url TEXT",
        "ALTER TABLE assignments ADD COLUMN active INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE assignments ADD COLUMN pdf_url TEXT",
    ):
        try:
            cur.execute(statement)
        except sqlite3.OperationalError:
            pass

    try:
        cur.execute("UPDATE assignments SET raw_title = title WHERE raw_title IS NULL")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("UPDATE assignments SET deadline = datetime WHERE deadline IS NULL")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("UPDATE assignments SET datetime = deadline WHERE datetime IS NULL")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("UPDATE assignments SET active = 1 WHERE active IS NULL")
    except sqlite3.OperationalError:
        pass

    cur.execute(
        """
        SELECT
            rowid,
            id,
            title,
            raw_title,
            course,
            source_url,
            COALESCE(deadline, datetime),
            all_day,
            synced,
            calendar_event_id,
            COALESCE(active, 1)
        FROM assignments
        ORDER BY rowid
        """
    )
    rows = cur.fetchall()

    survivors = {}
    duplicate_rowids = []

    for row in rows:
        (
            rowid,
            assignment_id,
            title,
            raw_title,
            course,
            source_url,
            deadline_value,
            all_day,
            synced,
            calendar_event_id,
            active,
        ) = row

        identity_key = build_assignment_identity_key(source_url, raw_title, title, course)
        dedupe_key = build_assignment_dedupe_key(raw_title, title, course, deadline_value)

        if identity_key not in survivors:
            survivors[identity_key] = {
                "rowid": rowid,
                "id": identity_key,
                "identity_key": identity_key,
                "title": title,
                "raw_title": raw_title,
                "course": course,
                "source_url": source_url,
                "deadline": deadline_value,
                "all_day": all_day or 0,
                "calendar_event_id": calendar_event_id,
                "synced": synced or 0,
                "active": active or 0,
                "dedupe_key": dedupe_key,
                "has_duplicates": False,
            }
            continue

        duplicate_rowids.append(rowid)
        survivor = survivors[identity_key]
        survivor["title"] = title
        survivor["raw_title"] = raw_title
        survivor["course"] = course
        survivor["source_url"] = source_url or survivor["source_url"]
        survivor["deadline"] = deadline_value
        survivor["all_day"] = all_day or 0
        survivor["calendar_event_id"] = calendar_event_id or survivor["calendar_event_id"]
        survivor["active"] = int(bool(survivor["active"] or active))
        survivor["synced"] = 0
        survivor["dedupe_key"] = dedupe_key
        survivor["has_duplicates"] = True

    for survivor in survivors.values():
        cur.execute(
            """
            UPDATE assignments
            SET
                id = ?,
                identity_key = ?,
                dedupe_key = ?,
                title = ?,
                raw_title = ?,
                course = ?,
                source_url = ?,
                datetime = ?,
                deadline = ?,
                all_day = ?,
                calendar_event_id = ?,
                synced = ?,
                active = ?
            WHERE rowid = ?
            """,
            (
                survivor["id"],
                survivor["identity_key"],
                survivor["dedupe_key"],
                survivor["title"],
                survivor["raw_title"],
                survivor["course"],
                survivor["source_url"],
                survivor["deadline"],
                survivor["deadline"],
                survivor["all_day"],
                survivor["calendar_event_id"],
                0 if survivor["has_duplicates"] else survivor["synced"],
                survivor["active"],
                survivor["rowid"],
            ),
        )

    for rowid in duplicate_rowids:
        cur.execute("DELETE FROM assignments WHERE rowid = ?", (rowid,))

    cur.execute("DROP INDEX IF EXISTS idx_assignments_dedupe_key")
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_assignments_dedupe_key
        ON assignments(dedupe_key)
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_assignments_identity_key
        ON assignments(identity_key)
        """
    )

    conn.commit()
    conn.close()


def insert_assignment(assignment, db_path=DB_PATH):
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

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    if source_url and identity_key != legacy_identity_key:
        cur.execute(
            """
            UPDATE assignments
            SET
                id = ?,
                identity_key = ?,
                source_url = COALESCE(source_url, ?),
                synced = 0
            WHERE identity_key = ?
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)
        ON CONFLICT(identity_key) DO UPDATE SET
            id = excluded.id,
            dedupe_key = excluded.dedupe_key,
            title = excluded.title,
            raw_title = excluded.raw_title,
            course = excluded.course,
            source_url = COALESCE(excluded.source_url, assignments.source_url),
            datetime = excluded.datetime,
            deadline = excluded.deadline,
            all_day = excluded.all_day,
            active = 1,
            synced = CASE
                WHEN assignments.title != excluded.title
                  OR COALESCE(assignments.raw_title, '') != COALESCE(excluded.raw_title, '')
                  OR COALESCE(assignments.course, '') != COALESCE(excluded.course, '')
                  OR COALESCE(assignments.source_url, '') != COALESCE(COALESCE(excluded.source_url, assignments.source_url), '')
                  OR COALESCE(assignments.deadline, assignments.datetime, '') != COALESCE(excluded.deadline, '')
                  OR COALESCE(assignments.all_day, 0) != COALESCE(excluded.all_day, 0)
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
    conn.close()

    assignment["id"] = identity_key
    assignment["identity_key"] = identity_key
    assignment["dedupe_key"] = dedupe_key
    return assignment


def get_all_assignments(active_only=False, db_path=DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

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

    conn.close()
    return rows


def mark_synced(task_id, calendar_event_id=None, db_path=DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    if calendar_event_id:
        cur.execute(
            """
            UPDATE assignments
            SET synced = 1, active = 1, calendar_event_id = ?
            WHERE id = ?
            """,
            (calendar_event_id, task_id),
        )
    else:
        cur.execute(
            "UPDATE assignments SET synced = 1, active = 1 WHERE id = ?",
            (task_id,),
        )
    conn.commit()
    conn.close()


def mark_inactive(task_id, db_path=DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE assignments
        SET active = 0, synced = 0, calendar_event_id = NULL
        WHERE id = ?
        """,
        (task_id,),
    )
    conn.commit()
    conn.close()


def save_pdf_url(task_id, pdf_url, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "UPDATE assignments SET pdf_url = ? WHERE id = ?",
        (pdf_url, task_id),
    )
    conn.commit()
    conn.close()
