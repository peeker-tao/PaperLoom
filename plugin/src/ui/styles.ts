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
  max-width: 620px;
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
}
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
`;
