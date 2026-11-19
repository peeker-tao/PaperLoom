import { useEffect, useRef, useState } from "react";
import { ACCEPT_ATTRIBUTE, ACCEPT_LABEL, MAX_IMAGES, checkCandidate, describeImages } from "../attachments";
import type { ChatImage } from "../attachments";
import { shouldSendOnEnter } from "../composer";
import { debug } from "../log";
import type { ReaderController, UIState } from "../reader/controller";
import type { Usage } from "../types";
import { Empty, MarkdownView, Spinner } from "./common";

/** Report the first keystroke once: it separates "keys never arrive" from
 * "keys arrive but the text does not stick". */
let loggedKeystroke = false;

/** Ids only need to be unique within one composer session. */
let imageSeq = 0;

function nextImageId(): string {
  imageSeq += 1;
  return `img-${Date.now()}-${imageSeq}`;
}

/**
 * Read a picked or pasted file into a data URL.
 *
 * A rejected read is reported rather than dropped: FileReader fails silently on
 * some clipboard sources, and the user would otherwise see nothing happen.
 */
function readAsDataUrl(file: Blob): Promise<string | null> {
  return new Promise((resolve) => {
    try {
      const reader = new FileReader();
      reader.onload = () => {
        const result = typeof reader.result === "string" ? reader.result : "";
        resolve(result.startsWith("data:image/") ? result : null);
      };
      reader.onerror = () => {
        debug("file read failed", String(reader.error));
        resolve(null);
      };
      reader.readAsDataURL(file);
    } catch (error) {
      debug("file read threw", String(error));
      resolve(null);
    }
  });
}

function usageLabel(usage: Usage): string {
  const tokens = (usage.promptTokens || 0) + (usage.completionTokens || 0);
  const cost = typeof usage.costUsd === "number" ? ` · $${usage.costUsd.toFixed(4)}` : "";
  return `${usage.estimated ? "≈" : ""}${tokens} tokens${cost}`;
}

