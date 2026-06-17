(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const boot = JSON.parse($("#bootstrap")?.textContent || "{}");
  const spacesById = Object.fromEntries((boot.spaces || []).map((s) => [s.id, s]));

  // ---- theme ---------------------------------------------------------------
  const THEME_KEY = "notes-theme";
  function applyTheme(t) { document.documentElement.dataset.theme = t; }
  function currentTheme() {
    return localStorage.getItem(THEME_KEY) ||
      (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  }
  $("#themeToggle")?.addEventListener("click", () => {
    const next = currentTheme() === "light" ? "dark" : "light";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  });

  // ---- sidebar collapse ----------------------------------------------------
  const app = $("#app");
  const COLLAPSE_KEY = "notes-collapsed";
  function setCollapsed(v) { app.classList.toggle("collapsed", v); localStorage.setItem(COLLAPSE_KEY, v ? "1" : ""); }
  if (localStorage.getItem(COLLAPSE_KEY)) app.classList.add("collapsed");
  const isMobile = () => matchMedia("(max-width: 760px)").matches;
  function toggleSidebar() {
    if (isMobile()) app.classList.toggle("mobile-open");
    else setCollapsed(!app.classList.contains("collapsed"));
  }
  $("#sidebarToggle")?.addEventListener("click", toggleSidebar);
  $("#brandToggle")?.addEventListener("click", toggleSidebar);

  // ---- views & filtering ---------------------------------------------------
  let currentView = "inbox";
  let currentSpaceId = null;
  let focusedId = null;
  const cards = $$(".note-card");
  const composer = $("#composer");
  const navItems = $$(".nav-item");

  function setView(view, spaceId = null) {
    currentView = view;
    currentSpaceId = view === "space" ? spaceId : null;
    navItems.forEach((n) =>
      n.classList.toggle("active",
        n.dataset.view === view && (view !== "space" || Number(n.dataset.space) === spaceId)));
    $("#view-notes").classList.toggle("hidden", !(view === "inbox" || view === "space"));
    $("#view-settings").classList.toggle("hidden", view !== "settings");
    $("#view-account").classList.toggle("hidden", view !== "account");
    if (view === "inbox" || view === "space") { updateHead(); filterNotes(); }
    if (isMobile()) app.classList.remove("mobile-open");
    refreshScopeOptions();
  }

  function updateHead() {
    if (currentView === "inbox") {
      $("#viewTitle").textContent = "Inbox";
      $("#viewSub").textContent = "Everything lands here. The AI files confident notes and flags the rest.";
      $("#eyebrow").textContent = "Capture";
    } else {
      const s = spacesById[currentSpaceId];
      $("#viewTitle").textContent = s ? s.name : "Space";
      $("#viewSub").textContent = s ? s.purpose : "";
      $("#eyebrow").textContent = "Space";
    }
  }

  function filterNotes() {
    let visible = 0;
    cards.forEach((c) => {
      const show = currentView === "inbox"
        ? c.dataset.status === "inbox"
        : Number(c.dataset.spaceId) === currentSpaceId;
      c.style.display = show ? "" : "none";
      if (show) visible++;
    });
    composer.style.display = currentView === "inbox" ? "" : "none";
    $("#emptyState").style.display = visible === 0 ? "" : "none";
  }

  navItems.forEach((n) => n.addEventListener("click", () => {
    const v = n.dataset.view;
    if (v === "space") setView("space", Number(n.dataset.space));
    else setView(v);
  }));

  // focus a note (for "this note" search/replace scope)
  cards.forEach((c) => c.addEventListener("click", (e) => {
    if (e.target.closest(".note-actions")) return;
    if (focusedId === Number(c.dataset.noteId)) { focusedId = null; c.classList.remove("focused"); }
    else { cards.forEach((x) => x.classList.remove("focused")); focusedId = Number(c.dataset.noteId); c.classList.add("focused"); }
    refreshScopeOptions();
  }));

  // ---- search --------------------------------------------------------------
  const searchInput = $("#search");
  const panel = $("#searchPanel");
  const results = $("#searchResults");
  const regexToggle = $("#regexToggle");
  let regexOn = false;
  let debounce;

  function escHtml(s) { return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function buildPattern(q) {
    try { return new RegExp(regexOn ? q : q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"); }
    catch { return null; }
  }
  function highlight(text, pat) {
    if (!pat) return escHtml(text);
    pat.lastIndex = 0;
    let out = "", last = 0, m;
    while ((m = pat.exec(text)) !== null) {
      out += escHtml(text.slice(last, m.index)) + "<mark>" + escHtml(m[0]) + "</mark>";
      last = m.index + m[0].length;
      if (m[0].length === 0) pat.lastIndex++;
    }
    return out + escHtml(text.slice(last));
  }

  regexToggle?.addEventListener("click", () => {
    regexOn = !regexOn;
    regexToggle.classList.toggle("on", regexOn);
    runSearch();
  });

  function openPanel() { panel.classList.add("open"); }
  function closePanel() { panel.classList.remove("open"); }

  async function runSearch() {
    const q = searchInput.value;
    if (!q) { closePanel(); return; }
    let res;
    try {
      res = await fetch(`/api/search?q=${encodeURIComponent(q)}&regex=${regexOn ? "true" : "false"}`);
    } catch { return; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      results.innerHTML = `<div class="sp-empty">${escHtml(err.error || "Search failed")}</div>`;
      openPanel();
      return;
    }
    const data = await res.json();
    renderResults(data.matches || [], buildPattern(q));
    openPanel();
  }

  function renderResults(matches, pat) {
    if (!matches.length) { results.innerHTML = `<div class="sp-empty">No matches</div>`; return; }
    const spaceCtx = currentView === "space" ? currentSpaceId
      : (focusedId != null ? (cardById(focusedId)?.dataset.spaceId || null) : null);
    const groups = [
      { label: "This note", rows: matches.filter((m) => m.id === focusedId), show: focusedId != null },
      { label: "This space", rows: matches.filter((m) => spaceCtx != null && String(m.space_id) === String(spaceCtx)), show: spaceCtx != null },
      { label: "Everywhere", rows: matches, show: true },
    ];
    let html = "";
    for (const g of groups) {
      if (!g.show || !g.rows.length) continue;
      html += `<div class="sp-group-label">${g.label} <span class="n">${g.rows.length}</span></div>`;
      for (const m of g.rows) {
        const where = m.space_id != null ? (spacesById[m.space_id]?.name || "Space")
          : (m.status === "inbox" ? "Inbox" : "Unfiled");
        html += `<button class="sp-result" data-id="${m.id}">
          <div class="sp-snippet">${highlight(m.snippets[0] || "", pat)}</div>
          <div class="sp-meta">${escHtml(where)} · ${m.count} match${m.count > 1 ? "es" : ""}</div>
        </button>`;
      }
    }
    results.innerHTML = html || `<div class="sp-empty">No matches</div>`;
    $$(".sp-result", results).forEach((b) => b.addEventListener("click", () => jumpToNote(Number(b.dataset.id))));
  }

  function cardById(id) { return cards.find((c) => Number(c.dataset.noteId) === id); }
  function jumpToNote(id) {
    const card = cardById(id);
    if (!card) return;
    const sid = card.dataset.spaceId;
    if (card.dataset.status === "inbox") setView("inbox");
    else if (sid) setView("space", Number(sid));
    cards.forEach((x) => x.classList.remove("focused"));
    focusedId = id; card.classList.add("focused");
    closePanel();
    card.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  let st;
  searchInput?.addEventListener("input", () => { clearTimeout(st); st = setTimeout(runSearch, 170); });
  searchInput?.addEventListener("focus", () => { if (searchInput.value) runSearch(); });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-wrap")) closePanel();
  });
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); searchInput.focus(); searchInput.select(); }
    if (e.key === "Escape") { closePanel(); closeModal(); }
  });

  // ---- replace -------------------------------------------------------------
  const scopeSelect = $("#scopeSelect");
  function refreshScopeOptions() {
    if (!scopeSelect) return;
    const opts = scopeSelect.options;
    // enable "This note" only when a note is focused; "This space" only in a space
    for (const o of opts) {
      if (o.value === "note") o.disabled = focusedId == null;
      if (o.value === "space") o.disabled = currentSpaceId == null;
    }
    if (scopeSelect.selectedOptions[0]?.disabled) scopeSelect.value = "everywhere";
  }

  function replaceParams(scope) {
    return {
      query: searchInput.value,
      replacement: $("#replaceInput").value,
      regex: regexOn,
      scope,
      space_id: currentSpaceId,
      note_id: focusedId,
    };
  }

  $("#btnReplace")?.addEventListener("click", () => startReplace("note"));
  $("#btnReplaceAll")?.addEventListener("click", () => startReplace(scopeSelect.value));

  async function startReplace(scope) {
    if (!searchInput.value) return;
    if (scope === "note" && focusedId == null) return;
    const params = replaceParams(scope);
    const res = await fetch("/api/replace/preview", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params),
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); alert(e.error || "Preview failed"); return; }
    const data = await res.json();
    openModal(params, data.changes || []);
  }

  // ---- modal ---------------------------------------------------------------
  const modal = $("#replaceModal");
  let pendingParams = null;

  function diffMarkup(text, pat, tag) {
    if (!pat) return escHtml(text);
    pat.lastIndex = 0; let out = "", last = 0, m;
    while ((m = pat.exec(text)) !== null) {
      out += escHtml(text.slice(last, m.index)) + `<${tag}>` + escHtml(m[0]) + `</${tag}>`;
      last = m.index + m[0].length; if (m[0].length === 0) pat.lastIndex++;
    }
    return out + escHtml(text.slice(last));
  }

  function openModal(params, changes) {
    pendingParams = params;
    const pat = buildPattern(params.query);
    const repPat = params.replacement ? buildPattern(params.replacement.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) : null;
    const scopeName = params.scope === "note" ? "this note" : params.scope === "space" ? "this space" : "everywhere";
    $("#modalTitle").textContent = changes.length ? `Replace in ${scopeName}` : "Nothing to replace";
    $("#modalSub").textContent = changes.length
      ? `Review ${changes.length} note${changes.length > 1 ? "s" : ""} before writing. Uncheck any you want to skip.`
      : "No matches were found in this scope.";
    if (!changes.length) {
      $("#modalBody").innerHTML = `<div class="sp-empty">No changes.</div>`;
      $("#btnConfirmReplace").disabled = true;
    } else {
      $("#modalBody").innerHTML = changes.map((c) => {
        const where = c.id; const card = cardById(c.id);
        const loc = card ? (card.dataset.status === "inbox" ? "Inbox" : (spacesById[card.dataset.spaceId]?.name || "Space")) : "";
        return `<div class="diff-row">
          <div class="diff-head">
            <label><input type="checkbox" class="diff-check" data-id="${c.id}" checked> include</label>
            <span class="where">${escHtml(loc)} · ${c.n} change${c.n > 1 ? "s" : ""}</span>
          </div>
          <div class="diff-text diff-before">${diffMarkup(c.before, pat, "del")}</div>
          <div class="diff-text diff-after">${diffMarkup(c.after, repPat, "ins")}</div>
        </div>`;
      }).join("");
      $("#btnConfirmReplace").disabled = false;
      updateModalCount();
      $$(".diff-check", modal).forEach((cb) => cb.addEventListener("change", updateModalCount));
    }
    modal.classList.add("open");
  }
  function checkedIds() { return $$(".diff-check", modal).filter((c) => c.checked).map((c) => Number(c.dataset.id)); }
  function updateModalCount() {
    const n = checkedIds().length;
    $("#modalCount").textContent = `${n} note${n === 1 ? "" : "s"} selected`;
    $("#btnConfirmReplace").disabled = n === 0;
  }
  function closeModal() { modal?.classList.remove("open"); }
  $("#btnCancelReplace")?.addEventListener("click", closeModal);
  modal?.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

  $("#btnConfirmReplace")?.addEventListener("click", async () => {
    const ids = checkedIds();
    if (!ids.length) return;
    const res = await fetch("/api/replace/apply", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...pendingParams, note_ids: ids }),
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); alert(e.error || "Replace failed"); return; }
    location.reload();
  });

  // ---- sidebar inline "new space" -----------------------------------------
  $("#newSpaceBtn")?.addEventListener("click", () => {
    const f = $("#newSpaceForm");
    f.classList.toggle("hidden");
    if (!f.classList.contains("hidden")) f.querySelector("input")?.focus();
  });

  // ---- init ----------------------------------------------------------------
  applyTheme(currentTheme());
  setView("inbox");
})();
