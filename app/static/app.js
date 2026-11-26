const state = {
  token: localStorage.getItem("legalally_token") || "",
  user: null,
  clients: [],
  cases: [],
  documents: [],
  invoices: [],
  timeEntries: [],
  opportunities: [],
  resources: [],
  guides: [],
  templates: [],
  tasks: [],
  trustEntries: [],
  auditLogs: [],
  spaces: [],
  spaceFilters: null,
  selectedSpace: null,
  agentConfig: null,
  agentSessions: [],
  agentSessionKey: null,
  selectedCaseId: null,
  timer: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const CHECKBAR_DISCLAIMER = "This information is general legal information, not legal advice. Verify the law and consult a qualified advocate before acting.";
const PILLAR_NAV = {
  "BriefCase": "briefcase",
  "The Checkbar": "checkbar",
  "Talent": "talent",
  "Academy": "education",
  "Innovation": "innovation",
};

let registerMode = false;
let googleReady = false;
let activeStream = null;
let pendingVerificationId = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cleanLegalText(value) {
  return String(value ?? "")
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) =>
      line
        .trim()
        .replace(/^#{1,6}\s*/, "")
        .replace(/^\s*>\s*/, "")
        .replace(/^\s*[-*+]\s+/, "")
        .replace(/\*\*|__|`/g, "")
        .replace(/\*+/g, "")
        .trim()
    )
    .filter(Boolean)
    .join("\n");
}

function legalDocumentHtml(value, emptyText = "No text to display.") {
  const lines = cleanLegalText(value).split("\n").filter(Boolean);
  if (!lines.length) return `<p class="empty">${escapeHtml(emptyText)}</p>`;
  const body = lines
    .map((line) => {
      if (/^[-=_]{3,}$/.test(line)) return '<div class="legal-rule"></div>';
      const heading = /^\d+[.)]\s+/.test(line) || (/^[A-Z][A-Z0-9 &,'’\-:]{3,}$/.test(line) && !/[a-z]/.test(line));
      if (heading) return `<h4>${escapeHtml(line)}</h4>`;
      return `<p>${escapeHtml(line)}</p>`;
    })
    .join("");
  return `<div class="legal-document">${body}</div>`;
}

function renderLegalOutput(selector, value, emptyText = "No text to display.") {
  const el = $(selector);
  if (!el) return;
  el.hidden = false;
  el.innerHTML = legalDocumentHtml(value, emptyText);
}

function formatDue(dueAt) {
  if (!dueAt) return { text: "No deadline", level: "" };
  const date = new Date(dueAt);
  if (Number.isNaN(date.getTime())) return { text: String(dueAt), level: "" };
  const diff = date.getTime() - Date.now();
  const days = Math.ceil(diff / 86400000);
  if (diff < 0) {
    const count = Math.max(1, Math.abs(days));
    return { text: `Overdue by ${count} day${count === 1 ? "" : "s"}`, level: "overdue" };
  }
  if (days <= 7) return { text: `Due in ${days} day${days === 1 ? "" : "s"}`, level: "soon" };
  return { text: date.toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" }), level: "" };
}

function clientName(clientId) {
  return state.clients.find((row) => row.id === clientId)?.name || "Unassigned client";
}

function caseTitle(caseId) {
  return state.cases.find((row) => row.id === caseId)?.title || "Removed matter";
}

function caseBalance(caseId) {
  return state.trustEntries
    .filter((row) => row.case_id === caseId)
    .reduce((total, row) => total + (row.kind === "receipt" ? row.amount_cents : -row.amount_cents), 0);
}

function toast(message, kind = "") {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast show ${kind}`.trim();
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    el.className = "toast";
  }, 4200);
}

function apiError(data, status) {
  if (data?.error?.message) return data.error.message;
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((item) => item?.msg || String(item)).join("; ");
  return `Request failed (${status})`;
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) throw new Error(apiError(data, response.status));
  return data;
}

function setAuthDrawer(open) {
  $("#auth-form").classList.toggle("open", open);
  $("#auth-trigger").setAttribute("aria-expanded", String(open));
  if (open) $("#auth-email").focus();
}

function setAuthUI() {
  const signedIn = Boolean(state.token && state.user);
  $("#auth-status").textContent = signedIn
    ? `${state.user.full_name} (${state.user.role})`
    : "Not signed in";
  $("#auth-dot").classList.toggle("live", signedIn);
  $("#auth-trigger").hidden = signedIn;
  $("#login-btn").hidden = signedIn;
  $("#logout-btn").hidden = !signedIn;
  $("#toggle-register").hidden = signedIn;
  $("#register-btn").hidden = true;
  $("#google-signin").hidden = signedIn || !googleReady;
  $("#auth-name").hidden = !registerMode || signedIn;
  $("#auth-tenant").hidden = !registerMode || signedIn;
  $("#login-btn").textContent = registerMode ? "Register" : "Sign in";
  $("#toggle-register").textContent = registerMode ? "Back to sign in" : "Create account";
  if (signedIn) setAuthDrawer(false);
  applyAuthGate();
}

function applyAuthGate() {
  const signedIn = Boolean(state.token && state.user);
  $$(".requires-auth").forEach((el) => {
    el.classList.toggle("locked", !signedIn);
    let note = el.querySelector(":scope > .auth-note");
    if (!signedIn && !note) {
      note = document.createElement("p");
      note.className = "muted auth-note";
      note.textContent = "Sign in to use this module.";
      el.prepend(note);
    }
    if (signedIn && note) note.remove();
  });
}

function showSection(name) {
  $$(".section").forEach((section) => section.classList.toggle("active", section.id === `section-${name}`));
  $$(".nav button").forEach((button) => button.classList.toggle("active", button.dataset.nav === name));
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (name === "spaces") loadSpaces();
  if (!state.user) return;
  const refresh = {
    checkbar: loadCheckbar,
    briefcase: () => Promise.allSettled([loadBriefcase(), loadWorkflows()]),
    talent: loadTalent,
    education: loadEducation,
    innovation: loadInnovation,
    platform: loadPlatformPrivate,
    spaces: loadSpaceEnquiries,
    agent: () => Promise.allSettled([loadAgentConfig(), loadAgentSessions()]),
  }[name];
  if (refresh) refresh();
}

function option(value, label = value) {
  return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
}

function fillSelect(selector, rows, placeholder, labelFn) {
  const el = $(selector);
  if (!el) return;
  el.innerHTML = option("", placeholder) + rows.map((row) => option(row.id, labelFn(row))).join("");
}

function renderItems(selector, rows, formatter, emptyText = "Nothing here yet.") {
  const el = $(selector);
  if (!el) return;
  el.innerHTML = rows.length
    ? rows.map((row) => `<div class="item">${formatter(row)}</div>`).join("")
    : `<p class="empty">${escapeHtml(emptyText)}</p>`;
}

function money(cents) {
  return `Ksh ${(Number(cents || 0) / 100).toLocaleString("en-KE", { minimumFractionDigits: 2 })}`;
}

async function authenticate() {
  const email = $("#auth-email").value.trim();
  const password = $("#auth-password").value;
  const path = registerMode ? "/api/auth/register" : "/api/auth/login";
  const body = registerMode
    ? {
        email,
        password,
        full_name: $("#auth-name").value.trim(),
        tenant_name: $("#auth-tenant").value.trim(),
      }
    : { email, password };
  try {
    const tokens = await api(path, { method: "POST", body: JSON.stringify(body) });
    state.token = tokens.access_token;
    localStorage.setItem("legalally_token", state.token);
    state.user = await api("/api/auth/me");
    $("#auth-password").value = "";
    setAuthUI();
    await loadProtectedData();
    toast(registerMode ? "Firm created. Welcome to LegAlly." : "Signed in.", "success");
    registerMode = false;
    setAuthUI();
  } catch (error) {
    toast(error.message, "error");
  }
}

function initializeGoogleIdentity(clientId) {
  if (!window.google?.accounts?.id) return;
  window.google.accounts.id.initialize({
    client_id: clientId,
    callback: handleGoogleCredential,
    ux_mode: "popup",
  });
  window.google.accounts.id.renderButton($("#google-signin"), {
    theme: "outline",
    size: "large",
    text: "continue_with",
    shape: "rect",
    width: 260,
  });
  googleReady = true;
  setAuthUI();
}

