import type { ReaderController, UIState } from "../reader/controller";
import type { Job } from "../types";

/**
 * One line that says what the translation job is doing.
 *
 * Before this, the only feedback was a thin footer bar: a queued job, a job
 * that was parsing, and a job that had silently failed all looked the same from
 * the sidebar. Each state names itself, and a finished job offers the two things
 * the user actually wants next — read the result, or regenerate the layout PDF.
 */
export function JobBanner(props: {
  controller: ReaderController;
  state: UIState;
}): JSX.Element | null {
  const { controller, state } = props;
  const job = state.job;
  if (!job) {
    return null;
  }
  const info = describe(job);
  if (!info) {
    return null;
  }

  const canRetry = job.state === "failed" || job.state === "interrupted";
  const layoutFailed = job.layout?.state === "failed";
  const showRead = job.state === "succeeded";

  return (
    <div className={`pl-job pl-job--${info.tone}`} role="status" aria-live="polite">
      <span className="pl-job__label">{info.label}</span>
      {info.detail ? <span className="pl-job__detail">{info.detail}</span> : null}
      <span style={{ flex: 1 }} />
      {showRead ? (
        <button
          type="button"
          className="pl-btn pl-btn--ghost pl-small"
          title="打开译文阅读视图"
          onClick={() => controller.toggleBilingual(true)}
        >
          查看译文
        </button>
      ) : null}
      {canRetry ? (
        <button
          type="button"
          className="pl-btn pl-btn--ghost pl-small"
          onClick={() => void controller.retryTranslation()}
        >
          重试
        </button>
      ) : null}
      {state.translating ? (
        <button
          type="button"
          className="pl-btn pl-btn--ghost pl-small"
          onClick={() => void controller.cancelTranslation()}
        >
          取消
        </button>
      ) : null}
      {layoutFailed ? (
        <span className="pl-small pl-muted" title={job.layout?.message || ""}>
          排版 PDF 未生成
        </span>
      ) : null}
    </div>
  );
}

interface Description {
  label: string;
  detail: string;
  tone: "info" | "ok" | "warn" | "error";
}

function describe(job: Job): Description | null {
  const progress = job.progress;
  const done = Number(progress?.done) || 0;
  const total = Number(progress?.total) || 0;
  const counter = total > 0 ? `${done}/${total} 段` : "";

  switch (job.state) {
    case "queued":
      return { label: "已排队", detail: "等待开始翻译", tone: "info" };
    case "running":
      if (job.stage === "parsing") {
        return { label: "正在解析", detail: "提取段落与坐标", tone: "info" };
      }
      if (job.stage === "layout") {
        return { label: "正在生成排版 PDF", detail: "段落译文已可用", tone: "info" };
      }
      return {
        label: "正在翻译",
        detail: [counter, progress?.page ? `第 ${progress.page} 页` : ""]
          .filter(Boolean)
          .join(" · "),
        tone: "info",
      };
    case "succeeded":
      return {
        label: "翻译完成",
        detail: [counter, job.usage?.costUsd ? `约 $${job.usage.costUsd.toFixed(4)}` : ""]
          .filter(Boolean)
          .join(" · "),
        tone: "ok",
      };
    case "failed":
      return {
        label: "翻译失败",
        detail: job.error?.message || "未知原因",
        tone: "error",
      };
    case "interrupted":
      return { label: "翻译中断", detail: "服务可能已重启，可重试", tone: "warn" };
    case "cancelled":
      return { label: "已取消", detail: counter ? `已完成 ${counter}` : "", tone: "warn" };
    default:
      return null;
  }
}
