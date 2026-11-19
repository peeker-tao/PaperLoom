import { errorText } from "./log";
import { ServiceManager } from "./service/manager";
import { createPrefs } from "./zotero/api";

const XHTML = "http://www.w3.org/1999/xhtml";

const prefs = createPrefs();
let manager: ServiceManager | null = null;

function el<K extends keyof HTMLElementTagNameMap>(
  doc: Document,
  tag: K,
  props: Partial<Record<string, string>> = {},
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = doc.createElementNS(XHTML, tag) as any;
  for (const [key, value] of Object.entries(props)) {
    if (key === "className") {
      node.className = value;
    } else {
      node.setAttribute(key, value as string);
    }
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node as HTMLElementTagNameMap[K];
}

function field(doc: Document, label: string, input: HTMLElement): HTMLElement {
  const wrap = el(doc, "div", { className: "pl-pref-field" });
  wrap.appendChild(el(doc, "label", { className: "pl-pref-label" }, label));
  wrap.appendChild(input);
  return wrap;
}

export async function init(): Promise<void> {
  const doc = (globalThis as any).document as Document;
  const root = doc?.getElementById("paperloom-prefs-root");
  if (!root) {
    return;
  }
  root.textContent = "";
  root.setAttribute("style", "font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;font-size:13px;");

  const status = el(doc, "div", { className: "pl-pref-status" }, "正在连接本地服务…");
  root.appendChild(status);

  const baseUrl = el(doc, "input", { type: "text", className: "pl-pref-input", style: "width:420px" }) as HTMLInputElement;
  const apiKey = el(doc, "input", {
    type: "password",
    className: "pl-pref-input",
    placeholder: "留空表示不修改",
    style: "width:420px",
  }) as HTMLInputElement;
  const translateModel = el(doc, "input", { type: "text", className: "pl-pref-input", style: "width:220px" }) as HTMLInputElement;
  const chatModel = el(doc, "input", { type: "text", className: "pl-pref-input", style: "width:220px" }) as HTMLInputElement;
  const analysisModel = el(doc, "input", { type: "text", className: "pl-pref-input", style: "width:220px" }) as HTMLInputElement;
  const message = el(doc, "div", { className: "pl-pref-message" }, "");

  const buttons = el(doc, "div", { className: "pl-pref-actions" });
  const save = el(doc, "button", { type: "button", className: "pl-pref-button pl-pref-button--primary" }, "保存");
  const test = el(doc, "button", { type: "button", className: "pl-pref-button" }, "测试连接");
  const restart = el(doc, "button", { type: "button", className: "pl-pref-button" }, "重启服务");
  const openFolder = el(doc, "button", { type: "button", className: "pl-pref-button" }, "打开数据目录");
  buttons.append(save, test, restart, openFolder);

  const diagnostics = el(doc, "div", { className: "pl-pref-diagnostics" }, "");

  root.appendChild(field(doc, "Base URL", baseUrl));
  root.appendChild(field(doc, "API Key（保存在本机服务，DPAPI 加密）", apiKey));
  const models = el(doc, "div", { className: "pl-pref-models" });
  models.append(
    field(doc, "翻译模型", translateModel),
    field(doc, "问答模型", chatModel),
    field(doc, "分析模型", analysisModel),
  );
  root.appendChild(models);
  root.appendChild(buttons);
  root.appendChild(message);
  root.appendChild(diagnostics);

  manager = new ServiceManager(prefs);

  const refreshDiagnostics = async () => {
    try {
      await manager!.ensure();
      const statusInfo = await manager!.client.status();
      const babeldoc = statusInfo.capabilities.babeldoc;
      diagnostics.textContent =
        `服务 ${statusInfo.version}（接口 v${statusInfo.apiVersion}） · ` +
        `BabelDOC ${babeldoc.available ? "可用" : "未安装（可选，AGPL-3.0）"} · ` +
        `数据目录 ${statusInfo.dataDir}`;
      status.textContent = `状态：已连接（${statusInfo.apiKey.configured ? "API Key 已配置" : "API Key 未配置"}）`;
      status.className = "pl-pref-status pl-pref-status--ok";
      const settings = await manager!.client.getSettings();
      baseUrl.value = settings.settings.base_url;
      translateModel.value = settings.settings.translate_model;
      chatModel.value = settings.settings.chat_model;
      analysisModel.value = settings.settings.analysis_model;
    } catch (error) {
      status.textContent = `状态：未连接 — ${errorText(error)}`;
      status.className = "pl-pref-status pl-pref-status--error";
      diagnostics.textContent =
        "请确认已安装 Python 依赖（pip install -e service），或在扩展设置 " +
        "extensions.paperloom.pythonPath 中指定 python.exe。日志位于 %APPDATA%\\PaperLoom\\logs。";
    }
  };

  save.addEventListener("click", async () => {
    message.textContent = "";
    try {
      const patch: Record<string, unknown> = {
        baseUrl: baseUrl.value.trim(),
        translateModel: translateModel.value.trim(),
        chatModel: chatModel.value.trim(),
        analysisModel: analysisModel.value.trim(),
      };
      if (apiKey.value.trim()) {
        patch.apiKey = apiKey.value.trim();
      }
      const result = await manager!.client.saveSettings(patch);
      apiKey.value = "";
      message.textContent = result.apiKey.configured
        ? `已保存，API Key：${result.apiKey.hint}`
        : "已保存（API Key 未配置）";
      await refreshDiagnostics();
    } catch (error) {
      message.textContent = `保存失败：${errorText(error)}`;
    }
  });

  test.addEventListener("click", async () => {
    message.textContent = "测试中…";
    try {
      // Same rule as the in-sidebar panel: test what is typed right now, and
      // never save it. A blank key means "use the saved one".
      const result = await manager!.client.testSettings({
        model: chatModel.value.trim() || undefined,
        baseUrl: baseUrl.value.trim() || undefined,
        apiKey: apiKey.value.trim() || undefined,
      });
      if (result.ok) {
        const used = result.usedTypedKey ? "，使用刚输入的 Key（未保存）" : "，使用已保存的 Key";
        message.textContent = `连接成功：${result.model || chatModel.value}，${result.latencyMs} ms（${result.reply}）${used}`;
      } else {
        const code = result.error?.code ? `（${result.error.code}）` : "";
        message.textContent = `连接失败${code}：${result.error?.message || "未知错误"}`;
      }
    } catch (error) {
      message.textContent = `连接失败：${errorText(error)}`;
    }
  });

  restart.addEventListener("click", async () => {
    status.textContent = "正在重启服务…";
    try {
      await manager!.restart();
      await refreshDiagnostics();
    } catch (error) {
      status.textContent = `重启失败：${errorText(error)}`;
    }
  });

  openFolder.addEventListener("click", () => {
    try {
      const file = (globalThis as any).Components.classes["@mozilla.org/file/local;1"].createInstance(
        (globalThis as any).Components.interfaces.nsIFile,
      );
      file.initWithPath(manager!.dataDir);
      file.launch();
    } catch (error) {
      message.textContent = `无法打开目录：${errorText(error)}`;
    }
  });

  await refreshDiagnostics();
}

(globalThis as any).PaperLoomPrefs = { init };