async function loadGoogleSignIn(clientId) {
  if (window.google?.accounts?.id) {
    initializeGoogleIdentity(clientId);
    return;
  }
  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
  initializeGoogleIdentity(clientId);
}

async function handleGoogleCredential(response) {
  try {
    const tokens = await api("/api/auth/google", {
      method: "POST",
      body: JSON.stringify({ credential: response.credential }),
    });
    state.token = tokens.access_token;
    localStorage.setItem("legalally_token", state.token);
    state.user = await api("/api/auth/me");
    setAuthUI();
    await loadProtectedData();
    window.google?.accounts?.id?.disableAutoSelect();
    setAuthDrawer(false);
    toast("Signed in with Google.", "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function configureGoogleSignIn() {
  try {
    const config = await api("/api/auth/config");
    if (config.google_client_id) await loadGoogleSignIn(config.google_client_id);
  } catch {
  }
}

async function createRegistryTask(event) {
  event.preventDefault();
  const caseId = Number($("#registry-case").value);
  if (!caseId) {
    toast("Select a matter first.", "error");
    return;
  }
  const action = $("#registry-action").value;
  const station = $("#registry-station").value.trim();
  const date = $("#registry-date").value;
  const portals = {
    efile: "https://efiling.court.go.ke/",
    causelist: "https://causelist.court.go.ke/causelist",
  };
  const labels = {
    efile: "Prepare eFiling bundle",
    causelist: "Check court cause list",
  };
  const dueAt = date ? new Date(`${date}T16:00:00`).toISOString() : null;
  const description = [
    `Official portal: ${portals[action]}`,
    station ? `Court station: ${station}` : "",
    date ? `Target date: ${date}` : "",
    "Complete the official filing or cause-list step outside LegAlly and save the receipt or result against the matter.",
  ]
    .filter(Boolean)
    .join("\n");
  try {
    const task = await api("/api/workflows/tasks", {
      method: "POST",
      body: JSON.stringify({
        case_id: caseId,
        title: `${labels[action]} · ${caseTitle(caseId)}`,
        description,
        due_at: dueAt,
        priority: "high",
        category: "registry",
        source: portals[action],
      }),
    });
    const output = $("#registry-output");
    output.hidden = false;
    output.innerHTML = `<p><strong>${escapeHtml(task.title)}</strong> added to the matter checklist.</p><p><a href="${portals[action]}" target="_blank" rel="noopener noreferrer">Open the official portal</a></p>`;
    event.target.reset();
    toast("Registry task created.", "success");
    await loadBriefcase();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function runStudio(event) {
  event.preventDefault();
  const button = event.target.querySelector("button[type='submit']");
  const output = $("#studio-output");
  const caseId = Number($("#studio-case").value) || null;
  if (!$("#studio-consent").checked) {
    toast("Confirm the AI-use notice first.", "error");
    return;
  }
  button.disabled = true;
  button.textContent = "Working...";
  output.hidden = false;
  output.textContent = "Preparing workspace output...";
  try {
    const result = await runAI(
      $("#studio-mode").value,
      $("#studio-prompt").value.trim(),
      { case_id: caseId, client_id: state.cases.find((row) => row.id === caseId)?.client_id || null }
    );
    renderLegalOutput("#studio-output", result.answer, "No output generated.");
    $("#studio-consent").checked = false;
    toast("Studio output ready.", "success");
  } catch (error) {
    output.textContent = error.message;
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Run Studio";
  }
}

async function loadPillars() {
  try {
    const pillars = await api("/api/platform/pillars");
    $("#pillar-grid").innerHTML = pillars
      .map((pillar) => {
        const nav = PILLAR_NAV[pillar.product] || "";
        return `
        <article class="panel pillar"${nav ? ` data-nav="${escapeHtml(nav)}"` : ""}>
          <p class="label">${escapeHtml(pillar.status)}</p>
          <h3>${escapeHtml(pillar.name)}</h3>
          <p>${escapeHtml(pillar.description)}</p>
          <span class="badge">${escapeHtml(pillar.product)}</span>
        </article>`;
      })
      .join("");
    $("#hero-pillar-count").textContent = `${String(pillars.length).padStart(2, "0")} Modules`;
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadHealth() {
  try {
    const health = await api("/api/platform/health");
    $("#health").innerHTML = `
      <p><strong>${escapeHtml(health.status)}</strong></p>
      <p class="muted">${escapeHtml(health.app)} v${escapeHtml(health.version)}</p>
      <p class="muted">Database: ${escapeHtml(health.database)}</p>
      <p class="muted">Environment: ${escapeHtml(health.environment)}</p>`;
    $("#hero-health").textContent = health.status === "ok" ? "System operational" : "System degraded";
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadCheckbar() {
  try {
    const rows = await api("/api/checkbar/history");
    renderItems(
      "#check-history",
      rows,
      (row) => `
        <div class="row"><strong>${escapeHtml(row.question)}</strong><span class="meta">${escapeHtml(row.provider)}</span></div>
        <div class="meta">${escapeHtml(row.created_at)}</div>`,
      "No questions yet."
    );
  } catch (error) {
    toast(error.message, "error");
  }
}

function renderInvoiceList() {
  renderItems(
    "#invoice-list",
    state.invoices,
    (row) => {
      const next = row.status === "draft" ? "sent" : row.status === "sent" ? "paid" : null;
      const action = next
        ? `<button type="button" class="btn ghost small invoice-status-btn" data-invoice="${row.id}" data-status="${next}">Mark ${next}</button>`
        : "";
      return `<div class="row"><strong>${escapeHtml(row.number)}</strong><span class="badge">${escapeHtml(row.status)}</span></div><div class="meta">${money(row.total_cents)} · ${escapeHtml(clientName(row.client_id))}</div>${action}`;
    },
    "No invoices yet."
  );
}

function renderMatterWorkspace(caseId) {
  const el = $("#matter-workspace");
  const label = $("#workspace-label");
  if (!el || !label) return;
  const item = state.cases.find((row) => row.id === caseId);
  if (!item) {
    state.selectedCaseId = null;
    label.textContent = "Select a matter";
    el.innerHTML = '<p class="empty">Choose a matter from the pipeline to open its file.</p>';
    return;
  }
  label.textContent = item.case_number || `Matter #${item.id}`;
  const documents = state.documents.filter((row) => row.case_id === item.id);
  const tasks = state.tasks.filter((row) => row.case_id === item.id && row.status === "open");
  const time = state.timeEntries.filter((row) => row.case_id === item.id);
  const invoices = state.invoices.filter((row) => row.case_id === item.id);
  const trust = state.trustEntries.filter((row) => row.case_id === item.id);
  const minutes = time.reduce((total, row) => total + Number(row.minutes || 0), 0);
  const balance = caseBalance(item.id);
  const nextDeadline = tasks
    .filter((row) => row.due_at)
    .sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime())[0];
  const due = nextDeadline ? formatDue(nextDeadline.due_at) : null;
  const documentLines = documents.slice(0, 5).map((row) => `<li>${escapeHtml(row.title)} · v${escapeHtml(row.version)}</li>`).join("");
  const invoiceLines = invoices.slice(0, 5).map((row) => `<li>${escapeHtml(row.number)} · ${escapeHtml(row.status)} · ${money(row.total_cents)}</li>`).join("");
  el.innerHTML = `
    <div class="matter-header">
      <p class="label">${escapeHtml(clientName(item.client_id))}</p>
      <h4>${escapeHtml(item.title)}</h4>
      <div class="matter-badges">
        <span class="badge">${escapeHtml(item.status)}</span>
        <span class="badge">${documents.length} documents</span>
        <span class="badge">${minutes} minutes</span>
        <span class="badge">${invoices.length} invoices</span>
      </div>
    </div>
    <div class="matter-grid">
      <div class="matter-block">
        <p class="label">Next deadline</p>
        <p>${due ? escapeHtml(due.text) : "No open deadline"}</p>
        <p class="meta">${nextDeadline ? escapeHtml(nextDeadline.title) : "Add a task to track a filing date."}</p>
      </div>
      <div class="matter-block">
        <p class="label">Trust position</p>
        <p style="color:${balance < 0 ? "var(--danger)" : "var(--accent)"}">${money(balance)}</p>
        <p class="meta">${trust.length} ledger entr${trust.length === 1 ? "y" : "ies"} · payments blocked on overdraw</p>
      </div>
      <div class="matter-block">
        <p class="label">Documents</p>
        ${documentLines ? `<ul>${documentLines}</ul>` : '<p class="meta">No documents filed.</p>'}
      </div>
      <div class="matter-block">
        <p class="label">Billing</p>
        ${invoiceLines ? `<ul>${invoiceLines}</ul>` : '<p class="meta">No invoices raised.</p>'}
      </div>
    </div>
    <div class="matter-actions">
      <button type="button" class="btn ghost small" data-focus="doc-case">Open document filing</button>
      <button type="button" class="btn ghost small" data-focus="time-case">Log time</button>
      <button type="button" class="btn ghost small" data-focus="trust-case">Post trust entry</button>
      <button type="button" class="btn ghost small" data-focus="task-case">Add deadline</button>
    </div>`;
}

function renderFirmCommand() {
  const now = Date.now();
  const activeMatters = state.cases.filter((row) => row.status !== "closed").length;
  const openTasks = state.tasks.filter((row) => row.status === "open").length;
  const overdue = state.tasks.filter(
    (row) => row.status === "open" && row.due_at && new Date(row.due_at).getTime() < now
  ).length;
  const unbilled = state.timeEntries.reduce(
    (total, row) => total + (row.billable === false ? 0 : Number(row.minutes || 0)),
    0
  );
  const outstanding = state.invoices.filter((row) => row.status !== "paid" && row.status !== "void").length;
  const trustHeld = state.cases.reduce((total, row) => total + Math.max(0, caseBalance(row.id)), 0);
  const stats = [
    [activeMatters, "active matters"],
    [openTasks, "open tasks"],
    [overdue, "overdue"],
    [unbilled, "minutes logged"],
    [outstanding, "unpaid invoices"],
    [money(trustHeld), "trust held"],
  ];
  const statsEl = $("#firm-today");
  if (statsEl) {
    statsEl.innerHTML = stats
      .map(([value, label]) => `<div class="command-stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`)
      .join("");
  }

  const deadlines = state.tasks
    .filter((row) => row.status === "open")
    .sort((a, b) => {
      const left = a.due_at ? new Date(a.due_at).getTime() : Number.MAX_SAFE_INTEGER;
      const right = b.due_at ? new Date(b.due_at).getTime() : Number.MAX_SAFE_INTEGER;
      return left - right;
    });
  const deadlineCount = $("#deadline-count");
  if (deadlineCount) deadlineCount.textContent = deadlines.length;
  const deadlineEl = $("#upcoming-list");
  if (deadlineEl) {
    deadlineEl.innerHTML = deadlines.length
      ? deadlines
          .slice(0, 8)
          .map((row) => {
            const due = formatDue(row.due_at);
            return `<div class="item deadline-${due.level || "none"}"><div class="row"><strong>${escapeHtml(row.title)}</strong><span class="badge">${escapeHtml(row.priority)}</span></div><div class="meta">${escapeHtml(caseTitle(row.case_id))} · ${escapeHtml(due.text)}</div></div>`;
          })
          .join("")
      : '<p class="empty">No open deadlines.</p>';
  }

  const query = ($("#matter-filter")?.value || "").toLowerCase();
  const status = $("#matter-status-filter")?.value || "";
  const matters = state.cases.filter((row) => {
    const haystack = `${row.title} ${row.case_number || ""} ${clientName(row.client_id)}`.toLowerCase();
    return haystack.includes(query) && (!status || row.status === status);
  });
  const pipelineCount = $("#pipeline-count");
  if (pipelineCount) pipelineCount.textContent = matters.length;
  const pipelineEl = $("#matter-pipeline");
  if (pipelineEl) {
    pipelineEl.innerHTML = matters.length
      ? matters
          .map((row) => {
            const next = state.tasks
              .filter((task) => task.case_id === row.id && task.status === "open" && task.due_at)
              .sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime())[0];
            const due = next ? formatDue(next.due_at) : { text: "No deadline" };
            const docs = state.documents.filter((doc) => doc.case_id === row.id).length;
            const minutes = state.timeEntries
              .filter((entry) => entry.case_id === row.id)
              .reduce((total, entry) => total + Number(entry.minutes || 0), 0);
            return `<div class="item"><button type="button" class="matter-row" data-open-matter="${row.id}"><div class="row"><strong>${escapeHtml(row.title)}</strong><span class="badge">${escapeHtml(row.status)}</span></div><div class="meta">${escapeHtml(clientName(row.client_id))} · ${escapeHtml(row.case_number || "No case number")}</div><div class="meta">${escapeHtml(due.text)} · ${docs} docs · ${minutes} minutes · ${money(caseBalance(row.id))} trust</div></button></div>`;
          })
          .join("")
      : '<p class="empty">No matters match this filter.</p>';
  }

  renderMatterWorkspace(state.selectedCaseId);
  renderItems(
    "#recent-activity",
    state.auditLogs.slice(0, 8),
    (row) => `<strong>${escapeHtml(row.action)}</strong><div class="meta">${escapeHtml(row.entity)} · ${escapeHtml(row.created_at)}</div>`,
    "No activity recorded."
  );
  renderInvoiceList();

  const timerSelect = $("#timer-case");
  if (timerSelect) {
    fillSelect("#timer-case", state.cases, "Select matter", (row) => row.title);
    if (state.selectedCaseId) timerSelect.value = String(state.selectedCaseId);
  }
}

async function loadBriefcase() {
  try {
    const [stats, clients, cases, documents, invoices, timeEntries, subscription, tasks, trustEntries, auditLogs] = await Promise.all([
      api("/api/briefcase/overview"),
      api("/api/briefcase/clients"),
      api("/api/briefcase/cases"),
      api("/api/briefcase/documents"),
      api("/api/briefcase/invoices"),
      api("/api/briefcase/time-entries"),
      api("/api/briefcase/subscription"),
      api("/api/workflows/tasks"),
      api("/api/workflows/trust"),
      api("/api/platform/audit-logs"),
    ]);
    state.clients = clients;
    state.cases = cases;
    state.documents = documents;
    state.invoices = invoices;
    state.timeEntries = timeEntries;
    state.tasks = tasks;
    state.trustEntries = trustEntries;
    state.auditLogs = auditLogs;

    $("#brief-stats").innerHTML = Object.entries(stats)
      .map(([key, value]) => `<div class="stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(key.replaceAll("_", " "))}</span></div>`)
      .join("");
    $("#client-count").textContent = clients.length;
    $("#case-count").textContent = cases.length;
    $("#doc-count").textContent = documents.length;
    $("#invoice-count").textContent = invoices.length;

    fillSelect("#case-client", clients, "Select client", (row) => row.name);
    fillSelect("#doc-case", cases, "No matter", (row) => row.title);
    fillSelect("#time-case", cases, "Select matter", (row) => row.title);
    fillSelect("#invoice-client", clients, "Select client", (row) => row.name);
    fillSelect("#invoice-case", cases, "No matter", (row) => row.title);
    fillSelect("#registry-case", cases, "Select matter", (row) => row.title);
    fillSelect("#studio-case", cases, "No matter", (row) => row.title);
    if (state.selectedCaseId) {
      $("#registry-case").value = String(state.selectedCaseId);
      $("#studio-case").value = String(state.selectedCaseId);
    }

    renderItems("#client-list", clients, (row) => `<strong>${escapeHtml(row.name)}</strong><div class="meta">${escapeHtml(row.email || row.phone || "No contact details")}</div>`);
    renderItems("#case-list", cases, (row) => `<button type="button" class="matter-row" data-open-matter="${row.id}"><div class="row"><strong>${escapeHtml(row.title)}</strong><span class="badge">${escapeHtml(row.status)}</span></div><div class="meta">${escapeHtml(row.case_number || row.category)}</div></button>`);
    renderItems("#doc-list", documents, (row) => `<strong>${escapeHtml(row.title)}</strong><div class="meta">${escapeHtml(row.doc_type)} · v${escapeHtml(row.version)}</div>`);
    renderItems("#time-list", timeEntries, (row) => `<div class="row"><strong>${escapeHtml(row.description)}</strong><span class="meta">${escapeHtml(row.minutes)} min</span></div>`);
    $("#subscription").innerHTML = `<p><strong>${escapeHtml(subscription.tier)}</strong> · ${escapeHtml(subscription.status)}</p><p class="muted">${money(subscription.monthly_price_cents)} per month</p>`;
    renderFirmCommand();
  } catch (error) {
    toast(error.message, "error");
  }
}

function openMatter(caseId) {
  state.selectedCaseId = Number(caseId);
  ["#doc-case", "#time-case", "#invoice-case", "#trust-case", "#task-case", "#timer-case", "#registry-case", "#studio-case"].forEach((selector) => {
    const el = $(selector);
    if (el) el.value = String(state.selectedCaseId);
  });
  renderFirmCommand();
  $("#matter-workspace")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function updateTimerDisplay() {
  const display = $("#timer-display");
  if (!display) return;
  if (!state.timer) {
    display.textContent = "00:00:00";
    return;
  }
  const total = Math.max(0, Math.floor((Date.now() - state.timer.startedAt) / 1000));
  const hours = String(Math.floor(total / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  display.textContent = `${hours}:${minutes}:${seconds}`;
}

function clearTimer() {
  if (state.timer?.interval) clearInterval(state.timer.interval);
  state.timer = null;
  const button = $("#timer-toggle");
  if (button) button.textContent = "Start timer";
  const discard = $("#timer-discard");
  if (discard) discard.hidden = true;
  updateTimerDisplay();
}

async function stopTimer() {
  if (!state.timer) return;
  const timer = state.timer;
  if (timer.interval) clearInterval(timer.interval);
  const minutes = Math.max(1, Math.round((Date.now() - timer.startedAt) / 60000));
  try {
    await api("/api/briefcase/time-entries", {
      method: "POST",
      body: JSON.stringify({
        case_id: timer.caseId,
        description: timer.description,
        minutes,
        rate_cents: 1500000,
      }),
    });
    toast(`Logged ${minutes} minutes.`, "success");
    clearTimer();
    await loadBriefcase();
  } catch (error) {
    timer.interval = setInterval(updateTimerDisplay, 1000);
    toast(error.message, "error");
  }
}

function toggleTimer() {
  if (state.timer) {
    stopTimer();
    return;
  }
  const caseId = Number($("#timer-case")?.value);
  if (!caseId) {
    toast("Choose a matter before starting the timer.", "error");
    return;
  }
  const description = $("#timer-description").value.trim() || "Billable work";
  state.timer = {
    caseId,
    description,
    startedAt: Date.now(),
    interval: setInterval(updateTimerDisplay, 1000),
  };
  $("#timer-toggle").textContent = "Stop & log";
  $("#timer-discard").hidden = false;
  updateTimerDisplay();
}

function sourceLinks(sources) {
  return `<div class="source-links">${(sources || [])
    .map((source) => `<a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.label)}</a>`)
    .join("")}</div>`;
}

function renderGuide(guide) {
  const body = guide.body || {};
  const steps = (body.steps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("");
  const documents = (body.documents || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const swahili = body.swahili ? `<p class="swahili">${escapeHtml(body.swahili)}</p>` : "";
  const warning = body.warning ? `<p class="warn">${escapeHtml(body.warning)}</p>` : "";
  $("#guide-detail").innerHTML = `
    <p class="label">${escapeHtml(guide.audience)} · ${escapeHtml(guide.topic)}</p>
    <h3>${escapeHtml(guide.title)}</h3>
    <p>${escapeHtml(guide.summary)}</p>
    ${steps ? `<ol>${steps}</ol>` : ""}
    ${documents ? `<p class="label">Documents to prepare</p><ul>${documents}</ul>` : ""}
    ${swahili}
    ${warning}
    ${sourceLinks(guide.sources)}
    <p class="meta">Last checked ${escapeHtml(guide.last_checked)}</p>`;
}

async function loadGuides() {
  try {
    const guides = await api("/api/workflows/guides");
    state.guides = guides;
    renderItems(
      "#guide-list",
      guides,
      (row) => `
        <button type="button" class="guide-btn" data-guide="${escapeHtml(row.key)}">
          <strong>${escapeHtml(row.title)}</strong>
          <span class="meta">${escapeHtml(row.audience)} · ${escapeHtml(row.topic)}</span>
        </button>`,
      "No pathways available."
    );
    if (guides.length) renderGuide(guides[0]);
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadWorkflows() {
  if (!state.user) return;
  try {
    const [templates, conflictChecks, cddRecords, tasks, cpdRecords, clients, cases, trustEntries] = await Promise.all([
      api("/api/workflows/templates"),
      api("/api/workflows/conflict-checks"),
      api("/api/workflows/cdd"),
      api("/api/workflows/tasks"),
      api("/api/workflows/cpd"),
      api("/api/briefcase/clients"),
      api("/api/briefcase/cases"),
      api("/api/workflows/trust"),
    ]);
    state.templates = templates;
    state.clients = clients;
    state.cases = cases;
    state.tasks = tasks;
    state.trustEntries = trustEntries;
    $("#template-select").innerHTML = templates.map((row) => option(row.key, row.title)).join("");
    fillSelect("#cdd-client", state.clients, "Select client", (row) => row.name);
    fillSelect("#task-case", state.cases, "Select matter", (row) => row.title);
    fillSelect("#trust-case", state.cases, "Select matter", (row) => row.title);
    fillSelect("#trust-client", state.clients, "Select client", (row) => row.name);

    renderItems(
      "#conflict-output",
      conflictChecks.slice(0, 1),
      (row) => `<strong>${escapeHtml(row.status.toUpperCase())}</strong><p>${escapeHtml(row.result.recommendation)}</p>`,
      "No conflict checks yet."
    );
    renderItems(
      "#cdd-list",
      cddRecords,
      (row) => `<div class="row"><strong>Client #${escapeHtml(row.client_id)}</strong><span class="badge">${escapeHtml(row.risk_tier)}</span></div><div class="meta">${escapeHtml(row.status)} · ${escapeHtml(row.reviewed_by || "not reviewed")}</div>`,
      "No CDD records yet."
    );
    renderItems(
      "#task-list",
      tasks,
      (row) => `<div class="row"><strong>${escapeHtml(row.title)}</strong><span class="badge">${escapeHtml(row.priority)}</span></div><div class="meta">${escapeHtml(row.status)} · ${escapeHtml(row.category)} · ${escapeHtml(row.due_at || "no deadline")}</div>${row.status !== "done" ? `<button type="button" class="btn ghost small task-done" data-task="${row.id}">Mark done</button>` : ""}`,
      "No deadlines yet."
    );
    renderItems(
      "#cpd-list",
      cpdRecords,
      (row) => `<div class="row"><strong>${escapeHtml(row.title)}</strong><span class="badge">${escapeHtml(row.units)} units</span></div><div class="meta">${escapeHtml(row.provider || "No provider")} · ${escapeHtml(row.completed_at)}</div>`,
      "No CPD records yet."
    );

    renderItems(
      "#trust-list",
      trustEntries,
      (row) => `<div class="row"><strong>${escapeHtml(row.kind)} · ${money(row.amount_cents)}</strong><span class="meta">${money(row.balance_cents)}</span></div><div class="meta">${escapeHtml(caseTitle(row.case_id))} · ${escapeHtml(row.reference || row.posted_by || "No reference")}</div>`,
      "No trust entries yet."
    );
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadTalent() {
  try {
    const opportunities = await api("/api/talent/opportunities");
    state.opportunities = opportunities;
    renderItems(
      "#opportunity-list",
      opportunities,
      (row) => `<strong>${escapeHtml(row.title)}</strong><div class="meta">${escapeHtml(row.organization || "LegAlly")} · ${escapeHtml(row.location || "Remote")}</div><p>${escapeHtml(row.description || "")}</p>`,
      "No open opportunities."
    );
    fillSelect("#application-opportunity", opportunities, "Select opportunity", (row) => row.title);
    if (state.user) {
      const applications = await api("/api/talent/applications");
      renderItems(
        "#application-list",
        applications,
        (row) => `<div class="row"><strong>${escapeHtml(row.name)}</strong><span class="badge">${escapeHtml(row.status)}</span></div><div class="meta">${escapeHtml(row.email)}</div>`
      );
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadEducation() {
  try {
    const resources = await api("/api/education/resources");
    state.resources = resources;
    renderItems(
      "#resource-list",
      resources,
      (row) => `<div class="row"><strong>${escapeHtml(row.title)}</strong><span class="badge">${escapeHtml(row.level)}</span></div><div class="meta">${escapeHtml(row.category)}</div><button type="button" class="btn ghost small enroll-btn" data-id="${row.id}">Enroll</button>`,
      "No published resources."
    );
    if (state.user) {
      const enrollments = await api("/api/education/enrollments");
      renderItems(
        "#enrollment-list",
        enrollments,
        (row) => `<div class="row"><strong>Resource #${escapeHtml(row.resource_id)}</strong><span class="badge">${escapeHtml(row.progress)}%</span></div><div class="meta">${escapeHtml(row.status)}</div>`
      );
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadInnovation() {
  if (!state.user) return;
  try {
    const rows = await api("/api/innovation/");
    renderItems(
      "#innovation-list",
      rows,
      (row) => `<div class="row"><strong>${escapeHtml(row.title)}</strong><span class="badge">${escapeHtml(row.status)}</span></div><div class="meta">${escapeHtml(row.sector || "General")} · ${escapeHtml(row.stage)}</div><p>${escapeHtml(row.description || "")}</p>`
    );
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadPlatformPrivate() {
  if (!state.user) return;
  try {
    const [metrics, logs] = await Promise.all([
      api("/api/platform/metrics"),
      api("/api/platform/audit-logs"),
    ]);
    $("#metrics").innerHTML = Object.entries(metrics.counts)
      .map(([key, value]) => `<p><strong>${escapeHtml(key.replaceAll("_", " "))}:</strong> ${escapeHtml(value)}</p>`)
      .join("");
    renderItems(
      "#audit-list",
      logs,
      (row) => `<strong>${escapeHtml(row.action)}</strong><div class="meta">${escapeHtml(row.entity)} · ${escapeHtml(row.created_at)}</div>`
    );
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadProtectedData() {
  await Promise.allSettled([
    loadCheckbar(),
    loadBriefcase(),
    loadTalent(),
    loadEducation(),
    loadInnovation(),
    loadWorkflows(),
    loadPlatformPrivate(),
    loadSpaceEnquiries(),
    loadAgentConfig(),
    loadAgentSessions(),
  ]);
}

function setCheckStreamStatus(text, mode = "") {
  const el = $("#check-stream-status");
  if (!el) return;
  el.textContent = text;
  el.dataset.mode = mode;
}

function beginAnswer() {
  const panel = $("#check-answer");
  panel.classList.add("streaming");
  panel.innerHTML = '<div id="check-answer-text"></div><span class="caret" aria-hidden="true"></span>';
  $("#check-citations").innerHTML = "";
  $("#check-disclaimer").textContent = CHECKBAR_DISCLAIMER;
}

function appendAnswer(text) {
  const el = $("#check-answer-text");
  if (el) el.textContent += String(text ?? "");
}

function finishAnswer(answer, provider) {
  const panel = $("#check-answer");
  panel.classList.remove("streaming");
  const el = $("#check-answer-text");
  if (el) el.innerHTML = legalDocumentHtml(answer, "No answer generated.");
  setCheckStreamStatus(`Pico / ${String(provider || "ready")}`, "done");
}

function renderCheckResult(result) {
  const panel = $("#check-answer");
  panel.classList.remove("streaming");
  panel.innerHTML = legalDocumentHtml(result.answer, "No answer generated.");
  $("#check-disclaimer").textContent = result.disclaimer;
  $("#check-citations").innerHTML = (result.citations || [])
    .map((citation) => `<span class="citation">${escapeHtml(citation.source)} ${escapeHtml(citation.section || "")}</span>`)
    .join("");
  setCheckStreamStatus(`Pico / ${String(result.provider || "local")}`, "done");
}

async function askCheckbar(payload) {
  if (activeStream) {
    activeStream.abort();
    activeStream = null;
  }
  beginAnswer();
  setCheckStreamStatus("Pico / connecting", "connecting");
  const question = $("#check-question");
  let settled = false;
  let fallbackStarted = false;
  let answerBuffer = "";
  let socket = null;
  let timer = null;

  function release() {
    clearTimeout(timer);
    if (socket) {
      try {
        socket.close();
      } catch (error) {
        void error;
      }
    }
    if (activeStream && activeStream.abort === abort) activeStream = null;
  }

  function abort() {
    settled = true;
    fallbackStarted = true;
    release();
  }

  async function fallback() {
    if (fallbackStarted || settled) return;
    fallbackStarted = true;
    release();
    setCheckStreamStatus("Pico / API fallback", "fallback");
    try {
      const result = await api("/api/checkbar/ask", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      settled = true;
      renderCheckResult(result);
      question.value = "";
      await loadCheckbar();
    } catch (error) {
      settled = true;
      $("#check-answer").classList.remove("streaming");
      setCheckStreamStatus("Pico / error", "error");
      toast(error.message, "error");
    } finally {
      activeStream = null;
    }
  }

  activeStream = { abort };

  try {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${scheme}://${location.host}/api/checkbar/stream?token=${encodeURIComponent(state.token)}`);
  } catch (error) {
    void error;
    await fallback();
    return;
  }

  timer = setTimeout(() => {
    if (!settled && !fallbackStarted) fallback();
  }, 25000);

  socket.onopen = () => {
    if (settled || fallbackStarted) return;
    setCheckStreamStatus("Pico / streaming", "streaming");
    try {
      socket.send(JSON.stringify(payload));
    } catch (error) {
      void error;
      fallback();
    }
  };

  socket.onmessage = (event) => {
    if (settled || fallbackStarted) return;
    let message;
    try {
      message = JSON.parse(event.data);
    } catch (error) {
      void error;
      return;
    }
    if (message.type === "chunk") {
      answerBuffer += String(message.text ?? "");
      appendAnswer(message.text);
      setCheckStreamStatus("Pico / streaming", "streaming");
      return;
    }
    if (message.type === "done") {
      if (!answerBuffer.trim()) {
        fallback();
        return;
      }
      settled = true;
      clearTimeout(timer);
      $("#check-answer").classList.remove("streaming");
      finishAnswer(answerBuffer, message.provider);
      question.value = "";
      activeStream = null;
      try {
        socket.close();
      } catch (error) {
        void error;
      }
      loadCheckbar();
      return;
    }
    if (message.type === "error") {
      clearTimeout(timer);
      fallback();
    }
  };

  socket.onerror = () => {
    if (!settled && !fallbackStarted) fallback();
  };

  socket.onclose = () => {
    if (!settled && !fallbackStarted) fallback();
  };
}

function submitForm(selector, path, bodyFn, message, after) {
  const form = $(selector);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api(path, { method: "POST", body: JSON.stringify(bodyFn()) });
      form.reset();
      toast(message, "success");
      if (after) await after();
    } catch (error) {
      toast(error.message, "error");
    }
  });
}

async function runAI(preset, prompt, context) {
  return api("/api/ai/ask", {
    method: "POST",
    body: JSON.stringify({ preset, prompt, context }),
  });
}

function formatMoney(cents) {
  return `KSh ${Math.round(Number(cents || 0) / 100).toLocaleString("en-KE")}`;
}

function titleCase(value) {
  return String(value || "")
    .split(/[-_]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function spaceCard(space) {
  return `
    <article class="space-card accent-${escapeHtml(space.accent)}">
      <div class="space-visual">
        <span class="mono">${escapeHtml(space.city)} / ${escapeHtml(space.space_type)}</span>
        <strong>${escapeHtml(space.area)}</strong>
        ${space.featured ? '<span class="space-badge">Featured</span>' : ""}
      </div>
      <div class="space-card-body">
        <div class="space-card-head">
          <h4>${escapeHtml(space.title)}</h4>
          <p class="space-price">${formatMoney(space.price_cents)}<span>/${escapeHtml(space.term)}</span></p>
        </div>
        <p class="muted">${escapeHtml(space.description.slice(0, 140))}${space.description.length > 140 ? "..." : ""}</p>
        <div class="chip-row muted-chips">
          <span>${space.capacity} desks</span>
          ${space.bedrooms ? `<span>${space.bedrooms} bedroom${space.bedrooms > 1 ? "s" : ""}</span>` : ""}
          <span>${escapeHtml(titleCase(space.term))}</span>
        </div>
        <button type="button" class="btn ghost small" data-space-slug="${escapeHtml(space.slug)}">View space</button>
      </div>
    </article>`;
}

async function loadSpaceFilters() {
  const filters = await api("/api/spaces/filters");
  state.spaceFilters = filters;
  const fill = (selector, values, formatter = titleCase) => {
    const el = $(selector);
    if (!el) return;
    const placeholder = el.querySelector("option").outerHTML;
    el.innerHTML = placeholder + values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(formatter(value))}</option>`).join("");
  };
  fill("#space-city", filters.cities || [], (value) => value);
  fill("#space-type", filters.types || []);
  fill("#space-term", filters.terms || []);
}

async function loadSpaces() {
  const params = new URLSearchParams();
  const values = {
    q: $("#space-q")?.value.trim(),
    city: $("#space-city")?.value,
    space_type: $("#space-type")?.value,
    term: $("#space-term")?.value,
    max_price_cents: $("#space-max-price")?.value,
    min_capacity: $("#space-capacity")?.value,
    sort: $("#space-sort")?.value || "featured",
  };
  Object.entries(values).forEach(([key, value]) => {
    if (value) params.set(key, String(value));
  });
  if (values.max_price_cents) params.set("max_price_cents", String(Number(values.max_price_cents) * 100));
  const rows = await api(`/api/spaces?${params.toString()}`);
  state.spaces = rows;
  const grid = $("#space-grid");
  grid.innerHTML = rows.length
    ? rows.map(spaceCard).join("")
    : '<div class="panel empty">No spaces match those filters. Try another city or term.</div>';
  if (state.user) await loadSpaceEnquiries();
}

async function loadSpaceEnquiries() {
  if (!state.token || !state.user) return;
  const rows = await api("/api/spaces/mine/enquiries");
  const el = $("#space-enquiries");
  el.innerHTML = rows.length
    ? rows
        .map(
          (row) => `<div class="list-row"><strong>${escapeHtml(row.space_title)}</strong><span class="mono">${escapeHtml(row.status)}</span><span>${escapeHtml(row.start_date)} · ${escapeHtml(titleCase(row.term))}</span></div>`
        )
        .join("")
    : '<p class="empty">No enquiries yet.</p>';
}

async function openSpaceDetail(slug) {
  try {
    const space = await api(`/api/spaces/${encodeURIComponent(slug)}`);
    state.selectedSpace = space;
    $("#space-detail-kicker").textContent = `${space.city} / ${space.area} / ${titleCase(space.space_type)}`;
    $("#space-detail-title").textContent = space.title;
    $("#space-detail-description").textContent = space.description;
    $("#space-detail-highlights").innerHTML = (space.highlights || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("");
    $("#space-detail-amenities").innerHTML = (space.amenities || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("");
    $("#enquiry-start").value = space.available_from || "";
    $("#enquiry-term").value = space.term;
    $("#enquiry-email").value = state.user?.email || "";
    $("#space-detail").hidden = false;
    $("#space-detail").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    toast(error.message, "error");
  }
}

async function createSpaceEnquiry(event) {
  event.preventDefault();
  if (!state.selectedSpace) return;
  try {
    await api(`/api/spaces/${encodeURIComponent(state.selectedSpace.slug)}/enquiries`, {
      method: "POST",
      body: JSON.stringify({
        start_date: $("#enquiry-start").value.trim(),
        term: $("#enquiry-term").value,
        message: $("#enquiry-message").value.trim() || null,
        contact_email: $("#enquiry-email").value.trim(),
      }),
    });
    $("#enquiry-message").value = "";
    toast("Enquiry sent. The owner can now follow up in the workspace.", "success");
    await loadSpaceEnquiries();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function submitSpaceListing(event) {
  event.preventDefault();
  try {
    await api("/api/spaces", {
      method: "POST",
      body: JSON.stringify({
        title: $("#listing-title").value.trim(),
        city: $("#listing-city").value.trim(),
        area: $("#listing-area").value.trim(),
        space_type: $("#listing-type").value,
        term: $("#listing-term").value,
        price_cents: Math.round(Number($("#listing-price").value) * 100),
        capacity: Number($("#listing-capacity").value),
        bedrooms: 0,
        bathrooms: 0,
        description: $("#listing-description").value.trim(),
        amenities: $("#listing-amenities").value.split(",").map((item) => item.trim()).filter(Boolean),
        highlights: [],
        available_from: $("#listing-available").value.trim() || null,
      }),
    });
    event.target.reset();
    $("#space-listing-panel").hidden = true;
    toast("Listing published.", "success");
    await loadSpaces();
  } catch (error) {
    toast(error.message, "error");
  }
}

function renderAgentStatus() {
  const config = state.agentConfig;
  const el = $("#agent-config");
  const banner = $("#agent-status");
  if (!config) return;
  const connected = config.connected;
  const status = connected
    ? `Connected · ${escapeHtml(config.mode)} · ${escapeHtml(config.model)}`
    : "Studio fallback · OpenCode service not configured";
  banner.textContent = status;
  banner.dataset.mode = connected ? "live" : "fallback";
  el.innerHTML = `
    <div class="agent-config-row"><span class="mono">Status</span><strong>${connected ? "Ready" : "Fallback"}</strong></div>
    <div class="agent-config-row"><span class="mono">Tools</span><span>${(config.tools || []).map(escapeHtml).join(", ")}</span></div>
    <p class="muted">${connected ? "Sessions run in an isolated OpenCode workspace. Shell access is disabled." : "Deploy agent-service and set AGENT_SERVICE_URL plus AGENT_SERVICE_KEY to enable the embedded OpenCode agent."}</p>`;
}

function renderAgentThread(messages = []) {
  const el = $("#agent-thread");
  if (!messages.length) {
    el.innerHTML = '<div class="agent-empty"><span class="mono">Workspace ready</span><h4>What should we work on?</h4><p class="muted">Draft a memo, research a procedure, review a clause or plan a matter. Verify all output before use.</p></div>';
    return;
  }
  el.innerHTML = messages
    .map(
      (message) => `
        <article class="agent-message agent-${escapeHtml(message.role)}">
          <span class="mono">${escapeHtml(message.role)}</span>
          <div>${legalDocumentHtml(message.content, "No content.")}</div>
        </article>`
    )
    .join("");
  el.scrollTop = el.scrollHeight;
}

function renderAgentSessions() {
  const el = $("#agent-session-list");
  el.innerHTML = state.agentSessions.length
    ? state.agentSessions
        .map(
          (session) => `<button type="button" class="agent-session ${session.session_key === state.agentSessionKey ? "active" : ""}" data-agent-session="${escapeHtml(session.session_key)}">${escapeHtml(session.title)}</button>`
        )
        .join("")
    : '<p class="empty">No sessions yet.</p>';
}

async function loadAgentConfig() {
  state.agentConfig = await api("/api/agent/config");
  renderAgentStatus();
}

async function loadAgentSessions() {
  if (!state.token || !state.user) return;
  state.agentSessions = await api("/api/agent/sessions");
  if (!state.agentSessionKey && state.agentSessions.length) {
    state.agentSessionKey = state.agentSessions[0].session_key;
  }
  renderAgentSessions();
  if (state.agentSessionKey) await openAgentSession(state.agentSessionKey);
}

async function openAgentSession(sessionKey) {
  const detail = await api(`/api/agent/sessions/${encodeURIComponent(sessionKey)}`);
  state.agentSessionKey = sessionKey;
  renderAgentSessions();
  renderAgentThread(detail.messages);
}

async function createAgentSession() {
  try {
    const session = await api("/api/agent/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "New workspace", mode: "workspace" }),
    });
    state.agentSessionKey = session.session_key;
    await loadAgentSessions();
    await openAgentSession(session.session_key);
    $("#agent-input").focus();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function sendAgentPrompt(event) {
  event.preventDefault();
  const input = $("#agent-input");
  const button = $("#agent-send");
  const text = input.value.trim();
  if (!text) return;
  if (!$("#agent-consent").checked) {
    toast("Confirm the AI-use notice first.", "error");
    return;
  }
  button.disabled = true;
  button.textContent = "Working...";
  try {
    if (!state.agentSessionKey) await createAgentSession();
    await api(`/api/agent/sessions/${encodeURIComponent(state.agentSessionKey)}/prompt`, {
      method: "POST",
      body: JSON.stringify({ text, consent: true }),
    });
    input.value = "";
    $("#agent-consent").checked = false;
    await openAgentSession(state.agentSessionKey);
    toast("Agent response ready.", "success");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Send";
  }
}

function wireEvents() {
  $$("[data-nav]").forEach((el) => el.addEventListener("click", () => showSection(el.dataset.nav)));

  $("#pillar-grid").addEventListener("click", (event) => {
    const target = event.target.closest("[data-nav]");
    if (target) showSection(target.dataset.nav);
  });

  $("#auth-trigger").addEventListener("click", () => {
    setAuthDrawer(!$("#auth-form").classList.contains("open"));
  });

  $("#auth-form").addEventListener("submit", (event) => {
    event.preventDefault();
    authenticate();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setAuthDrawer(false);
  });

  $("#demo-login").addEventListener("click", () => {
    $("#auth-email").value = "admin@legalally.co.ke";
    $("#auth-password").value = "Admin123!";
    if (registerMode) {
      registerMode = false;
      setAuthUI();
    }
    setAuthDrawer(true);
  });

  $("#toggle-register").addEventListener("click", () => {
    registerMode = !registerMode;
    setAuthUI();
  });
  $("#login-btn").addEventListener("click", authenticate);
  $("#register-btn").addEventListener("click", authenticate);
  $("#registry-form").addEventListener("submit", createRegistryTask);
  $("#studio-form").addEventListener("submit", runStudio);
  $("#space-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadSpaces();
  });
  $("#space-grid").addEventListener("click", (event) => {
    const target = event.target.closest("[data-space-slug]");
    if (target) openSpaceDetail(target.dataset.spaceSlug);
  });
  $("#space-detail-close").addEventListener("click", () => {
    $("#space-detail").hidden = true;
    state.selectedSpace = null;
  });
  $("#space-enquiry-form").addEventListener("submit", createSpaceEnquiry);
  $("#open-space-listing").addEventListener("click", () => {
    $("#space-listing-panel").hidden = !$("#space-listing-panel").hidden;
    if (!$("#space-listing-panel").hidden) $("#space-listing-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("#space-listing-form").addEventListener("submit", submitSpaceListing);
  $("#agent-form").addEventListener("submit", sendAgentPrompt);
  $("#agent-new-session").addEventListener("click", createAgentSession);
  $("#agent-session-list").addEventListener("click", (event) => {
    const target = event.target.closest("[data-agent-session]");
    if (target) openAgentSession(target.dataset.agentSession).catch((error) => toast(error.message, "error"));
  });
  $("#logout-btn").addEventListener("click", () => {
    if (activeStream) {
      activeStream.abort();
      activeStream = null;
    }
    state.token = "";
    state.user = null;
    localStorage.removeItem("legalally_token");
    setAuthUI();
    toast("Signed out.");
    setTimeout(() => window.location.reload(), 400);
  });

  $("#checkbar-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await askCheckbar({
      question: $("#check-question").value.trim(),
      user_type: $("#check-user-type").value,
      area_of_law: $("#check-area").value,
      location: $("#check-location").value.trim() || "Kenya",
    });
  });

  submitForm("#client-form", "/api/briefcase/clients", () => ({
    name: $("#client-name").value.trim(),
    email: $("#client-email").value.trim() || null,
    phone: $("#client-phone").value.trim() || null,
  }), "Client added.", loadBriefcase);

  submitForm("#case-form", "/api/briefcase/cases", () => ({
    title: $("#case-title").value.trim(),
    client_id: Number($("#case-client").value) || null,
    case_number: $("#case-number").value.trim() || null,
  }), "Matter added.", loadBriefcase);

  $("#matter-pipeline").addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-matter]");
    if (button) openMatter(button.dataset.openMatter);
  });

  $("#case-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-matter]");
    if (button) openMatter(button.dataset.openMatter);
  });

  $("#matter-workspace").addEventListener("click", (event) => {
    const button = event.target.closest("[data-focus]");
    if (!button || !state.selectedCaseId) return;
    const target = $(`#${button.dataset.focus}`);
    if (!target) return;
    target.value = String(state.selectedCaseId);
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.focus();
  });

  $("#matter-filter").addEventListener("input", renderFirmCommand);
  $("#matter-status-filter").addEventListener("change", renderFirmCommand);
  $("#timer-toggle").addEventListener("click", toggleTimer);
  $("#timer-discard").addEventListener("click", () => {
    clearTimer();
    toast("Timer discarded.");
  });

  $("#invoice-list").addEventListener("click", async (event) => {
    const button = event.target.closest(".invoice-status-btn");
    if (!button) return;
    try {
      await api(`/api/briefcase/invoices/${button.dataset.invoice}/status?status=${button.dataset.status}`, {
        method: "PATCH",
      });
      toast(`Invoice marked ${button.dataset.status}.`, "success");
      await loadBriefcase();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  $("#doc-content").addEventListener("input", () => {
    const preview = $("#doc-preview");
    const value = cleanLegalText($("#doc-content").value);
    preview.hidden = !value;
    preview.innerHTML = legalDocumentHtml(value, "Start drafting to preview the document.");
  });

  submitForm("#doc-form", "/api/briefcase/documents", () => ({
    title: $("#doc-title").value.trim(),
    case_id: Number($("#doc-case").value) || null,
    doc_type: $("#doc-type").value,
    content: $("#doc-content").value.trim() || null,
  }), "Document added.", async () => {
    $("#doc-preview").hidden = true;
    $("#doc-preview").innerHTML = "";
    await loadBriefcase();
  });

  $("#doc-draft-btn").addEventListener("click", async () => {
    const button = $("#doc-draft-btn");
    button.disabled = true;
    button.textContent = "Drafting...";
    try {
      const result = await runAI(
        "document",
        `Draft a ${$("#doc-type").value} document titled "${$("#doc-title").value.trim() || "Legal document"}" for a Kenyan client. Include all essential clauses and a signature block.`,
        { document_type: $("#doc-type").value, case_id: $("#doc-case").value || null }
      );
      $("#doc-content").value = cleanLegalText(result.answer);
      const preview = $("#doc-preview");
      preview.hidden = false;
      preview.innerHTML = legalDocumentHtml($("#doc-content").value, "No draft to preview.");
      toast("AI draft ready.", "success");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = "AI draft";
    }
  });

  $("#case-brief-btn").addEventListener("click", async () => {
    const button = $("#case-brief-btn");
    const output = $("#case-brief-output");
    button.disabled = true;
    button.textContent = "Analysing...";
    output.hidden = false;
    output.textContent = "Preparing case brief...";
    try {
      const result = await runAI(
        "strategy",
        `Prepare a concise case strategy brief for the Kenyan matter "${$("#case-title").value.trim() || "Untitled matter"}" (${$("#case-number").value.trim() || "no case number"}). Include issues, evidence, risks, next steps and likely outcomes.`,
        { client_id: $("#case-client").value || null, case_number: $("#case-number").value.trim() || null }
      );
      renderLegalOutput("#case-brief-output", result.answer, "No case brief generated.");
      toast("Case brief ready.", "success");
    } catch (error) {
      output.textContent = error.message;
      toast(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = "Generate case brief";
    }
  });

  $("#guide-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-guide]");
    if (!button) return;
    const guide = state.guides.find((row) => row.key === button.dataset.guide);
    if (guide) renderGuide(guide);
  });

  $("#conflict-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const output = $("#conflict-output");
    output.hidden = false;
    output.textContent = "Checking tenant records...";
    try {
      const result = await api("/api/workflows/conflict-check", {
        method: "POST",
        body: JSON.stringify({
          client_name: $("#conflict-client").value.trim(),
          adverse_parties: $("#conflict-parties").value
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
        }),
      });
      output.textContent = `${result.status.toUpperCase()}\n${result.result.recommendation}\n\nScope: ${result.result.scope}`;
      toast("Conflict check recorded.", "success");
      await loadWorkflows();
    } catch (error) {
      output.textContent = error.message;
      toast(error.message, "error");
    }
  });

  $("#cdd-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const clientId = Number($("#cdd-client").value);
    if (!clientId) {
      toast("Choose a client.", "error");
      return;
    }
    try {
      await api("/api/workflows/cdd", {
        method: "POST",
        body: JSON.stringify({
          client_id: clientId,
          risk_tier: $("#cdd-risk").value,
          checklist: {
            identity_verified: $("#cdd-identity").checked,
            beneficial_owner_checked: $("#cdd-owner").checked,
            purpose_recorded: $("#cdd-purpose").checked,
            risk_reason_recorded: $("#cdd-reason").checked,
          },
        }),
      });
      toast("CDD record saved.", "success");
      await loadWorkflows();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  $("#task-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const caseId = Number($("#task-case").value);
    if (!caseId) {
      toast("Choose a matter.", "error");
      return;
    }
    try {
      await api("/api/workflows/tasks", {
        method: "POST",
        body: JSON.stringify({
          case_id: caseId,
          title: $("#task-title").value.trim(),
          due_at: $("#task-due").value || null,
          priority: $("#task-priority").value,
          category: "deadline",
        }),
      });
      $("#task-title").value = "";
      $("#task-due").value = "";
      toast("Deadline added.", "success");
      await loadWorkflows();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  $("#task-list").addEventListener("click", async (event) => {
    const button = event.target.closest(".task-done");
    if (!button) return;
    try {
      await api(`/api/workflows/tasks/${button.dataset.task}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "done" }),
      });
      toast("Task marked done.", "success");
      await loadWorkflows();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  $("#trust-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const caseId = Number($("#trust-case").value);
    const clientId = Number($("#trust-client").value);
    if (!caseId || !clientId) {
      toast("Choose a matter and client.", "error");
      return;
    }
    try {
      await api("/api/workflows/trust", {
        method: "POST",
        body: JSON.stringify({
          case_id: caseId,
          client_id: clientId,
          kind: $("#trust-kind").value,
          amount_cents: Number($("#trust-amount").value),
          reference: $("#trust-reference").value.trim() || null,
        }),
      });
      $("#trust-reference").value = "";
      toast("Trust entry posted.", "success");
      await loadWorkflows();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  $("#template-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("#template-form button[type=submit]");
    const output = $("#template-output");
    const verifyButton = $(".verify-btn");
    button.disabled = true;
    button.textContent = "Drafting...";
    output.hidden = false;
    output.textContent = "Preparing draft...";
    try {
      const client = $("#template-client").value.trim();
      const matter = $("#template-matter").value.trim();
      const recipient = $("#template-recipient").value.trim();
      const values = {};
      if (client) {
        values.client_name = client;
        values.client = client;
        values.witness = client;
        values.applicant = client;
      }
      if (matter) {
        values.matter = matter;
        values.question = matter;
      }
      if (recipient) {
        values.recipient = recipient;
        values.adverse_parties = recipient;
      }
      const result = await api(`/api/workflows/templates/${encodeURIComponent($("#template-select").value)}/draft`, {
        method: "POST",
        body: JSON.stringify({ values, case_id: Number($("#doc-case").value) || null }),
      });
      renderLegalOutput("#template-output", `${cleanLegalText(result.draft)}\n\nNOTICE: ${result.notice}`, "No draft generated.");
      pendingVerificationId = result.output_id;
      verifyButton.hidden = false;
      toast("Draft ready for review.", "success");
    } catch (error) {
      output.textContent = error.message;
      toast(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = "Draft from template";
    }
  });

  $(".verify-btn").addEventListener("click", async () => {
    if (!pendingVerificationId) return;
    try {
      await api(`/api/workflows/ai/${pendingVerificationId}/verify`, {
        method: "POST",
        body: JSON.stringify({ verified_by: state.user.full_name, note: "Reviewed in workspace" }),
      });
      $(".verify-btn").hidden = true;
      toast("Draft marked as reviewed.", "success");
    } catch (error) {
      toast(error.message, "error");
    }
  });

  $("#fee-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const output = $("#fee-output");
    output.hidden = false;
    try {
      const result = await api("/api/workflows/fees/calculate", {
        method: "POST",
        body: JSON.stringify({
          hours: Number($("#fee-hours").value),
          hourly_rate_cents: Number($("#fee-rate").value),
          disbursements_cents: Number($("#fee-disbursements").value),
        }),
      });
      output.textContent = `Fees: ${money(result.fees_cents)}\nDisbursements: ${money(result.disbursements_cents)}\nVAT: ${money(result.vat_cents)}\nTotal: ${money(result.total_cents)}\n\n${result.note}`;
    } catch (error) {
      output.textContent = error.message;
      toast(error.message, "error");
    }
  });

  $("#cpd-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/workflows/cpd", {
        method: "POST",
        body: JSON.stringify({
          title: $("#cpd-title").value.trim(),
          provider: $("#cpd-provider").value.trim() || null,
          units: Number($("#cpd-units").value),
        }),
      });
      $("#cpd-form").reset();
      toast("CPD record added.", "success");
      await loadWorkflows();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  submitForm("#time-form", "/api/briefcase/time-entries", () => ({
    case_id: Number($("#time-case").value),
    description: $("#time-description").value.trim(),
    minutes: Number($("#time-minutes").value),
    rate_cents: Number($("#time-rate").value),
  }), "Time logged.", loadBriefcase);

  submitForm("#invoice-form", "/api/briefcase/invoices", () => ({
    client_id: Number($("#invoice-client").value),
    case_id: Number($("#invoice-case").value) || null,
    items: [
      {
        description: $("#invoice-description").value.trim(),
        quantity: 1,
        unit_price_cents: Number($("#invoice-amount").value),
      },
    ],
  }), "Invoice created.", loadBriefcase);

  submitForm("#waitlist-form", "/api/briefcase/waitlist", () => ({
    name: $("#wait-name").value.trim(),
    email: $("#wait-email").value.trim(),
    role: $("#wait-role").value.trim() || null,
  }), "Waitlist joined.", async () => {
    $("#waitlist-status").textContent = "You are on the BriefCase early access list.";
  });

  $("#application-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = Number($("#application-opportunity").value);
    if (!id) {
      toast("Choose an opportunity.", "error");
      return;
    }
    try {
      await api(`/api/talent/opportunities/${id}/apply`, {
        method: "POST",
        body: JSON.stringify({
          name: $("#application-name").value.trim(),
          email: $("#application-email").value.trim(),
          cover_letter: $("#application-letter").value.trim() || null,
        }),
      });
      toast("Application submitted.", "success");
      $("#application-form").reset();
      await loadTalent();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  $("#resource-list").addEventListener("click", async (event) => {
    const button = event.target.closest(".enroll-btn");
    if (!button) return;
    try {
      await api("/api/education/enrollments", {
        method: "POST",
        body: JSON.stringify({ resource_id: Number(button.dataset.id) }),
      });
      toast("Enrolled.", "success");
      await loadEducation();
    } catch (error) {
      toast(error.message, "error");
    }
  });

  submitForm("#innovation-form", "/api/innovation/", () => ({
    title: $("#innovation-title").value.trim(),
    sector: $("#innovation-sector").value.trim() || null,
    stage: $("#innovation-stage").value,
    description: $("#innovation-description").value.trim() || null,
  }), "Innovation submitted.", loadInnovation);
}

async function init() {
  wireEvents();
  await Promise.allSettled([
    loadPillars(),
    loadHealth(),
    loadTalent(),
    loadEducation(),
    loadGuides(),
    loadSpaceFilters(),
    loadSpaces(),
    configureGoogleSignIn(),
  ]);
  if (state.token) {
    try {
      state.user = await api("/api/auth/me");
    } catch {
      state.token = "";
      localStorage.removeItem("legalally_token");
    }
  }
  setAuthUI();
  if (state.user) await loadProtectedData();
}

init();
