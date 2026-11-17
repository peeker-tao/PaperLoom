import { useState } from "react";
import type { ReaderController, UIState } from "../reader/controller";
import { Empty, Spinner } from "./common";

export function GlossaryPanel(props: { controller: ReaderController; state: UIState }): JSX.Element {
  const { controller, state } = props;
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [scope, setScope] = useState<"paper" | "global">("paper");
  const [busy, setBusy] = useState(false);

  const add = async () => {
    if (!source.trim() || !target.trim()) {
      return;
    }
    setBusy(true);
    try {
      await controller.addTerm(source, target, scope);
      setSource("");
      setTarget("");
    } finally {
      setBusy(false);
    }
  };

  const paperTerms = state.terms.filter((term) => term.scope === "paper");
  const globalTerms = state.terms.filter((term) => term.scope === "global");

  const renderTerm = (term: (typeof state.terms)[number]) => (
    <div className="pl-term" key={term.id}>
      <span className="pl-term__src">{term.source}</span>
      <span>{term.target}</span>
      <span className="pl-row" style={{ gap: 4 }}>
        <span className={`pl-badge${term.status === "suggested" ? " pl-badge--suggested" : ""}`}>
          {term.status === "suggested" ? "待确认" : term.scope === "global" ? "全局" : "本文"}
        </span>
        {term.status === "suggested" ? (
          <button
            type="button"
            className="pl-btn pl-btn--ghost"
            onClick={() => void controller.updateTerm(term, { status: "confirmed" })}
          >
            确认
          </button>
        ) : null}
        <button type="button" className="pl-btn pl-btn--ghost" onClick={() => void controller.deleteTerm(term)}>
          删除
        </button>
      </span>
    </div>
  );

  return (
    <>
      <div className="pl-row" style={{ marginBottom: 8 }}>
        <button type="button" className="pl-btn" disabled={busy} onClick={() => void controller.extractTerms()}>
          {busy ? <Spinner /> : "从论文提取术语"}
        </button>
        <button type="button" className="pl-btn pl-btn--ghost" onClick={() => void controller.refreshTerms()}>
          刷新
        </button>
      </div>
      <div className="pl-card">
        <strong className="pl-small">新增术语</strong>
        <div className="pl-row" style={{ marginTop: 6, flexWrap: "wrap" }}>
          <input
            className="pl-input"
            style={{ flex: 1, minWidth: 110 }}
            placeholder="English term"
            value={source}
            onChange={(event) => setSource(event.target.value)}
          />
          <input
            className="pl-input"
            style={{ flex: 1, minWidth: 110 }}
            placeholder="中文译名"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
          />
          <select className="pl-select" value={scope} onChange={(event) => setScope(event.target.value as any)}>
            <option value="paper">当前论文</option>
            <option value="global">全局</option>
          </select>
          <button type="button" className="pl-btn pl-btn--primary" disabled={busy} onClick={() => void add()}>
            添加
          </button>
        </div>
      </div>

      <div className="pl-card">
        <div className="pl-small pl-muted" style={{ marginBottom: 4 }}>
          当前论文（{paperTerms.length}）
        </div>
        {paperTerms.length ? paperTerms.map(renderTerm) : <Empty text="暂无本文术语" />}
      </div>
      <div className="pl-card">
        <div className="pl-small pl-muted" style={{ marginBottom: 4 }}>
          全局（{globalTerms.length}）
        </div>
        {globalTerms.length ? globalTerms.map(renderTerm) : <Empty text="暂无全局术语" />}
      </div>
      <div className="pl-card pl-small pl-muted">
        修改译名后，旧译文不会自动改写；重新翻译对应页面即可应用新术语。
      </div>
    </>
  );
}
