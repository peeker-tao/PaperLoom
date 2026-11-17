import { createRoot } from "react-dom/client";
import type { ReaderController } from "../reader/controller";
import { App } from "./App";
import { SHADOW_CSS } from "./styles";

const HOST_CSS = `
#paperloom-host {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 2147483000;
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
  doc.body.appendChild(host);
  const shadow = host.attachShadow({ mode: "open" });
  const shadowStyle = doc.createElement("style");
  shadowStyle.textContent = SHADOW_CSS;
  shadow.appendChild(shadowStyle);
  const container = doc.createElement("div");
  shadow.appendChild(container);
  const root = createRoot(container);
  root.render(<App controller={controller} />);
  return () => {
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
