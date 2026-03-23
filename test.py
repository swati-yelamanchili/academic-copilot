import unittest
from unittest.mock import patch

import api
import calendar_sync
import main
import scraper
from parser import build_assignment_identity_key


def make_task(**overrides):
    task = {
        "id": "assignment-1",
        "identity_key": "assignment-1",
        "title": "Math - Worksheet 1",
        "raw_title": "Worksheet 1",
        "course": "Math",
        "source_url": "https://courses.iiit.ac.in/mod/assign/view.php?id=101",
        "deadline": "2026-03-23T18:00",
        "datetime": "2026-03-23T18:00",
        "all_day": False,
        "active": True,
        "synced": True,
        "calendar_event_id": None,
    }
    task.update(overrides)
    return task


class FakeRequest:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeEventsResource:
    def __init__(self, get_result=None, list_results=None):
        self.get_result = get_result
        self.list_results = list(list_results or [])
        self.get_calls = []
        self.list_calls = []

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return FakeRequest(self.get_result)

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        result = self.list_results.pop(0) if self.list_results else {"items": []}
        return FakeRequest(result)


class FakeService:
    def __init__(self, events_resource):
        self._events_resource = events_resource

    def events(self):
        return self._events_resource


class FakeBrowser:
    def __init__(self, page):
        self.page = page
        self.closed = False

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, browser):
        self.browser = browser
        self.launch_calls = []

    def launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        return self.browser


class FakePlaywrightContext:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakePage:
    def __init__(self, html="<html></html>", url="https://courses.iiit.ac.in/my/"):
        self._html = html
        self.url = url

    def content(self):
        return self._html


class ParserIdentityTests(unittest.TestCase):
    def test_assignment_identity_is_stable_when_source_url_matches(self):
        first_id = build_assignment_identity_key(
            "/mod/assign/view.php?id=101",
            "Worksheet 1",
            "Math - Worksheet 1",
            "Math",
        )
        updated_id = build_assignment_identity_key(
            "/mod/assign/view.php?id=101",
            "Worksheet 1 Updated",
            "Math - Worksheet 1 Updated",
            "Math",
        )

        self.assertEqual(first_id, updated_id)


class CalendarLookupTests(unittest.TestCase):
    def test_find_event_prefers_saved_calendar_event_id(self):
        events_resource = FakeEventsResource(get_result={"id": "evt-123"})
        service = FakeService(events_resource)

        event = calendar_sync.find_event(
            service,
            make_task(calendar_event_id="evt-123"),
        )

        self.assertEqual(event["id"], "evt-123")
        self.assertEqual(len(events_resource.get_calls), 1)
        self.assertEqual(events_resource.get_calls[0]["eventId"], "evt-123")
        self.assertEqual(events_resource.list_calls, [])

    def test_find_event_falls_back_to_matching_event_details(self):
        task = make_task(calendar_event_id=None)
        matching_event = calendar_sync.build_event(task) | {"id": "evt-456"}
        events_resource = FakeEventsResource(
            list_results=[
                {"items": []},
                {"items": [matching_event]},
            ]
        )
        service = FakeService(events_resource)

        event = calendar_sync.find_event(service, task)

        self.assertEqual(event["id"], "evt-456")
        self.assertEqual(len(events_resource.list_calls), 2)
        self.assertIn("privateExtendedProperty", events_resource.list_calls[0])
        self.assertIn("timeMin", events_resource.list_calls[1])


class ApiTests(unittest.TestCase):
    @patch("api.get_all_assignments")
    def test_next_endpoint_returns_highest_priority_assignment(self, mock_get_all_assignments):
        mock_get_all_assignments.return_value = [
            {
                "title": "Project Demo",
                "course": "SE",
                "datetime": "2099-03-24T18:00",
            },
            {
                "title": "Quiz",
                "course": "Math",
                "datetime": "2099-03-30T18:00",
            },
        ]

        response = api.next_task()

        self.assertEqual(response["title"], "Project Demo")

    @patch("api.run_pipeline")
    def test_sync_endpoint_returns_pipeline_result(self, mock_run_pipeline):
        mock_run_pipeline.return_value = {
            "added": 1,
            "updated": 2,
            "removed": 3,
            "unchanged": 4,
        }

        response = api.sync_now()

        self.assertEqual(
            response,
            {
                "status": "updated",
                "added": 1,
                "updated": 2,
                "removed": 3,
                "unchanged": 4,
            },
        )


