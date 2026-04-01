/**
 * SDLC Dashboard — Frontend JavaScript
 *
 * Polls /api/state and /api/tasks every 5 seconds and renders
 * the dashboard UI. No frameworks, no build step.
 */

const POLL_INTERVAL_MS = 5000;

const PHASE_NUMBERS = {
    "Bootstrap": 1,
    "Spec": 2,
    "Design": 3,
    "Decompose": 4,
    "Build": 5,
    "Ship": 6,
    "Evaluate": 7
};

// ===== State =====

let lastState = null;
let lastTasks = null;
let pollTimer = null;

// ===== API Fetching =====

async function fetchState() {
    try {
        const response = await fetch("/api/state", {
            cache: "no-store"
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        lastState = data;
        hideError();
        renderState(data);
    } catch (err) {
        showError(`Connection lost — retrying... (${err.message})`);
    }
}

async function fetchTasks() {
    try {
        const response = await fetch("/api/tasks", {
            cache: "no-store"
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        lastTasks = data;
        renderTasks(data);
    } catch (err) {
        // Task fetch failure is secondary — state fetch already shows error
    }
}

async function fetchAll() {
    await Promise.all([fetchState(), fetchTasks()]);
    updateConnectionStatus();
}

// ===== Rendering: Phase Timeline =====

function renderTimeline(phases) {
    const container = document.getElementById("phase-timeline");
    if (!container) return;

    container.innerHTML = "";

    phases.forEach((phase, index) => {
        // Phase node
        const node = document.createElement("div");
        node.className = `phase-node ${phase.status}`;

        const dot = document.createElement("div");
        dot.className = `phase-dot ${phase.status}`;

        if (phase.status === "completed") {
            dot.textContent = "\u2713";
        } else {
            dot.textContent = PHASE_NUMBERS[phase.name] || (index + 1);
        }

        const label = document.createElement("div");
        label.className = "phase-label";
        label.textContent = phase.name;

        node.appendChild(dot);
        node.appendChild(label);
        container.appendChild(node);

        // Connector (except after last)
        if (index < phases.length - 1) {
            const connector = document.createElement("div");
            connector.className = "phase-connector";
            if (phase.status === "completed") {
                connector.classList.add("completed");
            }
            container.appendChild(connector);
        }
    });
}

// ===== Rendering: DoD Checklist =====

function renderDoD(state) {
    const checklist = document.getElementById("dod-checklist");
    const progressBar = document.getElementById("dod-progress-bar");
    const progressText = document.getElementById("dod-progress-text");
    const phaseLabel = document.getElementById("dod-phase-label");

    if (!checklist) return;

    // Find the active phase
    const activePhase = state.phases.find(p => p.status === "active");

    if (phaseLabel) {
        phaseLabel.textContent = activePhase
            ? `\u2014 ${activePhase.name}`
            : "";
    }

    if (!activePhase || !activePhase.dod_items || activePhase.dod_items.length === 0) {
        checklist.innerHTML = '<li class="empty-text">No definition of done items for this phase</li>';
        if (progressBar) {
            progressBar.style.width = "0%";
        }
        if (progressText) {
            progressText.textContent = "N/A";
        }
        return;
    }

    // Progress bar
    const percentage = state.dod_progress.percentage || 0;
    if (progressBar) {
        progressBar.style.width = `${Math.max(percentage, 0)}%`;
    }
    if (progressText) {
        progressText.textContent = `${state.dod_progress.completed}/${state.dod_progress.total} (${percentage.toFixed(0)}%)`;
    }

    // Checklist items
    checklist.innerHTML = "";
    activePhase.dod_items.forEach(item => {
        const li = document.createElement("li");
        li.className = `dod-item ${item.done ? "done" : ""}`;

        const check = document.createElement("span");
        check.className = `dod-check ${item.done ? "checked" : ""}`;
        check.textContent = item.done ? "\u2713" : "";

        const text = document.createElement("span");
        text.className = "dod-text";
        text.textContent = item.item;

        li.appendChild(check);
        li.appendChild(text);
        checklist.appendChild(li);
    });
}

// ===== Rendering: State =====

function renderState(state) {
    // Current phase badge
    const badge = document.getElementById("current-phase-badge");
    if (badge) {
        badge.textContent = state.current_phase || "Unknown";
    }

    // Handle API-level errors
    if (state.error) {
        const checklist = document.getElementById("dod-checklist");
        if (checklist) {
            checklist.innerHTML = `<li class="empty-text">${escapeHtml(state.error)}</li>`;
        }
        return;
    }

    // Timeline
    if (state.phases) {
        renderTimeline(state.phases);
    }

    // DoD
    renderDoD(state);

    // Transition history
    renderHistory(state.transitions || []);
}

// ===== Rendering: Tasks =====

function renderTasks(data) {
    renderTaskStats(data);
    renderTaskChart(data);
}

function renderTaskStats(data) {
    const container = document.getElementById("task-stats");
    if (!container) return;

    if (data.error) {
        container.innerHTML = `<div class="empty-text">${escapeHtml(data.error)}</div>`;
        return;
    }

    const stats = [
        { label: "Total", value: data.total, cls: "total" },
        { label: "Completed", value: data.completed, cls: "completed" },
        { label: "In Progress", value: data.in_progress, cls: "in-progress" },
        { label: "Pending", value: data.pending, cls: "pending" },
        { label: "Blocked", value: data.blocked, cls: "blocked" },
    ];

    container.innerHTML = stats.map(s => `
        <div class="stat-box ${s.cls}">
            <div class="stat-value">${s.value}</div>
            <div class="stat-label">${s.label}</div>
        </div>
    `).join("");
}

function renderTaskChart(data) {
    const container = document.getElementById("task-chart");
    if (!container || data.error || data.total === 0) {
        if (container && (data.error || data.total === 0)) {
            container.innerHTML = "";
        }
        return;
    }

    const maxCount = data.total;
    const bars = [
        { label: "Completed", count: data.completed, cls: "completed" },
        { label: "In Progress", count: data.in_progress, cls: "in-progress" },
        { label: "Pending", count: data.pending, cls: "pending" },
        { label: "Blocked", count: data.blocked, cls: "blocked" },
        { label: "Deferred", count: data.deferred, cls: "deferred" },
    ].filter(b => b.count > 0);

    container.innerHTML = bars.map(b => {
        const widthPct = maxCount > 0 ? (b.count / maxCount) * 100 : 0;
        return `
            <div class="chart-row">
                <span class="chart-label">${b.label}</span>
                <div class="chart-bar-container">
                    <div class="chart-bar ${b.cls}" style="width: ${widthPct}%"></div>
                </div>
                <span class="chart-count">${b.count}</span>
            </div>
        `;
    }).join("");
}

// ===== Rendering: History =====

function renderHistory(transitions) {
    const container = document.getElementById("history-container");
    if (!container) return;

    if (!transitions || transitions.length === 0) {
        container.innerHTML = '<div class="history-empty">No phase transitions yet</div>';
        return;
    }

    let html = `
        <table class="history-table">
            <thead>
                <tr>
                    <th>From</th>
                    <th>To</th>
                    <th>Reason</th>
                    <th>When</th>
                </tr>
            </thead>
            <tbody>
    `;

    transitions.forEach(t => {
        const when = formatTimestamp(t.timestamp);
        html += `
            <tr>
                <td>${escapeHtml(t.from_phase)}</td>
                <td>${escapeHtml(t.to_phase)}</td>
                <td>${escapeHtml(t.reason)}</td>
                <td>${when}</td>
            </tr>
        `;
    });

    html += "</tbody></table>";
    container.innerHTML = html;
}

// ===== Error Handling =====

function showError(message) {
    const banner = document.getElementById("error-banner");
    const msgEl = document.getElementById("error-message");
    if (banner && msgEl) {
        msgEl.textContent = message;
        banner.style.display = "block";
    }
}

function hideError() {
    const banner = document.getElementById("error-banner");
    if (banner) {
        banner.style.display = "none";
    }
}

// ===== Connection Status =====

function updateConnectionStatus() {
    const el = document.getElementById("connection-status");
    if (el) {
        const now = new Date();
        el.textContent = `Last updated: ${now.toLocaleTimeString()}`;
    }
}

// ===== Dark Mode Toggle =====

function initTheme() {
    const saved = localStorage.getItem("sdlc-theme");
    if (saved) {
        document.documentElement.setAttribute("data-theme", saved);
    }
    updateThemeIcon();

    const toggle = document.getElementById("theme-toggle");
    if (toggle) {
        toggle.addEventListener("click", () => {
            const current = document.documentElement.getAttribute("data-theme");
            const next = current === "dark" ? "light" : "dark";
            document.documentElement.setAttribute("data-theme", next);
            localStorage.setItem("sdlc-theme", next);
            updateThemeIcon();
        });
    }
}

function updateThemeIcon() {
    const icon = document.getElementById("theme-icon");
    if (!icon) return;
    const theme = document.documentElement.getAttribute("data-theme");
    icon.textContent = theme === "dark" ? "\u2600" : "\u263E";
}

// ===== Utilities =====

function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function formatTimestamp(ts) {
    if (!ts) return "—";
    try {
        const date = new Date(ts);
        return date.toLocaleString();
    } catch {
        return ts;
    }
}

// ===== Polling =====

function startPolling() {
    fetchAll();
    pollTimer = setInterval(fetchAll, POLL_INTERVAL_MS);
}

// ===== Init =====

document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    startPolling();
});
