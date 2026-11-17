import { debug } from "./log";
import { ReaderController } from "./reader/controller";
import type { PluginHost } from "./reader/controller";
import { ServiceManager, dataDirectory } from "./service/manager";
import type { Selection } from "./types";
import { mountController } from "./ui/mount";
import { createPrefs, currentPage, isPdfReader, readerDocument } from "./zotero/api";

const PLUGIN_ID = "paperloom@peeker.dev";

/** Marker used by bootstrap.js to detect an already-loaded bundle. */
export const __paperloomApi = true;

interface Mounted {
  reader: any;
  controller: ReaderController;
  unmount: () => void;
  detachWindow: () => void;
}

interface Runtime extends PluginHost {
  mounted: Map<any, Mounted>;
  started: boolean;
  readerEvents: { type: string; handler: (event: any) => void }[];
  menuWindows: Set<any>;
}

const runtime: Runtime = {
  id: PLUGIN_ID,
  version: "",
  rootURI: "",
  prefs: createPrefs(),
  service: null as unknown as ServiceManager,
  client: null as any,
  mounted: new Map(),
  started: false,
  readerEvents: [],
  menuWindows: new Set(),
};

export async function startup({ id, version, rootURI }: { id: string; version: string; rootURI: string }): Promise<void> {
  if (runtime.started) {
    return;
  }
  runtime.id = id || PLUGIN_ID;
  runtime.version = version;
  runtime.rootURI = rootURI;
  runtime.prefs = createPrefs();
  runtime.service = new ServiceManager(runtime.prefs);
  runtime.client = runtime.service.client;
  runtime.started = true;

  registerReaderEvents();
  registerPreferencePane();
  for (const win of safeMainWindows()) {
    addToolsMenu(win);
  }
  void writeStartupHeartbeat();
  debug("startup complete", version);
}

/**
 * Writes a small startup record used by "Service diagnostics" and by support
 * requests. Failures are ignored; it must never block startup.
 */
async function writeStartupHeartbeat(): Promise<void> {
  try {
    const dir = dataDirectory();
    if (!(await IOUtils.exists(dir))) {
      await IOUtils.makeDirectory(dir, { ignoreExisting: true });
    }
    const payload = {
      plugin: runtime.id,
      version: runtime.version,
      zotero: (globalThis as any).Zotero?.version || "",
      platform: (globalThis as any).Services?.appinfo?.OS || "",
      startedAt: new Date().toISOString(),
    };
    await IOUtils.writeUTF8(PathUtils.join(dir, "plugin-startup.json"), JSON.stringify(payload, null, 2));
  } catch (error) {
    debug("heartbeat failed", String(error));
  }
}

export function shutdown(): void {
  for (const { type, handler } of runtime.readerEvents) {
    try {
      Zotero.Reader.unregisterEventListener(type, handler);
    } catch {
      // Zotero removes plugin handlers automatically on shutdown.
    }
  }
  runtime.readerEvents = [];
  for (const mounted of Array.from(runtime.mounted.values())) {
    detachReader(mounted.reader);
  }
  for (const win of Array.from(runtime.menuWindows)) {
    removeToolsMenu(win);
  }
  runtime.menuWindows.clear();
  try {
    runtime.service?.shutdown();
  } catch {
    // Best effort.
  }
  runtime.started = false;
  debug("shutdown complete");
}

export function onWindowLoad(window: any): void {
  addToolsMenu(window);
}

export function onWindowUnload(window: any): void {
  removeToolsMenu(window);
}

// --------------------------------------------------------------------------- //
// Reader integration
// --------------------------------------------------------------------------- //

function registerReaderEvents(): void {
  const add = (type: string, handler: (event: any) => void) => {
    try {
      Zotero.Reader.registerEventListener(type, handler, runtime.id);
      runtime.readerEvents.push({ type, handler });
    } catch (error) {
      debug("register reader event failed", type, String(error));
    }
  };

  add("renderToolbar", onRenderToolbar);
  add("renderTextSelectionPopup", onTextSelectionPopup);
  add("createAnnotationContextMenu", onAnnotationContextMenu);
}

