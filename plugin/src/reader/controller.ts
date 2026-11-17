import { errorText, debug } from "../log";
import { noteIndexPref, saveNote } from "../notes";
import type { ServiceClient } from "../service/client";
import { ServiceError } from "../service/client";
import type { ServiceManager } from "../service/manager";
import type {
  AttachmentContext,
  ChatMessage,
  Citation,
  DocumentMeta,
  Job,
  ReadMode,
  Scope,
  Segment,
  Selection,
  ServiceStatus,
  SidebarTab,
  Term,
} from "../types";
import { attachmentContext, attachmentContextFromItem, bestPdfAttachment, createPrefs, currentPage, findPaperLoomNotes, jumpToPage, readerDocument } from "../zotero/api";

export interface PluginHost {
  id: string;
  version: string;
  rootURI: string;
  service: ServiceManager;
  client: ServiceClient;
  prefs: ReturnType<typeof createPrefs>;
}

export interface AnalysisState {
  kind: string;
  text: string;
  status: "idle" | "streaming" | "done" | "error";
  error?: string;
  citations?: Citation[];
  model?: string;
}

export interface NoteSummary {
  id: number;
  key: string;
  snippet: string;
}

export interface UIState {
  ready: boolean;
  loading: boolean;
  error: string | null;
  notice: string | null;
  service: ServiceStatus | null;
  document: DocumentMeta | null;
  segments: Segment[];
  tab: SidebarTab;
  sidebarOpen: boolean;
  sidebarWidth: number;
  bilingualOpen: boolean;
  mode: ReadMode;
  page: number;
  scope: Scope;
  selection: Selection | null;
  messages: ChatMessage[];
  conversationId: string | null;
  streaming: boolean;
  composerDraft: string;
  job: Job | null;
  translating: boolean;
  terms: Term[];
  glossaryOpen: boolean;
  settingsOpen: boolean;
  analysis: AnalysisState | null;
  notes: NoteSummary[];
  alignmentNote: string;
  model: string;
  models: { id: string; label: string }[];
}

function initialState(prefs: PluginHost["prefs"]): UIState {
  return {
    ready: false,
    loading: true,
    error: null,
    notice: null,
    service: null,
    document: null,
    segments: [],
    tab: "chat",
    sidebarOpen: true,
    sidebarWidth: Number(prefs.get("extensions.paperloom.sidebarWidth", 380)) || 380,
    bilingualOpen: false,
    mode: "dual",
    page: 1,
    scope: (prefs.get("extensions.paperloom.lastScope", "selection") as Scope) || "selection",
    selection: null,
    messages: [],
    conversationId: null,
    streaming: false,
    composerDraft: "",
    job: null,
    translating: false,
    terms: [],
    glossaryOpen: false,
    settingsOpen: false,
    analysis: null,
    notes: [],
    alignmentNote: "",
    model: "",
    models: [],
  };
}

export class ReaderController {
  state: UIState;
  attachment: AttachmentContext | null = null;
  private listeners = new Set<() => void>();
  private chatAbort: AbortController | null = null;
  private analysisAbort: AbortController | null = null;
  private jobAbort: AbortController | null = null;
  private saveTimer: ReturnType<typeof setTimeout> | null = null;
  private pageHandler: ((event: any) => void) | null = null;
  private destroyed = false;
  private noteIndex: { get(): Record<string, string>; set(value: Record<string, string>): void };

  constructor(
    private readonly host: PluginHost,
    private readonly reader: any,
  ) {
    this.state = initialState(host.prefs);
    this.noteIndex = noteIndexPref(host.prefs);
  }

  get client(): ServiceClient {
    return this.host.client;
  }

  get serviceManager(): ServiceManager {
    return this.host.service;
  }

