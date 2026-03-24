# 🎓 Academic Copilot

Academic Copilot is a cloud-hosted Python backend and local browser extension that automatically tracks your academic assignments, ranks them by priority and effort, syncs them to Google Calendar, and allows you to quickly view associated assignment PDFs.

> **Note:** This project is designed specifically to match the IIIT Hyderabad college Moodle structure for scraping assignments. You may need to adapt the Playwright scraper in `scraper.py` if you intend to use it with other university portals.

---

## ✨ Features

- **✅ Automated Assignment Scraping**: Headless Playwright extraction of your upcoming assignments directly from your university portal.
- **🧠 Smart Ranking Algorithm**: Calculates an urgency and effort score to prioritize your focus automatically.
- **📅 Google Calendar Sync**: Pushes assignments into your Google Calendar as events natively using the Google Calendar API.
- **🧩 Browser Extension**: A sleek Chrome/Edge extension to quickly view your highest-priority tasks, deadlines, and a direct link to the assignment submission page.
- **☁️ Cloud Ready**: Unified Flask architecture backed by PostgreSQL, completely ready to immediately run on Render.

---

## 🚀 Installation & Setup

### 1. Local Development Requirements

- **Python 3.10+** (Python 3.12 recommended).
- **Google Cloud Platform account** (for Calendar Sync).
- **PostgreSQL server** (local or cloud-hosted via Supabase/Neon).

### 2. Environment Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/academic-copilot.git
   cd academic-copilot
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv app
   source app/bin/activate  # On MacOS/Linux (Windows: app\Scripts\activate)
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

---

## 🔒 Configuration

You will need to provide your exact authentication keys and database credentials to your hosting provider (such as Render) during the deployment process.

Place your `credentials.json` (Google Desktop App OAuth file) in the root directory before running or deploying.

---

## 🛠️ Deployment (Render)

This application is architected to deploy flawlessly on [Render](https://render.com) using its free tier.

**Web Service Setup:**
1. Connect your GitHub repository.
2. Select **Python 3** environment.
3. **Build Command**: `pip install -r requirements.txt && playwright install chromium`
4. **Start Command**: `gunicorn main:app`
5. Add all the properties from your `.env` into the Environment Variables table.

---

## 🧩 Loading the Extension

1. After deploying the backend, open `extension/popup.js`.
2. Update the `API_BASE` to match your deployed URL (e.g. `https://your-app.onrender.com/api`).
3. Open your Chromium-based browser and navigate to `chrome://extensions/`.
4. Toggle **Developer mode** on.
5. Click **Load unpacked** and select the `extension` folder.
6. Click the extension icon. If it asks you to connect, it will open your deployed portal to securely sign in with Google and enter your Moodle credentials!

## 🎮 How to Use

Once the extension is installed and your backend is deployed:

1. **Connect Your Account**: Click the Academic Copilot extension icon in your browser. Click **Connect Account**, which will open your deployed website. Log in securely with Google and enter your university Moodle credentials.
2. **View Your Next Priority**: Click the extension icon anytime to instantly see your highest-priority upcoming assignment, automatically ranked by urgency and estimated effort.
3. **Sync Assignments**: Click the **Sync** button in the extension. The backend will quietly log into your university portal, scrape any new assignments, rank them, and flawlessly add them as events to your Google Calendar.
4. **Read PDF**: Click the **Read PDF** button to jump straight to the assignment's attached instruction document (if the scraper found one).
5. **Submit**: Click the **Submit** button to instantly open the exact Moodle submission page for that specific assignment, skipping the dashboard navigation entirely.
6. **Mark Complete**: Done with the task? Click **Mark Complete** to remove it from your priority queue and cross it off your radar!

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

## 📝 License

This project is open-source and available under the terms of the MIT License.
