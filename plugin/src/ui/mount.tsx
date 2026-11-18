import { createRoot } from "react-dom/client";
import { debug } from "../log";
import type { ReaderController } from "../reader/controller";
import { App } from "./App";
import { registerSidebarRoot } from "./probe";
import { SHADOW_CSS } from "./styles";

const HOST_CSS = `
#paperloom-host {
  position: fixed;
  inset: 0;
  pointer-events: none;
  /* Highest value an engine honours: nested layering contexts in Zotero's
     reader must not be able to sit above the sidebar. */
  z-index: 2147483647;
}
body.paperloom-sidebar-open #split-view,
body.paperloom-sidebar-open #reader-ui {
  margin-right: var(--pl-width, 380px);
  transition: margin-right 0.18s ease;
}
@media print {
  #paperloom-host { display: none !important; }
}
`;

const HOST_STYLE_ID = "paperloom-host-style";

export function mountController(controller: ReaderController, doc: Document): () => void {
  if (!doc.getElementById(HOST_STYLE_ID)) {
    const style = doc.createElement("style");
    style.id = HOST_STYLE_ID;
    style.textContent = HOST_CSS;
    doc.head?.appendChild(style);
  }
  const host = doc.createElement("div");
  host.id = "paperloom-host";
  // Inline the properties that decide hit-testing. The stylesheet above can
  // lose to a Zotero rule with higher specificity, and a host that ends up
  // without `pointer-events: none` would swallow every click meant for the PDF.
  host.style.cssText = [
    "position:fixed",
    "top:0",
    "left:0",
    "right:0",
    "bottom:0",
    "pointer-events:none",
    "z-index:2147483647",
  ].join(";");
  // Appended to <html> rather than <body>: if Zotero's reader puts a stacking
  // context (transform / z-index) on <body>, a huge z-index inside it would be
  // confined to that context and could still be covered.
  (doc.documentElement || doc.body).appendChild(host);
  const shadow = host.attachShadow({ mode: "open" });
  const shadowStyle = doc.createElement("style");
  shadowStyle.textContent = SHADOW_CSS;
  shadow.appendChild(shadowStyle);
  const container = doc.createElement("div");
  shadow.appendChild(container);
  registerSidebarRoot(controller, container);
  const root = createRoot(container);
  root.render(<App controller={controller} />);

  // Any attempt to use a text field also hands keyboard focus to the reader
  // iframe. In Zotero the sidebar sits inside that iframe: if the main window
  // keeps focus, clicks land but keystrokes never arrive.
  //
  // The first click and the first keystroke are logged once. Together with the
  // service's request log they answer the only question that matters when a
  // button "does nothing": did the event arrive at all?
  let loggedClick = false;
  const onPointerDown = (event: Event) => {
    const target = event.target as HTMLElement | null;
    const tag = target?.tagName?.toLowerCase();
    if (!loggedClick) {
      loggedClick = true;
      debug("sidebar pointerdown", tag || "?");
    }
    if (tag === "input" || tag === "textarea" || tag === "select") {
      controller.ensureKeyboardFocus();
      // Focus the field itself as well: `iframeWindow.focus()` only makes the
      // document eligible for keys, it does not move the caret into the field.
      const field = target as HTMLInputElement | HTMLTextAreaElement | null;
      setTimeout(() => {
        try {
          field?.focus();
        } catch {
          // Element may be gone; nothing to do.
        }
      }, 0);
    }
  };
  container.addEventListener("pointerdown", onPointerDown, true);
  debug("sidebar mounted", doc.location?.href || "");

  return () => {
    container.removeEventListener("pointerdown", onPointerDown, true);
    try {
      root.unmount();
    } catch {
      // React may already be unmounted during window teardown.
    }
    host.remove();
    doc.getElementById(HOST_STYLE_ID)?.remove();
    doc.body?.classList.remove("paperloom-sidebar-open");
  };
}
