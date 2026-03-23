import os

from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError, sync_playwright

load_dotenv()

DASHBOARD_URL = "https://courses.iiit.ac.in/my/"
USERNAME_ENV = "ACADEMIC_COPILOT_USERNAME"
PASSWORD_ENV = "ACADEMIC_COPILOT_PASSWORD"
HEADLESS_ENV = "ACADEMIC_COPILOT_HEADLESS"
NAVIGATION_RETRY_ERRORS = (
    "ERR_NETWORK_CHANGED",
    "ERR_CONNECTION_RESET",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_TIMED_OUT",
)
# Selectors that indicate the dashboard shell has loaded (container present)
DASHBOARD_SHELL_SELECTORS = [
    "section.block_timeline",
    '[data-region="event-list-container"]',
    '[data-region="event-list-wrapper"]',
]
# Selectors that indicate the timeline's AJAX content has finished loading
# (actual task items OR the Moodle empty-state indicators)
DASHBOARD_CONTENT_SELECTORS = [
    '[data-region="event-list-item"]',
    # Moodle renders .empty-message / .no-events / similar nodes when list is empty
    '.block_timeline [data-region="empty-message"]',
    '.block_timeline [data-region="no-events-message"]',
    '.block_timeline .empty-placeholder',
    # The event-list-wrapper is only injected after AJAX; unlike event-list-container
    '[data-region="event-list-wrapper"]',
]
LOGIN_SELECTORS = [
    'input[name="username"]',
    'input[type="email"]',
    'input[type="password"]',
    'button[type="submit"]',
]


def _has_any_selector(page, selectors):
    try:
        return page.evaluate(
            """
            (selectorList) => selectorList.some((selector) => document.querySelector(selector))
            """,
            selectors,
        )
    except PlaywrightError:
        return False


def _wait_for_dashboard(page, timeout_ms=300000, poll_ms=1000, ajax_wait_ms=15000):
    """Two-phase wait:
    1. Wait for the dashboard shell (container) to appear.
    2. Wait for AJAX content (actual task items or empty-state) to populate.
    """
    elapsed = 0

    # Phase 1: wait for dashboard shell
    while elapsed < timeout_ms:
        if _has_any_selector(page, DASHBOARD_SHELL_SELECTORS + DASHBOARD_CONTENT_SELECTORS):
            break
        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms
    else:
        return False

    # Phase 2: wait for AJAX-populated content (task items or empty state)
    ajax_elapsed = 0
    while ajax_elapsed < ajax_wait_ms:
        if _has_any_selector(page, DASHBOARD_CONTENT_SELECTORS):
            return True
        page.wait_for_timeout(poll_ms)
        ajax_elapsed += poll_ms

    # If we timed out waiting for AJAX content, still return True if shell was found
    # (the timeline might be empty and use a selector we didn't anticipate)
    return True


def _goto_with_retries(page, url, retries=4, delay_ms=1500):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return
        except PlaywrightError as exc:
            last_error = exc
            message = str(exc)
            is_retryable = any(token in message for token in NAVIGATION_RETRY_ERRORS)

            if not is_retryable or attempt == retries:
                break

            print(
                f"Navigation attempt {attempt}/{retries} hit a transient network error. "
                "Retrying..."
            )
            page.wait_for_timeout(delay_ms)

    if last_error is not None and not any(
        token in str(last_error) for token in NAVIGATION_RETRY_ERRORS
    ):
        raise RuntimeError(
            f"Could not open the IIIT dashboard: {last_error}"
        ) from last_error

    raise RuntimeError(
        "Could not open the IIIT dashboard because the network changed during page load. "
        "Please make sure your connection is stable, then rerun the scraper."
    ) from last_error


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _login_with_credentials(page, username, password):
    username_input = page.locator('input[name="username"], input[type="email"]').first
    password_input = page.locator('input[type="password"]').first

    if username_input.count() == 0 or password_input.count() == 0:
        return False

    username_input.fill(username)
    password_input.fill(password)

    submit_button = page.locator('button[type="submit"], input[type="submit"]').first
    if submit_button.count():
        submit_button.click()
    else:
        password_input.press("Enter")

    return True


def get_dashboard_data(username=None, password=None, headless=None):
    username = username or os.getenv(USERNAME_ENV)
    password = password or os.getenv(PASSWORD_ENV)
    if headless is None:
        headless = _env_flag(HEADLESS_ENV, default=bool(username and password))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        closed = False

        try:
            _goto_with_retries(page, DASHBOARD_URL)
            login_required = _has_any_selector(page, LOGIN_SELECTORS)

            if login_required and username and password:
                print("Attempting automated portal login.")
                if not _login_with_credentials(page, username, password):
                    raise RuntimeError(
                        "Could not find the login form fields needed for automated sign-in."
                    )
            elif login_required:
                print(
                    "Complete the login flow in the opened browser. "
                    "The scraper will continue automatically as soon as the dashboard appears."
                )

            if not _wait_for_dashboard(page):
                print(f"Current URL when detection failed: {page.url}")
                raise RuntimeError(
                    "Could not detect the dashboard timeline after login. "
                    "The browser stayed open until detection finished, but the page "
                    "did not expose the expected timeline elements."
                )

            print("Dashboard timeline detected.")
            context = page.context
            context.storage_state(path="state.json")
            print("Session saved to state.json")
            html = page.content()

            # Extract all assignment links from the dashboard
            from bs4 import BeautifulSoup
            from parser import BASE_PORTAL_URL
            from urllib.parse import urljoin

            soup = BeautifulSoup(html, "html.parser")
            assign_links = [
                urljoin(BASE_PORTAL_URL, a["href"])
                for a in soup.select('[data-region="event-list-item"] a[href]')
                if "mod/assign" in a.get("href", "")
            ]

            # Visit each assignment page to find its PDF link
            pdf_map = {}  # source_url -> pdf_url
            for assign_url in assign_links:
                try:
                    assign_page = context.new_page()
                    assign_page.goto(assign_url, wait_until="domcontentloaded", timeout=30000)
                    assign_page.wait_for_timeout(2000)

                    for a in assign_page.query_selector_all("a"):
                        href = a.get_attribute("href") or ""
                        if "pluginfile.php" in href and (
                            ".pdf" in href.lower() or "forcedownload" in href
                        ):
                            pdf_map[assign_url] = href
                            break

                    assign_page.close()
                except Exception as exc:
                    print(f"Could not get PDF for {assign_url}: {exc}")

            browser.close()
            closed = True
            return html, pdf_map
        finally:
            if not closed:
                browser.close()
