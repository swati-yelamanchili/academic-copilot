# 🎓 Academic Copilot

Academic Copilot is an intelligent, cloud-hosted Python backend and local browser extension designed to supercharge your student life. It automatically tracks your academic assignments, ranks them by priority and effort, syncs them seamlessly to Google Calendar, and allows you to quickly view associated assignment PDFs and submission pages. entirely from a sleek Chrome extension.

> **Note:** This project is specifically configured to scrape assignments from the IIIT Hyderabad Moodle portal (`courses.iiit.ac.in/my/`). However, the Playwright scraper in `scraper.py` can be adapted to support other university Moodle portals.

---

## ✨ Key Features

- **✅ Automated Assignment Scraping**: Headless Playwright extraction of your upcoming assignments directly from your university portal.
- **🧠 Smart Ranking Algorithm**: Calculates an urgency and effort score to prioritize your tasks automatically, taking into account overdue deadlines.
- **📅 Google Calendar Sync**: Pushes assignments into your Google Calendar natively using the Google Calendar API, ensuring you never miss a deadline.
- **🧩 Browser Extension**: A modern Chrome/Edge extension interface built with HTML/CSS/JS to quickly view your highest-priority tasks, deadlines, and direct links to the assignment submission page or attached PDFs.
- **☁️ Cloud Ready**: Unified Flask architecture backed by PostgreSQL, Dockerized and ready to be deployed on platforms like Render.
- **🔒 Secure Authentication**: Integrated Google OAuth via Authlib, securely managing and persisting user session state both on the frontend and backend.

---

## 🛠️ Technology Stack

**Backend**
- **Python (3.10+)**: Core application logic.
- **Flask**: Lightweight WSGI web application framework serving the API and OAuth routes.
- **PostgreSQL**: Relational database for persistent storage of assignments, credentials, and configuration (interfaced via `psycopg2`).
- **Playwright**: Headless browser automation for robust JavaScript-heavy portal scraping.
- **BeautifulSoup4**: HTML parsing to extract assignment and PDF details from the scraped DOM.
- **Authlib & Google API Client**: Handling Google OAuth for user authentication and Google Calendar integration.
- **Gunicorn**: Production WSGI HTTP server.

**Frontend / Extension**
- **Vanilla JavaScript**: Lightweight client-side logic in `popup.js` interacting with the Flask REST API.
- **HTML & Vanilla CSS**: Clean, responsive, dark-mode styling for the browser extension popup.
- **Google Chrome Manifest V3**: Standard extension configuration.

**Infrastructure**
- **Docker**: Containerization using `Dockerfile` to simplify deployment and resolve Playwright dependency issues on cloud hosts.
- **Render** (Recommended): Setup is optimized for deployment as a Docker web service on Render.

---

## 🚀 User Setup (Quick Start)

If you just want to use the Academic Copilot extension with a pre-hosted backend, follow these simple steps:

1. **Download the Extension:** Download or clone this repository to your computer.
2. **Open Extensions Page:** Open your Chromium-based browser (Chrome, Edge, Brave) and navigate to `chrome://extensions/`.
3. **Enable Developer Mode:** Toggle **Developer mode** on (usually in the top right corner).
4. **Install:** Click the **Load unpacked** button and select the `extension` folder from the downloaded repository.
5. **Pin & Connect:** Pin the extension to your toolbar, click the icon, and select **Connect Account** to securely log in with your Google account and Moodle credentials.

---

## 💻 Developer Setup & Deployment

If you want to run your own backend, modify the code, or deploy a custom instance, follow the steps below.

### 1. Prerequisites

- **Python 3.10+** (Python 3.12 recommended).
- **Google Cloud Platform account**: You need to create a project, enable the Google Calendar API, and configure OAuth 2.0 Credentials (download as `credentials.json`).
- **PostgreSQL server**: A running local PostgreSQL instance or a cloud-hosted one (e.g., Supabase, Neon).

### 2. Local Environment Setup

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

### 3. Environment Variables

Create a `.env` file in the root directory and configure the following variables:
```env
SECRET_KEY=your_flask_secret_key
DATABASE_URL=postgresql://user:password@localhost:5432/academic_copilot
ENCRYPTION_KEY=your_fernet_encryption_key_for_passwords
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
PORT=5000
```
*Note: Make sure to place your `credentials.json` (Google Desktop App OAuth file) in the root directory to enable calendar sync functionality.*

### 4. Running Locally

Run the Flask application:
```bash
python main.py
```
The API will be available at `http://localhost:5000`.

---

## ☁️ Deployment (Render)

This project includes a `Dockerfile` customized for Playwright, making it trivial to deploy on Render.

1. Connect your GitHub repository to Render.
2. Create a new **Web Service** and select the **Docker** environment. Render will automatically detect the `Dockerfile`.
3. Add all the properties from your `.env` into the Render Environment Variables tab.
4. Deploy the service.

---

## 🧩 Custom Extension Setup (For Developers)

If you deployed your own backend, you must connect your local Chrome extension to it:

1. Open `extension/popup.js`.
2. Update the `API_BASE` and login URLs to match your deployed URL (e.g. `https://your-app.onrender.com/api`).
3. Follow the "User Setup" steps above to load the custom extension into your browser.

---

## 🎮 How to Use

Once the extension is installed and your backend is deployed:

1. **Connect Your Account**: Click the extension icon and select **Connect Account**. Log in securely with Google and enter your university Moodle credentials.
2. **View Your Next Priority**: Click the extension anytime to instantly see your highest-priority upcoming assignment, automatically ranked by urgency and estimated effort.
3. **Sync Assignments**: Click the **Sync** button in the extension. The backend will log into your portal, scrape assignments, rank them, and flawlessly add them as events to your Google Calendar.
4. **Read PDF**: Click the **Read PDF** button to jump straight to the assignment's attached instruction document (if supported/found).
5. **Submit**: Click the **Submit** button to open the exact Moodle submission page for that assignment, skipping dashboard navigation entirely.
6. **Mark Complete**: Done with the task? Click **Mark Complete** to remove it from your queue and cross it off your radar!

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to open a Pull Request if you've adapted the scraper for another university portal or have UI improvements.

## 📝 License

This project is open-source and available under the terms of the MIT License.
