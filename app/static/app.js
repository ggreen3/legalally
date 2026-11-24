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
let activeStream = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

async function loadBriefcase() {
  try {
    const [stats, clients, cases, documents, invoices, timeEntries, subscription] = await Promise.all([
      api("/api/briefcase/overview"),
      api("/api/briefcase/clients"),
      api("/api/briefcase/cases"),
      api("/api/briefcase/documents"),
      api("/api/briefcase/invoices"),
      api("/api/briefcase/time-entries"),
      api("/api/briefcase/subscription"),
    ]);
    state.clients = clients;
    state.cases = cases;
    state.documents = documents;
    state.invoices = invoices;
    state.timeEntries = timeEntries;

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

    renderItems("#client-list", clients, (row) => `<strong>${escapeHtml(row.name)}</strong><div class="meta">${escapeHtml(row.email || row.phone || "No contact details")}</div>`);
    renderItems("#case-list", cases, (row) => `<div class="row"><strong>${escapeHtml(row.title)}</strong><span class="badge">${escapeHtml(row.status)}</span></div><div class="meta">${escapeHtml(row.case_number || row.category)}</div>`);
    renderItems("#doc-list", documents, (row) => `<strong>${escapeHtml(row.title)}</strong><div class="meta">${escapeHtml(row.doc_type)} · v${escapeHtml(row.version)}</div>`);
    renderItems("#invoice-list", invoices, (row) => `<div class="row"><strong>${escapeHtml(row.number)}</strong><span class="badge">${escapeHtml(row.status)}</span></div><div class="meta">${money(row.total_cents)}</div>`);
    renderItems("#time-list", timeEntries, (row) => `<div class="row"><strong>${escapeHtml(row.description)}</strong><span class="meta">${escapeHtml(row.minutes)} min</span></div>`);
    $("#subscription").innerHTML = `<p><strong>${escapeHtml(subscription.tier)}</strong> · ${escapeHtml(subscription.status)}</p><p class="muted">${money(subscription.monthly_price_cents)} per month</p>`;
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
    loadPlatformPrivate(),
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
  panel.innerHTML = '<span id="check-answer-text"></span><span class="caret" aria-hidden="true"></span>';
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
  if (el) el.textContent = answer;
  setCheckStreamStatus(`Pico / ${String(provider || "ready")}`, "done");
}

function renderCheckResult(result) {
  const panel = $("#check-answer");
  panel.classList.remove("streaming");
  panel.textContent = result.answer;
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
  const result = await api("/api/ai/ask", {
    method: "POST",
    body: JSON.stringify({ preset, prompt, context }),
  });
  return result.answer;
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

  submitForm("#doc-form", "/api/briefcase/documents", () => ({
    title: $("#doc-title").value.trim(),
    case_id: Number($("#doc-case").value) || null,
    doc_type: $("#doc-type").value,
    content: $("#doc-content").value.trim() || null,
  }), "Document added.", loadBriefcase);

  $("#doc-draft-btn").addEventListener("click", async () => {
    const button = $("#doc-draft-btn");
    button.disabled = true;
    button.textContent = "Drafting...";
    try {
      const answer = await runAI(
        "document",
        `Draft a ${$("#doc-type").value} document titled "${$("#doc-title").value.trim() || "Legal document"}" for a Kenyan client. Include all essential clauses and a signature block.`,
        { document_type: $("#doc-type").value, case_id: $("#doc-case").value || null }
      );
      $("#doc-content").value = answer;
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
      const answer = await runAI(
        "strategy",
        `Prepare a concise case strategy brief for the Kenyan matter "${$("#case-title").value.trim() || "Untitled matter"}" (${$("#case-number").value.trim() || "no case number"}). Include issues, evidence, risks, next steps and likely outcomes.`,
        { client_id: $("#case-client").value || null, case_number: $("#case-number").value.trim() || null }
      );
      output.textContent = answer;
      toast("Case brief ready.", "success");
    } catch (error) {
      output.textContent = error.message;
      toast(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = "Generate case brief";
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
  await Promise.allSettled([loadPillars(), loadHealth(), loadTalent(), loadEducation()]);
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
