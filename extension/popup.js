console.log("[AcademicCopilot] popup.js loaded");

const loadingUI = document.getElementById("loadingUI");
const loginUI = document.getElementById("loginUI");
const mainUI = document.getElementById("mainUI");
const loginAppBtn = document.getElementById("loginAppBtn");

let globalUsername = null;
let globalPassword = null;

loginAppBtn.addEventListener("click", () => {
  console.log("[AcademicCopilot] Connect Account clicked");
  chrome.tabs.create({ url: "https://academicopilot.onrender.com/" });
});

console.log("[AcademicCopilot] Checking credentials...");
fetch("https://academicopilot.onrender.com/api/get-credentials", {
  method: "GET"
})
  .then(response => {
    console.log("[AcademicCopilot] Credentials response status:", response.status);
    return response.json();
  })
  .then(data => {
    console.log("[AcademicCopilot] Credentials data:", data);
    loadingUI.style.display = "none";
    if (data.error) {
      console.log("[AcademicCopilot] No credentials found, showing login UI");
      loginUI.style.display = "block";
      return;
    }

    console.log("[AcademicCopilot] Credentials OK, showing main UI");
    globalUsername = data.username;
    globalPassword = data.password;
    loginUI.style.display = "none";
    mainUI.style.display = "block";
    loadNextTask();
  })
  .catch(err => {
    console.error("[AcademicCopilot] Credential fetch FAILED:", err);
    loadingUI.style.display = "none";
    loginUI.style.display = "block";
  });


const API_BASE = "https://academicopilot.onrender.com/api";
const MOODLE_DASHBOARD = "https://courses.iiit.ac.in/my/";
const MOODLE_BASE = "https://courses.iiit.ac.in/";
const container = document.getElementById("container");
const status = document.getElementById("status");
const syncButton = document.getElementById("syncBtn");
const doneBtn = document.getElementById("doneBtn");
const viewPdfBtn = document.getElementById("viewPdfBtn");
const submitBtn = document.getElementById("submitBtn");
const prevTaskBtn = document.getElementById("prevTaskBtn");
const nextTaskBtn = document.getElementById("nextTaskBtn");
const taskCounter = document.getElementById("taskCounter");
const paginationControls = document.getElementById("paginationControls");

