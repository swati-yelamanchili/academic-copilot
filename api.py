from fastapi import FastAPI

from db import get_all_assignments, mark_inactive
from main import run_pipeline
from utils import (
    urgency_score, estimate_effort, priority_score,
)

app = FastAPI()


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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/assignments")
def get_assignments():
    return _ranked_assignments()


@app.get("/sync")
def sync_now():
    result = run_pipeline()
    return {
        "status": "updated",
        **result,
    }

@app.get("/next")
def next_task():
    rows = get_all_assignments(active_only=True)

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

        item["priority"] = priority_score(item["urgency"], item["effort"])
        result.append(item)

    print("RESULT:", result)

    if not result:
        return {}

    result.sort(key=lambda x: x["priority"], reverse=True)

    return result[0]



@app.post("/done")
def mark_done(task_id: str):
    mark_inactive(task_id)
    return {"status": "ok"}




if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
