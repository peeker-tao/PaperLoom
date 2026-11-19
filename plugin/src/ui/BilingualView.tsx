import { useEffect, useRef, useState } from "react";
import { describeCounts, translationCounts } from "../counts";
import type { ReaderController, UIState } from "../reader/controller";
import type { Segment, Selection } from "../types";
import type { RenderedPage } from "../zotero/api";
import { MarkdownReading } from "./MarkdownReading";
import { overlayGeometry } from "./overlay";
import { IconButton } from "./common";

type Layout = "markdown" | "overlay";

/**
 * Bilingual reading view.
 *
 * The default layout is Markdown: the paper as reflowed text, English first and
 * Chinese underneath, page by page. It needs no PDF layout, stays readable at
 * any width, never truncates a paragraph to fit a box, and can be exported as
 * Markdown.
 *
 * "overlay" is the optional layout-preserving view: the real page bitmap with
 * the translation drawn on top, useful when figures and equations matter more
 * than comfortable reading.
 */
export function BilingualView(props: { controller: ReaderController; state: UIState }): JSX.Element | null {
  const { controller, state } = props;
  const [active, setActive] = useState<string | null>(null);
  const [layout, setLayout] = useState<Layout>("markdown");
  const [showNoise, setShowNoise] = useState(false);
  const [image, setImage] = useState<RenderedPage | null>(null);
  const [renderFailed, setRenderFailed] = useState(false);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [stageWidth, setStageWidth] = useState(0);

  const document = state.document;
  const mode = state.mode;

  // Measure the stage so the bitmap is rendered at the right resolution.
  useEffect(() => {
    const node = stageRef.current;
    if (!node || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const width = Math.round(entries[0]?.contentRect?.width || 0);
      setStageWidth((previous) => (Math.abs(previous - width) > 12 ? width : previous));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [state.bilingualOpen, document?.id]);

  const dualColumns = mode === "dual" && (stageWidth === 0 || stageWidth > 560);
  const columnWidth = dualColumns
    ? Math.max(220, Math.floor((stageWidth - 30) / 2))
    : Math.max(220, Math.floor((stageWidth || 640) - 28));

  useEffect(() => {
    let cancelled = false;
    if (!state.bilingualOpen || !document || layout !== "overlay") {
      return;
    }
    setRenderFailed(false);
    void controller.loadPageImage(state.page, columnWidth).then((rendered) => {
      if (cancelled) {
        return;
      }
      setImage(rendered);
      setRenderFailed(!rendered);
    });
    return () => {
      cancelled = true;
    };
  }, [controller, state.bilingualOpen, state.page, document?.id, columnWidth, layout]);

  if (!state.bilingualOpen || !document) {
    return null;
  }

  const pageSegments = state.segments.filter(
    (segment) =>
      segment.page === state.page && (showNoise || segment.kind !== "noise"),
  );
  const noiseCount = state.segments.filter(
    (segment) => segment.page === state.page && segment.kind === "noise",
  ).length;
  // "本页 3/9" counted noise blocks as work to do, so a fully translated page
  // still read "3/9" next to a footer claiming a different denominator.
  const pageCounts = translationCounts(pageSegments);
  const paperCounts = translationCounts(state.segments);
  const overlayReady = layout === "overlay" && Boolean(image) && !renderFailed;
  // 版式视图 only draws *translations* on top of the page bitmap, so a page with
  // none shows nothing but the original page — which reads as "the translation
  // does not work" rather than "this page is not translated yet".
  const pageUntranslated = pageCounts.total > 0 && pageCounts.done === 0;
  const blockedReason = controller.translationBlockedReason();

  const activeSegment = active ? pageSegments.find((item) => item.id === active) || null : null;

  return (
    <div className={`pl-bilingual${state.sidebarOpen ? "" : " full"}`}>
      <div className="pl-bilingual__bar">
        <span className="pl-title">双语对照</span>
        <span className="pl-small pl-muted">
          {layout === "markdown"
            ? `全文 ${describeCounts(paperCounts)} 段已译`
            : `第 ${state.page} / ${document.pages} 页 · 本页 ${describeCounts(pageCounts)} 段已译`}
        </span>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          className={`pl-btn${mode === "original" ? " pl-btn--primary" : ""}`}
          onClick={() => controller.setMode("original")}
        >
          原文
        </button>
        <button
          type="button"
          className={`pl-btn${mode === "translated" ? " pl-btn--primary" : ""}`}
          onClick={() => controller.setMode("translated")}
        >
          译文
        </button>
        <button
          type="button"
          className={`pl-btn${mode === "dual" ? " pl-btn--primary" : ""}`}
          onClick={() => controller.setMode("dual")}
        >
          双语
        </button>
        <button
          type="button"
          className={`pl-btn${layout === "overlay" ? " pl-btn--primary" : ""}`}
          title={
            layout === "markdown"
              ? "切换为保留版式（页面原图 + 译文叠放，图片公式不丢）"
              : "切换回纯文本阅读（推荐）"
          }
          onClick={() => setLayout(layout === "markdown" ? "overlay" : "markdown")}
        >
          {layout === "markdown" ? "版式" : "阅读"}
        </button>
        {layout === "overlay" && noiseCount ? (
          <button
            type="button"
            className="pl-btn pl-btn--ghost"
            title="公式碎片、行号等不参与翻译的片段"
            onClick={() => setShowNoise(!showNoise)}
          >
            {showNoise ? `隐藏 ${noiseCount} 片段` : `显示 ${noiseCount} 片段`}
          </button>
        ) : null}
        {layout === "overlay" ? (
          <>
            <IconButton title="上一页" onClick={() => controller.jumpTo(Math.max(1, state.page - 1))}>
              ‹
            </IconButton>
            <input
              className="pl-input"
              style={{ width: 54, textAlign: "center" }}
              value={state.page}
              onChange={(event) => {
                const page = Number(event.target.value);
                if (page >= 1 && page <= document.pages) {
                  controller.jumpTo(page);
                }
              }}
            />
            <IconButton
              title="下一页"
              onClick={() => controller.jumpTo(Math.min(document.pages, state.page + 1))}
            >
              ›
            </IconButton>
          </>
        ) : null}
        <button
          type="button"
          className="pl-btn pl-btn--ghost"
          title={`回到原 PDF 第 ${state.page} 页（保留译文阅读位置）`}
          onClick={() => void controller.jumpToPageInPdf(state.page)}
        >
          返回 PDF
        </button>
      </div>

      {document.alignment !== "segment" ? (
        <div className="pl-card pl-card--warn pl-small" style={{ margin: "8px 12px 0" }}>
          {document.alignmentNote}（对齐级别：{document.alignment}）
        </div>
      ) : null}

      {layout === "markdown" ? (
        <MarkdownReading controller={controller} state={state} mode={mode} />
      ) : (
      <div
        ref={stageRef}
        className="pl-bilingual__cols"
        style={{ display: "block", overflowY: "auto" }}
      >
        {layout === "overlay" && pageUntranslated ? (
          <div className="pl-card pl-card--warn pl-small" style={{ margin: "8px 12px 0" }}>
            <strong>第 {state.page} 页还没有译文</strong>
            <div style={{ marginTop: 4 }}>
              版式视图是把译文盖在原文页面上，所以这一页现在只能看到原始 PDF。本页共{" "}
              {pageCounts.total} 段待译。
            </div>
            <div className="pl-actions">
              <button
                type="button"
                className="pl-btn pl-btn--primary"
                disabled={Boolean(blockedReason)}
                title={blockedReason || `翻译第 ${state.page} 页`}
                onClick={() => void controller.startTranslation([state.page])}
              >
                翻译本页
              </button>
              <button
                type="button"
                className="pl-btn pl-btn--ghost"
                title="纯文本阅读视图：英文与中文逐段对照，不需要先有译文"
                onClick={() => setLayout("markdown")}
              >
                改用阅读视图
              </button>
            </div>
          </div>
        ) : null}
        {!pageSegments.length ? (
          <div className="pl-bilingual__empty">
            本页没有可显示的段落。可能是扫描页、纯图表页，或分段合并失败。
          </div>
        ) : null}

        {overlayReady && image ? (
          <PageStage
            controller={controller}
            state={state}
            image={image}
            segments={pageSegments}
            dualColumns={dualColumns}
            onPick={setActive}
          />
        ) : (
          <>
            {renderFailed ? (
              <div className="pl-card pl-card--warn pl-small" style={{ margin: "8px 12px 0" }}>
                无法渲染页面图像（可能尚未加载完成或页面被旋转），已回退为纯文本。
              </div>
            ) : null}
            {pageSegments.map((segment) => (
              <div
                key={segment.id}
                data-segment-id={segment.id}
                className={`pl-seg${active === segment.id ? " active" : ""} pl-seg-grid${mode === "dual" ? "" : " single"}`}
                onClick={() => setActive(segment.id)}
              >
                {mode !== "translated" ? (
                  <div className="pl-seg--original">
                    <div className="pl-seg__kind">{segment.kind}</div>
                    <div className="pl-seg__text">{segment.text}</div>
                  </div>
                ) : null}
                {mode !== "original" ? (
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
                          controller.jumpToSegment(segment.id);
                        }}
                      >
                        PDF 第 {segment.page} 页
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            ))}
          </>
        )}
      </div>
      )}

      {layout === "overlay" && activeSegment ? (
        <div className="pl-page-detail">
          <div className="pl-row pl-row--between">
            <span className="pl-small pl-muted">
              第 {activeSegment.page} 页 · {activeSegment.kind} · {activeSegment.align}
            </span>
            <span className="pl-actions">
              <button
                type="button"
                className="pl-btn pl-btn--ghost"
                onClick={() => controller.jumpToSegment(activeSegment.id)}
              >
                定位原文
              </button>
              <button
                type="button"
                className="pl-btn pl-btn--ghost"
                onClick={() => controller.explainSelection(segmentToSelection(activeSegment))}
              >
                解释
              </button>
              <button type="button" className="pl-btn pl-btn--ghost" onClick={() => setActive(null)}>
                关闭
              </button>
            </span>
          </div>
          <div className="pl-small pl-muted">原文</div>
          <div className="pl-seg__text pl-seg--original">{activeSegment.text}</div>
          <div className="pl-small pl-muted" style={{ marginTop: 6 }}>
            译文
          </div>
          <div className="pl-seg__text">{activeSegment.translation || "（未翻译）"}</div>
        </div>
      ) : null}
    </div>
  );
}

/** Page bitmap with translated paragraphs anchored to their original boxes. */
function PageStage(props: {
  controller: ReaderController;
  state: UIState;
  image: RenderedPage;
  segments: Segment[];
  dualColumns: boolean;
  onPick(segmentId: string | null): void;
}): JSX.Element {
  const { controller, state, image, segments, dualColumns, onPick } = props;
  const showOriginal = state.mode !== "translated";
  const showTranslated = state.mode !== "original";

  const overlayColumn = (
    <div className="pl-page-col">
      <div className="pl-col-head">
        译文 · 保留版式 <span className="pl-small pl-muted">（点击段落定位原文）</span>
      </div>
      <div className="pl-page-frame" style={{ width: image.width, height: image.height }}>
        <img className="pl-page-img" src={image.dataUrl} alt={`第 ${image.page} 页`} draggable={false} />
        {segments
          .filter((segment) => Boolean(segment.translation))
          .map((segment) => {
            const style = overlayGeometry(segment, image);
            if (!style) {
              return null;
            }
            const isActive = state.highlight === segment.id;
            return (
              <button
                key={segment.id}
                type="button"
                className={`pl-seg-overlay${isActive ? " highlight" : ""}`}
                style={{
                  left: style.left,
                  top: style.top,
                  width: style.width,
                  height: style.height,
                  fontSize: style.fontSize,
                  lineHeight: style.lineHeight,
                }}
                title={segment.translation || segment.text}
                onClick={() => {
                  onPick(segment.id);
                  controller.jumpToSegment(segment.id);
                }}
              >
                {/* Pre-wrapped so the plugin and the Python preview agree. */}
                {style.lines.map((line, index) => (
                  <span key={index} className="pl-seg-overlay__line">
                    {line}
                  </span>
                ))}
              </button>
            );
          })}
      </div>
    </div>
  );

  const originalColumn = (
    <div className="pl-page-col">
      <div className="pl-col-head">原文 · 第 {image.page} 页</div>
      <div className="pl-page-frame" style={{ width: image.width, height: image.height }}>
        <img className="pl-page-img" src={image.dataUrl} alt={`第 ${image.page} 页`} draggable={false} />
        {segments
          .filter((segment) => state.highlight === segment.id)
          .map((segment) => {
            const style = overlayGeometry(segment, image);
            if (!style) {
              return null;
            }
            return (
              <div
                key={segment.id}
                className="pl-seg-box highlight"
                style={{ left: style.left, top: style.top, width: style.width, height: style.height }}
              />
            );
          })}
      </div>
    </div>
  );

  return (
    <div className={`pl-page-stage${dualColumns ? " dual" : ""}`}>
      {showOriginal ? originalColumn : null}
      {showTranslated ? overlayColumn : null}
    </div>
  );
}

/**
 * Map a PDF-user-space bbox onto the rendered bitmap.
 *
 * Segments store coordinates in PDF points with the origin at the bottom-left,
 * so the y axis is flipped. Rotated pages are skipped: pdf.js applies a matrix
 * that this simple scale/flip cannot reproduce.
 */
function segmentToSelection(segment: Segment): Selection {
  return {
    text: segment.text,
    page: segment.page,
    rects: [segment.bbox as unknown as number[]],
    kind: segment.kind === "formula" ? "formula" : "text",
  };
}
