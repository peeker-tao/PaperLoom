import { useMemo, useState } from "react";
import type { ReaderController, UIState } from "../reader/controller";
import type { Segment } from "../types";

const PROSE_KINDS = new Set(["body", "abstract", "caption"]);
const HIDDEN_KINDS = new Set(["noise", "meta", "formula", "table"]);

/**
 * Markdown reading view: the paper as reflowed text, English first and the
 * Chinese translation directly underneath each paragraph.
 *
 * There is deliberately no PDF layout here. Reflowed text stays readable at any
 * width, keeps every paragraph complete (no box to fit into), and can be copied
 * out as Markdown — which is what the export buttons do. Figures and equations
 * are not reproduced; they remain visible in the PDF, one click away through
 * the "第 N 页" link on each paragraph.
 */
export function MarkdownReading(props: {
  controller: ReaderController;
  state: UIState;
  mode: "original" | "translated" | "dual";
}): JSX.Element {
  const { controller, state, mode } = props;
  const [showReferences, setShowReferences] = useState(false);
  const [active, setActive] = useState<string | null>(null);

  const segments = useMemo(
    () =>
      state.segments.filter((segment) => {
        if (HIDDEN_KINDS.has(segment.kind)) {
          return false;
        }
        if (segment.kind === "reference") {
          return showReferences;
        }
        return true;
      }),
    [state.segments, showReferences],
  );

  const referenceCount = state.segments.filter((s) => s.kind === "reference").length;
  const translated = state.segments.filter((s) => s.translation).length;
  const translatable = state.segments.filter(
    (s) => !HIDDEN_KINDS.has(s.kind) && s.kind !== "reference",
  ).length;

  let lastPage = 0;
  const rows: JSX.Element[] = [];
  for (const segment of segments) {
    if (segment.page !== lastPage) {
      lastPage = segment.page;
      rows.push(
        <div key={`page-${segment.page}`} className="pl-md__page">
          <span>第 {segment.page} 页</span>
          <button
            type="button"
            className="pl-btn pl-btn--ghost pl-small"
            onClick={() => controller.jumpTo(segment.page)}
          >
            在 PDF 中查看
          </button>
        </div>,
      );
    }
    rows.push(
      <Paragraph
        key={segment.id}
        segment={segment}
        mode={mode}
        active={active === segment.id}
        onPick={() => setActive(active === segment.id ? null : segment.id)}
        onJump={() => controller.jumpToSegment(segment.id)}
      />,
    );
  }

  return (
    <div className="pl-md">
      <div className="pl-md__toolbar">
        <span className="pl-small pl-muted">
          {translated}/{translatable} 段已译 · {state.segments.length} 段
        </span>
        <span style={{ flex: 1 }} />
        {referenceCount ? (
          <button
            type="button"
            className="pl-btn pl-btn--ghost"
            title="参考文献通常不值得翻译，默认不显示"
            onClick={() => setShowReferences(!showReferences)}
          >
            {showReferences ? "隐藏参考文献" : `参考文献 ${referenceCount}`}
          </button>
        ) : null}
        <button
          type="button"
          className="pl-btn"
          title="复制全文 Markdown（英文在前，中文在后）"
          onClick={() => void controller.copyMarkdown({ references: showReferences })}
        >
          复制 Markdown
        </button>
        <button
          type="button"
          className="pl-btn"
          title="把全文双语保存为 Zotero 子笔记"
          onClick={() => void controller.saveMarkdownNote({ references: showReferences })}
        >
          存为笔记
        </button>
      </div>

      <div className="pl-md__body">
        {!segments.length ? (
          <div className="pl-bilingual__empty">
            还没有可读的正文。若刚打开论文，脚本可能仍在解析；扫描件需要先 OCR。
          </div>
        ) : null}
        {rows}
      </div>
    </div>
  );
}

function Paragraph(props: {
  segment: Segment;
  mode: "original" | "translated" | "dual";
  active: boolean;
  onPick(): void;
  onJump(): void;
}): JSX.Element {
  const { segment, mode, active, onPick, onJump } = props;
  const heading = segment.kind === "title" || segment.kind === "heading";
  const showOriginal = mode !== "translated";
  const showTranslation = mode !== "original";
  const hasTranslation = Boolean(segment.translation);

  if (heading) {
    const level = headingLevel(segment);
    return (
      <div
        className={`pl-md__heading pl-md__heading--${level}${active ? " active" : ""}`}
        onClick={onPick}
      >
        {showOriginal ? <div className="pl-md__en">{segment.text}</div> : null}
        {showTranslation && hasTranslation ? (
          <div className="pl-md__zh pl-md__zh--heading">{segment.translation}</div>
        ) : null}
        {active ? <SegmentActions onJump={onJump} /> : null}
      </div>
    );
  }

  return (
    <div
      className={`pl-md__para${PROSE_KINDS.has(segment.kind) ? "" : " pl-md__para--minor"}${
        active ? " active" : ""
      }`}
      onClick={onPick}
    >
      {showOriginal ? <p className="pl-md__en">{segment.text}</p> : null}
      {showTranslation && hasTranslation ? <p className="pl-md__zh">{segment.translation}</p> : null}
      {showTranslation && !hasTranslation && !showOriginal ? (
        <p className="pl-seg-note">未翻译</p>
      ) : null}
      {active ? <SegmentActions onJump={onJump} /> : null}
    </div>
  );
}

function SegmentActions(props: { onJump(): void }): JSX.Element {
  return (
    <div className="pl-md__actions">
      <button
        type="button"
        className="pl-btn pl-btn--ghost pl-small"
        onClick={(event) => {
          event.stopPropagation();
          props.onJump();
        }}
      >
        定位原文
      </button>
    </div>
  );
}

/** "2.1 Text-to-Image" -> 4; the chapter heading itself -> 3; title -> 2. */
function headingLevel(segment: Segment): number {
  if (segment.kind === "title") {
    return 2;
  }
  const match = /^(\d+(?:\.\d+)*)\s+/.exec(segment.text.trim());
  if (match) {
    return Math.min(6, 3 + match[1].split(".").length - 1);
  }
  return 3;
}
