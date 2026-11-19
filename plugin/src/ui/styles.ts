export const SHADOW_CSS = `
:host { all: initial; }
.pl-root {
  /* One place for the whole palette. The reading view is a lot of small text on
     a light background, so the neutrals are slightly warm and the accent is a
     deep green that survives being used for both text and fill at this size. */
  --pl-bg: #fbfaf7;
  --pl-panel: #ffffff;
  --pl-fg: #1f242a;
  --pl-fg-soft: #3d444a;
  --pl-muted: #6a716d;
  --pl-faint: #949b96;
  --pl-border: #e3e0d6;
  --pl-border-soft: #eeece4;
  --pl-accent: #23615a;
  --pl-accent-hover: #1b4f49;
  --pl-accent-weak: #e7f0ed;
  --pl-accent-ring: rgba(35, 97, 90, 0.16);
  --pl-warn: #8a5a12;
  --pl-danger: #a33a2c;
  --pl-radius: 9px;
  --pl-radius-sm: 6px;
  --pl-shadow-1: 0 1px 2px rgba(24, 34, 30, 0.06);
  --pl-shadow-2: 0 4px 16px rgba(24, 34, 30, 0.10);
  --pl-shadow-3: 0 10px 34px rgba(24, 34, 30, 0.16);
  --pl-serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, "Source Serif Pro", serif;
  --pl-mono: ui-monospace, "SF Mono", "Cascadia Mono", "Consolas", monospace;
  position: fixed;
  inset: 0;
  pointer-events: none;
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
  font-size: 13px;
  line-height: 1.55;
  color: var(--pl-fg);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  z-index: 2147483000;
}
.pl-root * { box-sizing: border-box; }
/* Keyboard users get a visible ring; mouse users are not interrupted by one.
   :focus-visible is not honoured in every Gecko build Zotero ships, so the
   fallback keeps focus visible for real focus (not for programmatic .focus()). */
.pl-root :is(button, input, textarea, select, [tabindex]):focus-visible {
  outline: 2px solid #74a79b;
  outline-offset: 1px;
  border-radius: var(--pl-radius-sm);
}
/* A thin, unobtrusive scrollbar: the reading column is long and the default
   scrollbar in the reader iframe is wide enough to eat a line of text. */
.pl-scroll, .pl-md__body, .pl-bilingual__cols, .pl-page-scroll {
  scrollbar-width: thin;
  scrollbar-color: #cfd6d1 transparent;
}
.pl-scroll::-webkit-scrollbar, .pl-md__body::-webkit-scrollbar,
.pl-bilingual__cols::-webkit-scrollbar { width: 10px; height: 10px; }
.pl-scroll::-webkit-scrollbar-thumb, .pl-md__body::-webkit-scrollbar-thumb,
.pl-bilingual__cols::-webkit-scrollbar-thumb {
  background: #d5dbd7; border-radius: 999px; border: 3px solid transparent;
  background-clip: content-box;
}
.pl-scroll::-webkit-scrollbar-thumb:hover, .pl-md__body::-webkit-scrollbar-thumb:hover {
  background: #b9c3bd; background-clip: content-box;
}
.pl-sidebar {
  position: absolute;
  top: 0; right: 0; bottom: 0;
  /* Clamped to the viewport. A saved width wider than the reader pane pushed
     the sidebar's left edge off-screen, which silently made the leftmost
     controls (tabs, the first menu items) impossible to click. */
  width: min(var(--pl-width, 380px), 100vw);
  min-width: 0;
  /* Matches SIDEBAR_MAX_WIDTH in the controller: a reading column should be
     able to use the screen instead of stopping at a fixed strip. */
  max-width: min(960px, 100vw);
  display: flex;
  flex-direction: column;
  background: var(--pl-bg);
  border-left: 1px solid var(--pl-border);
  box-shadow: -6px 0 20px rgba(20, 30, 25, 0.07);
  pointer-events: auto;
  /* Above the reading view: that layer carries z-index 6, so with "auto" here
     it painted over the sidebar wherever the two overlapped — the sidebar then
     looked covered by an invisible sheet and its fields could not be clicked. */
  z-index: 10;
  transition: transform 0.18s ease;
}
.pl-sidebar.closed { transform: translateX(100%); }
.pl-sidebar__grip {
  position: absolute; left: -4px; top: 0; bottom: 0; width: 8px;
  cursor: col-resize; z-index: 4;
}
.pl-sidebar__grip:hover { background: rgba(35, 97, 90, 0.12); }
.pl-reopen {
  position: absolute; right: 0; top: 40%;
  writing-mode: vertical-rl;
  padding: 10px 6px;
  background: var(--pl-accent);
  color: #fff;
  border: none; border-radius: 6px 0 0 6px;
  cursor: pointer; pointer-events: auto;
  font-size: 12px; letter-spacing: 1px;
}
/* "返回译文": shown after a jump hid the reading layer. Sits at the top-left of
   the reader so it is the first thing reachable when the PDF is in view, and
   never overlaps the sidebar on the right. */
.pl-return-pill {
  position: absolute; left: 14px; top: 14px;
  z-index: 9;
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 13px;
  background: var(--pl-accent); color: #fff;
  border: none; border-radius: 999px;
  box-shadow: 0 2px 10px rgba(22, 60, 56, 0.28);
  cursor: pointer; pointer-events: auto;
  font-size: 12.5px; font-weight: 600; letter-spacing: 0.2px;
}
.pl-return-pill:hover { background: #1c5049; }
.pl-return-pill:active { transform: translateY(1px); }
.pl-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--pl-border);
  background: var(--pl-panel);
}
.pl-brand { font-weight: 650; letter-spacing: 0.2px; color: var(--pl-accent); display: flex; align-items: center; gap: 6px; }
.pl-doc-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--pl-muted); font-size: 12px; }
.pl-icon-btn {
  border: 1px solid transparent; background: transparent; color: var(--pl-muted);
  width: 26px; height: 26px; border-radius: 6px; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center; font-size: 14px;
}
.pl-icon-btn:hover { background: var(--pl-accent-weak); color: var(--pl-accent); }
.pl-icon-btn.active { background: var(--pl-accent-weak); color: var(--pl-accent); }
.pl-tabs { display: flex; gap: 2px; padding: 6px 10px; border-bottom: 1px solid var(--pl-border); background: var(--pl-panel); }
.pl-tab {
  flex: 1; border: none; background: transparent; padding: 5px 8px; border-radius: 6px;
  cursor: pointer; color: var(--pl-muted); font-size: 12.5px;
}
.pl-tab.active { background: var(--pl-accent-weak); color: var(--pl-accent); font-weight: 600; }
.pl-body { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.pl-scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 10px 12px; }
.pl-card {
  background: var(--pl-panel); border: 1px solid var(--pl-border);
  border-radius: var(--pl-radius); padding: 10px 12px; margin-bottom: 10px;
}
.pl-card--warn { border-color: #edd9b0; background: #fffaf0; color: #6a4a10; }
.pl-card--error { border-color: #e6c3bc; background: #fdf4f2; color: #7c3025; }
.pl-msg { margin-bottom: 14px; }
.pl-msg__role {
  font-size: 10.5px; color: var(--pl-faint); margin-bottom: 4px;
  letter-spacing: 0.5px;
}
.pl-msg--user .pl-msg__bubble {
  background: var(--pl-accent-weak); border-radius: 12px 12px 3px 12px;
  padding: 9px 12px; white-space: pre-wrap; word-break: break-word;
  box-shadow: var(--pl-shadow-1); color: var(--pl-fg-soft);
}
.pl-msg--assistant .pl-msg__bubble {
  background: var(--pl-panel); border: 1px solid var(--pl-border-soft);
  border-radius: 12px 12px 12px 3px; padding: 10px 13px;
  box-shadow: var(--pl-shadow-1);
}
.pl-msg__bubble p { margin: 0 0 6px; }
.pl-msg__bubble ul, .pl-msg__bubble ol { margin: 4px 0 8px; padding-left: 20px; }
.pl-msg__bubble h3, .pl-msg__bubble h4, .pl-msg__bubble h5 { margin: 8px 0 4px; font-size: 13.5px; }
.pl-msg__bubble blockquote { margin: 6px 0; padding-left: 8px; border-left: 3px solid var(--pl-border); color: #4d5350; }
.pl-msg__bubble code { background: #f2f0ea; padding: 1px 4px; border-radius: 4px; font-size: 12px; }
.pl-msg__bubble pre { background: #f5f3ee; padding: 8px; border-radius: 6px; overflow-x: auto; }
.pl-msg__bubble pre code { background: transparent; padding: 0; }
.pl-table { border-collapse: collapse; width: 100%; margin: 6px 0 8px; font-size: 12px; }
.pl-table td { border: 1px solid var(--pl-border); padding: 4px 6px; vertical-align: top; }
.pl-cite {
  border: 1px solid #cfe0da; background: #f1f7f4; color: var(--pl-accent);
  border-radius: 999px; padding: 0 6px; margin: 0 1px; font-size: 11px; cursor: pointer;
}
.pl-cite:hover { background: #e2efe9; }
.pl-actions { display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
.pl-btn {
  border: 1px solid var(--pl-border); background: var(--pl-panel); color: var(--pl-fg-soft);
  border-radius: var(--pl-radius-sm); padding: 4px 10px; font-size: 12px; cursor: pointer;
  font-family: inherit;
  transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease,
    box-shadow 0.12s ease;
}
.pl-btn:hover { border-color: #cfd8d4; background: #f7f8f6; color: var(--pl-fg); }
.pl-btn:active { background: #eef1ee; }
/* Interactive elements opt back into hit-testing explicitly. .pl-root has
   pointer-events: none so clicks on empty space reach the PDF; if any host rule
   (or a future wrapper) inherits that onto a control, the button would look
   normal and be dead. */
.pl-btn, .pl-icon-btn, .pl-tab, .pl-textarea, .pl-input, .pl-select,
.pl-reopen, .pl-chip button, .pl-md__page button, .pl-md__figure-fallback,
.pl-seg-overlay, .pl-seg-overlay__line, .pl-return-pill {
  pointer-events: auto;
}
.pl-btn--primary {
  background: var(--pl-accent); border-color: var(--pl-accent); color: #fff;
  box-shadow: 0 1px 2px rgba(35, 97, 90, 0.24);
}
.pl-btn--primary:hover { background: var(--pl-accent-hover); border-color: var(--pl-accent-hover); color: #fff; }
.pl-btn--ghost { border-color: transparent; color: var(--pl-muted); background: transparent; }
.pl-btn--ghost:hover { color: var(--pl-fg); background: #eef1ee; border-color: transparent; }
.pl-btn--danger { color: var(--pl-danger); border-color: #e6c3bc; }
.pl-btn--danger:hover { background: #fdf4f2; border-color: #d9b0a8; }
.pl-btn:disabled { opacity: 0.5; cursor: not-allowed; box-shadow: none; }
.pl-btn:disabled:hover { background: var(--pl-panel); border-color: var(--pl-border); color: var(--pl-fg-soft); }
.pl-btn--primary:disabled:hover { background: var(--pl-accent); border-color: var(--pl-accent); color: #fff; }
/* Small hint under a disabled control: says *why* it is disabled instead of
   leaving the user to guess. */
.pl-hint { font-size: 11px; color: var(--pl-faint); margin-top: 4px; line-height: 1.45; }
.pl-select, .pl-input, .pl-textarea {
  border: 1px solid var(--pl-border); background: var(--pl-panel); color: var(--pl-fg);
  border-radius: 6px; padding: 5px 8px; font-size: 12.5px; font-family: inherit; outline: none;
  /* Inside Zotero the sidebar lives in a chrome-privileged document; without an
     explicit focus policy a text field can look editable but refuse focus, and
     nothing can be typed into it. */
  -moz-user-focus: normal;
  user-select: text;
  pointer-events: auto;
  cursor: text;
}
.pl-select { cursor: pointer; }
.pl-textarea { caret-color: var(--pl-accent); }
.pl-select:focus, .pl-input:focus, .pl-textarea:focus { border-color: #9dbfb6; box-shadow: 0 0 0 2px rgba(35,97,90,0.1); }
.pl-composer {
  border-top: 1px solid var(--pl-border); padding: 8px 10px 10px; background: var(--pl-panel);
  /* Keeps the composer above the message list's scroll shadows inside the
     sidebar's own stacking context. */
  position: relative; z-index: 2;
}
.pl-composer__row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
.pl-textarea { width: 100%; min-height: 60px; max-height: 160px; resize: vertical; line-height: 1.5; }
/* The sidebar can be as narrow as 300px, and the composer now holds three
   controls plus send. Both rows wrap, so nothing is pushed off the edge — the
   send button used to end up outside the panel at the narrow end. */
.pl-composer__bottom {
  display: flex; justify-content: space-between; align-items: flex-start;
  margin-top: 6px; gap: 8px; flex-wrap: wrap;
}
.pl-composer__bottom > .pl-row { flex-wrap: wrap; min-width: 0; }
/* margin-left:auto keeps send on the right on whichever line it lands. */
.pl-composer__bottom > .pl-row:last-child { flex: 0 0 auto; margin-left: auto; }
.pl-chip {
  display: inline-flex; align-items: center; gap: 6px; max-width: 100%;
  background: #f3f6f3; border: 1px solid #dbe5df; color: #45514c;
  border-radius: 999px; padding: 2px 8px; font-size: 11.5px;
}
.pl-chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 210px; }
.pl-chip button { border: none; background: transparent; cursor: pointer; color: inherit; font-size: 12px; }
/* ---- attachments ------------------------------------------------------- */
/* A row of thumbnails above the textarea. They stay small and horizontal so a
   four-image question does not push the textarea off the screen. */
.pl-attach {
  display: flex; gap: 6px; overflow-x: auto; padding: 2px 0 6px;
  scrollbar-width: thin;
}
.pl-attach__item {
  position: relative; flex: 0 0 auto; width: 78px;
  display: flex; flex-direction: column; gap: 3px;
}
.pl-attach__thumb {
  width: 78px; height: 62px; object-fit: cover; border-radius: var(--pl-radius-sm);
  border: 1px solid var(--pl-border); background: #f2f0ea; display: block;
}
.pl-attach__remove {
  position: absolute; top: -5px; right: -5px;
  width: 18px; height: 18px; padding: 0; line-height: 1;
  border-radius: 999px; border: 1px solid #d8d5c9; background: #fff;
  color: #6b6f6c; font-size: 11px; cursor: pointer;
  box-shadow: var(--pl-shadow-1);
}
.pl-attach__remove:hover { background: #fdeceb; border-color: #e5b4b0; color: #a33b33; }
.pl-attach__caption {
  width: 78px; font-size: 10.5px; padding: 2px 4px; border-radius: 5px;
  border: 1px solid var(--pl-border); background: #fff; color: var(--pl-fg);
}
.pl-attach__caption::placeholder { color: var(--pl-faint); }
.pl-attach__error {
  color: #a33b33; background: #fdf3f2; border: 1px solid #f0d6d3;
  border-radius: var(--pl-radius-sm); padding: 4px 6px; margin-bottom: 6px;
}
.pl-attach__add { flex: 0 0 auto; }
/* Images inside a sent question. */
.pl-msg__images { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.pl-msg__image { margin: 0; }
.pl-msg__image img {
  max-width: 100%; max-height: 220px; display: block; border-radius: var(--pl-radius-sm);
  border: 1px solid var(--pl-border); background: #fff;
}
.pl-msg__image figcaption {
  font-size: 11px; color: var(--pl-muted); margin-top: 2px; max-width: 220px;
}
.pl-footer {
  display: flex; align-items: center; gap: 8px; padding: 5px 10px;
  border-top: 1px solid var(--pl-border); background: #f6f5f0; color: var(--pl-muted); font-size: 11px;
}
.pl-progress { flex: 1; height: 4px; background: #e7e4da; border-radius: 999px; overflow: hidden; }
.pl-progress > div {
  height: 100%; background: var(--pl-accent); border-radius: 999px;
  transition: width 0.3s cubic-bezier(0.2, 0.7, 0.3, 1);
}
/* Live service health. A dot is the smallest thing that answers "为什么按钮没反应"
   without the user opening a diagnostic panel. */
.pl-dot {
  width: 7px; height: 7px; border-radius: 50%; flex: none;
  background: #b9c3bd; box-shadow: 0 0 0 3px rgba(185, 195, 189, 0.18);
}
.pl-dot[data-state="ok"] { background: #2f8f6b; box-shadow: 0 0 0 3px rgba(47, 143, 107, 0.16); }
.pl-dot[data-state="warn"] { background: #c08a2e; box-shadow: 0 0 0 3px rgba(192, 138, 46, 0.16); }
.pl-dot[data-state="down"] { background: var(--pl-danger); box-shadow: 0 0 0 3px rgba(163, 58, 44, 0.16); }

/* Job status line. Sits under the header so "翻译到哪儿了" is answered without
   opening a panel; each state carries its own colour and verb. */
.pl-job {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 12px; font-size: 11.5px;
  border-bottom: 1px solid var(--pl-border);
  background: #f4f7f5; color: var(--pl-fg-soft);
}
.pl-job--info { background: #f2f6f5; }
.pl-job--ok { background: #eef7f1; }
.pl-job--warn { background: #fdf8ec; color: #6a4a10; }
.pl-job--error { background: #fdf4f2; color: #7c3025; }
.pl-job__label { font-weight: 600; }
.pl-job__detail { color: var(--pl-muted); min-width: 0; }
.pl-job--warn .pl-job__detail, .pl-job--error .pl-job__detail { color: inherit; opacity: 0.85; }
.pl-muted { color: var(--pl-muted); }
.pl-small { font-size: 11.5px; }
.pl-row { display: flex; align-items: center; gap: 8px; }
.pl-row--between { justify-content: space-between; }
.pl-col { display: flex; flex-direction: column; gap: 8px; }
.pl-label { font-size: 11.5px; color: var(--pl-muted); margin-bottom: 2px; display: block; }
.pl-field { margin-bottom: 8px; }
.pl-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.pl-spinner {
  width: 12px; height: 12px; border: 2px solid #cfd8d4; border-top-color: var(--pl-accent);
  border-radius: 50%; animation: pl-spin 0.8s linear infinite; display: inline-block;
}
@keyframes pl-spin { to { transform: rotate(360deg); } }
.pl-modal-backdrop {
  position: absolute; inset: 0; background: rgba(28, 34, 30, 0.28);
  pointer-events: auto; display: flex; align-items: center; justify-content: center; z-index: 20;
}
.pl-modal {
  width: min(520px, calc(100% - 40px)); max-height: 84%; overflow-y: auto;
  background: var(--pl-panel); border-radius: 12px; border: 1px solid var(--pl-border);
  box-shadow: 0 20px 50px rgba(0,0,0,0.22); padding: 14px 16px;
}
.pl-modal h3 { margin: 0 0 8px; font-size: 15px; display: flex; justify-content: space-between; align-items: center; }
.pl-term { display: grid; grid-template-columns: 1fr 1fr auto; gap: 6px; align-items: center; padding: 5px 0; border-bottom: 1px dashed var(--pl-border); }
.pl-term__src { font-weight: 600; }
.pl-badge { font-size: 10.5px; border-radius: 4px; padding: 0 5px; background: #eef1ee; color: #5b6661; }
.pl-badge--suggested { background: #fdf3e3; color: #8a5a12; }
.pl-empty { text-align: center; color: var(--pl-muted); padding: 28px 10px; font-size: 12px; }

/* Bilingual overlay */
.pl-bilingual {
  position: absolute; top: 0; left: 0; bottom: 0;
  /* Same clamp as .pl-sidebar: the two must agree exactly, otherwise the
     reading layer slides under the sidebar and covers its controls. */
  right: min(var(--pl-width, 380px), 100vw);
  background: #fdfcf8; border-right: 1px solid var(--pl-border);
  display: flex; flex-direction: column; pointer-events: auto; z-index: 6;
}
.pl-bilingual.full { right: 0; }
.pl-bilingual__bar {
  display: flex; align-items: center; gap: 8px; padding: 7px 12px;
  border-bottom: 1px solid var(--pl-border); background: #fff;
}
.pl-bilingual__bar .pl-title { font-weight: 600; color: var(--pl-accent); }
.pl-bilingual__cols { flex: 1; min-height: 0; display: flex; }
.pl-col-scroll { flex: 1; min-width: 0; overflow-y: auto; padding: 14px 18px; }
.pl-col-scroll + .pl-col-scroll { border-left: 1px solid var(--pl-border); background: #fffefb; }
.pl-col-head { font-size: 11px; letter-spacing: 0.6px; color: var(--pl-muted); text-transform: uppercase; margin-bottom: 8px; }
.pl-seg { margin-bottom: 12px; padding: 4px 6px; border-radius: 6px; cursor: default; }
.pl-seg:hover { background: #f5f7f4; }
.pl-seg.active { background: var(--pl-accent-weak); box-shadow: inset 2px 0 0 var(--pl-accent); }
.pl-seg__kind { font-size: 10px; color: #8a938d; margin-right: 4px; }
.pl-seg__text { font-size: 13.5px; }
.pl-seg--original .pl-seg__text { font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif; font-size: 14px; }
.pl-seg-note { font-size: 11px; color: var(--pl-warn); }
.pl-seg-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  padding: 8px 18px;
  border-bottom: 1px solid #f0eee7;
}
.pl-seg-grid.single { grid-template-columns: 1fr; }
@media (max-width: 900px) {
  .pl-seg-grid { grid-template-columns: 1fr; gap: 8px; }
  .pl-sidebar { width: min(var(--pl-width, 380px), 100vw); }
}
.pl-bilingual__empty { padding: 40px; text-align: center; color: var(--pl-muted); }
.pl-page-stage { display: flex; flex-direction: column; gap: 14px; padding: 12px 14px 20px; }
.pl-page-stage.dual { flex-direction: row; align-items: flex-start; }
.pl-page-col { min-width: 0; }
.pl-page-stage.dual .pl-page-col { flex: 1; }
.pl-page-frame {
  position: relative; overflow: hidden; background: #fff;
  border: 1px solid var(--pl-border); border-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}
.pl-page-img { display: block; width: 100%; height: 100%; user-select: none; }
.pl-seg-overlay {
  position: absolute; display: block; margin: 0; padding: 1px 1px 0; overflow: hidden;
  border: 0; border-radius: 2px; text-align: left; cursor: pointer;
  font-family: "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif;
  color: #14181b;
  /* Opaque: a translucent panel lets the English show through and makes the
     page look like it has doubled text. */
  background: #fffdf8;
  box-shadow: 0 0 0 1px rgba(45, 106, 79, 0.18);
  user-select: text; white-space: nowrap;
}
.pl-seg-overlay__line { display: block; white-space: pre; }
.pl-seg-overlay:hover { background: #fff; box-shadow: 0 0 0 1px var(--pl-accent); z-index: 3; }
.pl-seg-overlay.highlight { background: var(--pl-accent-weak); box-shadow: 0 0 0 2px var(--pl-accent); z-index: 4; }
.pl-seg-box { position: absolute; border-radius: 2px; pointer-events: none; }
.pl-seg-box.highlight { background: rgba(45, 106, 79, 0.16); box-shadow: 0 0 0 2px var(--pl-accent); }
.pl-page-detail {
  border-top: 1px solid var(--pl-border); background: #fff;
  padding: 8px 12px 10px; max-height: 38%; overflow-y: auto;
}

/* ---------------------------------------------------------------- markdown */
.pl-md { flex: 1; min-height: 0; display: flex; flex-direction: column; background: #fdfcf8; }
.pl-md__toolbar {
  display: flex; align-items: center; gap: 8px; padding: 6px 12px;
  border-bottom: 1px solid var(--pl-border); background: #fff;
  position: sticky; top: 0; z-index: 5;
}
.pl-md__body {
  flex: 1; min-height: 0; overflow-y: auto;
  /* Fill the sidebar: a centred narrow column left visible dead space on both
     sides and made long English paragraphs wrap more than the width allowed. */
  padding: 18px 20px 72px;
  width: 100%;
  font-size: 14px; line-height: 1.62; color: #16191c;
}
.pl-md__page {
  display: flex; align-items: center; gap: 8px;
  margin: 22px 0 10px; color: var(--pl-faint); font-size: 10.5px;
  letter-spacing: 0.7px; text-transform: uppercase;
  position: sticky; top: -1px; z-index: 3;
  background: linear-gradient(#fdfcf8 82%, rgba(253, 252, 248, 0));
  padding: 4px 0 5px;
}
.pl-md__page::after { content: ""; flex: 1; height: 1px; background: var(--pl-border-soft); }
.pl-md__page:first-child { margin-top: 0; }
.pl-md__heading { margin: 26px 0 12px; cursor: default; }
.pl-md__heading--2 { font-size: 20px; font-weight: 700; letter-spacing: -0.2px; }
.pl-md__heading--3 { font-size: 16.5px; font-weight: 650; letter-spacing: -0.1px; }
.pl-md__heading--4, .pl-md__heading--5, .pl-md__heading--6 { font-size: 14.5px; font-weight: 650; }
.pl-md__para {
  margin: 0 0 6px; padding: 7px 10px; border-radius: var(--pl-radius-sm);
  cursor: default;
  transition: background 0.12s ease;
}
.pl-md__figure {
  margin: 10px 0 18px; padding: 10px; border-radius: var(--pl-radius);
  background: #fff; border: 1px solid var(--pl-border);
  box-shadow: var(--pl-shadow-1);
  transition: box-shadow 0.16s ease, border-color 0.16s ease;
}
.pl-md__figure:hover { box-shadow: var(--pl-shadow-2); border-color: #d8d5c9; }
.pl-md__figure-img {
  display: block; width: 100%; height: auto; cursor: zoom-in;
  border-radius: 4px; background: #fff;
}
.pl-md__figure-label {
  display: flex; align-items: center; gap: 8px;
  margin-top: 8px; color: var(--pl-muted); font-size: 11.5px;
  letter-spacing: 0.3px;
}
.pl-md__figure-loading,
.pl-md__figure-fallback {
  display: block; width: 100%; padding: 26px 10px;
  border: 1px dashed var(--pl-border); border-radius: var(--pl-radius-sm);
  background: #faf9f5; color: var(--pl-muted); font-size: 12px; text-align: center;
}
/* A quiet shimmer while the crop is being rendered, instead of a bare sentence
   that reads like an error. */
.pl-md__figure-loading {
  background: linear-gradient(100deg, #faf9f5 30%, #f3f2ec 50%, #faf9f5 70%);
  background-size: 220% 100%;
  animation: pl-shimmer 1.4s ease-in-out infinite;
}
@keyframes pl-shimmer {
  from { background-position: 130% 0; }
  to { background-position: -30% 0; }
}
.pl-md__figure-fallback { cursor: pointer; }
.pl-md__figure-fallback:hover { border-color: #c9c5b6; color: var(--pl-fg-soft); }
/* When both render paths fail the reason and the two ways out are shown here,
   so a missing figure is a dead end that says why. */
.pl-md__figure-failed {
  display: flex; flex-direction: column; gap: 6px;
  padding: 14px 12px; border: 1px dashed var(--pl-border);
  border-radius: var(--pl-radius-sm); background: #faf9f5; color: var(--pl-fg-soft);
}
.pl-md__figure-failed .pl-actions { margin-top: 0; }

/* ---- zoom overlay ------------------------------------------------------ */
/* A fixed layer rather than a route: the reading position must not move while
   a picture is being looked at. */
.pl-zoom {
  position: fixed; inset: 0; z-index: 60;
  background: rgba(24, 27, 26, 0.72);
  display: flex; align-items: center; justify-content: center;
  padding: 18px;
  animation: pl-fade-in 0.14s ease-out;
}
@keyframes pl-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
.pl-zoom__panel {
  display: flex; flex-direction: column; max-width: 100%; max-height: 100%;
  background: #fff; border-radius: var(--pl-radius);
  box-shadow: var(--pl-shadow-3); overflow: hidden;
}
.pl-zoom__bar {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 6px 10px; border-bottom: 1px solid var(--pl-border-soft); background: #faf9f5;
}
.pl-zoom__canvas {
  overflow: auto; padding: 10px; background: #f2f0ea;
  display: flex; align-items: flex-start; justify-content: center;
}
.pl-zoom__canvas img {
  max-width: 100%; height: auto; display: block; background: #fff;
  box-shadow: var(--pl-shadow-1); border-radius: 3px;
}
.pl-md__para:hover, .pl-md__heading:hover { background: #f5f7f3; }
.pl-md__para.active, .pl-md__heading.active {
  background: var(--pl-accent-weak); box-shadow: inset 3px 0 0 var(--pl-accent);
}
.pl-md__para--minor { opacity: 0.88; font-size: 13px; }
.pl-md__en {
  margin: 0;
  font-family: var(--pl-serif);
  font-size: 14.5px; line-height: 1.66; color: #1a1d20;
  /* Long English words and DOIs must not blow out the column width. */
  overflow-wrap: break-word;
}
.pl-md__zh {
  margin: 7px 0 0; padding-left: 11px;
  border-left: 2px solid var(--pl-accent-weak);
  font-family: "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif;
  font-size: 13.8px; line-height: 1.78; color: #232f29;
  overflow-wrap: break-word;
}
.pl-md__zh--heading { margin-top: 4px; border-left-color: var(--pl-accent); font-weight: 600; }
.pl-md__actions { display: flex; gap: 6px; margin-top: 6px; }
@media (max-width: 620px) {
  .pl-md__body { padding: 12px 12px 56px; }
  .pl-md__en { font-size: 14px; }
}
`;
