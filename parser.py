import re
from datetime import datetime, time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import hashlib

BASE_PORTAL_URL = "https://courses.iiit.ac.in/"

def generate_id(title, dt):
    return hashlib.md5((title + str(dt)).encode()).hexdigest()


def build_assignment_identity_key(source_url, raw_title, title, course):
    normalized_source = _normalize_source_url(source_url)
    if normalized_source:
        return hashlib.md5(normalized_source.encode()).hexdigest()

    canonical_title = canonicalize_identity_title(raw_title or title, course)
    if not canonical_title:
        canonical_title = canonicalize_identity_title(title, course)

    course_key = _normalize_spaces(course or "").lower()
    return hashlib.md5(f"{canonical_title}|{course_key}".encode()).hexdigest()


def build_assignment_dedupe_key(raw_title, title, course, deadline):
    canonical_title = canonicalize_identity_title(raw_title or title, course)
    if not canonical_title:
        canonical_title = canonicalize_identity_title(title, course)

    course_key = _normalize_spaces(course or "").lower()
    deadline_key = _normalize_spaces(deadline or "")
    return hashlib.md5(f"{canonical_title}|{course_key}|{deadline_key}".encode()).hexdigest()

TIME_PATTERN = re.compile(r"\b\d{1,2}:\d{2}(?:\s*[APap][Mm])?\b")
COURSE_END_PATTERN = re.compile(
    r"\s+(?:Add submission|Edit submission|View|Open|Closed|Submitted|Submission status)\b.*$",
    re.IGNORECASE,
)
DATE_SUFFIX_PATTERN = re.compile(r"(\d+)(st|nd|rd|th)\b", re.IGNORECASE)
GENERIC_TITLE_PATTERN = re.compile(
    r"^(?:submission(?:\s+on\s+.+)?|submission status|assignment|quiz|exam|lab|project)$",
    re.IGNORECASE,
)


def _clean_text(node):
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def _clean_href(node):
    if node is None:
        return None

    href = (node.get("href") or "").strip()
    if not href:
        return None

    return _normalize_source_url(href)


def _event_text(event):
    return re.sub(r"\s+", " ", event.get_text(" ", strip=True))


def _normalize_spaces(text):
    return re.sub(r"\s+", " ", text).strip()


def _normalize_source_url(source_url):
    normalized = _normalize_spaces(source_url or "")
    if not normalized:
        return None

    return urljoin(BASE_PORTAL_URL, normalized)


def _extract_time(event):
    text = _event_text(event)
    match = TIME_PATTERN.search(text)
    if match:
        return match.group(0)

    if "all day" in text.lower():
        return "All day"

    return None


def _extract_course(event):
    text = _event_text(event)
    match = re.search(r"(?:is due|closes)\s+", text, re.IGNORECASE)

    if not match:
        return None

    course = text[match.end():].strip(" .,-:;|·")
    course = COURSE_END_PATTERN.sub("", course).strip(" .,-:;|·")
    return course or None


def _parse_date(date_text):
    if not date_text:
        return None

    cleaned = DATE_SUFFIX_PATTERN.sub(r"\1", _normalize_spaces(date_text))
    candidates = [cleaned]

    if ", " in cleaned:
        candidates.append(cleaned.split(", ", 1)[1])

    for candidate in candidates:
        for date_format in ("%A, %d %B %Y", "%d %B %Y"):
            try:
                return datetime.strptime(candidate, date_format).date()
            except ValueError:
                continue

    return None


def _parse_time(time_text):
    if not time_text:
        return time(23, 59), True

    cleaned = _normalize_spaces(time_text)
    if cleaned.lower() == "all day":
        return time(23, 59), True

    for time_format in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(cleaned, time_format).time(), False
        except ValueError:
            continue

    return None, False


def _build_deadline(date_text, time_text):
    parsed_date = _parse_date(date_text)
    if parsed_date is None:
        return None, False

    parsed_time, all_day = _parse_time(time_text)
    if parsed_time is None:
        return parsed_date.isoformat(), False

    deadline = datetime.combine(parsed_date, parsed_time).isoformat(timespec="minutes")
    return deadline, all_day


def _normalize_title(raw_title, course):
    title = _normalize_spaces(raw_title).strip(" .,-:;|·")
    lowered = title.lower()

    if course and course.lower() not in lowered:
        if GENERIC_TITLE_PATTERN.match(title):
            return f"{course} submission"
        return f"{course} - {title}"

    return title


def canonicalize_identity_title(title, course=None):
    if not title:
        return ""

    normalized = _normalize_spaces(title).strip(" .,-:;|·")

    if course:
        course_text = _normalize_spaces(course).strip(" .,-:;|·")
        prefix_pattern = re.compile(
            rf"^{re.escape(course_text)}(?:\s*[-:|]\s*|\s+)?",
            re.IGNORECASE,
        )
        normalized = prefix_pattern.sub("", normalized, count=1).strip(" .,-:;|·")

    if GENERIC_TITLE_PATTERN.match(normalized):
        return "submission"

    return normalized.lower()


def extract_assignments(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    events = soup.select('[data-region="event-list-item"]')

    for event in events:
        title_node = event.find("a")
        raw_title = _clean_text(title_node)
        if not raw_title:
            continue

        mod_link = event.find("a", href=lambda h: h and "mod/" in h)
        source_url = _clean_href(mod_link) if mod_link else _clean_href(title_node)
        date_node = event.find_previous(attrs={"data-region": "event-list-content-date"})
        date_text = _clean_text(date_node)
        time_text = _extract_time(event)
        course = _extract_course(event)
        deadline, all_day = _build_deadline(date_text, time_text)
        title = _normalize_title(raw_title, course)
        identity_key = build_assignment_identity_key(source_url, raw_title, title, course)
        dedupe_key = build_assignment_dedupe_key(raw_title, title, course, deadline)

        results.append(
            {
                "id": identity_key,
                "identity_key": identity_key,
                "title": title,
                "raw_title": raw_title,
                "course": course,
                "source_url": source_url,
                "deadline": deadline,
                "datetime": deadline,
                "all_day": all_day,
                "dedupe_key": dedupe_key,
            }
        )

    return results
