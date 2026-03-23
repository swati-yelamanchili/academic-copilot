from calendar_sync import (
    add_event,
    delete_event,
    event_needs_update,
    find_event,
    get_service,
    update_event,
)
from db import get_all_assignments, init_db, insert_assignment, mark_inactive, mark_synced, save_pdf_url
from parser import (
    build_assignment_dedupe_key,
    build_assignment_identity_key,
    extract_assignments,
)
from scraper import get_dashboard_data


def persist_assignments(assignments):
    init_db()
    deduped_assignments = {}

    for assignment in assignments:
        deadline = assignment.get("deadline") or assignment.get("datetime")
        if not deadline:
            print(f"Skipping assignment without deadline: {assignment}")
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

    saved_assignments = []
    for assignment in deduped_assignments.values():
        saved_assignments.append(insert_assignment(assignment))

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
        except Exception as exc:
            print(f"Failed to remove stale assignment {task['title']}: {exc}")

    return removed_tasks


def sync_assignments(assignments):
    current_assignment_ids = {_assignment_id(assignment) for assignment in assignments}
    service = get_service()

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
        except Exception as exc:
            print(f"Failed to sync {task['title']}: {exc}")

    print(
        f"Added {len(added_tasks)} assignments, "
        f"updated {len(updated_tasks)}, "
        f"removed {len(removed_tasks)}, "
        f"left {len(unchanged_tasks)} unchanged."
    )
    return {
        "added": added_tasks,
        "updated": updated_tasks,
        "removed": removed_tasks,
        "unchanged": unchanged_tasks,
    }

def run_pipeline():
    try:
        html, pdf_map = get_dashboard_data()
    except RuntimeError as exc:
        print(exc)
        return {
            "added": 0,
            "updated": 0,
            "removed": 0,
            "unchanged": 0,
        }

    assignments = extract_assignments(html)
    saved_assignments = persist_assignments(assignments)

    # Save PDF URLs discovered during scraping
    for assignment in saved_assignments:
        url = pdf_map.get(assignment.get("source_url"))
        if url:
            save_pdf_url(assignment["id"], url)

    result = sync_assignments(saved_assignments)

    return {
        "added": len(result["added"]),
        "updated": len(result["updated"]),
        "removed": len(result["removed"]),
        "unchanged": len(result["unchanged"]),
    }


def main():
    try:
        html, pdf_map = get_dashboard_data()
    except RuntimeError as exc:
        print(exc)
        return

    assignments = extract_assignments(html)
    saved_assignments = persist_assignments(assignments)

    for assignment in saved_assignments:
        url = pdf_map.get(assignment.get("source_url"))
        if url:
            save_pdf_url(assignment["id"], url)
        print(assignment)

    print(f"Saved {len(saved_assignments)} current assignments to tasks.db")
    sync_assignments(saved_assignments)


if __name__ == "__main__":
    main()

