/**
 * Runtime DOM probes for the sidebar.
 *
 * The sidebar behaves differently inside Zotero's reader iframe than in a plain
 * browser: a sibling layer can sit on top of it, or the iframe can refuse
 * keyboard focus. From the outside both look like "the box cannot be clicked",
 * so this module reports which element actually receives the pointer at a given
 * point — walking through shadow roots, which is where a naive
 * `document.elementFromPoint` stops.
 */

const roots = new WeakMap<object, HTMLElement>();

export function registerSidebarRoot(controller: object, container: HTMLElement): void {
  roots.set(controller, container);
}

export interface ProbeResult {
  ok: boolean;
  detail: string;
}

/** Describe an element compactly enough to recognise it in a log line. */
function describe(element: Element | null): string {
  if (!element) {
    return "(无)";
  }
  const tag = element.tagName.toLowerCase();
  const id = element.id ? `#${element.id}` : "";
  const cls =
    typeof element.className === "string" && element.className.trim()
      ? `.${element.className.trim().split(/\s+/).slice(0, 2).join(".")}`
      : "";
  return `${tag}${id}${cls}`;
}

/** Topmost element at a viewport point, descending into shadow roots. */
function elementAt(doc: Document, x: number, y: number): Element | null {
  let element = doc.elementFromPoint(x, y);
  let guard = 0;
  while (element && guard < 8) {
    const shadow = (element as HTMLElement).shadowRoot;
    if (!shadow) {
      break;
    }
    const inner = shadow.elementFromPoint(x, y);
    if (!inner || inner === element) {
      break;
    }
    element = inner;
    guard += 1;
  }
  return element;
}

/**
 * Check that the question box receives clicks.
 *
 * Returns the element that actually sits under the pointer when it is not the
 * textarea, which names the blocker instead of describing the symptom.
 */
export function probeComposer(controller: object): ProbeResult {
  const root = roots.get(controller);
  if (!root) {
    return { ok: false, detail: "侧边栏未挂载" };
  }
  const textarea = root.querySelector("textarea");
  if (!textarea) {
    return { ok: false, detail: "找不到输入框" };
  }
  const rect = textarea.getBoundingClientRect();
  if (rect.width < 16 || rect.height < 8) {
    return {
      ok: false,
      detail: `输入框尺寸异常 ${Math.round(rect.width)}×${Math.round(rect.height)}`,
    };
  }
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;
  if (y < 0 || y > (textarea.ownerDocument.defaultView?.innerHeight || 0)) {
    return { ok: false, detail: "输入框在可视区之外（侧边栏布局异常）" };
  }
  const top = elementAt(textarea.ownerDocument, x, y);
  if (top === textarea) {
    return { ok: true, detail: `可点击（${Math.round(rect.width)}×${Math.round(rect.height)}）` };
  }
  const inside = textarea.contains(top);
  return {
    ok: false,
    detail: `被 ${describe(top)} 遮挡${inside ? "" : "（该元素不属于输入框）"}`,
  };
}

/** Whether the reader document currently owns keyboard focus. */
export function probeFocus(controller: object): ProbeResult {
  const root = roots.get(controller);
  const doc = root?.ownerDocument;
  if (!doc) {
    return { ok: false, detail: "侧边栏未挂载" };
  }
  try {
    return doc.hasFocus()
      ? { ok: true, detail: "阅读器窗口持有键盘焦点" }
      : { ok: false, detail: "阅读器窗口没有键盘焦点（按键会发送到主窗口）" };
  } catch {
    return { ok: false, detail: "无法查询焦点状态" };
  }
}

/** Label a control the way the user would recognise it on screen. */
function labelOf(element: Element): string {
  const text = (element.textContent || "").trim().replace(/\s+/g, " ").slice(0, 12);
  if (text) {
    return `「${text}」`;
  }
  const placeholder = element.getAttribute("placeholder");
  if (placeholder) {
    return `「${placeholder.slice(0, 8)}」`;
  }
  const title = element.getAttribute("title") || element.getAttribute("aria-label");
  return title ? `「${title.slice(0, 8)}」` : describe(element);
}

/**
 * Hit-test every control in the sidebar.
 *
 * In Zotero the sidebar is nested inside reader chrome that a plain browser test
 * never reproduces, and a single covering layer makes *many* buttons look dead
 * at once. Checking each control's centre point turns that into a list of named
 * controls plus the element that intercepted them.
 */
export function probeInteractive(controller: object): ProbeResult {
  const root = roots.get(controller);
  const doc = root?.ownerDocument;
  const win = doc?.defaultView;
  if (!root || !doc || !win) {
    return { ok: false, detail: "侧边栏未挂载" };
  }
  const controls = Array.from(
    root.querySelectorAll("button, input, textarea, select, [role='tab']"),
  );
  const blocked: string[] = [];
  let checked = 0;
  for (const control of controls) {
    const rect = control.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) {
      continue;
    }
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    if (x < 0 || y < 0 || x > win.innerWidth || y > win.innerHeight) {
      // Off-screen is a layout problem, not a coverage problem; report it too.
      blocked.push(`${labelOf(control)} 在可视区之外`);
      continue;
    }
    checked += 1;
    const top = elementAt(doc, x, y);
    if (top && (top === control || control.contains(top))) {
      continue;
    }
    blocked.push(`${labelOf(control)} 被 ${describe(top)} 遮挡`);
  }
  if (!blocked.length) {
    return { ok: true, detail: `${checked} 个控件均可点击` };
  }
  const shown = blocked.slice(0, 3).join("；");
  const rest = blocked.length > 3 ? ` 等 ${blocked.length} 个` : "";
  return { ok: false, detail: shown + rest };
}
