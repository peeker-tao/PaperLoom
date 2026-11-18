export const SHADOW_CSS = `
:host { all: initial; }
.pl-root {
  --pl-bg: #fbfaf7;
  --pl-panel: #ffffff;
  --pl-fg: #22262b;
  --pl-muted: #6d736f;
  --pl-border: #e4e1d8;
  --pl-accent: #23615a;
  --pl-accent-weak: #e7f0ed;
  --pl-warn: #8a5a12;
  --pl-danger: #a33a2c;
  --pl-radius: 8px;
  position: fixed;
  inset: 0;
  pointer-events: none;
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
  font-size: 13px;
  line-height: 1.55;
  color: var(--pl-fg);
  z-index: 2147483000;
}
.pl-root * { box-sizing: border-box; }
.pl-sidebar {
  position: absolute;
  top: 0; right: 0; bottom: 0;
  width: var(--pl-width, 380px);
  min-width: 300px;
  /* Matches SIDEBAR_MAX_WIDTH in the controller: a reading column should be
     able to use the screen instead of stopping at a fixed strip. */
  max-width: min(960px, 100vw);
  display: flex;
  flex-direction: column;
  background: var(--pl-bg);
  border-left: 1px solid var(--pl-border);
  box-shadow: -6px 0 20px rgba(20, 30, 25, 0.07);
  pointer-events: auto;
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
.pl-msg { margin-bottom: 12px; }
.pl-msg__role { font-size: 11px; color: var(--pl-muted); margin-bottom: 3px; text-transform: uppercase; letter-spacing: 0.4px; }
.pl-msg--user .pl-msg__bubble {
  background: var(--pl-accent-weak); border-radius: 10px 10px 2px 10px;
  padding: 8px 10px; white-space: pre-wrap; word-break: break-word;
}
.pl-msg--assistant .pl-msg__bubble {
  background: var(--pl-panel); border: 1px solid var(--pl-border);
  border-radius: 10px 10px 10px 2px; padding: 8px 10px;
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
  border: 1px solid var(--pl-border); background: var(--pl-panel); color: var(--pl-fg);
  border-radius: 6px; padding: 4px 9px; font-size: 12px; cursor: pointer;
}
.pl-btn:hover { border-color: #cfd8d4; background: #f7f8f6; }
.pl-btn--primary { background: var(--pl-accent); border-color: var(--pl-accent); color: #fff; }
.pl-btn--primary:hover { background: #1c5049; }
.pl-btn--ghost { border-color: transparent; color: var(--pl-muted); }
.pl-btn--danger { color: var(--pl-danger); border-color: #e6c3bc; }
.pl-btn:disabled { opacity: 0.55; cursor: not-allowed; }
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
.pl-composer { border-top: 1px solid var(--pl-border); padding: 8px 10px 10px; background: var(--pl-panel); }
.pl-composer__row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
.pl-textarea { width: 100%; min-height: 60px; max-height: 160px; resize: vertical; line-height: 1.5; }
.pl-composer__bottom { display: flex; justify-content: space-between; align-items: center; margin-top: 6px; gap: 8px; }
.pl-chip {
  display: inline-flex; align-items: center; gap: 6px; max-width: 100%;
  background: #f3f6f3; border: 1px solid #dbe5df; color: #45514c;
  border-radius: 999px; padding: 2px 8px; font-size: 11.5px;
}
.pl-chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 210px; }
.pl-chip button { border: none; background: transparent; cursor: pointer; color: inherit; font-size: 12px; }
.pl-footer {
  display: flex; align-items: center; gap: 8px; padding: 5px 10px;
  border-top: 1px solid var(--pl-border); background: #f6f5f0; color: var(--pl-muted); font-size: 11px;
}
.pl-progress { flex: 1; height: 4px; background: #e7e4da; border-radius: 999px; overflow: hidden; }
.pl-progress > div { height: 100%; background: var(--pl-accent); transition: width 0.25s; }
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
  position: absolute; top: 0; left: 0; bottom: 0; right: var(--pl-width, 380px);
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
  padding: 16px 18px 60px;
  width: 100%;
  font-size: 14px; line-height: 1.62; color: #16191c;
}
.pl-md__page {
  display: flex; align-items: center; gap: 8px;
  margin: 26px 0 12px; color: var(--pl-muted); font-size: 11px;
  letter-spacing: 0.4px; text-transform: uppercase;
}
.pl-md__page::after { content: ""; flex: 1; height: 1px; background: var(--pl-border); }
.pl-md__page:first-child { margin-top: 0; }
.pl-md__heading { margin: 22px 0 10px; cursor: default; }
.pl-md__heading--2 { font-size: 19px; font-weight: 700; }
.pl-md__heading--3 { font-size: 16px; font-weight: 650; }
.pl-md__heading--4, .pl-md__heading--5, .pl-md__heading--6 { font-size: 14.5px; font-weight: 650; }
.pl-md__para { margin: 0 0 14px; padding: 4px 8px; border-radius: 5px; cursor: default; }
.pl-md__figure {
  margin: 6px 0 16px; padding: 8px; border-radius: 6px;
  background: #fff; border: 1px solid var(--pl-border);
}
.pl-md__figure-img {
  display: block; width: 100%; height: auto; cursor: zoom-in;
  border-radius: 3px; background: #fff;
}
.pl-md__figure-label {
  display: flex; align-items: center; gap: 8px;
  margin-top: 6px; color: var(--pl-muted); font-size: 11.5px;
  letter-spacing: 0.3px;
}
.pl-md__figure-loading,
.pl-md__figure-fallback {
  display: block; width: 100%; padding: 24px 10px;
  border: 1px dashed var(--pl-border); border-radius: 4px;
  background: #faf9f5; color: var(--pl-muted); font-size: 12px; text-align: center;
}
.pl-md__figure-fallback { cursor: pointer; }
.pl-md__para:hover, .pl-md__heading:hover { background: #f4f6f3; }
.pl-md__para.active, .pl-md__heading.active {
  background: var(--pl-accent-weak); box-shadow: inset 2px 0 0 var(--pl-accent);
}
.pl-md__para--minor { opacity: 0.86; font-size: 13px; }
.pl-md__en {
  margin: 0;
  font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: 14.5px; line-height: 1.6; color: #1a1d20;
}
.pl-md__zh {
  margin: 6px 0 0; padding-left: 10px;
  border-left: 2px solid var(--pl-accent-weak);
  font-family: "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif;
  font-size: 13.8px; line-height: 1.75; color: #24302a;
}
.pl-md__zh--heading { margin-top: 4px; border-left-color: var(--pl-accent); font-weight: 600; }
.pl-md__actions { display: flex; gap: 6px; margin-top: 4px; }
@media (max-width: 620px) {
  .pl-md__body { padding: 12px 12px 48px; }
  .pl-md__en { font-size: 14px; }
}
`;