class ScraperTests(unittest.TestCase):
    @patch("builtins.input")
    @patch("scraper._wait_for_dashboard", return_value=True)
    @patch("scraper._goto_with_retries")
    @patch("scraper._has_any_selector", return_value=True)
    def test_manual_login_waits_for_dashboard_without_terminal_prompt(
        self,
        mock_has_any_selector,
        mock_goto,
        mock_wait_for_dashboard,
        mock_input,
    ):
        page = FakePage("<html>dashboard</html>")
        browser = FakeBrowser(page)
        playwright_context = FakePlaywrightContext(browser)

        with patch("scraper.sync_playwright", return_value=playwright_context):
            html = scraper.get_dashboard_data(username=None, password=None, headless=False)

        self.assertEqual(html, "<html>dashboard</html>")
        self.assertTrue(browser.closed)
        mock_input.assert_not_called()


class SyncAssignmentsTests(unittest.TestCase):
    @patch("main.mark_synced")
    @patch("main.add_event")
    @patch("main.find_event")
    @patch("main.get_service")
    @patch("main.get_all_assignments")
    def test_sync_assignments_recreates_missing_calendar_event(
        self,
        mock_get_all_assignments,
        mock_get_service,
        mock_find_event,
        mock_add_event,
        mock_mark_synced,
    ):
        task = make_task()
        service = object()

        mock_get_all_assignments.side_effect = [[task], [task]]
        mock_get_service.return_value = service
        mock_find_event.return_value = None
        mock_add_event.return_value = {"id": "evt-new"}

        result = main.sync_assignments([{"id": task["id"]}])

        self.assertEqual(result["added"], [task])
        mock_find_event.assert_called_once_with(service, task)
        mock_add_event.assert_called_once_with(service, task)
        mock_mark_synced.assert_called_once_with(task["id"], "evt-new")

    @patch("main.mark_synced")
    @patch("main.update_event")
    @patch("main.event_needs_update")
    @patch("main.find_event")
    @patch("main.get_service")
    @patch("main.get_all_assignments")
    def test_sync_assignments_updates_existing_calendar_event(
        self,
        mock_get_all_assignments,
        mock_get_service,
        mock_find_event,
        mock_event_needs_update,
        mock_update_event,
        mock_mark_synced,
    ):
        task = make_task(calendar_event_id="evt-existing")
        service = object()
        existing_event = {"id": "evt-existing"}

        mock_get_all_assignments.side_effect = [[task], [task]]
        mock_get_service.return_value = service
        mock_find_event.return_value = existing_event
        mock_event_needs_update.return_value = True
        mock_update_event.return_value = {"id": "evt-existing"}

        result = main.sync_assignments([{"id": task["id"]}])

        self.assertEqual(result["updated"], [task])
        mock_find_event.assert_called_once_with(service, task)
        mock_event_needs_update.assert_called_once_with(task, existing_event)
        mock_update_event.assert_called_once_with(service, "evt-existing", task)
        mock_mark_synced.assert_called_once_with(task["id"], "evt-existing")

    @patch("main.mark_synced")
    @patch("main.mark_inactive")
    @patch("main.delete_event")
    @patch("main.event_needs_update")
    @patch("main.find_event")
    @patch("main.get_service")
    @patch("main.get_all_assignments")
    def test_sync_assignments_deletes_removed_assignments(
        self,
        mock_get_all_assignments,
        mock_get_service,
        mock_find_event,
        mock_event_needs_update,
        mock_delete_event,
        mock_mark_inactive,
        mock_mark_synced,
    ):
        current_task = make_task(id="assignment-1", identity_key="assignment-1")
        stale_task = make_task(
            id="assignment-2",
            identity_key="assignment-2",
            title="Physics - Old Lab",
            raw_title="Old Lab",
            source_url="https://courses.iiit.ac.in/mod/assign/view.php?id=202",
            calendar_event_id="evt-stale",
        )
        service = object()

        mock_get_all_assignments.side_effect = [
            [current_task, stale_task],
            [current_task],
        ]
        mock_get_service.return_value = service
        mock_find_event.side_effect = [
            {"id": "evt-stale"},
            {"id": "evt-current"},
        ]
        mock_event_needs_update.return_value = False

        result = main.sync_assignments([{"id": current_task["id"]}])

        self.assertEqual(result["removed"], [stale_task])
        mock_delete_event.assert_called_once_with(service, "evt-stale")
        mock_mark_inactive.assert_called_once_with(stale_task["id"])
        mock_mark_synced.assert_called_once_with(current_task["id"], "evt-current")


if __name__ == "__main__":
    unittest.main()
