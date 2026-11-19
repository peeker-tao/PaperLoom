import { useMemo } from "react";
import type { ReactNode } from "react";
import { renderMarkdown } from "../markdown";

export function Spinner(): JSX.Element {
  return <span className="pl-spinner" aria-label="加载中" />;
}

export function IconButton(props: {
  title: string;
  onClick: () => void;
  children: ReactNode;
  active?: boolean;
  disabled?: boolean;
  /**
   * Word labels ("双语") need room to sit on one line. The square variant is
   * 26px wide, which wrapped two Chinese characters onto two rows — the header
   * read as a stack of stray glyphs on a narrow sidebar.
   */
  text?: boolean;
}): JSX.Element {
  return (
    <button
      type="button"
      className={`pl-icon-btn${props.text ? " pl-icon-btn--text" : ""}${props.active ? " active" : ""}`}
      title={props.title}
      aria-label={props.title}
      onClick={props.onClick}
      disabled={props.disabled}
    >
      {props.children}
    </button>
  );
}

export function MarkdownView(props: {
  text: string;
  onCite?: (segmentId: string) => void;
  resolve?: (segmentId: string) => { page?: number } | null;
}): JSX.Element {
  const html = useMemo(() => renderMarkdown(props.text, { resolve: props.resolve }), [props.text, props.resolve]);
  return (
    <div
      className="pl-markdown"
      onClick={(event) => {
        const target = (event.target as HTMLElement).closest("[data-cite]") as HTMLElement | null;
        if (target && props.onCite) {
          event.preventDefault();
          const segmentId = target.getAttribute("data-cite");
          if (segmentId) {
            props.onCite(segmentId);
          }
        }
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export function Modal(props: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}): JSX.Element {
  return (
    <div
      className="pl-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          props.onClose();
        }
      }}
    >
      <div className="pl-modal" style={props.wide ? { width: "min(680px, calc(100% - 32px))" } : undefined}>
        <h3>
          <span>{props.title}</span>
          <IconButton title="关闭" onClick={props.onClose}>
            ✕
          </IconButton>
        </h3>
        {props.children}
      </div>
    </div>
  );
}

export function Empty(props: { text: string }): JSX.Element {
  return <div className="pl-empty">{props.text}</div>;
}
