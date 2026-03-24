const loginUI = document.getElementById("loginUI");
const mainUI = document.getElementById("mainUI");
const loginAppBtn = document.getElementById("loginAppBtn");

loginAppBtn.addEventListener("click", () => {
  chrome.tabs.create({ url: "http://127.0.0.1:5000/" });
});

fetch("http://127.0.0.1:5000/api/get-credentials", {
  method: "GET",
  credentials: "include"
})
  .then(response => response.json())
  .then(data => {
    if (data.error) {
      loginUI.style.display = "block";
      return;
    }

    loginUI.style.display = "none";
    mainUI.style.display = "block";
    loadNextTask();
  })
  .catch(err => {
    console.error("Fetch failed:", err);
    loginUI.style.display = "block";
  });


const API_BASE = "http://127.0.0.1:5000/api";
const container = document.getElementById("container");
const status = document.getElementById("status");
const syncButton = document.getElementById("syncBtn");
const doneBtn = document.getElementById("doneBtn");
const viewPdfBtn = document.getElementById("viewPdfBtn");
const submitBtn = document.getElementById("submitBtn");

let currentTask = null;


function renderEmptyState(message) {
  container.innerHTML = `<div class="card"><div class="value">${message}</div></div>`;
}


function renderTask(item) {
  if (!item || !item.title) {
    renderEmptyState("No tasks found");
    return;
  }

  container.innerHTML = `
    <div class="card">
      <div class="title">${item.title}</div>
      <div class="course">${item.course || ""}</div>

      <div class="label">Priority</div>
      <div class="value">${item.priority}</div>

      <div class="label">Deadline</div>
      <div class="value">${item.datetime ? new Date(item.datetime).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short'
  }) : "No deadline"}</div>

      <div class="label">Urgency</div>
      <div class="value">${"🔥".repeat(Math.min(item.urgency || 0, 3)) || "None"}</div>

      <div class="label">Effort</div>
      <div class="value">${item.effort || "Unknown"}</div>
    </div>
  `;
}


async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}


async function loadNextTask() {
  try {
    const item = await fetchJson("/next");
    currentTask = item;
    renderTask(item);
    status.textContent = "";
    doneBtn.disabled = !item || !item.id;
    viewPdfBtn.disabled = !item || !item.pdf_url;
    submitBtn.disabled = !item || !item.source_url;
  } catch (error) {
    console.error(error);
    renderEmptyState("Backend not running");
    status.textContent = "Start the local API with: ./app/bin/python api.py";
    doneBtn.disabled = true;
    viewPdfBtn.disabled = true;
    submitBtn.disabled = true;
  }
}


syncButton.addEventListener("click", async () => {
  status.textContent = "Syncing...";
  syncButton.disabled = true;

  try {
    const data = await fetchJson("/sync");
    status.textContent =
      `+${data.added} added | ~${data.updated} updated | -${data.removed} removed`;
    await loadNextTask();
  } catch (error) {
    console.error(error);
    status.textContent = "Sync failed";
  } finally {
    syncButton.disabled = false;
  }
});


// Load is triggered selectively when credentials are valid


doneBtn.addEventListener("click", () => {
  if (!currentTask || !currentTask.id) {
    status.textContent = "No task selected";
    return;
  }

  status.textContent = "Deleting...";

  fetch(`${API_BASE}/done?task_id=${currentTask.id}`, { method: "POST" })
    .then(res => res.json())
    .then(() => {
      status.textContent = "Task completed!";
      loadNextTask();
    })
    .catch(() => {
      status.textContent = "Failed";
    });
});


async function applyCredentialsAndOpen(url) {
  status.textContent = "Applying credentials...";
  try {
    const data = await fetchJson("/cookies");
    if (data.cookies && data.cookies.length > 0) {
      for (const cookie of data.cookies) {
        const protocol = cookie.secure ? "https://" : "http://";
        const domain = cookie.domain.startsWith('.') ? cookie.domain.substring(1) : cookie.domain;
        const cookieUrl = `${protocol}${domain}${cookie.path}`;

        const cookieDetails = {
          url: cookieUrl,
          name: cookie.name,
          value: cookie.value,
          domain: cookie.domain,
          path: cookie.path,
          secure: cookie.secure,
          httpOnly: cookie.httpOnly
        };

        if (cookie.sameSite === "None") {
          cookieDetails.sameSite = "no_restriction";
        } else if (cookie.sameSite === "Lax") {
          cookieDetails.sameSite = "lax";
        } else if (cookie.sameSite === "Strict") {
          cookieDetails.sameSite = "strict";
        }

        if (cookie.expires !== -1) {
          cookieDetails.expirationDate = cookie.expires;
        }

        await chrome.cookies.set(cookieDetails);
      }
    }
    status.textContent = "";
    chrome.tabs.create({ url });
  } catch (err) {
    console.error("Failed to apply credentials:", err);
    status.textContent = "Error: " + err.message;
    setTimeout(() => chrome.tabs.create({ url }), 2000);
  }
}

viewPdfBtn.addEventListener("click", () => {
  if (!currentTask || !currentTask.pdf_url) {
    status.textContent = "No PDF available (try Sync first)";
    return;
  }
  applyCredentialsAndOpen(currentTask.pdf_url);
});


submitBtn.addEventListener("click", () => {
  if (!currentTask || !currentTask.source_url) {
    status.textContent = "No submission link available";
    return;
  }
  applyCredentialsAndOpen(currentTask.source_url);
});


document.getElementById("calendarBtn").addEventListener("click", () => {
  applyCredentialsAndOpen("https://calendar.google.com");
});

