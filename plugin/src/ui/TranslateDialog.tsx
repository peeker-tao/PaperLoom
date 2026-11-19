import { useEffect, useRef, useState } from "react";
import type { ReaderController, UIState } from "../reader/controller";
import { Modal } from "./common";

/**
 * Page-range entry for "指定页" translation.
 *
 * Replaces `window.prompt()`. That call is not reliably available on Zotero's
 * main window, and when it threw the old code treated the exception as "user
 * cancelled", so the button did nothing and explained nothing. A dialog that
 * lives in the sidebar behaves the same in a tab, an embedded reader and a
 * separate window, and can show the parser's own error next to the field.
 */
export function TranslateDialog(props: {
  controller: ReaderController;
  state: UIState;
}): JSX.Element | null {
  const { controller, state } = props;
  const [value, setValue] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const pages = Number(state.document?.pages) || 0;

  useEffect(() => {
    if (!state.translateDialogOpen) {
      return;
    }
    setValue("");
    setProblem(null);
    setBusy(false);
    // Focus after the modal is in the document, otherwise the field cannot take
    // focus inside the reader iframe on first open.
    const timer = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(timer);
  }, [state.translateDialogOpen]);

  if (!state.translateDialogOpen) {
    return null;
  }

  const blocked = controller.translationBlockedReason();

  const submit = async () => {
    if (busy) {
      return;
    }
    setBusy(true);
    try {
      const error = await controller.translatePages(value);
      if (error) {
        setProblem(error);
      }
    } finally {
      setBusy(false);
    }
  };

  const quick = (text: string) => {
    setValue(text);
    setProblem(null);
    inputRef.current?.focus();
  };

  return (
    <Modal title="翻译指定页" onClose={() => controller.openTranslateDialog(false)}>
      <p className="pl-small pl-muted" style={{ marginTop: 0 }}>
        {pages ? `这篇论文共 ${pages} 页。` : ""}
        输入页码或范围，用逗号分隔，例如 <code>1-3,5</code>；留空则翻译全文。
      </p>

      <input
        ref={inputRef}
        className="pl-input"
        style={{ width: "100%" }}
        placeholder="1-3,5"
        value={value}
        disabled={Boolean(blocked) || busy}
        onChange={(event) => {
          setValue(event.target.value);
          setProblem(null);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void submit();
          }
        }}
      />

      <div className="pl-actions" style={{ marginTop: 8 }}>
        <button type="button" className="pl-btn pl-btn--ghost" onClick={() => quick(String(state.page))}>
          当前页（{state.page}）
        </button>
        {pages ? (
          <button type="button" className="pl-btn pl-btn--ghost" onClick={() => quick(`1-${Math.min(pages, 5)}`)}>
            前 5 页
          </button>
        ) : null}
        {pages ? (
          <button type="button" className="pl-btn pl-btn--ghost" onClick={() => quick(`1-${pages}`)}>
            全部（1-{pages}）
          </button>
        ) : null}
      </div>

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
          {busy ? "正在开始…" : "开始翻译"}
        </button>
      </div>
    </Modal>
  );
}
