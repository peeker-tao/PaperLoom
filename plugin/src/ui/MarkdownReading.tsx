import { useMemo, useState } from "react";
import { describeCounts, translationCounts } from "../counts";
import type { ReaderController, UIState } from "../reader/controller";
import type { Segment } from "../types";
import { PageCrop } from "./PageCrop";

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
  // Counted with the same rule the translator uses, so this number agrees with
  // the footer instead of quietly measuring something else.
  const counts = translationCounts(state.segments);

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
            title="隐藏译文，在 PDF 中定位到这一页"
            onClick={() => void controller.jumpToPageInPdf(segment.page)}
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
        controller={controller}
        mode={mode}
        active={active === segment.id}
        onPick={() => setActive(active === segment.id ? null : segment.id)}
        onJump={() => controller.jumpToSegmentInPdf(segment.id)}
      />,
    );
  }

  return (
    <div className="pl-md">
      <div className="pl-md__toolbar">
        <span className="pl-small pl-muted">
          {describeCounts(counts)} 段已译
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
        {/* "只显示译文" with nothing translated is a blank page. Say why, and
            offer the one click that fixes it. */}
        {mode === "translated" && counts.done === 0 ? (
          <div className="pl-card pl-card--warn pl-small" style={{ marginBottom: 12 }}>
            <strong>还没有任何译文</strong>
            <div style={{ marginTop: 4 }}>
              当前是「只显示译文」模式，所以这里是空的。可以先翻译，或切回双语看原文。
            </div>
            <div className="pl-actions">
              <button
                type="button"
                className="pl-btn pl-btn--primary"
                disabled={Boolean(controller.translationBlockedReason())}
                onClick={() => void controller.startTranslation([state.page])}
              >
                翻译本页
              </button>
              <button
                type="button"
                className="pl-btn pl-btn--ghost"
                onClick={() => controller.setMode("dual")}
              >
                改看双语
              </button>
            </div>
          </div>
        ) : null}
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
  controller: ReaderController;
  mode: "original" | "translated" | "dual";
  active: boolean;
  onPick(): void;
  onJump(): void;
}): JSX.Element {
  const { segment, controller, mode, active, onPick, onJump } = props;
  const heading = segment.kind === "title" || segment.kind === "heading";
  const showOriginal = mode !== "translated";
  const showTranslation = mode !== "original";
  const hasTranslation = Boolean(segment.translation);

  if (segment.kind === "figure") {
    // The service marks the empty area next to a caption; the picture itself is
    // cropped out of the rendered page, so figures stay visible in the
    // reading view instead of silently disappearing.
    return (
      <figure className="pl-md__figure" data-segment-id={segment.id} onClick={onPick}>
        <PageCrop
          controller={controller}
          page={segment.page}
          bbox={segment.bbox}
          alt={segment.text || "原文图片"}
          onOpen={onJump}
        />
        <figcaption className="pl-md__figure-label">
          {segment.text}
          <button
            type="button"
            className="pl-btn pl-btn--ghost pl-small"
            onClick={(event) => {
              event.stopPropagation();
              onJump();
            }}
          >
            查看原页
          </button>
        </figcaption>
      </figure>
    );
  }

  if (heading) {
    const level = headingLevel(segment);
    return (
      <div
        className={`pl-md__heading pl-md__heading--${level}${active ? " active" : ""}`}
        data-segment-id={segment.id}
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
      data-segment-id={segment.id}
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
