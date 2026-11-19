import { useEffect } from "react";
import { useSyncExternalStore } from "react";
import type { ReaderController, UIState } from "../reader/controller";
import { AnalysisPanel } from "./AnalysisPanel";
import { BilingualView } from "./BilingualView";
import { ChatPanel } from "./ChatPanel";
import { GlossaryPanel } from "./GlossaryPanel";
import { NotesPanel } from "./NotesPanel";
import { SettingsPanel } from "./SettingsPanel";
import { IconButton, Modal } from "./common";

function serviceState(state: UIState): "ok" | "warn" | "down" {
  if (state.error) {
    return "down";
  }
  if (!state.service) {
    return "warn";
  }
  return state.service.apiKey?.configured ? "ok" : "warn";
}

function serviceTitle(state: UIState): string {
  if (state.error) {
    return `服务异常：${state.error}`;
  }
  if (!state.service) {
    return "正在连接本地服务…";
  }
  const key = state.service.apiKey?.configured ? "API Key 已配置" : "API Key 未配置";
  return `服务 ${state.service.version} · ${key}`;
}

export function App({ controller }: { controller: ReaderController }): JSX.Element {
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (state.settingsOpen) {
          controller.openSettings(false);
        } else if (state.glossaryOpen) {
          controller.openGlossary(false);
        }
      }
    };
    const doc = (controller as any).reader?._iframeWindow?.document as Document | undefined;
    doc?.addEventListener("keydown", onKey);
    return () => doc?.removeEventListener("keydown", onKey);
  }, [controller, state.settingsOpen, state.glossaryOpen]);

  const translated = state.segments.filter((segment) => segment.translation).length;
  const progress = state.job?.progress;
  const percent =
    progress && progress.total > 0 ? Math.min(100, (progress.done / progress.total) * 100) : translated ? 100 : 0;

  return (
    <div className="pl-root" data-paperloom-root="1">
      {!state.sidebarOpen ? (
        <button type="button" className="pl-reopen" title="打开 PaperLoom 侧边栏" onClick={() => controller.toggleSidebar(true)}>
          PaperLoom
        </button>
      ) : null}

      <BilingualView controller={controller} state={state} />

      {state.canReturnToTranslation && !state.bilingualOpen ? (
        <button
          type="button"
          className="pl-return-pill"
          title={`回到译文（第 ${state.page} 页附近）`}
          onClick={() => controller.returnToTranslation()}
        >
          ← 返回译文
        </button>
      ) : null}

      <aside className={`pl-sidebar${state.sidebarOpen ? "" : " closed"}`} aria-label="PaperLoom">
        <div
          className="pl-sidebar__grip"
          title="拖动调整宽度"
          onPointerDown={(event) => {
            event.preventDefault();
            const startX = event.clientX;
            const startWidth = state.sidebarWidth;
            const target = event.currentTarget as HTMLElement;
            target.setPointerCapture(event.pointerId);
            const move = (moveEvent: PointerEvent) => {
              controller.setSidebarWidth(startWidth + (startX - moveEvent.clientX));
            };
            const up = () => {
              target.releasePointerCapture(event.pointerId);
              target.removeEventListener("pointermove", move);
              target.removeEventListener("pointerup", up);
            };
            target.addEventListener("pointermove", move);
            target.addEventListener("pointerup", up);
          }}
        />

        <div className="pl-header">
          <span className="pl-brand" title="PaperLoom · 文织">
            <span style={{ fontSize: 15 }}>◫</span> PaperLoom
          </span>
          <span className="pl-doc-title" title={state.document?.title || ""}>
            {state.document?.title || (state.loading ? "加载中…" : "")}
          </span>
          <IconButton
            title={state.bilingualOpen ? "关闭双语对照" : "打开双语对照"}
            active={state.bilingualOpen}
            disabled={!state.ready || state.document?.alignment === "none"}
            onClick={() => controller.toggleBilingual()}
          >
            双语
          </IconButton>
          <IconButton title="术语表" onClick={() => controller.openGlossary(true)}>
            术语
          </IconButton>
          <IconButton title="设置" onClick={() => controller.openSettings(true)}>
            ⚙
          </IconButton>
          <IconButton title="收起侧边栏" onClick={() => controller.toggleSidebar(false)}>
            ›
          </IconButton>
        </div>

        <div className="pl-tabs" role="tablist">
          {(["chat", "notes", "analysis"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={state.tab === tab}
              className={`pl-tab${state.tab === tab ? " active" : ""}`}
              onClick={() => controller.setTab(tab)}
            >
              {tab === "chat" ? "对话" : tab === "notes" ? "笔记" : "分析"}
            </button>
          ))}
        </div>

        <div className="pl-body">
          {state.translationStatus?.needsAttention ? (
            <div className="pl-card pl-card--warn pl-small" style={{ margin: "8px 10px 0" }}>
              <strong>
                {state.translationStatus.stale > 0
                  ? `${state.translationStatus.stale} 段译文的生成配置已变更`
                  : `${state.translationStatus.unknown} 段译文缺少生成配置记录`}
              </strong>
              <div style={{ marginTop: 4 }}>
                {state.translationStatus.reasonsText.length
                  ? state.translationStatus.reasonsText.join("；")
                  : "历史译文，无法确认是否与当前模型/术语一致"}
              </div>
              <div className="pl-actions">
                <button
                  type="button"
                  className="pl-btn pl-btn--primary"
                  disabled={state.translating}
                  onClick={() => void controller.retranslateStale()}
                >
                  重译过时段落
                </button>
                <button type="button" className="pl-btn pl-btn--ghost" onClick={() => controller.dismissStale()}>
                  保留现有译文
                </button>
              </div>
            </div>
          ) : null}
          {state.tab === "chat" ? <ChatPanel controller={controller} state={state} /> : null}
          {state.tab === "notes" ? <NotesPanel controller={controller} state={state} /> : null}
          {state.tab === "analysis" ? <AnalysisPanel controller={controller} state={state} /> : null}
        </div>

        <div className="pl-footer">
          <span className="pl-dot" data-state={serviceState(state)} title={serviceTitle(state)} />
          <span title="阅读位置自动保存">p.{state.page}</span>
          <span className="pl-progress" title={`已翻译 ${translated}/${state.segments.length} 段`}>
            <div style={{ width: `${percent}%` }} />
          </span>
          <span>
            {state.segments.length ? `${translated}/${state.segments.length}` : "未解析"}
          </span>
          {state.job?.layout && state.job.layout.state === "failed" ? (
            <span
              className="pl-small pl-muted"
              title={state.job.layout.message || "排版 PDF 生成失败，段落译文仍可使用"}
            >
              排版PDF失败
            </span>
          ) : state.job?.layout?.state === "missing" ? (
            <span className="pl-small pl-muted" title={state.job.layout.message || "未安装 BabelDOC"}>
              无排版引擎
            </span>
          ) : null}
          {state.translating ? (
            <button type="button" className="pl-btn pl-btn--ghost" onClick={() => void controller.cancelTranslation()}>
              取消翻译
            </button>
          ) : (
            <>
              <button type="button" className="pl-btn pl-btn--ghost" title="翻译当前页" onClick={() => void controller.startTranslation([state.page])}>
                本页
              </button>
              <button
                type="button"
                className="pl-btn pl-btn--ghost"
                title="指定页码范围"
                onClick={() => void controller.startTranslationWithPrompt()}
              >
                页码…
              </button>
              <button
                type="button"
                className="pl-btn pl-btn--ghost"
                title="翻译全文"
                onClick={() => void controller.startTranslation()}
              >
                全文
              </button>
            </>
          )}
          {state.job && (state.job.state === "failed" || state.job.state === "interrupted") ? (
            <button type="button" className="pl-btn pl-btn--ghost" onClick={() => void controller.retryTranslation()}>
              重试
            </button>
          ) : null}
          {state.job?.artifacts?.some((artifact) => artifact.kind === "dual" || artifact.kind === "mono") ? (
            <button
              type="button"
              className="pl-btn pl-btn--ghost"
              title="把排版保留 PDF 导入为 Zotero 附件"
              onClick={() => void controller.importArtifacts()}
            >
              导入PDF
            </button>
          ) : null}
        </div>
      </aside>

      {state.notice ? (
        <div
          className="pl-card"
          style={{
            position: "absolute",
            left: "50%",
            bottom: 20,
            transform: "translateX(-50%)",
            pointerEvents: "auto",
            maxWidth: 420,
            zIndex: 30,
            boxShadow: "0 8px 24px rgba(0,0,0,.14)",
          }}
        >
          {state.notice}
        </div>
      ) : null}

      {state.error ? (
        <div
          className="pl-card pl-card--error"
          style={{
            position: "absolute",
            left: "50%",
            bottom: 60,
            transform: "translateX(-50%)",
            pointerEvents: "auto",
            maxWidth: 440,
            zIndex: 30,
          }}
        >
          <div className="pl-row pl-row--between">
            <span>{state.error}</span>
            <span className="pl-row" style={{ gap: 4, flex: "none" }}>
              <button type="button" className="pl-btn pl-btn--ghost" onClick={() => controller.openSettings(true)}>
                设置
              </button>
              {/* Without a way to dismiss it, one failure left a red banner on
                  screen for the rest of the session. */}
              <button
                type="button"
                className="pl-btn pl-btn--ghost"
                title="关闭提示"
                onClick={() => controller.clearMessages()}
              >
                ✕
              </button>
            </span>
          </div>
        </div>
      ) : null}

      {state.settingsOpen ? (
        <Modal title="PaperLoom 设置" wide onClose={() => controller.openSettings(false)}>
          <SettingsPanel controller={controller} state={state} />
        </Modal>
      ) : null}

      {state.glossaryOpen ? (
        <Modal title="术语表" wide onClose={() => controller.openGlossary(false)}>
          <GlossaryPanel controller={controller} state={state} />
        </Modal>
      ) : null}
    </div>
  );
}
