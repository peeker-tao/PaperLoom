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

  // A cancelled job is a dead end otherwise: the banner says so and offers
  // nothing, which is where the user in the report ended up (已取消 · 0/9 段 and
  // no way forward). Continuing is the obvious next action, and it is free for
  // the segments that already finished.
  const canRetry =
    job.state === "failed" ||
    job.state === "interrupted" ||
    (job.state === "cancelled" && isUnfinished(job));
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
          title="重新开始同一批页面的翻译（已译好的段落会跳过）"
          onClick={() => void controller.retryTranslation()}
        >
          {job.state === "cancelled" ? "继续翻译" : "重试"}
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
      return {
        label: "已取消",
        detail: isUnfinished(job)
          ? counter
            ? `已完成 ${counter}，可以继续`
            : "还没有开始翻译"
          : counter,
        tone: "warn",
      };
    default:
      return null;
  }
}

/** True while a job stopped before it finished its page set. */
function isUnfinished(job: Job): boolean {
  const total = Number(job.progress?.total) || 0;
  const done = Number(job.progress?.done) || 0;
  return total === 0 || done < total;
}
