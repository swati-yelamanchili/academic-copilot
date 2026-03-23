import datetime
import os
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]
REMINDER_MINUTES = [180, 720, 1440, 4320]
CALENDAR_ID = "primary"
CALENDAR_TIMEZONE = "Asia/Kolkata"
PRIVATE_ASSIGNMENT_KEY = "assignment_id"
PRIVATE_SOURCE_URL_KEY = "source_url"
TOKEN_PATH = "token.json"


def get_service():
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def _coerce_task_datetime(task):
    dt = task.get("deadline") or task["datetime"]

    if isinstance(dt, str):
        start = datetime.datetime.fromisoformat(dt)
    else:
        start = dt

    if start.tzinfo is None:
        start = start.replace(tzinfo=ZoneInfo(CALENDAR_TIMEZONE))

    return start


def _build_event_description(task):
    course = task.get("course") or "Assignment"
    description = f"{course} (Auto-added)"
    if task.get("source_url"):
        description = f"{description}\n{task['source_url']}"
    return description


def _build_private_properties(task):
    properties = {
        PRIVATE_ASSIGNMENT_KEY: task["id"],
    }
    if task.get("source_url"):
        properties[PRIVATE_SOURCE_URL_KEY] = task["source_url"]
    return properties


def build_event(task):
    start = _coerce_task_datetime(task)
    end = start + datetime.timedelta(hours=1)

    return {
        "summary": task["title"],
        "description": _build_event_description(task),
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": CALENDAR_TIMEZONE,
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": CALENDAR_TIMEZONE,
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": minutes}
                for minutes in REMINDER_MINUTES
            ],
        },
        "extendedProperties": {
            "private": _build_private_properties(task),
        },
    }


def _event_signature(event):
    private_props = event.get("extendedProperties", {}).get("private", {})
    reminders = event.get("reminders", {}).get("overrides", [])

    return {
        "summary": event.get("summary"),
        "description": event.get("description"),
        "start": event.get("start", {}).get("dateTime"),
        "start_time_zone": event.get("start", {}).get("timeZone"),
        "end": event.get("end", {}).get("dateTime"),
        "end_time_zone": event.get("end", {}).get("timeZone"),
        "assignment_id": private_props.get(PRIVATE_ASSIGNMENT_KEY),
        "source_url": private_props.get(PRIVATE_SOURCE_URL_KEY),
        "reminders": sorted(
            (reminder.get("method"), reminder.get("minutes"))
            for reminder in reminders
        ),
    }


def event_needs_update(task, event):
    expected_event = build_event(task)
    return _event_signature(event) != _event_signature(expected_event)


def add_event(service, task):
    event = build_event(task)
    return service.events().insert(calendarId=CALENDAR_ID, body=event).execute()


def update_event(service, event_id, task):
    event = build_event(task)
    return service.events().update(
        calendarId=CALENDAR_ID,
        eventId=event_id,
        body=event,
    ).execute()


def delete_event(service, event_id):
    if not event_id:
        return

    try:
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    except HttpError as exc:
        if getattr(exc.resp, "status", None) == 404:
            return
        raise


def _get_event_by_id(service, event_id):
    if not event_id:
        return None

    try:
        event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
    except HttpError as exc:
        if getattr(exc.resp, "status", None) == 404:
            return None
        raise

    if event.get("status") == "cancelled":
        return None

    return event


def _find_event_by_assignment_id(service, assignment_id):
    if not assignment_id:
        return None

    response = service.events().list(
        calendarId=CALENDAR_ID,
        privateExtendedProperty=f"{PRIVATE_ASSIGNMENT_KEY}={assignment_id}",
        showDeleted=False,
        maxResults=1,
    ).execute()
    items = response.get("items", [])
    return items[0] if items else None


def _find_event_by_details(service, task):
    start = _coerce_task_datetime(task).astimezone(ZoneInfo(CALENDAR_TIMEZONE))
    window_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = window_start + datetime.timedelta(days=1)
    page_token = None

    while True:
        response = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=window_start.isoformat(),
            timeMax=window_end.isoformat(),
            singleEvents=True,
            showDeleted=False,
            pageToken=page_token,
        ).execute()

        for event in response.get("items", []):
            if not event_needs_update(task, event):
                return event

        page_token = response.get("nextPageToken")
        if not page_token:
            return None


def find_event(service, task):
    event = _get_event_by_id(service, task.get("calendar_event_id"))
    if event:
        return event

    event = _find_event_by_assignment_id(service, task.get("id"))
    if event:
        return event

    return _find_event_by_details(service, task)
