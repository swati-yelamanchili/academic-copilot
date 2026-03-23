# 🎓 Academic Copilot

Academic Copilot is a local browser extension and Python backend that automatically tracks your academic assignments, ranks them by priority and urgency, syncs them directly to Google Calendar, and allows you to view associated assignment PDFs.

> **Note:** This project is designed specifically to match the IIIT Hyderabad college Moodle structure for scraping assignments. You may need to adapt the Playwright scraper in `scraper.py` if you intend to use it with other university portals.

Designed to keep you on top of your coursework without manual data entry, it seamlessly aggregates your tasks into one unified dashboard.

---

## ✨ Features

- **✅ Automated Assignment Scraping**: Headless browser extraction of your upcoming assignments directly from your university portal.
- **🧠 Smart Ranking Algorithm**: Calculates an urgency and effort score to prioritize your focus automatically.
- **📅 Google Calendar Sync**: Pushes assignments to your Google Calendar as events, keeping your schedule up to date.
- **🧩 Browser Extension**: A sleek, dark-mode inspired Chrome/Edge extension to quickly view your next highest-priority task, its deadline, and a direct link to the assignment PDF.

---

## 🚀 Installation & Setup

Follow these steps to run Academic Copilot on your local machine.

### 1. Requirements

- **Python 3.10+** (Python 3.12 is recommended).
- **Google Cloud Platform account** (for Calendar Sync).
- A Chromium-based browser (Chrome, Edge, Brave) to load the extension.

### 2. Environment Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/academic-copilot.git
   cd academic-copilot
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv app
   source app/bin/activate  # On MacOS/Linux
   # On Windows: app\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirement.txt
   ```

4. **Install Playwright Browsers:**
   Since Academic Copilot uses Playwright to scrape your portal, you need to install the Chromium browser engine:
   ```bash
   playwright install chromium
   ```

---

## 🔒 Configuration

You need to provide credentials for both the university portal scraper and Google Calendar sync.

### 1. Environment Variables (`.env`)

Create a `.env` file in the root directory. This securely stores your university login credentials so the headless scraper can access your portal.

Add the following lines to your `.env` file:
```env
# Your university portal login credentials
ACADEMIC_COPILOT_USERNAME=your_student_username
ACADEMIC_COPILOT_PASSWORD=your_student_password

# Optional: Run the browser visibly for debugging (set to true or false)
ACADEMIC_COPILOT_HEADLESS=true
```

> **Note:** The `.env` file is included in `.gitignore` and will never be committed to GitHub.

### 2. Google Calendar Sync (`credentials.json`)

To sync tasks to Google Calendar:
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project and enable the **Google Calendar API**.
3. Go to **Credentials** > **Create Credentials** > **OAuth client ID**.
4. Choose **Desktop App** as the application type.
5. Download the JSON credentials file and rename it to `credentials.json`.
6. Place `credentials.json` in the root of the project directory.

*Note: On your first run, the app will open a browser window asking you to authenticate with your Google account. It will then save a `token.json` file locally for future runs.*

### 3. Playwright Session (`state.json`)

The backend securely saves your authenticated university portal session in a local `state.json` file. This prevents the need to log in manually every time the scraper runs. This file is also git-ignored.

---

## 🛠️ Usage

### 1. Running the Backend Server

Academic Copilot relies on a local FastAPI backend to feed data to the browser extension.

```bash
# Ensure your virtual environment is activated
source app/bin/activate

# Run the backend server
uvicorn api:app --reload
# or natively via Python:
# python api.py
```
The server will now be running at `http://127.0.0.1:8000`.

### 2. Loading the Extension

1. Open your Chromium-based browser (Chrome, Edge, Brave).
2. Navigate to your extensions page (`chrome://extensions/` or `edge://extensions/`).
3. Toggle **Developer mode** on (usually in the top right corner).
4. Click **Load unpacked**.
5. Select the `extension` folder located inside this repository.

### 3. Using the Extension

- Click the **Academic Copilot** icon in your browser toolbar.
- The sleek popup will display your top-priority assignment and its deadline.
- Click **Sync** to trigger the backend to scrape new assignments and sync them with Google Calendar.
- Click **Read PDF** to directly open the assignment instructions.
- Click **Mark Complete** to remove the task from your prioritized list.

### 4. Running Automatically on Linux Startup (Optional)

To have the Academic Copilot backend start automatically in the background when your Linux computer boots, you can create a `systemd` service.

1. Create a service file:
   ```bash
   sudo nano /etc/systemd/system/academic-copilot.service
   ```

2. Add the following configuration (replace `/path/to/academic-copilot` with your actual absolute directory path and `your_username` with your Linux username):
   ```ini
   [Unit]
   Description=Academic Copilot API Backend
   After=network.target

   [Service]
   User=your_username
   WorkingDirectory=/path/to/academic-copilot
   ExecStart=/path/to/academic-copilot/app/bin/uvicorn api:app --host 127.0.0.1 --port 8000
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable academic-copilot.service
   sudo systemctl start academic-copilot.service
   ```

Now the backend will quietly run in the background automatically whenever your machine is on!

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!
Feel free to check out the [issues page](../../issues).

## 📝 License

This project is open-source and available under the terms of the MIT License.
