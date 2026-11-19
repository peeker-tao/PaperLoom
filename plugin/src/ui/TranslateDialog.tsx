import { useEffect, useMemo, useRef, useState } from "react";
import { formatPageInput, parsePageInput } from "../pages";
import type { ReaderController, UIState } from "../reader/controller";
import { Modal } from "./common";

/**
 * Page-range entry for "指定页" translation.
 *
 * Three usability problems with the typed-only version this replaces:
 *
 * * "1-3,5" is a syntax to learn. Wanting pages 4 to 9 of a twelve-page paper is
 *   two clicks in the grid below and a typo-free result.
 * * an out-of-range number was only caught *after* pressing 开始翻译, so a typo
 *   meant a round trip.
 * * which pages already had a translation was invisible, so the same pages could
 *   be paid for twice.
 *
 * The text field stays: it is faster for "1-40", it is what the previous version
 * showed, and the grid and the field are two views of one set.
 */
export function TranslateDialog(props: {
  controller: ReaderController;
  state: UIState;
}): JSX.Element | null {
  const { controller, state } = props;
  const [value, setValue] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const pages = Number(state.document?.pages) || 0;

  useEffect(() => {
    if (!state.translateDialogOpen) {
      return;
    }
    setValue("");
    setSelected([]);
    setProblem(null);
    setBusy(false);
    // Focus after the modal is in the document, otherwise the field cannot take
    // focus inside the reader iframe on first open.
    const timer = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(timer);
  }, [state.translateDialogOpen]);

  /** Pages that already contain at least one translation. */
  const donePages = useMemo(() => {
    const set = new Set<number>();
    for (const segment of state.segments) {
      if (segment.translation) {
        set.add(segment.page);
      }
    }
    return set;
  }, [state.segments]);

  if (!state.translateDialogOpen) {
    return null;
  }

  const blocked = controller.translationBlockedReason();

  /** Apply a typed value: keep whatever parses, report whatever does not. */
  const applyText = (text: string) => {
    setValue(text);
    const parsed = parsePageInput(text);
    setProblem(parsed.error);
    if (parsed.error) {
      return;
    }
    if (!text.trim()) {
      setSelected([]);
      return;
    }
    const tooBig = parsed.pages.filter((page) => pages > 0 && page > pages);
    if (tooBig.length) {
      setProblem(`第 ${tooBig.join("、")} 页超出这篇论文的 ${pages} 页范围`);
      setSelected(parsed.pages.filter((page) => page <= pages));
      return;
    }
    setSelected(parsed.pages);
  };

  const setRange = (list: number[]) => {
    setSelected(list);
    setValue(formatPageInput(list));
    setProblem(null);
  };

  const toggle = (page: number) => {
    setRange(
      selected.includes(page)
        ? selected.filter((item) => item !== page)
        : [...selected, page].sort((a, b) => a - b),
    );
  };

  const submit = async () => {
    if (busy) {
      return;
    }
    setBusy(true);
    try {
      // An empty field means the whole paper, which is what the old dialog did
      // and what pressing Enter on an untouched dialog should do.
      const error = await controller.translatePages(value);
      if (error) {
        setProblem(error);
      }
    } finally {
      setBusy(false);
    }
  };

  const all = pages ? Array.from({ length: pages }, (_, index) => index + 1) : [];
  const untranslated = all.filter((page) => !donePages.has(page));
  const summary = selected.length ? `已选 ${selected.length} 页` : "未选就是全文";

  return (
    <Modal title="翻译指定页" onClose={() => controller.openTranslateDialog(false)}>
      <p className="pl-small pl-muted" style={{ marginTop: 0 }}>
        {pages ? `这篇论文共 ${pages} 页。` : ""}
        点下面的页码直接选，或在输入框里写 <code>1-3,5</code>；不选则翻译全文。
      </p>

      <input
        ref={inputRef}
        className="pl-input"
        style={{ width: "100%" }}
        placeholder="1-3,5（留空 = 全文）"
        value={value}
        disabled={Boolean(blocked) || busy}
        onChange={(event) => applyText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void submit();
          }
        }}
      />

      <div className="pl-actions" style={{ marginTop: 8 }}>
        <button type="button" className="pl-btn pl-btn--ghost" disabled={busy} onClick={() => setRange([state.page])}>
          当前页（{state.page}）
        </button>
        {pages ? (
          <button
            type="button"
            className="pl-btn pl-btn--ghost"
            disabled={busy}
            onClick={() => setRange(all.slice(0, Math.min(pages, 5)))}
          >
            前 5 页
          </button>
        ) : null}
        {pages ? (
          <button
            type="button"
            className="pl-btn pl-btn--ghost"
            disabled={busy}
            title="选中所有还没有译文的页；如果都译过了就选中全部"
            onClick={() => setRange(untranslated.length ? untranslated : all)}
          >
            未译页
          </button>
        ) : null}
        {pages ? (
          <button type="button" className="pl-btn pl-btn--ghost" disabled={busy} onClick={() => setRange(all)}>
            全部
          </button>
        ) : null}
        {selected.length ? (
          <button type="button" className="pl-btn pl-btn--ghost" disabled={busy} onClick={() => setRange([])}>
            清空
          </button>
        ) : null}
      </div>

      {pages ? (
        <>
          <div className="pl-pagegrid__head">
            <span className="pl-small pl-muted">{summary}</span>
            {donePages.size ? (
              <span className="pl-small pl-muted">
                <span className="pl-pagegrid__key" /> 已有译文
              </span>
            ) : null}
          </div>
          <div className="pl-pagegrid" role="group" aria-label="选择要翻译的页">
            {all.map((page) => {
              const on = selected.includes(page);
              return (
                <button
                  key={page}
                  type="button"
                  className={`pl-pagegrid__cell${on ? " active" : ""}${donePages.has(page) ? " done" : ""}`}
                  aria-pressed={on}
                  title={`第 ${page} 页${donePages.has(page) ? "（已有译文）" : ""}`}
                  disabled={Boolean(blocked) || busy}
                  onClick={() => toggle(page)}
                >
                  {page}
                </button>
              );
            })}
          </div>
        </>
      ) : null}

      {problem ? (
        <div className="pl-card pl-card--error pl-small" style={{ marginTop: 10, marginBottom: 0 }}>
          {problem}
        </div>
      ) : null}
      {blocked ? (
        <div className="pl-card pl-card--warn pl-small" style={{ marginTop: 10, marginBottom: 0 }}>
          {blocked}
        </div>
      ) : null}

      <div className="pl-actions" style={{ marginTop: 12, justifyContent: "flex-end" }}>
        <button type="button" className="pl-btn" onClick={() => controller.openTranslateDialog(false)}>
          取消
        </button>
        <button
          type="button"
          className="pl-btn pl-btn--primary"
          disabled={Boolean(blocked) || busy}
          onClick={() => void submit()}
        >
          {busy ? "正在开始…" : selected.length ? `翻译这 ${selected.length} 页` : "翻译全文"}
        </button>
      </div>
    </Modal>
  );
}