function onRenderToolbar(event: any): void {
  try {
    const { reader, doc, append } = event;
    if (!isPdfReader(reader)) {
      return;
    }
    const controller = attachReader(reader);
    if (doc.getElementById("paperloom-toolbar-button")) {
      return;
    }
    const button = doc.createElement("button");
    button.id = "paperloom-toolbar-button";
    button.type = "button";
    button.textContent = "PaperLoom";
    button.title = "打开/收起 PaperLoom 侧边栏";
    button.style.cssText = toolbarStyle();
    button.addEventListener("click", () => controller?.toggleSidebar());
    append(button);

    const bilingual = doc.createElement("button");
    bilingual.type = "button";
    bilingual.textContent = "双语";
    bilingual.title = "双语对照阅读";
    bilingual.style.cssText = toolbarStyle();
    bilingual.addEventListener("click", () => {
      controller?.toggleSidebar(true);
      controller?.toggleBilingual(true);
    });
    append(bilingual);
  } catch (error) {
    debug("renderToolbar failed", String(error));
  }
}

function toolbarStyle(): string {
  return [
    "display:inline-flex",
    "align-items:center",
    "height:24px",
    "padding:0 8px",
    "margin:0 2px",
    "border:1px solid transparent",
    "border-radius:5px",
    "background:transparent",
    "color:inherit",
    "font:inherit",
    "font-size:12px",
    "cursor:pointer",
    "white-space:nowrap",
  ].join(";");
}

function onTextSelectionPopup(event: any): void {
  try {
    const { reader, doc, params, append } = event;
    const annotation = params?.annotation || {};
    const text = String(annotation.text || "").trim();
    if (!text || !isPdfReader(reader)) {
      return;
    }
    const controller = attachReader(reader);
    if (!controller) {
      return;
    }
    const selection = selectionFromAnnotation(reader, annotation, "text");
    const container = doc.createElement("div");
    container.style.cssText = "display:flex;gap:4px;margin:2px;";
    const makeButton = (label: string, title: string, onClick: () => void) => {
      const button = doc.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.title = title;
      button.style.cssText = [
        "height:26px",
        "padding:0 10px",
        "border:1px solid #d9d6cc",
        "border-radius:6px",
        "background:#fff",
        "color:#22262b",
        "font:inherit",
        "font-size:12px",
        "cursor:pointer",
      ].join(";");
      button.addEventListener("click", (clickEvent: Event) => {
        clickEvent.preventDefault();
        clickEvent.stopPropagation();
        onClick();
      });
      return button;
    };
    container.appendChild(
      makeButton("解释", "用 DeepSeek 解释这段内容", () => {
        controller.toggleSidebar(true);
        controller.explainSelection(selection);
      }),
    );
    container.appendChild(
      makeButton("提问", "以此段为上下文提问", () => {
        controller.toggleSidebar(true);
        controller.askSelection(selection);
      }),
    );
    container.appendChild(
      makeButton("保存笔记", "把该段原文保存为 Zotero 笔记", () => {
        void controller.saveSelectionNote(selection);
      }),
    );
    append(container);
  } catch (error) {
    debug("selection popup failed", String(error));
  }
}

function onAnnotationContextMenu(event: any): void {
  try {
    const { reader, params, append } = event;
    if (!isPdfReader(reader)) {
      return;
    }
    const ids: string[] = params?.ids || [];
    const annotation = ids.length ? resolveAnnotation(reader, ids[0]) : null;
    if (!annotation) {
      return;
    }
    const isImage = annotation.type === "image";
    const text = String(annotation.text || annotation.comment || "").trim();
    if (!isImage && !text) {
      return;
    }
    const controller = attachReader(reader);
    if (!controller) {
      return;
    }
    const selection = selectionFromAnnotation(reader, annotation, isImage ? "figure" : "formula");
    append({
      label: isImage ? "用 PaperLoom 解释此图/表" : "用 PaperLoom 解释此公式",
      onCommand: () => {
        controller.toggleSidebar(true);
        const kindNote = isImage
          ? "（图像内容未直接发送；以下基于选中区域附近的正文与图注）"
          : "";
        controller.setSelection(selection);
        controller.setScope("selection");
        controller.setTab("chat");
        void controller.ask(
          `${isImage ? "请解释这个图表" : "请解释这个公式"}，说明其含义、符号与在论文中的作用：\n\n> ${text || "(选区无文本)"}\n${kindNote}`,
          { selection, scope: "selection" },
        );
      },
    });
  } catch (error) {
    debug("annotation menu failed", String(error));
  }
}

