import datetime
import os

from dotenv import load_dotenv

load_dotenv()  # reads your .env file

def urgency_score(dt_str):
    if not dt_str:
        return 0

    deadline = datetime.datetime.fromisoformat(dt_str)
    # Use tz-aware now() if the stored deadline is tz-aware, to avoid TypeError
    if deadline.tzinfo is not None:
        now = datetime.datetime.now(datetime.timezone.utc)
    else:
        now = datetime.datetime.now()

    delta = (deadline - now).total_seconds() / 3600  # hours

    if delta < 0:
        return 5   # overdue = max urgency

    elif delta < 24:
        return 4   # due today

    elif delta < 72:
        return 3   # next 3 days

    elif delta < 120:
        return 2   # next 5 days

    else:
        return 1   # far away


def estimate_effort(title):
    t = title.lower()

    if "project" in t:
        return "High"
    elif "assignment" in t:
        return "Medium"
    else:
        return "Low"
    
def priority_score(urgency, effort, overdue=False):
    effort_map = {
        "Low": 1,
        "Medium": 2,
        "High": 3
    }

    base = urgency * effort_map.get(effort, 1)

    if overdue:
        base += 5   # strong penalty

    return base




def get_pdf_url(assign_url):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state="state.json")
        page = context.new_page()

        page.goto(assign_url)
        page.wait_for_timeout(3000)

        # Search all links on the page for instructor-attached PDFs
        links = page.query_selector_all("a")

        for link in links:
            href = link.get_attribute("href") or ""

            if "pluginfile.php" in href and ".pdf" in href.lower():
                browser.close()
                return href

        browser.close()
        return None


def download_pdf_with_session(pdf_url):
    """Download a PDF that requires authentication, using the saved Playwright session."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state="state.json")
        page = context.new_page()

        # Use the authenticated session to fetch the PDF bytes directly
        response = page.request.get(pdf_url)
        pdf_bytes = response.body()

        browser.close()
        return pdf_bytes


from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("ENCRYPTION_KEY").encode()
fernet = Fernet(key)

def encrypt(text):
    return fernet.encrypt(text.encode())

def decrypt(token):
    # psycopg2 returns BYTEA as memoryview; coerce to bytes before decrypting
    if isinstance(token, memoryview):
        token = bytes(token)
    elif isinstance(token, str):
        token = token.encode()
    return fernet.decrypt(token).decode()