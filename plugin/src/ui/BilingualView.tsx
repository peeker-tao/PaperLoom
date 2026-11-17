import { useState } from "react";
import type { ReaderController, UIState } from "../reader/controller";
import type { Selection } from "../types";
import { IconButton } from "./common";

export function BilingualView(props: { controller: ReaderController; state: UIState }): JSX.Element | null {
  const { controller, state } = props;
  const [active, setActive] = useState<string | null>(null);
  const [picked, setPicked] = useState<Selection | null>(null);
  if (!state.bilingualOpen || !state.document) {
    return null;
  }
  const pageSegments = state.segments.filter((segment) => segment.page === state.page);
  const translated = pageSegments.filter((segment) => segment.translation).length;
  const dual = state.mode === "dual";

  const captureSelection = () => {
    const doc = (controller as any).reader?._iframeWindow?.document as Document | undefined;
    const selection = doc?.getSelection?.() || null;
    const text = selection?.toString().trim();
    if (text && text.length > 1) {
      setPicked({ text, page: state.page, kind: "text" });
    }
  };

  return (
    <div className={`pl-bilingual${state.sidebarOpen ? "" : " full"}`}>
      <div className="pl-bilingual__bar">
        <span className="pl-title">双语对照</span>
        <span className="pl-small pl-muted">
          第 {state.page} / {state.document.pages} 页 · 本页 {translated}/{pageSegments.length} 段已译
        </span>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          className={`pl-btn${state.mode === "original" ? " pl-btn--primary" : ""}`}
          onClick={() => controller.setMode("original")}
        >
          原文
        </button>
        <button
          type="button"
          className={`pl-btn${state.mode === "translated" ? " pl-btn--primary" : ""}`}
          onClick={() => controller.setMode("translated")}
        >
          译文
        </button>
        <button
          type="button"
          className={`pl-btn${state.mode === "dual" ? " pl-btn--primary" : ""}`}
          onClick={() => controller.setMode("dual")}
        >
          双语
        </button>
        <IconButton title="上一页" onClick={() => controller.jumpTo(Math.max(1, state.page - 1))}>
          ‹
        </IconButton>
        <input
          className="pl-input"
          style={{ width: 54, textAlign: "center" }}
          value={state.page}
          onChange={(event) => {
            const page = Number(event.target.value);
            if (page >= 1 && page <= state.document!.pages) {
              controller.jumpTo(page);
            }
          }}
        />
        <IconButton title="下一页" onClick={() => controller.jumpTo(Math.min(state.document!.pages, state.page + 1))}>
          ›
        </IconButton>
        <button type="button" className="pl-btn pl-btn--ghost" onClick={() => controller.toggleBilingual(false)}>
          返回 PDF
        </button>
      </div>

      {picked ? (
        <div className="pl-bilingual__bar" style={{ background: "#f7f8f5" }}>
          <span className="pl-chip" title={picked.text}>
            <span>{picked.text.slice(0, 80)}</span>
          </span>
          <button type="button" className="pl-btn" onClick={() => controller.explainSelection(picked)}>
            解释
          </button>
          <button type="button" className="pl-btn" onClick={() => controller.askSelection(picked)}>
            提问
          </button>
          <button type="button" className="pl-btn" onClick={() => void controller.saveSelectionNote(picked)}>
            保存笔记
          </button>
          <button type="button" className="pl-btn pl-btn--ghost" onClick={() => setPicked(null)}>
            取消
          </button>
        </div>
      ) : null}

      {state.document.alignment !== "segment" ? (
        <div className="pl-card pl-card--warn pl-small" style={{ margin: "8px 12px 0" }}>
          {state.document.alignmentNote}（对齐级别：{state.document.alignment}）
        </div>
      ) : null}

      <div
        className="pl-bilingual__cols"
        style={{ display: "block", overflowY: "auto" }}
        onMouseUp={captureSelection}
      >
        {!pageSegments.length ? (
          <div className="pl-bilingual__empty">
            本页没有可显示的段落。可能是扫描页、纯图表页，或分段合并失败。
          </div>
        ) : null}
        {pageSegments.map((segment) => (
          <div
            key={segment.id}
            className={`pl-seg${active === segment.id ? " active" : ""} pl-seg-grid${dual ? "" : " single"}`}
            onClick={() => setActive(segment.id)}
          >
            {state.mode !== "translated" ? (
              <div className="pl-seg--original">
                <div className="pl-seg__kind">{segment.kind}</div>
                <div className="pl-seg__text">{segment.text}</div>
              </div>
            ) : null}
            {state.mode !== "original" ? (
              <div>
                {segment.translation ? (
                  <div className="pl-seg__text">{segment.translation}</div>
                ) : (
                  <div className="pl-seg-note">未翻译（{segment.kind}）</div>
                )}
                <div className="pl-actions" style={{ marginTop: 2 }}>
                  <button
                    type="button"
                    className="pl-btn pl-btn--ghost"
                    onClick={(event) => {
                      event.stopPropagation();
                      controller.jumpTo(segment.page);
                    }}
                  >
                    PDF 第 {segment.page} 页
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
