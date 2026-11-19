import { useEffect, useRef, useState } from "react";
import type { ReaderController, UIState } from "../reader/controller";
import type { Selection } from "../types";
import { readSelectionFrom, selectionOf, type SelectionHit } from "./text-selection";

/**
 * Floating toolbar for a selection made inside the sidebar.
 *
 * Selecting a paragraph in the reading view used to do nothing: the only
 * selection handlers were the Zotero PDF popup and the one bound to the page
 * overlay, and the latter read the *reader's* document, which cannot see a
 * selection made inside the sidebar's shadow root. So the place people actually
 * read was the one place where "select some text and ask about it" did not work.
 *
 * The toolbar sits above the selection. `mousedown` is cancelled so that pressing
 * a button does not clear the selection first — otherwise the click would act on
 * an already-empty range.
 */
export function SelectionToolbar(props: {
  controller: ReaderController;
  state: UIState;
}): JSX.Element {
  const { controller, state } = props;
  const [hit, setHit] = useState<SelectionHit | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  // The listeners are attached once; the state they read must not be a stale
  // closure, or a selection would be attributed to the paragraph that was on
  // screen when the component mounted.
  const latest = useRef(state);
  latest.current = state;
  const blocked = Boolean(state.settingsOpen || state.glossaryOpen || state.translateDialogOpen);
  const blockedRef = useRef(blocked);
  blockedRef.current = blocked;

  useEffect(() => {
    const node = hostRef.current;
    if (!node) {
      return;
    }
    const root = node.getRootNode() as ShadowRoot | Document;

    const read = () => {
      // A modal is a different task; a toolbar over it would be noise.
      if (blockedRef.current) {
        return;
      }
      const next = readSelectionFrom(selectionOf(root));
      if (!next) {
        setHit(null);
        return;
      }
      setHit(next);
      // Publish the selection immediately, so typing in the composer asks about
      // *this* paragraph and the scope chip is already correct. Writing it to the
      // database is debounced, so a burst of selections costs one write.
      const current = latest.current;
      const segment = next.segmentId
        ? current.segments.find((item) => item.id === next.segmentId)
        : undefined;
      const page = segment?.page ?? current.page;
      controller.setSelection({ text: next.text, page, pageLabel: String(page), kind: "text" });
      controller.setScope("selection");
    };

    // `pointerup` rather than `mouseup`: the reader is a touch-capable web app.
    const onPointerUp = (event: Event) => {
      const target = event.target as HTMLElement | null;
      // Clicking a control is a command, not a selection.
      if (target?.closest?.("button, a, input, textarea, select, [role='option']")) {
        return;
      }
      setTimeout(read, 0);
    };
    const onKeyUp = (event: Event) => {
      const key = (event as KeyboardEvent).key;
      if ((event as KeyboardEvent).shiftKey || key === "Shift") {
        setTimeout(read, 0);
      }
    };
    // The rect is captured at selection time; once the text moves, the toolbar
    // would point at the wrong place.
    const onScroll = () => setHit(null);

    root.addEventListener("pointerup", onPointerUp, true);
    root.addEventListener("keyup", onKeyUp, true);
    root.addEventListener("scroll", onScroll, true);
    return () => {
      root.removeEventListener("pointerup", onPointerUp, true);
      root.removeEventListener("keyup", onKeyUp, true);
      root.removeEventListener("scroll", onScroll, true);
    };
  }, [controller]);

  // Nothing selected (or a modal is open): render the host and no toolbar, so
  // the listener anchor stays mounted.
  if (!hit || blocked) {
    return <div className="pl-selhost" ref={hostRef} />;
  }

  const selection: Selection = {
    text: hit.text,
    page: state.selection?.page ?? state.page,
    kind: "text",
  };
  const rect = hit.rect;
  // Above the selection, clamped so it never leaves the viewport: a selection
  // near the right edge would otherwise put most of the bar off-screen. Without
  // a rect (a stale range) it pins to the top instead of vanishing.
  const width = Math.min(360, (typeof window !== "undefined" && window.innerWidth) || 800);
  const style = rect
    ? {
        top: Math.max(6, Math.round(rect.top) - 44),
        left: Math.max(6, Math.min(Math.round(rect.left), width - 40)),
      }
    : { top: 8, left: 8 };

  const release = () => {
    setHit(null);
    controller.ensureKeyboardFocus();
  };

  return (
    <div className="pl-selhost" ref={hostRef}>
      <div
        className="pl-seltool"
        style={style}
        role="toolbar"
        aria-label="选区操作"
        onMouseDown={(event) => event.preventDefault()}
      >
        <span className="pl-seltool__text" title={hit.text}>
          {hit.text}
        </span>
        <button
          type="button"
          className="pl-seltool__btn"
          title="用当前模型解释这段内容"
          onClick={() => {
            release();
            controller.explainSelection(selection);
          }}
        >
          解释
        </button>
        <button
          type="button"
          className="pl-seltool__btn"
          title="把这段作为提问上下文，并打开输入框"
          onClick={() => {
            release();
            controller.askSelection(selection);
          }}
        >
          提问
        </button>
        <button
          type="button"
          className="pl-seltool__btn"
          title="把这段原文保存为 Zotero 笔记"
          onClick={() => {
            release();
            void controller.saveSelectionNote(selection);
          }}
        >
          存笔记
        </button>
        <button
          type="button"
          className="pl-seltool__close"
          title="关闭"
          aria-label="关闭选区工具条"
          onClick={() => setHit(null)}
        >
          ✕
        </button>
      </div>
    </div>
  );
}
