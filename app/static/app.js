(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const boot = JSON.parse($("#bootstrap")?.textContent || "{}");
  const spacesById = Object.fromEntries((boot.spaces || []).map((s) => [s.id, s]));

  // ---- theme ---------------------------------------------------------------
  const THEME_KEY = "notes-theme";
  const applyTheme = (t) => { document.documentElement.dataset.theme = t; };
  const currentTheme = () => localStorage.getItem(THEME_KEY) ||
    (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  $("#themeToggle")?.addEventListener("click", () => {
    const next = currentTheme() === "light" ? "dark" : "light";
    localStorage.setItem(THEME_KEY, next); applyTheme(next);
  });

  // ---- sidebar -------------------------------------------------------------
  const app = $("#app");
  const COLLAPSE_KEY = "notes-collapsed";
  const isMobile = () => matchMedia("(max-width: 760px)").matches;
  if (localStorage.getItem(COLLAPSE_KEY)) app.classList.add("collapsed");
  function toggleSidebar() {
    if (isMobile()) app.classList.toggle("mobile-open");
    else { app.classList.toggle("collapsed"); localStorage.setItem(COLLAPSE_KEY, app.classList.contains("collapsed") ? "1" : ""); }
  }
  $("#sidebarToggle")?.addEventListener("click", toggleSidebar);
  $("#brandToggle")?.addEventListener("click", toggleSidebar);
  $("#scrim")?.addEventListener("click", () => app.classList.remove("mobile-open"));

  // ---- views ---------------------------------------------------------------
  let currentView = "inbox", currentSpaceId = null, focusedId = null;
  const navItems = $$(".nav-item");
  const cards = () => $$(".note-card");

  function setView(view, spaceId = null) {
    currentView = view; currentSpaceId = view === "space" ? spaceId : null;
    navItems.forEach((n) => n.classList.toggle("active",
      n.dataset.view === view && (view !== "space" || Number(n.dataset.space) === spaceId)));
    $("#view-notes").classList.toggle("hidden", !(view === "inbox" || view === "space"));
    $("#view-settings").classList.toggle("hidden", view !== "settings");
    $("#view-account").classList.toggle("hidden", view !== "account");
    if (view === "inbox" || view === "space") {
      $("#inboxView").classList.toggle("hidden", view !== "inbox");
      $("#spaceView").classList.toggle("hidden", view !== "space");
      if (view === "space") $$(".space-group").forEach((g) => g.classList.toggle("hidden", Number(g.dataset.space) !== spaceId));
      updateHead();
    }
    if (isMobile()) app.classList.remove("mobile-open");
    refreshScopeOptions();
  }
  function updateHead() {
    if (currentView === "inbox") {
      $("#eyebrow").textContent = "Capture";
      $("#viewTitle").textContent = "Inbox";
      $("#viewSub").textContent = "Triage to empty: keep the AI's pick or move it. Confident notes are filed for you and wait here for a nod.";
    } else {
      const s = spacesById[currentSpaceId];
      $("#eyebrow").textContent = "Space";
      $("#viewTitle").textContent = s ? s.name : "Space";
      $("#viewSub").textContent = s ? s.purpose : "";
    }
  }
  navItems.forEach((n) => n.addEventListener("click", () =>
    n.dataset.view === "space" ? setView("space", Number(n.dataset.space)) : setView(n.dataset.view)));

  // ---- collapse + move reveal (event-delegated) ----------------------------
  document.addEventListener("click", (e) => {
    const moveBtn = e.target.closest(".move-btn");
    if (moveBtn) {
      const reveal = moveBtn.closest(".row-foot")?.querySelector(".chip-reveal");
      reveal?.classList.toggle("hidden");
      return;
    }
    const row = e.target.closest(".inbox-row");
    if (row && !e.target.closest("form, button, select, input, .chip, .chip-row")) {
      row.classList.toggle("collapsed");
      cards().forEach((c) => c.classList.remove("focused"));
      if (!row.classList.contains("collapsed")) { row.classList.add("focused"); focusedId = Number(row.dataset.noteId); }
      else focusedId = null;
      refreshScopeOptions();
    }
  });
  // focus a space card for "this note" scope
  $$("#spaceView .note-card").forEach((c) => c.addEventListener("click", (e) => {
    if (e.target.closest("form, button, select, input")) return;
    cards().forEach((x) => x.classList.remove("focused"));
    if (focusedId === Number(c.dataset.noteId)) focusedId = null;
    else { focusedId = Number(c.dataset.noteId); c.classList.add("focused"); }
    refreshScopeOptions();
  }));

  // ---- new space inline ----------------------------------------------------
  $("#newSpaceBtn")?.addEventListener("click", () => {
    const f = $("#newSpaceForm"); f.classList.toggle("hidden");
    if (!f.classList.contains("hidden")) f.querySelector("input")?.focus();
  });

  // ---- search --------------------------------------------------------------
  const searchInput = $("#search"), panel = $("#searchPanel"), results = $("#searchResults"), regexToggle = $("#regexToggle");
  let regexOn = false, st;
  const escHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function buildPattern(q) { try { return new RegExp(regexOn ? q : q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"); } catch { return null; } }
  function hl(text, pat) {
    if (!pat) return escHtml(text);
    pat.lastIndex = 0; let out = "", last = 0, m;
    while ((m = pat.exec(text)) !== null) { out += escHtml(text.slice(last, m.index)) + "<mark>" + escHtml(m[0]) + "</mark>"; last = m.index + m[0].length; if (m[0].length === 0) pat.lastIndex++; }
    return out + escHtml(text.slice(last));
  }
  regexToggle?.addEventListener("click", () => { regexOn = !regexOn; regexToggle.classList.toggle("on", regexOn); runSearch(); });
  const openPanel = () => panel.classList.add("open");
  const closePanel = () => panel.classList.remove("open");

  async function runSearch() {
    const q = searchInput.value; if (!q) { closePanel(); return; }
    let res; try { res = await fetch(`/api/search?q=${encodeURIComponent(q)}&regex=${regexOn}`); } catch { return; }
    if (!res.ok) { const e = await res.json().catch(() => ({})); results.innerHTML = `<div class="sp-empty">${escHtml(e.error || "Search failed")}</div>`; openPanel(); return; }
    renderResults((await res.json()).matches || [], buildPattern(q)); openPanel();
  }
  function firstCard(id) { return cards().find((c) => Number(c.dataset.noteId) === id); }
  function renderResults(matches, pat) {
    if (!matches.length) { results.innerHTML = `<div class="sp-empty">No matches</div>`; return; }
    const spaceCtx = currentView === "space" ? currentSpaceId : (focusedId != null ? (firstCard(focusedId)?.dataset.spaceId || null) : null);
    const groups = [
      { label: "This note", rows: matches.filter((m) => m.id === focusedId), show: focusedId != null },
      { label: "This space", rows: matches.filter((m) => spaceCtx && String(m.space_id) === String(spaceCtx)), show: spaceCtx != null },
      { label: "Everywhere", rows: matches, show: true },
    ];
    let html = "";
    for (const g of groups) {
      if (!g.show || !g.rows.length) continue;
      html += `<div class="sp-group-label">${g.label} <span class="n">${g.rows.length}</span></div>`;
      for (const m of g.rows) {
        const where = m.space_id != null ? (spacesById[m.space_id]?.name || "Space") : (m.status === "inbox" ? "Inbox" : "Unfiled");
        html += `<button class="sp-result" data-id="${m.id}"><div class="sp-snippet">${hl(m.snippets[0] || "", pat)}</div><div class="sp-meta">${escHtml(where)} · ${m.count} match${m.count > 1 ? "es" : ""}</div></button>`;
      }
    }
    results.innerHTML = html || `<div class="sp-empty">No matches</div>`;
    $$(".sp-result", results).forEach((b) => b.addEventListener("click", () => jump(Number(b.dataset.id))));
  }
  function jump(id) {
    const card = firstCard(id); if (!card) return;
    if (card.dataset.status === "filed" && card.dataset.spaceId) setView("space", Number(card.dataset.spaceId));
    else setView("inbox");
    const target = firstCard(id);
    cards().forEach((x) => x.classList.remove("focused"));
    clearNoteHighlights();
    if (target) {
      target.classList.remove("collapsed");
      target.classList.add("focused");
      focusedId = id;
      highlightNoteBody(target, buildPattern(searchInput.value));
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    closePanel();
  }
  searchInput?.addEventListener("input", () => { clearTimeout(st); st = setTimeout(runSearch, 170); });
  searchInput?.addEventListener("focus", () => { if (searchInput.value) runSearch(); });
  document.addEventListener("click", (e) => { if (!e.target.closest(".search-wrap")) closePanel(); });
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); searchInput.focus(); searchInput.select(); }
    if (e.key === "Escape") { closePanel(); closeModal(); }
  });

  // ---- replace -------------------------------------------------------------
  const scopeSelect = $("#scopeSelect");
  function refreshScopeOptions() {
    if (!scopeSelect) return;
    for (const o of scopeSelect.options) {
      if (o.value === "note") o.disabled = focusedId == null;
      if (o.value === "space") o.disabled = currentSpaceId == null;
    }
    if (scopeSelect.selectedOptions[0]?.disabled) scopeSelect.value = "everywhere";
  }
  const rParams = (scope) => ({ query: searchInput.value, replacement: $("#replaceInput").value, regex: regexOn, scope, space_id: currentSpaceId, note_id: focusedId });
  $("#btnReplace")?.addEventListener("click", () => startReplace("note"));
  $("#btnReplaceAll")?.addEventListener("click", () => startReplace(scopeSelect.value));
  async function startReplace(scope) {
    if (!searchInput.value) return; if (scope === "note" && focusedId == null) return;
    const params = rParams(scope);
    const res = await fetch("/api/replace/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params) });
    if (!res.ok) { const e = await res.json().catch(() => ({})); alert(e.error || "Preview failed"); return; }
    openModal(params, (await res.json()).changes || []);
  }

  const modal = $("#replaceModal"); let pendingParams = null;
  function diff(text, pat, tag) {
    if (!pat) return escHtml(text);
    pat.lastIndex = 0; let out = "", last = 0, m;
    while ((m = pat.exec(text)) !== null) { out += escHtml(text.slice(last, m.index)) + `<${tag}>` + escHtml(m[0]) + `</${tag}>`; last = m.index + m[0].length; if (m[0].length === 0) pat.lastIndex++; }
    return out + escHtml(text.slice(last));
  }
  function openModal(params, changes) {
    pendingParams = params;
    const pat = buildPattern(params.query);
    const repPat = params.replacement ? buildPattern(params.replacement.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) : null;
    const scopeName = params.scope === "note" ? "this note" : params.scope === "space" ? "this space" : "everywhere";
    $("#modalTitle").textContent = changes.length ? `Replace in ${scopeName}` : "Nothing to replace";
    $("#modalSub").textContent = changes.length ? `Review ${changes.length} note${changes.length > 1 ? "s" : ""}. Uncheck any to skip.` : "No matches in this scope.";
    if (!changes.length) { $("#modalBody").innerHTML = `<div class="sp-empty">No changes.</div>`; $("#btnConfirmReplace").disabled = true; }
    else {
      $("#modalBody").innerHTML = changes.map((c) => `<div class="diff-row"><div class="diff-head"><label><input type="checkbox" class="diff-check" data-id="${c.id}" checked> include</label><span class="where">${c.n} change${c.n > 1 ? "s" : ""}</span></div><div class="diff-text diff-before">${diff(c.before, pat, "del")}</div><div class="diff-text diff-after">${diff(c.after, repPat, "ins")}</div></div>`).join("");
      $("#btnConfirmReplace").disabled = false; updateCount();
      $$(".diff-check", modal).forEach((cb) => cb.addEventListener("change", updateCount));
    }
    modal.classList.add("open");
  }
  const checkedIds = () => $$(".diff-check", modal).filter((c) => c.checked).map((c) => Number(c.dataset.id));
  function updateCount() { const n = checkedIds().length; $("#modalCount").textContent = `${n} note${n === 1 ? "" : "s"} selected`; $("#btnConfirmReplace").disabled = n === 0; }
  function closeModal() { modal?.classList.remove("open"); }
  $("#btnCancelReplace")?.addEventListener("click", closeModal);
  modal?.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });
  $("#btnConfirmReplace")?.addEventListener("click", async () => {
    const ids = checkedIds(); if (!ids.length) return;
    const res = await fetch("/api/replace/apply", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...pendingParams, note_ids: ids }) });
    if (!res.ok) { const e = await res.json().catch(() => ({})); alert(e.error || "Replace failed"); return; }
    location.reload();
  });

  function clearNoteHighlights() {
    $$(".note-body[data-raw-text]").forEach((body) => {
      body.textContent = body.dataset.rawText || body.textContent;
      delete body.dataset.rawText;
    });
  }

  function highlightNoteBody(card, pat) {
    const body = $(".note-body", card);
    if (!body) return;
    const raw = body.dataset.rawText || body.textContent || "";
    body.dataset.rawText = raw;
    body.innerHTML = pat ? hl(raw, pat) : escHtml(raw);
  }

  // ---- init ----------------------------------------------------------------
  applyTheme(currentTheme());
  setView("inbox");
})();
