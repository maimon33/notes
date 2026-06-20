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
    const editBtn = e.target.closest(".edit-btn");
    if (editBtn) {
      const card = editBtn.closest(".note-card");
      if (card) openEditor(Number(card.dataset.noteId), card);
      return;
    }
    const moveBtn = e.target.closest(".move-btn");
    if (moveBtn) {
      const container = moveBtn.closest(".row-foot, .note-foot");
      const reveal = container?.querySelector(".chip-reveal");
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
  document.addEventListener("dblclick", (e) => {
    const card = e.target.closest(".note-card");
    if (!card || e.target.closest("form, button, select, input, textarea")) return;
    openEditor(Number(card.dataset.noteId), card);
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

  // ---- editor --------------------------------------------------------------
  const editorShell = $("#editorShell");
  const editorTextarea = $("#editorTextarea");
  const editorMeta = $("#editorMeta");
  const editorCount = $("#editorCount");
  const editorDirty = $("#editorDirty");
  const editorSave = $("#editorSave");
  const editorPreview = $("#editorPreview");
  const editorWorkspace = $("#editorWorkspace");
  const editorPanel = $(".editor-panel", editorShell);
  const editorFont = $("#editorFont");
  const editorSpacing = $("#editorSpacing");
  const editorWidth = $("#editorWidth");
  const editorTextType = $("#editorTextType");
  const editorToggleChrome = $("#editorToggleChrome");
  const editorTogglePreview = $("#editorTogglePreview");
  const EDITOR_CHROME_KEY = "notes.editor.controlsHidden.v2";
  let editingNoteId = null;
  let editingCard = null;
  let savedBody = "";
  let editorControlsHidden = false;
  let editorPreviewVisible = false;

  function countWords(text) {
    return (text.trim().match(/\S+/g) || []).length;
  }

  function countLines(text) {
    return Math.max(1, text.split("\n").length);
  }

  function refreshEditorMeta() {
    const text = editorTextarea.value;
    editorMeta.textContent = `${countWords(text)} words`;
    editorCount.textContent = `${countLines(text)} line${countLines(text) === 1 ? "" : "s"}`;
    editorDirty.classList.toggle("hidden", text === savedBody);
    renderEditorPreview(text);
  }

  function esc(text) {
    return escHtml(text).replace(/\n/g, "<br>");
  }

  function renderInline(text) {
    return escHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<span class="media-inline">$1</span>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  }

  function renderTable(lines) {
    const rows = lines.map((line) => line.split("|").slice(1, -1).map((cell) => renderInline(cell.trim())));
    if (rows.length < 2) return `<p>${rows.map((r) => r.join(" | ")).join("<br>")}</p>`;
    const head = rows[0].map((cell) => `<th>${cell}</th>`).join("");
    const bodyRows = rows.slice(2).map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("");
    return `<table><thead><tr>${head}</tr></thead><tbody>${bodyRows}</tbody></table>`;
  }

  function renderBlocks(text) {
    const lines = text.split("\n");
    let i = 0;
    const blocks = [];
    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();
      if (!trimmed) { i += 1; continue; }
      if (trimmed.startsWith("```")) {
        const code = [];
        i += 1;
        while (i < lines.length && !lines[i].trim().startsWith("```")) { code.push(lines[i]); i += 1; }
        i += 1;
        blocks.push(`<pre><code>${escHtml(code.join("\n"))}</code></pre>`);
        continue;
      }
      if (/^# /.test(trimmed)) { blocks.push(`<h1>${renderInline(trimmed.slice(2))}</h1>`); i += 1; continue; }
      if (/^## /.test(trimmed)) { blocks.push(`<h2>${renderInline(trimmed.slice(3))}</h2>`); i += 1; continue; }
      if (/^### /.test(trimmed)) { blocks.push(`<h3>${renderInline(trimmed.slice(4))}</h3>`); i += 1; continue; }
      if (/^> /.test(trimmed)) {
        const quote = [];
        while (i < lines.length && /^> /.test(lines[i].trim())) { quote.push(renderInline(lines[i].trim().slice(2))); i += 1; }
        blocks.push(`<blockquote>${quote.join("<br>")}</blockquote>`);
        continue;
      }
      if (/^[-*] /.test(trimmed)) {
        const items = [];
        while (i < lines.length && /^[-*] /.test(lines[i].trim())) { items.push(`<li>${renderInline(lines[i].trim().slice(2))}</li>`); i += 1; }
        blocks.push(`<ul>${items.join("")}</ul>`);
        continue;
      }
      if (/^\d+\. /.test(trimmed)) {
        const items = [];
        while (i < lines.length && /^\d+\. /.test(lines[i].trim())) { items.push(`<li>${renderInline(lines[i].trim().replace(/^\d+\.\s*/, ""))}</li>`); i += 1; }
        blocks.push(`<ol>${items.join("")}</ol>`);
        continue;
      }
      if (/^\|.*\|$/.test(trimmed)) {
        const tableLines = [];
        while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) { tableLines.push(lines[i].trim()); i += 1; }
        blocks.push(renderTable(tableLines));
        continue;
      }
      if (/^!\[([^\]]*)\]\(([^)]+)\)/.test(trimmed)) {
        const match = trimmed.match(/^!\[([^\]]*)\]\(([^)]+)\)/);
        const alt = match?.[1] || "media";
        const url = match?.[2] || "";
        const isImage = /\.(png|jpe?g|gif|webp|svg)$/i.test(url);
        blocks.push(`<div class="media-block"><div class="media-label">Media</div><div>${renderInline(trimmed)}</div>${isImage ? `<img src="${url}" alt="${escHtml(alt)}">` : ""}</div>`);
        i += 1;
        continue;
      }
      const para = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,3} |> |[-*] |\d+\. |\|.*\||```|!\[)/.test(lines[i].trim())) { para.push(lines[i]); i += 1; }
      blocks.push(`<p>${para.map((line) => renderInline(line)).join("<br>")}</p>`);
    }
    return blocks.join("");
  }

  function renderEditorPreview(text) {
    if (!editorPreview) return;
    const fontClass = `font-${editorFont?.value || "mono"}`;
    editorPreview.className = `editor-preview markdown-body ${fontClass}`;
    editorPreview.innerHTML = `<div class="editor-preview-inner">${renderBlocks(text || "") || "<p>Nothing yet. Use the toolbar to add headings, lists, tables, or media.</p>"}</div>`;
  }

  function applyEditorPreferences() {
    if (!editorTextarea || !editorPreview || !editorWorkspace) return;
    const font = editorFont?.value || "mono";
    editorTextarea.classList.remove("font-mono", "font-sans", "font-serif");
    editorTextarea.classList.add(`font-${font}`);
    editorWorkspace.style.setProperty("--editor-line-height", editorSpacing?.value || "1.7");
    editorWorkspace.style.setProperty("--editor-content-width", editorWidth?.value || "860px");
    renderEditorPreview(editorTextarea.value);
  }

  function applyEditorChromeState(hidden) {
    editorControlsHidden = Boolean(hidden);
    editorPanel?.classList.toggle("controls-collapsed", editorControlsHidden);
    if (editorToggleChrome) {
      editorToggleChrome.textContent = editorControlsHidden ? "Show tools" : "Hide tools";
      editorToggleChrome.setAttribute("aria-pressed", editorControlsHidden ? "true" : "false");
    }
    try {
      window.localStorage.setItem(EDITOR_CHROME_KEY, editorControlsHidden ? "1" : "0");
    } catch (_err) {
      // Ignore storage failures and keep the in-memory state.
    }
  }

  function loadEditorChromeState() {
    try {
      const stored = window.localStorage.getItem(EDITOR_CHROME_KEY);
      return stored == null ? true : stored === "1";
    } catch (_err) {
      return true;
    }
  }

  function applyEditorPreviewState(visible) {
    editorPreviewVisible = Boolean(visible);
    editorWorkspace?.classList.toggle("preview-hidden", !editorPreviewVisible);
    if (editorTogglePreview) {
      editorTogglePreview.textContent = editorPreviewVisible ? "Hide preview" : "Show preview";
      editorTogglePreview.setAttribute("aria-pressed", editorPreviewVisible ? "true" : "false");
    }
  }

  function wrapSelection(prefix, suffix = "", placeholder = "text") {
    const start = editorTextarea.selectionStart;
    const end = editorTextarea.selectionEnd;
    const selected = editorTextarea.value.slice(start, end) || placeholder;
    const next = `${editorTextarea.value.slice(0, start)}${prefix}${selected}${suffix}${editorTextarea.value.slice(end)}`;
    editorTextarea.value = next;
    const cursorStart = start + prefix.length;
    const cursorEnd = cursorStart + selected.length;
    editorTextarea.focus();
    editorTextarea.setSelectionRange(cursorStart, cursorEnd);
    refreshEditorMeta();
  }

  function prefixLines(prefix) {
    const start = editorTextarea.selectionStart;
    const end = editorTextarea.selectionEnd;
    const value = editorTextarea.value;
    const blockStart = value.lastIndexOf("\n", start - 1) + 1;
    const blockEnd = value.indexOf("\n", end);
    const sliceEnd = blockEnd === -1 ? value.length : blockEnd;
    const selected = value.slice(blockStart, sliceEnd);
    const replaced = selected.split("\n").map((line, idx) => {
      if (!line.trim()) return line;
      return typeof prefix === "function" ? prefix(line, idx) : `${prefix}${line}`;
    }).join("\n");
    editorTextarea.value = `${value.slice(0, blockStart)}${replaced}${value.slice(sliceEnd)}`;
    editorTextarea.focus();
    editorTextarea.setSelectionRange(blockStart, blockStart + replaced.length);
    refreshEditorMeta();
  }

  function insertTemplate(kind) {
    if (kind === "bullet") return prefixLines("- ");
    if (kind === "numbered") return prefixLines((_line, idx) => `${idx + 1}. `);
    if (kind === "table") return wrapSelection("| Column A | Column B |\n| --- | --- |\n| Value | Value |\n", "", "");
    if (kind === "media") return wrapSelection("![Alt text](https://example.com/media.jpg)", "", "");
  }

  function applyTextType(kind) {
    if (kind === "body") return;
    if (kind === "h1") return prefixLines("# ");
    if (kind === "h2") return prefixLines("## ");
    if (kind === "h3") return prefixLines("### ");
    if (kind === "quote") return prefixLines("> ");
    if (kind === "code") return wrapSelection("```\n", "\n```", "code");
  }

  function syncCardBody(noteId, body) {
    cards()
      .filter((card) => Number(card.dataset.noteId) === noteId)
      .forEach((card) => {
        const bodyEl = $(".note-body", card);
        if (!bodyEl) return;
        bodyEl.textContent = body;
        bodyEl.dataset.rawText = body;
      });
  }

  async function openEditor(noteId, card) {
    const res = await fetch(`/api/notes/${noteId}`);
    if (!res.ok) return;
    const data = await res.json();
    editingNoteId = noteId;
    editingCard = card;
    savedBody = data.note.body || "";
    editorTextarea.value = savedBody;
    editorControlsHidden = loadEditorChromeState();
    editorPreviewVisible = false;
    applyEditorChromeState(editorControlsHidden);
    applyEditorPreviewState(editorPreviewVisible);
    applyEditorPreferences();
    refreshEditorMeta();
    editorShell.classList.add("open");
    editorShell.setAttribute("aria-hidden", "false");
    setTimeout(() => editorTextarea.focus(), 10);
  }

  function closeEditor() {
    editorShell.classList.remove("open");
    editorShell.setAttribute("aria-hidden", "true");
    editingNoteId = null;
    editingCard = null;
    savedBody = "";
  }

  $("#editorCancel")?.addEventListener("click", closeEditor);
  editorShell?.addEventListener("click", (e) => {
    if (e.target === editorShell) closeEditor();
  });
  editorTextarea?.addEventListener("input", refreshEditorMeta);
  editorFont?.addEventListener("change", applyEditorPreferences);
  editorSpacing?.addEventListener("change", applyEditorPreferences);
  editorWidth?.addEventListener("change", applyEditorPreferences);
  editorToggleChrome?.addEventListener("click", () => applyEditorChromeState(!editorControlsHidden));
  editorTogglePreview?.addEventListener("click", () => applyEditorPreviewState(!editorPreviewVisible));
  editorTextType?.addEventListener("change", () => {
    applyTextType(editorTextType.value);
    editorTextType.value = "body";
  });

  editorSave?.addEventListener("click", async () => {
    if (editingNoteId == null) return;
    const res = await fetch(`/api/notes/${editingNoteId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: editorTextarea.value }),
    });
    if (!res.ok) return;
    const data = await res.json();
    savedBody = data.note.body || editorTextarea.value;
    syncCardBody(editingNoteId, savedBody);
    if (editingCard) {
      editingCard.classList.remove("collapsed");
      editingCard.classList.add("focused");
    }
    refreshEditorMeta();
    closeEditor();
  });

  $$("[data-transform]").forEach((btn) => btn.addEventListener("click", async () => {
    if (editingNoteId == null) return;
    const res = await fetch(`/api/notes/${editingNoteId}/transform`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: editorTextarea.value, mode: btn.dataset.transform }),
    });
    if (!res.ok) return;
    const data = await res.json();
    editorTextarea.value = data.body || editorTextarea.value;
    refreshEditorMeta();
  }));
  $$("[data-insert]").forEach((btn) => btn.addEventListener("click", () => insertTemplate(btn.dataset.insert)));

  // ---- init ----------------------------------------------------------------
  applyTheme(currentTheme());
  editorControlsHidden = loadEditorChromeState();
  editorPreviewVisible = false;
  applyEditorChromeState(editorControlsHidden);
  applyEditorPreviewState(editorPreviewVisible);
  applyEditorPreferences();
  setView("inbox");
})();
