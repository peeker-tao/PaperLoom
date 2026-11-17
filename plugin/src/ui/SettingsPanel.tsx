import { useEffect, useState } from "react";
import type { ReaderController, UIState } from "../reader/controller";
import type { SettingsPayload } from "../types";
import { IconButton } from "./common";

export function SettingsPanel(props: { controller: ReaderController; state: UIState }): JSX.Element {
  const { controller, state } = props;
  const client = controller.client;
  const [payload, setPayload] = useState<SettingsPayload | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [form, setForm] = useState({
    baseUrl: "https://api.deepseek.com",
    translateModel: "deepseek-flash",
    chatModel: "deepseek-flash",
    analysisModel: "deepseek-v4-pro",
    timeoutSeconds: 120,
    connectTimeoutSeconds: 15,
    concurrency: 4,
    qps: 4,
    maxRetries: 3,
    contextChars: 24000,
    maxOutputTokens: 8192,
    thinking: false,
    babeldocEnabled: true,
  });

  const load = async () => {
    try {
      const data = await client.getSettings();
      setPayload(data);
      setForm({
        baseUrl: data.settings.base_url,
        translateModel: data.settings.translate_model,
        chatModel: data.settings.chat_model,
        analysisModel: data.settings.analysis_model,
        timeoutSeconds: data.settings.timeout_seconds,
        connectTimeoutSeconds: data.settings.connect_timeout_seconds,
        concurrency: data.settings.concurrency,
        qps: data.settings.qps,
        maxRetries: data.settings.max_retries,
        contextChars: data.settings.context_chars,
        maxOutputTokens: data.settings.max_output_tokens,
        thinking: data.settings.thinking,
        babeldocEnabled: data.settings.babeldoc_enabled,
      });
    } catch (error) {
      setMessage(controller.friendlyError(error));
    }
  };

  useEffect(() => {
    if (state.settingsOpen) {
      void load();
      setMessage(null);
      setTestResult(null);
      setApiKey("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.settingsOpen]);

  const save = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const patch: Record<string, unknown> = { ...form };
      if (apiKey.trim()) {
        patch.apiKey = apiKey.trim();
      }
      const result = await client.saveSettings(patch);
      setPayload((current) => (current ? { ...current, apiKey: result.apiKey } : current));
      setApiKey("");
      setMessage(`已保存。API Key：${result.apiKey.configured ? `已配置（${result.apiKey.hint}）` : "未配置"}`);
      await controller.init();
    } catch (error) {
      setMessage(controller.friendlyError(error));
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    setTestResult(null);
    try {
      const result = await client.testSettings(form.chatModel);
      if (result.ok) {
        setTestResult(`连接成功：${result.latencyMs} ms，回复“${result.reply}”`);
      } else {
        setTestResult(`连接失败：${result.error?.message || "未知错误"}`);
      }
    } catch (error) {
      setTestResult(controller.friendlyError(error));
    } finally {
      setBusy(false);
    }
  };

  const clearKey = async () => {
    setBusy(true);
    try {
      await client.saveSettings({ apiKey: "" });
      await load();
      setMessage("已删除保存的 API Key");
    } catch (error) {
      setMessage(controller.friendlyError(error));
    } finally {
      setBusy(false);
    }
  };

  const diag = state.service;

  return (
    <div className="pl-scroll">
      <div className="pl-card">
        <div className="pl-row pl-row--between">
          <strong>DeepSeek 连接</strong>
          <span className="pl-small pl-muted">
            {payload?.apiKey.configured ? `已配置 ${payload.apiKey.hint}` : "未配置"}
          </span>
        </div>
        <div className="pl-field" style={{ marginTop: 8 }}>
          <label className="pl-label">Base URL</label>
          <input
            className="pl-input"
            style={{ width: "100%" }}
            value={form.baseUrl}
            onChange={(event) => setForm({ ...form, baseUrl: event.target.value })}
          />
          {payload?.baseUrlCheck ? (
            <div
              className="pl-small"
              style={{ marginTop: 4, color: payload.baseUrlCheck.ok ? "#45514c" : "#a33a2c" }}
            >
              {payload.baseUrlCheck.message}
            </div>
          ) : null}
        </div>
        <div className="pl-field">
          <label className="pl-label">API Key（仅保存在本机服务，使用系统加密存储）</label>
          <div className="pl-row">
            <input
              className="pl-input"
              style={{ flex: 1 }}
              type={showKey ? "text" : "password"}
              placeholder={payload?.apiKey.configured ? "留空表示不修改" : "sk-…"}
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
            <IconButton title={showKey ? "隐藏" : "显示"} onClick={() => setShowKey(!showKey)}>
              {showKey ? "🙈" : "👁"}
            </IconButton>
            <button type="button" className="pl-btn pl-btn--danger" disabled={busy} onClick={() => void clearKey()}>
              删除
            </button>
          </div>
        </div>
        <div className="pl-actions">
          <button type="button" className="pl-btn pl-btn--primary" disabled={busy} onClick={() => void save()}>
            保存
          </button>
          <button type="button" className="pl-btn" disabled={busy} onClick={() => void test()}>
            测试连接
          </button>
          {state.service && !state.service.apiKey.configured ? (
            <span className="pl-small pl-muted">未配置时可先用“演示模式”验证界面</span>
          ) : null}
        </div>
        {testResult ? <div className="pl-small" style={{ marginTop: 6 }}>{testResult}</div> : null}
        {message ? <div className="pl-small" style={{ marginTop: 6 }}>{message}</div> : null}
      </div>

      <div className="pl-card">
        <strong>模型与限制</strong>
        <div className="pl-field" style={{ marginTop: 8 }}>
          <label className="pl-label">翻译模型</label>
          <input
            className="pl-input"
            style={{ width: "100%" }}
            list="pl-models"
            value={form.translateModel}
            onChange={(event) => setForm({ ...form, translateModel: event.target.value })}
          />
        </div>
        <div className="pl-field">
          <label className="pl-label">问答模型</label>
          <input
            className="pl-input"
            style={{ width: "100%" }}
            list="pl-models"
            value={form.chatModel}
            onChange={(event) => setForm({ ...form, chatModel: event.target.value })}
          />
        </div>
        <div className="pl-field">
          <label className="pl-label">分析模型</label>
          <input
            className="pl-input"
            style={{ width: "100%" }}
            list="pl-models"
            value={form.analysisModel}
            onChange={(event) => setForm({ ...form, analysisModel: event.target.value })}
          />
        </div>
        <datalist id="pl-models">
          {(payload?.models || []).map((model) => (
            <option key={model.id} value={model.id}>
              {model.label}
            </option>
          ))}
        </datalist>
        <div className="pl-grid2">
          <div className="pl-field">
            <label className="pl-label">超时（秒）</label>
            <input
              className="pl-input"
              type="number"
              style={{ width: "100%" }}
              value={form.timeoutSeconds}
              onChange={(event) => setForm({ ...form, timeoutSeconds: Number(event.target.value) })}
            />
          </div>
          <div className="pl-field">
            <label className="pl-label">并发</label>
            <input
              className="pl-input"
              type="number"
              style={{ width: "100%" }}
              value={form.concurrency}
              onChange={(event) => setForm({ ...form, concurrency: Number(event.target.value) })}
            />
          </div>
          <div className="pl-field">
            <label className="pl-label">QPS</label>
            <input
              className="pl-input"
              type="number"
              step="0.5"
              style={{ width: "100%" }}
              value={form.qps}
              onChange={(event) => setForm({ ...form, qps: Number(event.target.value) })}
            />
          </div>
          <div className="pl-field">
            <label className="pl-label">最大重试</label>
            <input
              className="pl-input"
              type="number"
              style={{ width: "100%" }}
              value={form.maxRetries}
              onChange={(event) => setForm({ ...form, maxRetries: Number(event.target.value) })}
            />
          </div>
          <div className="pl-field">
            <label className="pl-label">上下文字符数</label>
            <input
              className="pl-input"
              type="number"
              style={{ width: "100%" }}
              value={form.contextChars}
              onChange={(event) => setForm({ ...form, contextChars: Number(event.target.value) })}
            />
          </div>
          <div className="pl-field">
            <label className="pl-label">最大输出 tokens</label>
            <input
              className="pl-input"
              type="number"
              style={{ width: "100%" }}
              value={form.maxOutputTokens}
              onChange={(event) => setForm({ ...form, maxOutputTokens: Number(event.target.value) })}
            />
          </div>
        </div>
        <label className="pl-row pl-small" style={{ gap: 6 }}>
          <input
            type="checkbox"
            checked={form.thinking}
            onChange={(event) => setForm({ ...form, thinking: event.target.checked })}
          />
          问答/分析启用推理模式（更慢，翻译始终关闭）
        </label>
        <label className="pl-row pl-small" style={{ gap: 6, marginTop: 4 }}>
          <input
            type="checkbox"
            checked={form.babeldocEnabled}
            onChange={(event) => setForm({ ...form, babeldocEnabled: event.target.checked })}
          />
          尝试生成排版保留 PDF（需要已安装 BabelDOC）
        </label>
        <div className="pl-actions">
          <button type="button" className="pl-btn pl-btn--primary" disabled={busy} onClick={() => void save()}>
            保存设置
          </button>
        </div>
      </div>

      <div className="pl-card">
        <strong>服务诊断</strong>
        <div className="pl-small" style={{ marginTop: 6, wordBreak: "break-all" }}>
          <div>版本：{diag?.version || "未连接"}（接口 v{diag?.apiVersion || "?"}）</div>
          <div>数据目录：{diag?.dataDir}</div>
          <div>BabelDOC：{diag?.capabilities.babeldoc.available ? "可用" : "未安装（可选，AGPL-3.0）"}</div>
          <div>FTS5：{diag?.capabilities.fts5 ? "可用" : "不可用"}</div>
          <div>翻译队列：{diag?.activeJobs ?? 0} 个活动任务</div>
        </div>
        <div className="pl-actions">
          <button
            type="button"
            className="pl-btn"
            onClick={async () => {
              try {
                await controller.restartService();
                setMessage("服务已重启");
              } catch (error) {
                setMessage(controller.friendlyError(error));
              }
            }}
          >
            重启本地服务
          </button>
          <button type="button" className="pl-btn pl-btn--ghost" onClick={() => void load()}>
            刷新状态
          </button>
        </div>
      </div>

      <div className="pl-card pl-small pl-muted">
        API Key 通过 Windows DPAPI 加密后保存在服务的 secret.bin 中，不会写入插件配置、日志或笔记。
        你也可以用环境变量 DEEPSEEK_API_KEY 提供密钥（优先级更低）。
      </div>
    </div>
  );
}