export function ChatPanel(props: { controller: ReaderController; state: UIState }): JSX.Element {
  const { controller, state } = props;
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const lastSent = useRef<string | null>(null);
  /** True while an IME composition is open; see onCompositionStart below. */
  const composing = useRef(false);
  const [draft, setDraft] = useState(state.composerDraft);
  const last = state.messages[state.messages.length - 1];

  // The draft is owned locally and mirrored into the store. A controlled value
  // straight from the store silently reverted keystrokes when the round trip did
  // not come back (React restores the value it last saw), which made the box
  // look read-only. Only an *external* change (e.g. "关于这段内容：" filled in by
  // a quote action) overwrites what the user typed.
  useEffect(() => {
    if (state.composerDraft === lastSent.current) {
      return;
    }
    setDraft(state.composerDraft);
  }, [state.composerDraft]);

  const update = (text: string) => {
    setDraft(text);
    lastSent.current = text;
    controller.setComposerDraft(text);
  };

  const canSend = Boolean(draft.trim()) || state.attachments.length > 0;

  const submit = () => {
    const text = draft.trim();
    if (!text && !state.attachments.length) {
      return;
    }
    update("");
    inputRef.current?.focus();
    void controller.ask(text);
  };

  /**
   * Attach files the user picked or pasted.
   *
   * Each file is checked before it is read, so a 40MB TIFF is refused in a
   * millisecond instead of after decoding it. A refusal is surfaced as a notice
   * from the controller — silence reads as "paste does nothing".
   */
  const attachFiles = async (files: File[]) => {
    for (const file of files) {
      const problem = checkCandidate(file);
      if (problem) {
        controller.rejectAttachment(problem);
        break;
      }
      const dataUrl = await readAsDataUrl(file);
      if (!dataUrl) {
        controller.rejectAttachment(`${file.name || "这张图片"} 没有读到内容，请重新选择或粘贴`);
        break;
      }
      const image: ChatImage = {
        id: nextImageId(),
        dataUrl,
        caption: "",
        name: file.name || "粘贴的图片",
      };
      if (!controller.addAttachment(image)) {
        break;
      }
    }
  };

  useEffect(() => {
    const node = scrollRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [state.messages.length, last?.content.length, state.streaming]);

  if (!state.ready && state.loading) {
    return (
      <div className="pl-scroll">
        <div className="pl-empty">
          <Spinner />
          <div style={{ marginTop: 8 }}>正在连接本地服务并解析论文…</div>
        </div>
      </div>
    );
  }

  if (!state.ready && state.error) {
    return (
      <div className="pl-scroll">
        <div className="pl-card pl-card--error">
          <strong>无法启动</strong>
          <div className="pl-small" style={{ marginTop: 6 }}>
            {state.error}
          </div>
          <div className="pl-actions">
            <button type="button" className="pl-btn" onClick={() => void controller.init()}>
              重试
            </button>
            <button type="button" className="pl-btn pl-btn--ghost" onClick={() => controller.openSettings(true)}>
              服务与 API 设置
            </button>
          </div>
        </div>
      </div>
    );
  }

  const keyMissing = state.service && !state.service.apiKey.configured;
  const fakeMode = state.service && (state.service as any).llm === "fake";

  return (
    <>
      <div className="pl-scroll" ref={scrollRef}>
        {fakeMode ? (
          <div className="pl-card pl-card--warn">
            <strong>演示模式</strong>
            <div className="pl-small" style={{ marginTop: 4 }}>
              未配置 DeepSeek API Key，当前回答与译文由本地假实现生成，仅用于验证界面与流程。
            </div>
          </div>
        ) : null}
        {keyMissing ? (
          <div className="pl-card pl-card--warn">
            <strong>尚未配置 DeepSeek API Key</strong>
            <div className="pl-small" style={{ marginTop: 4 }}>
              翻译、问答和分析都通过你自己的 DeepSeek 账户调用。密钥只保存在本机服务中。
            </div>
            <div className="pl-actions">
              <button type="button" className="pl-btn pl-btn--primary" onClick={() => controller.openSettings(true)}>
                打开设置
              </button>
            </div>
          </div>
        ) : null}

        {state.alignmentNote && state.document?.alignment !== "segment" ? (
          <div className="pl-card pl-card--warn pl-small">
            定位提示：{state.alignmentNote}（实际回退级别：{state.document?.alignment}）
          </div>
        ) : null}

        {!state.messages.length ? (
          <Empty text="选中论文中的文字，或直接在下方提问。支持连续追问，回答会标注原文出处。" />
        ) : null}

        {state.messages.map((message, index) => (
          <div key={message.id} className={`pl-msg pl-msg--${message.role}`}>
            <div className="pl-msg__role">
              {message.role === "user" ? "我" : `PaperLoom${message.model ? ` · ${message.model}` : ""}`}
              {message.status === "cancelled" ? " · 已取消" : ""}
              {message.status === "failed" ? " · 失败" : ""}
            </div>
            <div className="pl-msg__bubble">
              {message.role === "assistant" ? (
                <MarkdownView
                  text={message.content || (message.status === "streaming" ? "…" : "")}
                  onCite={(segmentId) => controller.jumpToSegment(segmentId)}
                  resolve={(segmentId) => {
                    const segment = state.segments.find((item) => item.id === segmentId);
                    return segment ? { page: segment.page } : null;
                  }}
                />
              ) : (
                <>
                  {message.images?.length ? (
                    <div className="pl-msg__images">
                      {message.images.map((image) => (
                        <figure key={image.id} className="pl-msg__image">
                          <img src={image.dataUrl} alt={image.name || "附图"} />
                          {image.caption ? <figcaption>{image.caption}</figcaption> : null}
                        </figure>
                      ))}
                    </div>
                  ) : null}
                  {message.content}
                </>
              )}
              {message.role === "assistant" && message.status === "streaming" ? (
                <div className="pl-small pl-muted" style={{ marginTop: 4 }}>
                  <Spinner /> 生成中…
                </div>
              ) : null}
            </div>
            {message.role === "assistant" && message.status === "done" ? (
              <div className="pl-actions">
                <button type="button" className="pl-btn pl-btn--ghost" onClick={() => void controller.saveMessageNote(message)}>
                  保存笔记
                </button>
                {index === state.messages.length - 1 ? (
                  <button type="button" className="pl-btn pl-btn--ghost" onClick={() => controller.retryLast()}>
                    重新生成
                  </button>
                ) : null}
                {message.citations?.length ? (
                  <span className="pl-small pl-muted">{message.citations.length} 处原文依据</span>
                ) : null}
                {message.usage ? <span className="pl-small pl-muted">{usageLabel(message.usage)}</span> : null}
              </div>
            ) : null}
          </div>
        ))}
      </div>

      <div className="pl-composer">
        {state.selection ? (
          <div className="pl-row" style={{ marginBottom: 6 }}>
            <span className="pl-chip" title={state.selection.text}>
              <span>
                第 {state.selection.page} 页 · {state.selection.text.slice(0, 60)}
              </span>
              <button type="button" title="清除选区" onClick={() => controller.setSelection(null)}>
                ✕
              </button>
            </span>
          </div>
        ) : null}
        {state.attachments.length ? (
          <div className="pl-attach">
            {state.attachments.map((image) => (
              <div key={image.id} className="pl-attach__item">
                <img className="pl-attach__thumb" src={image.dataUrl} alt={image.name || "附图"} />
                <button
                  type="button"
                  className="pl-attach__remove"
                  title="移除这张图片"
                  aria-label={`移除 ${image.name || "图片"}`}
                  onClick={() => controller.removeAttachment(image.id)}
                >
                  ✕
                </button>
                <input
                  className="pl-attach__caption"
                  placeholder="说明"
                  aria-label="图片说明"
                  value={image.caption}
                  onChange={(event) => controller.setAttachmentCaption(image.id, event.target.value)}
                />
              </div>
            ))}
          </div>
        ) : null}
        {state.attachmentError ? (
          <div className="pl-small pl-attach__error">{state.attachmentError}</div>
        ) : null}
        <textarea
          ref={inputRef}
          className="pl-textarea"
          placeholder={
            state.attachments.length
              ? "就这些图片提问，Enter 发送，Shift+Enter 换行"
              : "就这篇论文提问，Enter 发送，Shift+Enter 换行；可粘贴或添加图片"
          }
          value={draft}
          onChange={(event) => update(event.target.value)}
          onPaste={(event) => {
            // A screenshot on the clipboard arrives as a file item, not as text,
            // so the default paste does nothing at all — which is exactly what an
            // ignored paste looks like. Intercept it and attach instead.
            const files = Array.from(event.clipboardData?.items || [])
              .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
              .map((item) => item.getAsFile())
              .filter((file): file is File => Boolean(file));
            if (files.length) {
              event.preventDefault();
              void attachFiles(files);
            }
          }}
          onInput={(event) => {
            // `onChange` in React is backed by `input`; handling it directly too
            // costs nothing and survives the store being slow.
            const value = (event.target as HTMLTextAreaElement).value;
            if (value !== draft) {
              update(value);
            }
          }}
          onFocus={() => controller.ensureKeyboardFocus()}
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            // Cleared on a timeout: on some builds the keydown that confirms the
            // candidate arrives *after* compositionend within the same tick, so
            // clearing immediately would let that Enter send the message.
            setTimeout(() => {
              composing.current = false;
            }, 0);
          }}
          onKeyDown={(event) => {
            if (!loggedKeystroke) {
              loggedKeystroke = true;
              debug("composer keystroke", event.key);
            }
            const native = event.nativeEvent;
            const send = shouldSendOnEnter({
              key: event.key,
              shiftKey: event.shiftKey,
              ctrlKey: event.ctrlKey,
              metaKey: event.metaKey,
              altKey: event.altKey,
              isComposing: native?.isComposing,
              keyCode: native?.keyCode,
              composing: composing.current,
            });
            if (event.key === "Enter" && !send && !event.shiftKey) {
              // Enter was consumed by the IME: do nothing so the candidate
              // window keeps control. (Not preventing default is what lets the
              // IME finish its work.)
              return;
            }
            if (send) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="pl-composer__bottom">
          <div className="pl-row" style={{ gap: 6 }}>
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPT_ATTRIBUTE}
              multiple
              style={{ display: "none" }}
              onChange={(event) => {
                const files = Array.from(event.target.files || []);
                // Reset immediately: picking the same file twice must fire again.
                event.target.value = "";
                void attachFiles(files);
              }}
            />
            <button
              type="button"
              className="pl-btn pl-btn--ghost pl-attach__add"
              title={`添加图片（${ACCEPT_LABEL}，最多 ${MAX_IMAGES} 张，也可直接粘贴）`}
              aria-label="添加图片"
              disabled={state.attachments.length >= MAX_IMAGES}
              onClick={() => fileRef.current?.click()}
            >
              + 图片
            </button>
            <select
              className="pl-select"
              value={state.scope}
              onChange={(event) => controller.setScope(event.target.value as any)}
              title="上下文范围"
            >
              <option value="selection" disabled={!state.selection}>
                当前选区
              </option>
              <option value="section">当前章节</option>
              <option value="paper">整篇论文</option>
            </select>
            {state.models.length ? (
              <select
                className="pl-select"
                value={state.model}
                title="问答模型（只影响提问；翻译与分析各用设置里的模型）"
                aria-label="问答模型"
                onChange={(event) => controller.setModel(event.target.value)}
              >
                {state.models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label ? `${model.label}` : model.id}
                  </option>
                ))}
                {state.model && !state.models.some((model) => model.id === state.model) ? (
                  <option value={state.model}>{state.model}</option>
                ) : null}
              </select>
            ) : (
              <span className="pl-small pl-muted">{state.model || "默认模型"}</span>
            )}
          </div>
          <div className="pl-row">
            {state.streaming ? (
              <button type="button" className="pl-btn" onClick={() => controller.stop()}>
                停止生成
              </button>
            ) : (
              <button
                type="button"
                className="pl-btn pl-btn--primary"
                disabled={!canSend || state.streaming}
                title={state.attachments.length ? describeImages(state.attachments) : undefined}
                onClick={() => submit()}
              >
                发送
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
