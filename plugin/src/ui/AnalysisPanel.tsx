import { useState } from "react";
import type { ReaderController, UIState } from "../reader/controller";
import { MarkdownView, Spinner } from "./common";

const KINDS: { id: string; label: string; hint: string }[] = [
  { id: "card", label: "阅读卡片", hint: "研究问题 / 背景 / 方法 / 结果 / 创新 / 局限" },
  { id: "experiment", label: "实验解读", hint: "数据集 / 基线 / 指标 / 消融 / 缺失实验" },
  { id: "novelty", label: "创新点", hint: "作者主张 / 贡献 / 相关工作对照 / 证据强度" },
  { id: "limitations", label: "不足点", hint: "问题 / 依据 / 影响 / 可信度 / 改进建议" },
  { id: "compare", label: "论文对比", hint: "问题 / 方法 / 数据 / 指标 / 结果 / 条件差异" },
  { id: "outline", label: "汇报提纲", hint: "时间分配 / 讲解要点 / 推荐图表" },
];

export function AnalysisPanel(props: { controller: ReaderController; state: UIState }): JSX.Element {
  const { controller, state } = props;
  const [focus, setFocus] = useState("");
  const [minutes, setMinutes] = useState(10);
  const analysis = state.analysis;

  return (
    <div className="pl-scroll">
      <div className="pl-grid2" style={{ marginBottom: 8 }}>
        {KINDS.map((kind) => (
          <button
            key={kind.id}
            type="button"
            className={`pl-btn${analysis?.kind === kind.id ? " pl-btn--primary" : ""}`}
            title={kind.hint}
            onClick={() => {
              if (kind.id === "compare") {
                void controller.compareSelected();
              } else {
                void controller.analyze(kind.id, focus);
              }
            }}
          >
            {kind.label}
          </button>
        ))}
      </div>
      <div className="pl-field">
        <label className="pl-label">额外关注（可选）</label>
        <input
          className="pl-input"
          style={{ width: "100%" }}
          value={focus}
          placeholder="例如：重点看消融实验与可复现性"
          onChange={(event) => setFocus(event.target.value)}
        />
      </div>
      <div className="pl-row" style={{ marginBottom: 8 }}>
        <span className="pl-small pl-muted">汇报时长（分钟）</span>
        <input
          className="pl-input"
          type="number"
          min={3}
          max={90}
          value={minutes}
          style={{ width: 70 }}
          onChange={(event) => setMinutes(Number(event.target.value) || 10)}
        />
      </div>
      <div className="pl-card pl-small pl-muted">
        对比模式会使用主窗口当前选中的文献（可多选）。每篇需有已下载的 PDF 附件，首次使用会自动解析。
      </div>

      {analysis ? (
        <div className="pl-card">
          <div className="pl-row pl-row--between" style={{ marginBottom: 6 }}>
            <strong>{KINDS.find((kind) => kind.id === analysis.kind)?.label || analysis.kind}</strong>
            <span className="pl-small pl-muted">
              {analysis.status === "streaming" ? <Spinner /> : analysis.model || ""}
            </span>
          </div>
          {analysis.error ? <div className="pl-card pl-card--error pl-small">{analysis.error}</div> : null}
          <MarkdownView
            text={analysis.text || (analysis.status === "streaming" ? "…" : "")}
            onCite={(segmentId) => controller.jumpToSegment(segmentId)}
            resolve={(segmentId) => {
              const segment = state.segments.find((item) => item.id === segmentId);
              return segment ? { page: segment.page } : null;
            }}
          />
          <div className="pl-actions">
            <button
              type="button"
              className="pl-btn"
              disabled={analysis.status === "streaming" || !analysis.text}
              onClick={() => void controller.saveAnalysisNote()}
            >
              保存笔记
            </button>
            <button
              type="button"
              className="pl-btn pl-btn--ghost"
              onClick={() => void controller.analyze(analysis.kind, focus)}
            >
              重新生成
            </button>
            {analysis.status === "streaming" ? (
              <button type="button" className="pl-btn pl-btn--ghost" onClick={() => controller.stop()}>
                停止
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