let currentTask = null;
let allTasks = [];
let currentTaskIndex = 0;


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
  const url = `${API_BASE}${path}`;
  console.log(`[AcademicCopilot] fetchJson → GET ${url}`);
  const response = await fetch(url);
  console.log(`[AcademicCopilot] fetchJson ← status ${response.status} from ${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  const data = await response.json();
  console.log(`[AcademicCopilot] fetchJson ← data from ${path}:`, data);
  return data;
}


async function postJson(path, body) {
  const url = `${API_BASE}${path}`;
  console.log(`[AcademicCopilot] postJson → POST ${url}`, Object.keys(body));
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  console.log(`[AcademicCopilot] postJson ← status ${response.status} from ${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  const data = await response.json();
  console.log(`[AcademicCopilot] postJson ← data from ${path}:`, data);
  return data;
}


// ── Moodle Scraping (runs in-browser, not on server) ───────────────

function scrapeMoodleDashboard() {
  return new Promise((resolve, reject) => {
    console.log("[AcademicCopilot] Opening Moodle dashboard tab...");

    chrome.tabs.create({ url: MOODLE_DASHBOARD, active: false }, (tab) => {
      const tabId = tab.id;
      console.log(`[AcademicCopilot] Moodle tab created: ${tabId}`);

      // Listen for the tab to finish loading
      function onUpdated(updatedTabId, changeInfo) {
        if (updatedTabId !== tabId || changeInfo.status !== "complete") return;
        chrome.tabs.onUpdated.removeListener(onUpdated);

        console.log("[AcademicCopilot] Moodle tab loaded, waiting for AJAX...");

        // Wait for AJAX content to load (timeline events)
        // Poll for timeline content instead of static 8s wait
        (async () => {
          try {
            let waited = 0;
            const pollInterval = 1000;
            const maxWait = 30000;

            while (waited < maxWait) {
              try {
                const hasTimeline = await chrome.scripting.executeScript({
                  target: { tabId },
                  func: (user, pass) => {
                    const userInput = document.querySelector('input[name="username"], input[type="email"]');
                    const passInput = document.querySelector('input[type="password"]');
                    const submitBtn = document.querySelector('button[type="submit"], input[type="submit"], #loginbtn');

                    if (userInput && passInput && submitBtn) {
                      if (user && pass && !userInput.value) {
                        userInput.value = user;
                        passInput.value = pass;
                        submitBtn.click();
                      }
                      return { loginPage: true };
                    }

                    const items = document.querySelectorAll('[data-region="event-list-item"]');
                    const container = document.querySelector('[data-region="event-list-container"], [data-region="event-list-wrapper"], section.block_timeline');
                    return { items: items.length, hasContainer: !!container, loginPage: false };
                  },
                  args: [globalUsername, globalPassword]
                });
                const info = hasTimeline[0]?.result;
                if (info?.items > 0) {
                  break;
                }
                // If container is present but no items after 15s, the page may have no events
                if (!info?.loginPage && info?.hasContainer && waited >= 15000) {
                  break;
                }
              } catch (pollErr) {
                // Ignore transient errors during page load
              }
              await sleep(pollInterval);
              waited += pollInterval;
            }

            if (waited >= maxWait) {
              console.warn(`[AcademicCopilot] Timeline wait timed out at ${maxWait}ms`);
            }

            // Additional settle time for any remaining AJAX
            await sleep(2000);

            // Extract HTML from the page
            const results = await chrome.scripting.executeScript({
              target: { tabId },
              func: () => document.documentElement.outerHTML,
            });

            const html = results[0]?.result;
            console.log(`[AcademicCopilot] Moodle HTML captured: ${html?.length || 0} chars`);

            if (!html || html.length < 500) {
              chrome.tabs.remove(tabId);
              reject(new Error("Failed to capture Moodle page HTML"));
              return;
            }

            // Find assignment links in the page to scrape PDFs
            const linkResults = await chrome.scripting.executeScript({
              target: { tabId },
              func: () => {
                const links = [];
                document.querySelectorAll('[data-region="event-list-item"] a[href]').forEach(a => {
                  const href = a.getAttribute("href") || "";
                  if (href.includes("mod/assign")) {
                    links.push(href);
                  }
                });
                return links;
              },
            });

            const assignLinks = linkResults[0]?.result || [];
            console.log(`[AcademicCopilot] Found ${assignLinks.length} assignment links for PDF scraping`);

            // Scrape PDFs from each assignment page
            const pdfMap = {};
            for (const link of assignLinks) {
              try {
                const fullUrl = link.startsWith("http") ? link : MOODLE_BASE + link;
                console.log(`[AcademicCopilot]   Checking PDF for: ${fullUrl}`);

                await chrome.tabs.update(tabId, { url: fullUrl });
                await waitForTabLoad(tabId);
                await sleep(2000);

                const pdfResults = await chrome.scripting.executeScript({
                  target: { tabId },
                  func: () => {
                    for (const a of document.querySelectorAll("a")) {
                      const href = a.getAttribute("href") || "";
                      if (href.includes("pluginfile.php") && (href.toLowerCase().includes(".pdf") || href.includes("forcedownload"))) {
                        return href;
                      }
                    }
                    return null;
                  },
                });

                const pdfUrl = pdfResults[0]?.result;
                if (pdfUrl) {
                  pdfMap[fullUrl] = pdfUrl;
                  console.log(`[AcademicCopilot]   ✅ PDF found`);
                }
              } catch (e) {
                console.warn(`[AcademicCopilot]   Could not get PDF for ${link}:`, e);
              }
            }

            // Close the tab
            chrome.tabs.remove(tabId);
            console.log(`[AcademicCopilot] Moodle tab closed. PDFs found: ${Object.keys(pdfMap).length}`);

            resolve({ html, pdfMap });
          } catch (err) {
            chrome.tabs.remove(tabId);
            reject(err);
          }
        })();
      }

      chrome.tabs.onUpdated.addListener(onUpdated);

      // Timeout safety: if tab doesn't load in 60s, fail
      setTimeout(() => {
        chrome.tabs.onUpdated.removeListener(onUpdated);
        chrome.tabs.remove(tabId).catch(() => { });
        reject(new Error("Moodle page load timed out"));
      }, 60000);
    });
  });
}


function waitForTabLoad(tabId) {
  return new Promise((resolve) => {
    function onUpdated(updatedTabId, changeInfo) {
      if (updatedTabId === tabId && changeInfo.status === "complete") {
        chrome.tabs.onUpdated.removeListener(onUpdated);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(onUpdated);
  });
}


function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}


// ── Main Actions ───────────────────────────────────────────────────

async function loadNextTask() {
  console.log("[AcademicCopilot] loadNextTask() called");
  try {
    const items = await fetchJson("/assignments");
    console.log("[AcademicCopilot] All tasks loaded:", items?.length);

    allTasks = Array.isArray(items) ? items : [];
    currentTaskIndex = 0;

    if (allTasks.length > 0) {
      paginationControls.style.display = "flex";
    } else {
      paginationControls.style.display = "none";
    }

    renderCurrentTask();
  } catch (error) {
    console.error("[AcademicCopilot] loadNextTask FAILED:", error);
    renderEmptyState("Backend not running");
    status.textContent = "Start the local API with: ./app/bin/python api.py";
    disableInteractions();
    paginationControls.style.display = "none";
  }
}

function disableInteractions() {
  doneBtn.disabled = true;
  viewPdfBtn.disabled = true;
  submitBtn.disabled = true;
  prevTaskBtn.disabled = true;
  nextTaskBtn.disabled = true;
}

function renderCurrentTask() {
  if (allTasks.length === 0) {
    currentTask = null;
    renderTask(null);
    disableInteractions();
    return;
  }

  currentTask = allTasks[currentTaskIndex];
  renderTask(currentTask);
  status.textContent = "";

  // Update pagination UI
  taskCounter.textContent = `${currentTaskIndex + 1}/${allTasks.length}`;
  prevTaskBtn.disabled = currentTaskIndex === 0;
  nextTaskBtn.disabled = currentTaskIndex >= allTasks.length - 1;

  // Update action buttons
  doneBtn.disabled = !currentTask || !currentTask.id;
  viewPdfBtn.disabled = !currentTask || !currentTask.pdf_url;
  submitBtn.disabled = !currentTask || !currentTask.source_url;
}

prevTaskBtn.addEventListener("click", () => {
  if (currentTaskIndex > 0) {
    currentTaskIndex--;
    renderCurrentTask();
  }
});

nextTaskBtn.addEventListener("click", () => {
  if (currentTaskIndex < allTasks.length - 1) {
    currentTaskIndex++;
    renderCurrentTask();
  }
});


syncButton.addEventListener("click", async () => {
  console.log("[AcademicCopilot] ===== SYNC CLICKED =====");
  status.textContent = "Applying credentials...";
  syncButton.disabled = true;

  try {
    await applyCredentials();
    status.textContent = "Scraping Moodle...";

    // Step 1: Scrape Moodle from the extension (user's browser can reach it)
    console.log("[AcademicCopilot] Step 1: Scraping Moodle dashboard...");
    const { html, pdfMap } = await scrapeMoodleDashboard();

    // Step 2: Send HTML to backend for parsing + storage
    status.textContent = "Syncing to server...";
    console.log("[AcademicCopilot] Step 2: Posting HTML to backend...");
    const data = await postJson("/sync", { html, pdf_map: pdfMap });

    console.log("[AcademicCopilot] Sync response:", data);
    status.textContent =
      `+${data.added} added | ~${data.updated} updated | -${data.removed} removed`;
    await loadNextTask();
  } catch (error) {
    console.error("[AcademicCopilot] Sync FAILED:", error);
    status.textContent = "Sync failed: " + error.message;
  } finally {
    syncButton.disabled = false;
  }
});


// Load is triggered selectively when credentials are valid


doneBtn.addEventListener("click", () => {
  console.log("[AcademicCopilot] Done/Complete clicked, currentTask:", currentTask);
  if (!currentTask || !currentTask.id) {
    status.textContent = "No task selected";
    return;
  }

  status.textContent = "Deleting...";

  fetch(`${API_BASE}/done?task_id=${currentTask.id}`, { method: "POST" })
    .then(res => {
      console.log("[AcademicCopilot] Done response status:", res.status);
      return res.json();
    })
    .then((data) => {
      console.log("[AcademicCopilot] Done response data:", data);
      status.textContent = "Task completed!";
      loadNextTask();
    })
    .catch((err) => {
      console.error("[AcademicCopilot] Done request FAILED:", err);
      status.textContent = "Failed";
    });
});


async function applyCredentials() {
  status.textContent = "Applying credentials...";
  const data = await fetchJson("/cookies");
  console.log("[AcademicCopilot] Got cookies:", data.cookies?.length, "cookies");
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
}

async function applyCredentialsAndOpen(url) {
  console.log("[AcademicCopilot] applyCredentialsAndOpen:", url);
  try {
    await applyCredentials();
    chrome.tabs.create({ url });
  } catch (err) {
    console.error("[AcademicCopilot] Failed to apply credentials:", err);
    status.textContent = "Error: " + err.message;
    setTimeout(() => chrome.tabs.create({ url }), 2000);
  }
}

viewPdfBtn.addEventListener("click", () => {
  console.log("[AcademicCopilot] View PDF clicked");
  if (!currentTask || !currentTask.pdf_url) {
    status.textContent = "No PDF available (try Sync first)";
    return;
  }
  applyCredentialsAndOpen(currentTask.pdf_url);
});


submitBtn.addEventListener("click", () => {
  console.log("[AcademicCopilot] Submit clicked");
  if (!currentTask || !currentTask.source_url) {
    status.textContent = "No submission link available";
    return;
  }
  applyCredentialsAndOpen(currentTask.source_url);
});


document.getElementById("calendarBtn").addEventListener("click", () => {
  console.log("[AcademicCopilot] Calendar clicked");
  applyCredentialsAndOpen("https://calendar.google.com");
});