  // ---------------------------------------------------------------- store
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): UIState => this.state;

  private set(patch: Partial<UIState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) {
      try {
        listener();
      } catch {
        // A broken subscriber must not stop others.
      }
    }
  }

  private notice(message: string): void {
    this.set({ notice: message });
    setTimeout(() => {
      if (this.state.notice === message) {
        this.set({ notice: null });
      }
    }, 6000);
  }

  // ---------------------------------------------------------------- init
  async init(): Promise<void> {
    try {
      this.attachment = await attachmentContext(this.reader);
      await this.host.service.ensure();
      const status = await this.host.service.client.status();
      this.set({ service: status, model: "" });
      const registered = await this.host.service.client.registerDocument({
        libraryId: String(this.attachment.libraryID),
        itemKey: this.attachment.itemKey,
        attachmentKey: this.attachment.attachmentKey,
        pdfPath: this.attachment.pdfPath,
        title: this.attachment.title,
      });
      const document = registered.document;
      const segments = (await this.host.service.client.getSegments(document.id)).segments;
      const terms = (await this.host.service.client.getGlossary(document.id)).terms;
      let chatModel = "";
      let models: { id: string; label: string }[] = [];
      try {
        const settings = await this.host.service.client.getSettings();
        chatModel = settings.settings.chat_model;
        models = settings.models || [];
      } catch (error) {
        debug("settings unavailable", errorText(error));
      }
      this.set({
        document,
        segments,
        terms,
        ready: true,
        loading: false,
        model: chatModel,
        models,
        alignmentNote: document.alignmentNote,
      });
      this.applyBodyStyles();
      await this.restoreReadingState();
      await this.restoreConversation();
      await this.restoreAnalysis();
      await this.refreshNotes();
      await this.attachLatestJob();
      this.watchPageChanges();
    } catch (error) {
      this.set({ loading: false, ready: false, error: this.friendlyError(error) });
      debug("init failed", errorText(error));
    }
  }

  private async restoreReadingState(): Promise<void> {
    if (!this.state.document) {
      return;
    }
    try {
      const { state } = await this.host.service.client.getReading(this.state.document.id);
      if (state && Object.keys(state).length) {
        this.set({
          page: state.page || 1,
          mode: (state.mode as ReadMode) || "dual",
          sidebarWidth: state.sidebar_width || this.state.sidebarWidth,
          sidebarOpen: state.sidebar_open !== 0,
          selection: (state as any).selection || null,
        });
        this.applyBodyStyles();
        if (state.page && state.page > 1) {
          jumpToPage(this.reader, state.page);
        }
      }
    } catch (error) {
      debug("reading state unavailable", errorText(error));
    }
  }

  private async restoreConversation(): Promise<void> {
    if (!this.state.document) {
      return;
    }
    try {
      const { conversations } = await this.host.service.client.listConversations(this.state.document.id);
      if (!conversations.length) {
        return;
      }
      const conversation = conversations[0];
      const { messages } = await this.host.service.client.getMessages(conversation.id);
      const mapped: ChatMessage[] = messages
        .filter((item) => item.role === "user" || item.role === "assistant")
        .map((item) => ({
          id: item.id,
          role: item.role,
          content: item.content,
          citations: item.citations || [],
          status: item.status === "failed" ? "failed" : item.status === "cancelled" ? "cancelled" : "done",
          model: item.model,
          usage: item.usage || undefined,
        }));
      this.set({ conversationId: conversation.id, messages: mapped });
    } catch (error) {
      debug("conversation restore failed", errorText(error));
    }
  }

  private async restoreAnalysis(): Promise<void> {
    if (!this.state.document) {
      return;
    }
    try {
      const { analyses } = await this.host.service.client.listAnalyses(this.state.document.id, 1);
      const latest = analyses[0];
      if (latest) {
        this.set({
          analysis: {
            kind: latest.kind,
            text: latest.result,
            status: latest.result ? "done" : "idle",
            model: latest.model,
          },
        });
      }
    } catch (error) {
      debug("analysis restore failed", errorText(error));
    }
  }

  private async attachLatestJob(): Promise<void> {
    if (!this.state.document) {
      return;
    }
    try {
      const { jobs } = await this.host.service.client.listJobs(this.state.document.id, 3);
      const latest = jobs[0];
      if (!latest) {
        return;
      }
      this.set({ job: latest });
      if (latest.state === "running" || latest.state === "queued") {
        await this.followJob(latest.id);
      } else if (latest.state === "interrupted") {
        this.notice("上次翻译任务被中断，可点击重试（已完成段落不会重复翻译）");
      }
    } catch (error) {
      debug("job restore failed", errorText(error));
    }
  }

  private watchPageChanges(): void {
    try {
      const app = this.reader._iframeWindow?.PDFViewerApplication;
      if (!app?.eventBus?.on) {
        return;
      }
      if (this.pageHandler && app.eventBus.off) {
        app.eventBus.off("pagechanging", this.pageHandler);
      }
      this.pageHandler = (event: any) => {
        const page = Number(event?.pageNumber) || currentPage(this.reader);
        if (page !== this.state.page) {
          this.set({ page });
          this.scheduleSaveReading({ page });
        }
      };
      app.eventBus.on("pagechanging", this.pageHandler);
    } catch (error) {
      debug("page listener failed", errorText(error));
    }
  }

  // ---------------------------------------------------------------- UI state
  setTab(tab: SidebarTab): void {
    this.set({ tab });
  }

  toggleSidebar(open?: boolean): void {
    this.set({ sidebarOpen: open ?? !this.state.sidebarOpen });
    this.applyBodyStyles();
    this.scheduleSaveReading({ sidebar_open: this.state.sidebarOpen });
  }

  setSidebarWidth(width: number): void {
    const clamped = Math.max(300, Math.min(620, Math.round(width)));
    this.set({ sidebarWidth: clamped });
    this.applyBodyStyles();
    this.host.prefs.set("extensions.paperloom.sidebarWidth", clamped);
    this.scheduleSaveReading({ sidebar_width: clamped });
  }

  setMode(mode: ReadMode): void {
    this.set({ mode });
    this.scheduleSaveReading({ mode });
  }

  setScope(scope: Scope): void {
    this.set({ scope });
    this.host.prefs.set("extensions.paperloom.lastScope", scope);
  }

  setSelection(selection: Selection | null): void {
    this.set({ selection });
    this.scheduleSaveReading({ selection });
  }

  setModel(model: string): void {
    this.set({ model });
  }

  setComposerDraft(text: string): void {
    this.set({ composerDraft: text });
  }

  openSettings(open = true): void {
    this.set({ settingsOpen: open });
  }

  toggleBilingual(open?: boolean): void {
    this.set({ bilingualOpen: open ?? !this.state.bilingualOpen });
  }

  async restartService(): Promise<void> {
    await this.host.service.restart();
    await this.init();
  }

  openGlossary(open = true): void {
    this.set({ glossaryOpen: open });
  }

  jumpTo(page: number): void {
    jumpToPage(this.reader, page);
    this.set({ page });
    this.scheduleSaveReading({ page });
  }

  jumpToSegment(segmentId: string): void {
    const segment = this.state.segments.find((item) => item.id === segmentId);
    if (segment) {
      this.jumpTo(segment.page);
    }
  }

  private applyBodyStyles(): void {
    const doc = readerDocument(this.reader);
    if (!doc?.body) {
      return;
    }
    doc.body.style.setProperty("--pl-width", `${this.state.sidebarWidth}px`);
    doc.body.classList.toggle("paperloom-sidebar-open", this.state.sidebarOpen);
  }

  private scheduleSaveReading(patch: Record<string, unknown>): void {
    if (!this.state.document) {
      return;
    }
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
    }
    const documentId = this.state.document.id;
    this.saveTimer = setTimeout(() => {
      this.host.service.client.saveReading(documentId, patch).catch((error) => {
        debug("save reading failed", errorText(error));
      });
    }, 700);
  }

  // ---------------------------------------------------------------- chat
  async ask(question: string, options: { selection?: Selection | null; scope?: Scope } = {}): Promise<void> {
    const document = this.state.document;
    if (!document) {
      this.notice("论文尚未就绪");
      return;
    }
    if (this.state.streaming) {
      return;
    }
    const trimmed = question.trim();
    if (!trimmed) {
      return;
    }
    const selection = options.selection ?? this.state.selection;
    let scope = options.scope ?? this.state.scope;
    if (scope === "selection" && !selection) {
      scope = "paper";
      this.notice("未选中文字，已改为整篇论文上下文");
    }
    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: trimmed,
      status: "done",
    };
    const assistant: ChatMessage = {
      id: `a-${Date.now()}`,
      role: "assistant",
      content: "",
      status: "streaming",
      citations: [],
    };
    const history = this.state.messages
      .filter((message) => message.status !== "streaming")
      .slice(-10)
      .map((message) => ({ role: message.role, content: message.content }));
    this.set({
      messages: [...this.state.messages, userMessage, assistant],
      streaming: true,
      error: null,
      tab: "chat",
      composerDraft: "",
      selection,
      scope,
    });
    const abort = new AbortController();
    this.chatAbort = abort;
    try {
      const events = this.host.service.client.chat(
        {
          documentId: document.id,
          conversationId: this.state.conversationId,
          scope,
          selection,
          image: selection?.kind === "figure" ? selection.image : undefined,
          messages: [...history, { role: "user", content: trimmed }],
        },
        abort.signal,
      );
      for await (const event of events) {
        const data = event.data || {};
        if (event.event === "context") {
          this.set({ conversationId: data.conversationId });
          if (data.note) {
            this.set({ alignmentNote: data.note });
          }
        } else if (event.event === "delta") {
          this.patchAssistant(assistant.id, (current) => ({
            content: current.content + String(data.text || ""),
          }));
        } else if (event.event === "citations") {
          this.patchAssistant(assistant.id, () => ({ citations: data.citations || [] }));
        } else if (event.event === "usage") {
          this.patchAssistant(assistant.id, () => ({ usage: data.usage }));
        } else if (event.event === "error") {
          this.patchAssistant(assistant.id, () => ({
            status: "failed",
            content: `生成失败：${data.error?.message || "未知错误"}`,
          }));
        } else if (event.event === "done") {
          this.patchAssistant(assistant.id, (current) => ({
            content: data.text || current.content,
            status: data.status === "failed" ? "failed" : data.status === "cancelled" ? "cancelled" : "done",
            model: data.model,
            usage: data.usage || current.usage,
          }));
        }
      }
    } catch (error) {
      if ((error as any)?.name === "AbortError") {
        this.patchAssistant(assistant.id, () => ({ status: "cancelled", content: this.assistantText(assistant.id) }));
      } else {
        this.patchAssistant(assistant.id, () => ({
          status: "failed",
          content: this.friendlyError(error),
        }));
      }
    } finally {
      this.chatAbort = null;
      this.set({ streaming: false });
    }
  }

  stop(): void {
    this.chatAbort?.abort();
    this.analysisAbort?.abort();
    this.set({ streaming: false });
  }

  retryLast(): void {
    const messages = [...this.state.messages];
    let lastUser: ChatMessage | undefined;
    while (messages.length) {
      const message = messages.pop();
      if (message?.role === "user") {
        lastUser = message;
        break;
      }
    }
    if (!lastUser) {
      return;
    }
    this.set({ messages });
    void this.ask(lastUser.content);
  }

  explainSelection(selection: Selection): void {
    this.set({ selection, scope: "selection", tab: "chat" });
    void this.ask(`请解释这段内容（第 ${selection.page} 页）：\n\n> ${selection.text}`);
  }

  askSelection(selection: Selection): void {
    this.set({
      selection,
      scope: "selection",
      tab: "chat",
      composerDraft: "关于这段内容：",
    });
  }

  private assistantText(id: string): string {
    return this.state.messages.find((message) => message.id === id)?.content || "";
  }

  private patchAssistant(id: string, update: (current: ChatMessage) => Partial<ChatMessage>): void {
    this.set({
      messages: this.state.messages.map((message) =>
        message.id === id ? { ...message, ...update(message) } : message,
      ),
    });
  }

  // ---------------------------------------------------------------- notes
  async saveConversationNote(): Promise<void> {
    const attachment = this.attachment;
    const document = this.state.document;
    if (!attachment || !document) {
      return;
    }
    const usable = this.state.messages.filter((message) => message.status === "done" && message.content.trim());
    if (!usable.length) {
      this.notice("当前没有可保存的对话");
      return;
    }
    const lines = usable
      .map((message) => (message.role === "user" ? `**问：** ${message.content}` : message.content))
      .join("\n\n");
    const citations = usable.flatMap((message) => message.citations || []);
    const dedupe = `${document.id}:conv:${this.state.conversationId || "local"}`;
    try {
      const { updated } = await saveNote(
        {
          dedupeKey: dedupe,
          docTitle: document.title,
          attachment,
          page: this.state.page,
          selection: this.state.selection,
          question: usable.find((message) => message.role === "user")?.content,
          answer: lines,
          citations,
          segments: this.state.segments,
          model: this.state.model,
          kind: "对话",
        },
        attachment.parentItemID || attachment.attachmentItemID,
        attachment.libraryID,
        this.noteIndex,
      );
      this.notice(updated ? "已更新对话笔记" : "已保存整段对话到 Zotero 笔记");
      await this.refreshNotes();
    } catch (error) {
      this.set({ error: `保存笔记失败：${errorText(error)}` });
    }
  }

  async saveSelectionNote(selection: Selection): Promise<void> {
    const attachment = this.attachment;
    const document = this.state.document;
    if (!attachment || !document) {
      return;
    }
    const segment = this.state.segments.find(
      (item) => item.page === selection.page && selection.text && item.text.includes(selection.text.slice(0, 40)),
    );
    try {
      const { note, updated } = await saveNote(
        {
          dedupeKey: `${document.id}:sel:${selection.page}:${hash(selection.text)}`,
          docTitle: document.title,
          attachment,
          page: selection.page,
          selection,
          translation: segment?.translation || undefined,
          segments: this.state.segments,
          model: "manual",
          kind: "选区",
        },
        attachment.parentItemID || attachment.attachmentItemID,
        attachment.libraryID,
        this.noteIndex,
      );
      this.notice(updated ? "已更新选区笔记" : "已保存选区笔记");
      await this.refreshNotes();
      void note;
    } catch (error) {
      this.set({ error: `保存笔记失败：${errorText(error)}` });
    }
  }

  async saveMessageNote(message: ChatMessage): Promise<void> {
    const attachment = this.attachment;
    const document = this.state.document;
    if (!attachment || !document) {
      return;
    }
    const index = this.state.messages.findIndex((item) => item.id === message.id);
    let question = "";
    for (let i = index - 1; i >= 0; i -= 1) {
      if (this.state.messages[i].role === "user") {
        question = this.state.messages[i].content;
        break;
      }
    }
    try {
      const { updated } = await saveNote(
        {
          dedupeKey: `${document.id}:msg:${message.id}`,
          docTitle: document.title,
          attachment,
          page: message.citations?.[0]?.page || this.state.page,
          selection: this.state.selection,
          question,
          answer: message.content,
          citations: message.citations,
          segments: this.state.segments,
          model: message.model || this.state.model,
        },
        attachment.parentItemID || attachment.attachmentItemID,
        attachment.libraryID,
        this.noteIndex,
      );
      this.notice(updated ? "已更新该回答的笔记" : "已保存回答到 Zotero 笔记");
      await this.refreshNotes();
    } catch (error) {
      this.set({ error: `保存笔记失败：${errorText(error)}` });
    }
  }

  async refreshNotes(): Promise<void> {
    const attachment = this.attachment;
    if (!attachment) {
      return;
    }
    const parentID = attachment.parentItemID || attachment.attachmentItemID;
    const notes = await findPaperLoomNotes(parentID);
    this.set({
      notes: notes.slice(0, 20).map((note) => {
        const html: string = note.getNote?.() || "";
        const text = html
          .replace(/<[^>]+>/g, " ")
          .replace(/\s+/g, " ")
          .trim();
        return { id: note.id, key: note.key, snippet: text.slice(0, 120) };
      }),
    });
  }

  // ---------------------------------------------------------------- translation
  async startTranslation(pages?: number[]): Promise<void> {
    const document = this.state.document;
    if (!document || this.state.translating) {
      return;
    }
    if (document.scanned) {
      this.set({ error: "该 PDF 未检测到文本层（疑似扫描件），请先 OCR 后再翻译" });
      return;
    }
    this.set({ translating: true, error: null });
    try {
      const { job } = await this.host.service.client.startTranslation(document.id, {
        pages: pages && pages.length ? pages : null,
      });
      this.set({ job });
      await this.followJob(job.id);
    } catch (error) {
      this.set({ translating: false, error: this.friendlyError(error) });
    }
  }

  /** Ask for a page range (e.g. "1-3,5") and translate only those pages. */
  async startTranslationWithPrompt(): Promise<void> {
    let input: string | null = null;
    try {
      const win = Zotero.getMainWindow();
      input = win.prompt("输入页码范围（例如 1-3,5；留空表示全文）", "");
    } catch {
      input = null;
    }
    if (input === null) {
      return;
    }
    const pages = parsePageRanges(input);
    if (pages === null) {
      this.set({ error: "页码范围格式无效，请输入如 1-3,5" });
      return;
    }
    await this.startTranslation(pages.length ? pages : undefined);
  }

  private async followJob(jobId: string): Promise<void> {
    this.jobAbort?.abort();
    const abort = new AbortController();
    this.jobAbort = abort;
    this.set({ translating: true });
    try {
      const stream = this.host.service.client.getStream(
        `${this.host.service.client.jobEventsUrl(jobId, -1)}`,
        abort.signal,
      );
      for await (const event of stream) {
        const data = event.data || {};
        if (event.event === "job") {
          this.set({ job: data as Job });
        } else if (event.event === "progress") {
          const current = this.state.job;
          this.set({
            job: current
              ? { ...current, progress: data, state: "running" }
              : ({ id: jobId, state: "running", stage: "translating", progress: data } as Job),
          });
        } else if (event.event === "segment") {
          this.patchSegment(String(data.id), String(data.translation || ""));
        } else if (event.event === "log") {
          this.notice(String(data.message || ""));
        } else if (event.event === "error") {
          this.set({ error: data.error?.message || "翻译失败" });
        } else if (event.event === "done") {
          this.set({ translating: false, job: { ...(this.state.job as Job), state: data.state } });
          if (data.state === "succeeded") {
            this.notice(
              `翻译完成：${data.translated ?? 0} 段` + (data.warnings?.length ? `（${data.warnings.length} 条提示）` : ""),
            );
            await this.reloadSegments();
            await this.importArtifacts(jobId, data.artifacts);
          }
        }
      }
    } catch (error) {
      if ((error as any)?.name !== "AbortError") {
        this.set({ error: this.friendlyError(error) });
      }
    } finally {
      this.set({ translating: false });
    }
  }

  async cancelTranslation(): Promise<void> {
    const job = this.state.job;
    if (!job) {
      return;
    }
    this.jobAbort?.abort();
    try {
      const { job: updated } = await this.host.service.client.cancelJob(job.id);
      this.set({ job: updated, translating: false });
      this.notice("已取消翻译任务");
    } catch (error) {
      this.set({ error: this.friendlyError(error) });
    }
  }

  async retryTranslation(): Promise<void> {
    const job = this.state.job;
    if (!job) {
      void this.startTranslation();
      return;
    }
    try {
      const { job: next } = await this.host.service.client.retryJob(job.id);
      this.set({ job: next });
      await this.followJob(next.id);
    } catch (error) {
      this.set({ error: this.friendlyError(error) });
    }
  }

  private patchSegment(id: string, translation: string): void {
    this.set({
      segments: this.state.segments.map((segment) =>
        segment.id === id ? { ...segment, translation } : segment,
      ),
    });
  }

  /**
   * Import BabelDOC PDF output into Zotero only after verifying it is a real
   * PDF. Existing attachments with the same title are left untouched.
   */
  async importArtifacts(jobId?: string, artifacts?: { kind: string }[]): Promise<void> {
    const attachment = this.attachment;
    const document = this.state.document;
    const id = jobId || this.state.job?.id;
    if (!attachment || !document || !id) {
      return;
    }
    const kinds = (artifacts || this.state.job?.artifacts || [])
      .map((artifact) => artifact.kind)
      .filter((kind) => kind === "dual" || kind === "mono");
    for (const kind of kinds) {
      try {
        const buffer = await this.client.downloadArtifact(id, kind);
        const head = new TextDecoder().decode(new Uint8Array(buffer.slice(0, 5)));
        if (head !== "%PDF-") {
          debug("artifact is not a pdf", kind);
          continue;
        }
        const title = kind === "dual" ? "PaperLoom 双语版" : "PaperLoom 中文版";
        const parentID = attachment.parentItemID;
        if (parentID) {
          const parent = Zotero.Items.get(parentID);
          const childIDs = await parent.getAttachments();
          const exists = childIDs.some((childID: number) => {
            const child = Zotero.Items.get(childID);
            return child && child.getField("title") === title;
          });
          if (exists) {
            continue;
          }
        }
        const dir = PathUtils.join(PathUtils.tempDir, "paperloom");
        if (!(await IOUtils.exists(dir))) {
          await IOUtils.makeDirectory(dir, { ignoreExisting: true });
        }
        const path = PathUtils.join(dir, `${document.id}-${kind}.pdf`);
        await IOUtils.write(path, new Uint8Array(buffer));
        const imported = await Zotero.Attachments.importFromFile({
          file: path,
          parentItemID: parentID || undefined,
          libraryID: attachment.libraryID,
        });
        imported.setField("title", title);
        await imported.saveTx();
        this.notice(`已创建 Zotero 附件：${title}`);
      } catch (error) {
        debug("artifact import failed", errorText(error));
        this.notice(`导入翻译 PDF 失败：${errorText(error)}`);
      }
    }
  }

  private async reloadSegments(): Promise<void> {
    const document = this.state.document;
    if (!document) {
      return;
    }
    const [{ segments }, meta] = await Promise.all([
      this.host.service.client.getSegments(document.id),
      this.host.service.client.getDocument(document.id),
    ]);
    this.set({ segments, document: meta.document });
  }

  // ---------------------------------------------------------------- analysis
  async analyze(kind: string, focus = "", durationMinutes = 10): Promise<void> {
    const document = this.state.document;
    if (!document) {
      return;
    }
    await this.runAnalysis(kind, focus, [document.id], durationMinutes);
  }

  /** Compare the current paper with the items selected in the Zotero main window. */
  async compareSelected(): Promise<void> {
    const document = this.state.document;
    if (!document) {
      return;
    }
    const documentIds = new Set<string>([document.id]);
    const skipped: string[] = [];
    try {
      const mainWindow = Zotero.getMainWindow();
      const selected = mainWindow?.ZoteroPane?.getSelectedItems?.() || [];
      for (const item of selected) {
        const attachment = await bestPdfAttachment(item);
        if (!attachment) {
          skipped.push(item.getField?.("title") || item.key || "(未知条目)");
          continue;
        }
        const context = await attachmentContextFromItem(attachment);
        if (!context) {
          skipped.push(String(attachment.key || "(无法读取文件)"));
          continue;
        }
        const registered = await this.host.service.client.registerDocument({
          libraryId: String(context.libraryID),
          itemKey: context.itemKey,
          attachmentKey: context.attachmentKey,
          pdfPath: context.pdfPath,
          title: context.title,
        });
        documentIds.add(registered.document.id);
      }
    } catch (error) {
      this.set({ error: `读取选中文献失败：${errorText(error)}` });
      return;
    }
    if (documentIds.size < 2) {
      this.set({ error: "请先在主窗口选中至少一篇其它带 PDF 的文献，再点击“论文对比”。" });
      return;
    }
    if (skipped.length) {
      this.notice(`已跳过 ${skipped.length} 个没有 PDF 的条目`);
    }
    await this.runAnalysis("compare", "", Array.from(documentIds));
  }

  private async runAnalysis(
    kind: string,
    focus: string,
    documentIds: string[],
    durationMinutes = 10,
  ): Promise<void> {
    if (this.state.analysis?.status === "streaming") {
      this.analysisAbort?.abort();
    }
    this.set({
      analysis: { kind, text: "", status: "streaming" },
      tab: "analysis",
      error: null,
    });
    const abort = new AbortController();
    this.analysisAbort = abort;
    try {
      const body = {
        kind,
        documentIds,
        selection: this.state.scope === "selection" ? this.state.selection : null,
        durationMinutes,
        focus,
      };
      for await (const event of this.host.service.client.analysis(body, abort.signal)) {
        const data = event.data || {};
        if (event.event === "delta") {
          this.patchAnalysis((current) => ({ text: current.text + String(data.text || "") }));
        } else if (event.event === "citations") {
          this.patchAnalysis(() => ({ citations: data.citations || [] }));
        } else if (event.event === "error") {
          this.patchAnalysis(() => ({ status: "error", error: data.error?.message || "分析失败" }));
        } else if (event.event === "done") {
          this.patchAnalysis((current) => ({
            text: data.text || current.text,
            status: data.status === "failed" ? "error" : "done",
            model: data.model,
          }));
        }
      }
    } catch (error) {
      if ((error as any)?.name !== "AbortError") {
        this.patchAnalysis(() => ({ status: "error", error: this.friendlyError(error) }));
      }
    }
  }

  private patchAnalysis(update: (current: AnalysisState) => Partial<AnalysisState>): void {
    const current = this.state.analysis;
    if (!current) {
      return;
    }
    this.set({ analysis: { ...current, ...update(current) } });
  }

  async saveAnalysisNote(): Promise<void> {
    const analysis = this.state.analysis;
    const attachment = this.attachment;
    const document = this.state.document;
    if (!analysis || !attachment || !document) {
      return;
    }
    try {
      await saveNote(
        {
          dedupeKey: `${document.id}:analysis:${analysis.kind}`,
          docTitle: document.title,
          attachment,
          page: this.state.page,
          selection: this.state.selection,
          answer: analysis.text,
          citations: analysis.citations,
          segments: this.state.segments,
          model: analysis.model,
          kind: analysis.kind,
        },
        attachment.parentItemID || attachment.attachmentItemID,
        attachment.libraryID,
        this.noteIndex,
      );
      this.notice("分析结果已保存到笔记（重复保存会更新）");
      await this.refreshNotes();
    } catch (error) {
      this.set({ error: `保存笔记失败：${errorText(error)}` });
    }
  }

  // ---------------------------------------------------------------- glossary
  async refreshTerms(): Promise<void> {
    const document = this.state.document;
    if (!document) {
      return;
    }
    try {
      const { terms } = await this.host.service.client.getGlossary(document.id);
      this.set({ terms });
    } catch (error) {
      debug("glossary refresh failed", errorText(error));
    }
  }

  async addTerm(source: string, target: string, scope: "paper" | "global"): Promise<void> {
    const document = this.state.document;
    if (!document || !source.trim() || !target.trim()) {
      return;
    }
    const result = await this.host.service.client.addTerm({
      documentId: scope === "paper" ? document.id : null,
      source: source.trim(),
      target: target.trim(),
      scope,
      status: "confirmed",
    });
    await this.refreshTerms();
    this.notice(
      result.affectedSegments
        ? `术语已保存；有 ${result.affectedSegments} 段旧译文可能受影响，可重新翻译`
        : "术语已保存",
    );
  }

  async updateTerm(term: Term, patch: Record<string, unknown>): Promise<void> {
    await this.host.service.client.patchTerm(term.id, patch);
    await this.refreshTerms();
  }

  async deleteTerm(term: Term): Promise<void> {
    await this.host.service.client.deleteTerm(term.id);
    await this.refreshTerms();
  }

  async extractTerms(): Promise<void> {
    const document = this.state.document;
    if (!document) {
      return;
    }
    this.notice("正在提取术语…");
    try {
      const result = await this.host.service.client.extractTerms(document.id);
      await this.refreshTerms();
      this.notice(`已提取 ${result.count} 个候选术语`);
    } catch (error) {
      this.set({ error: `术语提取失败：${this.friendlyError(error)}` });
    }
  }

  // ---------------------------------------------------------------- errors
  friendlyError(error: unknown): string {
    if (error instanceof ServiceError) {
      if (error.code === "service_down" || error.status === 0) {
        return `${error.message}。请检查本地服务是否安装并运行（设置 → 服务诊断）。`;
      }
      if (error.code === "no_api_key") {
        return "尚未配置 DeepSeek API Key，请在设置中填写并测试连接。";
      }
      if (error.code === "auth") {
        return "DeepSeek 鉴权失败，请检查 API Key 是否正确或已失效。";
      }
      if (error.code === "insufficient_balance") {
        return "DeepSeek 余额不足，请充值后重试。";
      }
      if (error.code === "rate_limit") {
        return "请求过于频繁（限流），已自动重试；可降低并发或稍后再试。";
      }
      if (error.code === "context_length") {
        return "上下文超出模型限制，请把范围切换为“当前选区”或减少上下文长度。";
      }
      return error.message;
    }
    return errorText(error);
  }

  // ---------------------------------------------------------------- lifecycle
  destroy(): void {
    if (this.destroyed) {
      return;
    }
    this.destroyed = true;
    this.chatAbort?.abort();
    this.analysisAbort?.abort();
    this.jobAbort?.abort();
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
    }
    try {
      const app = this.reader._iframeWindow?.PDFViewerApplication;
      if (this.pageHandler && app?.eventBus?.off) {
        app.eventBus.off("pagechanging", this.pageHandler);
      }
    } catch {
      // ignore
    }
    const doc = readerDocument(this.reader);
    doc?.body?.classList.remove("paperloom-sidebar-open");
    this.listeners.clear();
  }
}

function hash(text: string): string {
  let value = 0;
  for (let index = 0; index < text.length; index += 1) {
    value = (value * 31 + text.charCodeAt(index)) | 0;
  }
  return Math.abs(value).toString(36);
}

function parsePageRanges(input: string): number[] | null {
  const text = input.trim();
  if (!text) {
    return [];
  }
  const pages = new Set<number>();
  for (const part of text.split(/[,，\s]+/).filter(Boolean)) {
    const match = /^(\d+)(?:\s*[-~]\s*(\d+))?$/.exec(part);
    if (!match) {
      return null;
    }
    const start = Number(match[1]);
    const end = match[2] ? Number(match[2]) : start;
    if (start < 1 || end < start || end > 5000) {
      return null;
    }
    for (let page = start; page <= end; page += 1) {
      pages.add(page);
    }
  }
  return Array.from(pages).sort((a, b) => a - b);
}