function resolveAnnotation(reader: any, id: string): any | null {
  try {
    const state = reader?._internalReader?._state || reader?.state;
    const list = state?.annotations;
    if (Array.isArray(list)) {
      const found = list.find((item: any) => item?.id === id);
      if (found) {
        return found;
      }
    }
  } catch {
    // ignore
  }
  try {
    const manager = reader?._internalReader?._annotationManager;
    if (manager?.get) {
      return manager.get(id) || null;
    }
    if (manager?._annotations?.get) {
      return manager._annotations.get(id) || null;
    }
  } catch {
    // ignore
  }
  return null;
}

function selectionFromAnnotation(reader: any, annotation: any, kind: Selection["kind"]): Selection {
  const pageIndex = Number(annotation?.position?.pageIndex);
  const page = Number.isFinite(pageIndex) ? pageIndex + 1 : currentPage(reader);
  return {
    text: String(annotation.text || annotation.comment || "").trim(),
    page,
    pageLabel: annotation.pageLabel || String(page),
    rects: annotation.position?.rects || [],
    kind,
  };
}

function attachReader(reader: any): ReaderController | null {
  const existing = runtime.mounted.get(reader);
  if (existing) {
    return existing.controller;
  }
  const doc = readerDocument(reader);
  if (!doc?.body) {
    debug("reader document not ready");
    return null;
  }
  const controller = new ReaderController(runtime, reader);
  const unmount = mountController(controller, doc);
  const win = reader._iframeWindow;
  const detachWindow = () => detachReader(reader);
  try {
    win?.addEventListener("unload", detachWindow, { once: true });
  } catch {
    // ignore
  }
  runtime.mounted.set(reader, { reader, controller, unmount, detachWindow });
  void controller.init();
  return controller;
}

function detachReader(reader: any): void {
  const mounted = runtime.mounted.get(reader);
  if (!mounted) {
    return;
  }
  runtime.mounted.delete(reader);
  try {
    mounted.reader?._iframeWindow?.removeEventListener("unload", mounted.detachWindow);
  } catch {
    // ignore
  }
  try {
    mounted.unmount();
  } catch {
    // ignore
  }
  try {
    mounted.controller.destroy();
  } catch {
    // ignore
  }
}

// --------------------------------------------------------------------------- //
// Preferences pane and Tools menu
// --------------------------------------------------------------------------- //

function registerPreferencePane(): void {
  try {
    Zotero.PreferencePanes.register({
      pluginID: runtime.id,
      src: runtime.rootURI + "prefs.xhtml",
      scripts: [runtime.rootURI + "content/prefs.js"],
      stylesheets: [runtime.rootURI + "content/prefs.css"],
      label: "PaperLoom",
    });
  } catch (error) {
    debug("preference pane registration failed", String(error));
  }
}

function addToolsMenu(win: any): void {
  try {
    const doc = win?.document;
    if (!doc || doc.getElementById("paperloom-tools-menu-item")) {
      return;
    }
    const popup = doc.getElementById("menu_ToolsPopup");
    if (!popup) {
      return;
    }
    const item = doc.createXULElement
      ? doc.createXULElement("menuitem")
      : doc.createElement("menuitem");
    item.id = "paperloom-tools-menu-item";
    item.setAttribute("label", "PaperLoom 设置…");
    item.addEventListener("command", openPreferences);
    popup.appendChild(item);
    runtime.menuWindows.add(win);
  } catch (error) {
    debug("tools menu failed", String(error));
  }
}

function removeToolsMenu(win: any): void {
  try {
    win?.document?.getElementById("paperloom-tools-menu-item")?.remove();
  } catch {
    // ignore
  }
  runtime.menuWindows.delete(win);
}

function openPreferences(): void {
  try {
    if (Zotero.Utilities.Internal.openPreferences) {
      Zotero.Utilities.Internal.openPreferences(runtime.id);
      return;
    }
  } catch {
    // Fall back to the generic preferences window.
  }
  try {
    Zotero.Utilities.Internal.openPreferences();
  } catch (error) {
    debug("open preferences failed", String(error));
  }
}

function safeMainWindows(): any[] {
  try {
    return Zotero.getMainWindows() || [];
  } catch {
    return [];
  }
}

// Marker used by bootstrap.js to detect an already-loaded bundle.
(runtime as any).__paperloomApi = true;

export default runtime;
