# Changelog

All notable changes to PaperLoom are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed — 划词

- **在侧边栏阅读视图里划词什么都不发生。** 之前只有两个选区入口：PDF 里的
  Zotero 弹窗，和双语浮层上的一个 `onMouseUp`——而后者读的是
  `reader._iframeWindow.document.getSelection()`，**看不见侧边栏 shadow root 里的选区**。
  于是"真正在读的地方"反而是唯一不能划词的地方。
- 现在侧边栏任意位置（阅读视图、版式浮层、对话、笔记）划词都会浮出一条工具条：
  **解释 / 提问 / 存笔记**，并立刻把选区写入上下文——输入框上方出现
  「第 N 页 · 选中的文字」，范围自动切到「选区」，直接打字提问就带这段。
- 页号取自选区所在段落的 `data-segment-id`，所以跨段落选区也能落到正确的那一页。
- 三类"假选中"不会弹工具条：单击（折叠选区）、只剩标点、以及在输入框里选字
  （否则改个错别字也会弹窗）。

### Changed — 侧边栏的选择控件

- **模型下拉看不出区别，也不知道为什么不能选。** 原生 `<select>` 的选项只能是
  字符串：`deepseek-v4-pro` 不能读图这件事在界面上完全不可见，选中后附图才被拒绝。
  换成面板内的自定义下拉：每个模型一行名字 + 能力徽章（**可读图 / 无图**）+ 一行说明，
  已选项打勾，向上展开（输入框在面板底部，向下开会跑出视口）。
- **上下文范围从下拉改成三段控件**（选区 / 章节 / 全文）。三个选项本来就少，
  下拉要两次点击才看到另外两个；「选区」不可用时现在悬停就说明原因
  （"先选中一段文字"），而不是默默变灰。
- 两者都不会再被窄侧边栏挤出行外。

### Changed — 翻译的页码选择

- **"页码…"要背 `1-3,5` 这种语法。** 弹窗里现在是**可点的页码网格**：
  点数字即选中，选中同步回填到输入框；`当前页 / 前 5 页 / 未译页 / 全部 / 清空`
  一键到位，按钮文字直接写「翻译这 3 页」。
- **超出页数只能在开跑之后才知道。** 输入 `1-40` 会立刻提示
  「第 18～40 页超出这篇论文的 17 页范围」，并把合法部分保留在选区里。
- **哪些页已经有译文看不出来**，容易重复付费：已有译文的页带一个小圆点，
  「未译页」按钮直接选中所有还没有译文的页。
- 底部按钮 `页码…` 改名为 `选页…`，与弹窗的实际操作一致。

### Tests

- `plugin/test/selection.test.mjs` (20) — 折叠选区/单字符/纯标点不触发、输入框内不触发、
  `data-segment-id` 向上查找（含跨 shadow 边界与自引用链）、矩形缺失时仍可用。
- `plugin/test/pages.test.mjs` (+3, 共 11) — 页码网格的回填格式化，以及
  "格式化与解析互为逆运算"（否则点 4、5 两页会翻译成别的页）。

## [Unreleased]

### Fixed — 「翻译出来就是这样」

- **版式视图在还没翻译的页面上只显示原始 PDF，看上去像翻译坏了。** 版式视图是把译文
  盖在页面图上，一页 0 段译文时它就只是一张原文页面，没有任何说明。现在会明确写
  「第 N 页还没有译文（本页共 M 段待译）」，并给 **翻译本页** 与 **改用阅读视图**
  两个按钮。
- **「只显示译文」模式下 0 译文是一片空白。** 同样的说明与出口（翻译本页 / 改看双语）。
- **底部进度一直显示 0/469，看起来像卡住。** 那其实是全文计数。翻译第 1 页时现在显示
  「第 1 页 · 3/9 段」，进度条也只按当前任务算——否则等 4 秒就以为没反应而取消。
- **取消之后是死路。** 「已取消」横幅原来没有任何按钮。现在未译完的取消任务提供
  **继续翻译**（已译好的段落会跳过），并写明「已完成 0/9 段，可以继续」。

### Fixed — 分段（PARSER_VERSION 9）

- **8pt 的子图注被当成正文段落。** 论文把子图注释、表注排得比正文小（10pt 正文
  配 8pt 注），这些行出现在两段正文之间，像一句凭空冒出来的话。小于正文 1.5pt 以上、
  长度 < 300 且不是表格单元/文献/公式的行现在归为 `caption`。实测同一篇论文：
  正文段从 77 降到 71，6 个假段落消失。
- **单个表头行被当成正文。** 「表里至少要有 3 个单元才判为表」这条规则保护了短句子，
  但也放过了单独出现的指标表头。指标箭头（↑↓▲▼）在正文里不会出现，所以带箭头的行
  直接判为 `table`。

## [0.3.0] - 2026-11-19

### Fixed — 在 PDF 中查看

- **点了跳转，译文层还盖在原 PDF 上面.** The reading layer covers the whole
  reader area, so "jumping to the PDF" left the user looking at the translation
  with the PDF hidden behind it — read as "跳转没反应". The layer is now hidden
  first, and a **← 返回译文** pill appears so the reading position is not lost.
  `返回 PDF` in the bilingual bar does the same and remembers where to come back
  to (page, paragraph and scroll offset).
- **失败也当成成功，还存了页码.** `jumpToAndReport` updated and saved `page`
  regardless of whether the reader had scrolled, so the stored reading position
  drifted to a page the user never saw. A jump is now recorded only after it is
  verified, and a failure reports the reason
  (`未能定位到第 N 页：阅读器没有响应跳转请求（当前停在第 M 页）`).
- **成功与否靠函数返回值判断.** `jumpToPage` now returns a structured
  `{ok, level, page, via, reason}` and confirms against the viewer's own state
  (`currentPageNumber`, `reader.state.pageIndex`) with a short poll, instead of
  trusting that a call returning means a scroll happened.
- **只有页码时假装定位到了区域.** Paragraphs and figures have coordinates, so the
  jump aims at their box (`convertToViewportRectangle` → scroll a quarter down the
  viewport). When only the page can be reached it says so
  (`已定位到第 N 页（未能精确到该区域）`) instead of implying a highlight.
- 段落定位不再重复跳两次（原实现在 `jumpToSegment` 里既调 `jumpTo` 又调
  `jumpToPage`）。

### Changed — 界面

- **窄侧边栏里"双语/术语"被拆成两行字.** 那两枚按钮用的是 26px 见方的图标样式，
  两个汉字塞进去就竖着断了行，标题栏看起来像一堆散落的字。文字型按钮现在按内容
  自适应宽度、不换行；"PaperLoom" 也不会被压断。
- **侧边栏窄到底部一行时，「发送」会被挤出面板、完全点不到**（280px 实测，
  按钮右边缘超出面板 47px）。输入框下方两行现在都会换行，「发送」始终贴右。
- 附图缩略图 78px、说明输入框同宽（原来 66px 会把占位文字截断）。
- 阅读视图排版：正文行高 1.66、页标记改为吸顶细分隔线、图表卡片加阴影与
  悬停反馈、图片加载改为柔光 shimmer 而不是像报错的文字。
- 侧边栏：统一设计令牌（暖中性色 + 深绿强调色、三级阴影、等宽字体令牌）、
  键盘可见的 `:focus-visible` 焦点环、细滚动条、按钮 hover/active/disabled
  状态补齐（禁用时不再是"灰一下"，主按钮保持可辨识）。
- 底部状态栏新增**服务健康圆点**（绿/黄/红 + 悬停说明），一眼看出"为什么按钮
  没反应"。
- 对话气泡改为带阴影的圆角卡片，角色标签更轻。

### Fixed — 中文输入法误发送

- **用中文输入法按 Enter 选词会直接把半句话发出去.** The composer's `onKeyDown`
  never checked `isComposing`, so the Enter that confirms an IME candidate was
  treated as "send". `src/composer.ts` now decides with three signals because no
  single one is reliable across the Gecko builds Zotero ships: the standard
  `isComposing`, the deprecated-but-necessary `keyCode === 229`, and our own
  `compositionstart`/`compositionend` tracking (cleared on a timeout, because the
  confirming keydown can arrive *after* `compositionend` in the same tick).
  Shift+Enter still inserts a newline; Ctrl/Cmd/Alt+Enter is left to the browser.

### Fixed — 设置页测试连接

- **刚填的 Base URL 和 API Key 没有参与测试.** `/v1/settings/test` accepted only a
  model, so a URL or key the user had just typed was ignored: the panel said
  "连接成功" for the *saved* configuration. The endpoint now takes
  `{model, baseUrl, apiKey}` and builds a throwaway client, and the panel sends
  what is on screen. Nothing is saved by testing.
- **留空 Key 的规则说不清楚.** The field now states it: blank means "use the saved
  key", a typed key is used **for this test only**, and only 保存 writes it. The
  result line also says which key was used.
- **测试成功却不能接着保存.** A successful test now offers 「保存当前配置」.
- **密钥可能泄漏到错误文本里.** Error messages are scrubbed
  (`Authorization: Bearer ***`, `x-api-key: ***`, `sk-***`) before they reach the UI
  or the log, and a typed key is never echoed back.
- 测试结果现在写明**测试的模型、耗时、使用的地址**，以及失败时的错误码。

### Fixed — 翻译入口

- **「页码…」在 Zotero 里点了没反应.** It called `window.prompt()`, which is not
  reliably available on Zotero's main window; when it threw, the `catch` treated
  the exception as "user cancelled", so nothing happened and nothing was
  explained. Replaced with an in-sidebar dialog (`TranslateDialog`) that behaves
  the same in a tab, an embedded reader and a separate window.
- **页码范围只有一句"格式无效".** `src/pages.ts` now names the offending
  fragment (`无法识别的页码片段「abc」`), rejects reversed ranges and page 0, caps
  absurd numbers, accepts full-width commas and dashes, de-duplicates and sorts.
  The dialog also checks the range against the paper's page count.
- **排队/解析/翻译/完成/失败/取消看不出来.** Added `JobBanner`: each state names
  itself with a colour (已排队 / 正在解析 / 正在翻译 N/M 段 · 第 K 页 / 翻译完成 +
  cost / 翻译失败 + reason / 已取消 / 翻译中断), and a finished job offers
  「查看译文」directly.
- **禁用按钮不说原因.** `translationBlockedReason()` explains why the three
  translate buttons are unavailable (扫描件需 OCR / 正在翻译 / 服务未连接) instead of
  just greying them out; the same text is the button tooltip.
- **已有译文时不知道该点哪个.** A partial-translation card offers the three
  genuinely different intents: 查看译文 (read what exists), 继续翻译 (only the
  missing segments), 重译全文 (redo everything — explicitly flagged as costing
  money again).



### Fixed — 模型选择

- **切换问答模型没有任何效果.** The picker called `setModel`, which only updated
  local UI state; `ask()` never put `model` in the request body, so every
  question ran on `settings.chat_model` while the sidebar displayed the chosen
  one. `ask` now snapshots `state.model` at send time and sends it, which also
  means changing the picker mid-answer cannot swap the model under a running
  stream.
- **选择在重启后丢失.** The pick is saved to the Zotero preference
  `extensions.paperloom.chatModel` and restored on startup, but only while the
  service still offers that model — a retired id falls back to the configured
  default instead of breaking every question.
- **未知模型会变成一个看不懂的上游报错.** `SUPPORTED_MODELS` is now one constant
  used by `/v1/settings`, chat, analysis and translation jobs, so the picker and
  the validator cannot drift apart. An unknown id returns
  `400 unknown_model` naming the available models; `/v1/settings` refuses to
  save one, and clearing a model field keeps the previous value instead of
  storing `""`.
- 问答、翻译、分析现在各自的模型来源是明确的：问答用用户选择（默认取
  `chat_model`）、翻译用 `translate_model`、分析用 `analysis_model`。侧边栏的
  下拉框只影响提问，标题与通知都写明了这一点；回答头部显示**实际**使用的模型
  （`done` 事件回传，服务端回退时会与所选不同）。

### Added — 对话图片输入

- **只能靠"给图表加注释"把图片塞进提问。** 直接在输入框里粘贴截图毫无反应（
  剪贴板里是文件项，不是文字），看起来就像剪贴板坏了。现在可以从三个入口附图：
  **粘贴、选择文件、图表注释**，三者的规矩完全一样。
- 每张图有缩略图、移除按钮和**可选的说明**——说明会随图片一起送给模型，
  否则"图 2 有什么区别"里的编号就失效了。
- 规则集中在 `plugin/src/attachments.ts`（而不是散在 React 组件里）：仅
  **PNG/JPEG/WebP**，单张 **2.5MB**、合计 **6MB**、最多 **4 张**。每种拒绝都写清
  楚限制与支持的格式——"静默丢弃"和"模型没看图"在界面上长得一模一样。
- **不能读图的模型会在发请求之前就拦下来。** `vision` 来自服务的模型列表
  （`/v1/settings`），插件不再自己维护一份会过期的能力表；`deepseek-v4-pro`
  无视觉能力，以前发过去会得到一个像服务故障的上游报错。图表注释同样走这个检查。
- **图片在重开论文后还在**：随用户消息一起存库并随会话恢复，不会变成
  "一个关于空气的问题"。
- 只有图片、没有文字也可以发送（自动补一句默认问法），因为"这是什么"配一张
  图本来就是正常问法。

### Fixed — 论文图片显示

- **旋转页面裁到了错误的位置.** pdfium 渲染时会把页面转正，所以带 `/Rotate 90`
  的页面出来的位图是"竖"的，而 bbox 来自 pdfminer（忽略旋转，仍用未旋转坐标系）。
  旧代码按"所有页面都是正的"去映射。它**不会报错**，而是裁出一个看起来合理的
  矩形——图变成了页面上另一条不相干的带子。四种旋转现在分别处理；映射是**对着
  真实渲染量出来的**，不是纸上推的（我第一版 270° 把上下写反了，测试抓住了）。
- 每种旋转两个测试，因为一个不够：标记必须落在裁切结果**内部**，
  而裁切空白区域必须**保持空白**。只"大致接近"的变换能过第一个、过不了第二个。
- **两条渲染路径都失败时只说"本页无法渲染"。** 现在分别说明是哪条路径失败，并给出
  「重试」——两条路径的原因完全不同（服务不可达 vs. 阅读器不交位图），
  用户能据此做点事情。阅读器回退路径仍然**拒绝**旋转页面：它的坐标会以同样的
  方式出错，说出来比画一个像样的谎话好。
- **点击图表直接跳 PDF。** 现在先打开**高清放大**（按 2400px 重新渲染该区域，
  不是把栏宽缩略图放大——图看不清通常是因为渲染得小，不是因为屏幕小），
  浮层不改变阅读位置，Esc 或点击外部关闭，高清渲染失败时降级显示缩略图。

### Fixed — 未接通的功能（审计）

- **分析面板点「停止」后转圈不停.** 中止 fetch 抛的是 `AbortError`，
  而 `catch` 特意忽略了它，于是 `status` 一直停在 `streaming`。中止不再被当成错误，
  但它仍然是一个**结束**：现在会置为 `cancelled`，并用 `finally` 兜底把残留的
  `streaming` 收尾（服务重启、连接断掉也一样）。
- **对话消息卡在"生成中"** 同理：流没有 `done` 事件就结束时，消息永远保持
  streaming、发送按钮一直禁用，只能重开阅读器。中止路径现在会收尾，
  并保留已经收到的文字。
- **同一批页面被翻译两次、也计费两次.** 双击、或 `withService` 在响应丢失后的重试，
  会两次调用创建接口。`/v1/jobs` 现在带 `attach_existing=True`，
  管理器发现**同一请求**（页序无关，`None` 只匹配 `None`）正在排队/运行时直接返回
  那个任务。**不同**的页集合在服务端仍然允许（翻第 5 页和翻 1-3 页同时进行是合理的），
  但客户端会明确拒绝并说明原因，而不是悄悄换掉任务。

### Tests

- `plugin/test/attachments.test.mjs` (21) — format/size/count limits, duplicate
  paste, base64 byte accounting, and that the file picker advertises exactly the
  formats the validator accepts.
- `service/tests/test_chat_images.py` (13) — image validation (non-data URL,
  unsupported format, oversized), the vision-capability gate, the legacy single
  `image` path, and that a question keeps its image across a reload.
- `service/tests/test_job_idempotency.py` (7) — the guard is exercised in a single
  tick, which is the real double-click window (the fake LLM finishes instantly, so
  going through HTTP could not reproduce it).
- `service/tests/test_render.py` (+7) — one marker crop and one blank crop per
  rotation (0/90/180/270), plus a whole rotated page.
- `plugin/test/pages.test.mjs` (8) — range parsing: `1-3,5`, full-width commas and
  dashes, de-duplication, blank = whole paper, and the error cases that would
  otherwise translate the wrong pages.
- `plugin/test/composer.test.mjs` (8) — Enter vs. IME confirmation, Shift+Enter,
  modifier combinations, and that English typing still sends after a composition.
- `plugin/test/jump.test.mjs` (7) — the jump contract, including
  "a navigate that resolves without moving is not a success".
- `plugin/test/model.test.mjs` (7) — model selection rule.
- `service/tests/test_settings_test.py` (10) — the connection test uses the typed
  URL/key, saves nothing, rejects a bad URL and an unknown model, and never
  echoes the key (plus the redaction helper).

## [0.2.2] - 2026-11-18

### Fixed

- **「在 PDF 中查看」点了没反应.** `jumpToPage` tried `reader.navigate()` first.
  That call only posts a message to the reader iframe, so it never throws — the
  function hit `return true` on the first attempt and the pdf.js branch
  underneath it was unreachable. The sidebar then recorded the new page and
  looked successful while the PDF had not moved. The order is now:
  pdf.js `pdfViewer.currentPageNumber` (synchronous, and the same viewer the
  page renderer uses) → `getPageView().div.scrollIntoView()` → the documented
  `reader.navigate()`, awaited. `jumpToPage` returns whether the scroll actually
  happened, so "无从定位" is reported instead of silently ignored.
- **图片位置是空白，既没有图也没有提示.** `<img>` had no `onError`, so an image
  the reader refused to load (blocked `blob:` URL under the reader iframe's CSP,
  truncated response) left an empty box: `failed` stayed `false`, so the user got
  neither the picture nor the 「回到 PDF 查看」button. Crops are now passed as
  `data:` URLs, which the reader always allows, and a load failure falls back to
  the visible button. The jump result is also surfaced in the sidebar notice.
- `jumpToSegment` no longer double-jumps when the target page is already shown.

### Tests

- `plugin/test/jump.test.mjs` (5 cases) pins the strategy order: pdf.js is used
  and `reader.navigate` is never reached when pdf.js works; a refused page falls
  back to `scrollIntoView`; an async `navigate` is awaited; and a reader with no
  usable API reports failure instead of pretending. Wired into
  `npm run test:unit` and `scripts/check.ps1`.

## [0.2.1] - 2026-11-18

### Fixed

- **翻译直接报错，原因却是服务已经不在了.** Reading a paper with several
  figures made the local service **disappear**. The log stopped mid-request
  (three concurrent `GET …/page/N.png` at the same second, then nothing), the
  port was left with only `TIME_WAIT` sockets, and stderr contained **no
  traceback** — the signature of a native crash, not a Python exception.
  `pypdfium2` is not thread-safe, and FastAPI runs every `def` endpoint on a
  worker thread, so a page with several figures entered pdfium concurrently.
  Reproduced by firing 17 concurrent page renders: a mix of 500s, then the
  process gone. Rendering is now serialized behind one module-level lock, and
  17 concurrent renders all return 200 with the service still alive.
- **The error message blamed the wrong thing.** With the service gone, `fetch`
  rejects with an opaque `TypeError`. The client's port was cached from the last
  successful `/health`, so the plugin reported
  "NetworkError when attempting to fetch resource" for every action instead of
  naming the real cause. `fetch` is now wrapped: a connection failure becomes
  `本地服务无响应。请确认 PaperLoom 服务正在运行…`.
- **The plugin now recovers on its own.** A `service_down` error triggers one
  `ServiceManager.ensure()` (ping → re-discover → respawn) and a single retry
  before the error is shown, so a service that died no longer needs Zotero to be
  reopened.
- A render failure now returns `500 render_failed` with a message and
  `retryable: true` instead of a bare `Internal Server Error`.

### Changed

- Rendered pages and crops are cached (24 entries, keyed by file stamp, page,
  width and bbox). Re-rendering the same figure — which the sidebar does on
  every refresh — now costs nothing: a second pass over all 17 pages of a paper
  took 0.07 s instead of 1.22 s.

### Tests

- `test_concurrent_renders_do_not_crash_pdfium` and
  `test_identical_requests_are_served_from_the_cache` reproduce the crash and
  pin the cache. 180 service tests, 17 plugin tests, ruff clean.

## [0.2.0] - 2026-11-19

Reading view gets both fixes it needed: every paragraph is a complete sentence,
and figures are actually drawn inside Zotero.

### Fixed

- **一段话被切成两三段.** pdfminer occasionally emits two objects for one
  visual line. On page 2 of E-RayZer it produced
  `E-RayZer operates directly in 3D space,` (x 58.5–233.07) and
  `learning self-` (x 239.09–294.75) — both at `y = 401.84` — which became two
  separate paragraphs, the second starting with a lowercase word. A line on the
  same baseline whose start is at or after the previous line's end is now
  treated as the rest of that line (`continuation`), and is excluded from the
  column-edge measurement that decides paragraph ends.
- **段落跨栏被截断.** A paragraph that ran from the bottom of the left column
  to the top of the right column (`…We highlight key conclusions` at y 78.85,
  then `and summarize our contributions as follows:` at y 707.89) was never
  joined. Cross-column merges are now allowed when both lines are body-size and
  either the previous line ends with a hyphen or it ends with an open sentence
  and fills at least 86% of the column width.
- **算式把句子劈成两段.** `"…as self-supervision:"` / `[equation]` /
  `"where Percep denotes …"` used to become two paragraphs, so the second one
  was translated as a fragment that starts with a lowercase word. A continuation
  is now looked for past the interrupting block; a colon counts as an opening
  tail because it is what introduces a display equation.
- **小节标签插在句子中间.** `"…results of E-RayZer"` / `"Datasets."` /
  `"trained on both …"` — a run-in label laid out as its own block between the
  two halves of a sentence. The label is lifted out of the flow and the sentence
  rejoined, which fixes the case where the second half started lowercase.
- **句子被打断后另一半以大写开头.** When an equation or a picture sits inside a
  sentence, the rest often starts with a capital or a bracket
  (`"… of target views"` / `"(Itgt) to render …"`), so the "starts lowercase"
  test alone missed it. A paragraph that stops at a function word
  (`… are conducted on`), after a comma, or after more than 120 characters
  without punctuation is now recognised as unfinished.
- **`E-RayZer` 变成 `E- RayZer`.** The joiner inserted a space after any
  trailing hyphen. A hyphen at a line break now never adds a space when the next
  fragment starts with a capital letter, so compound names survive while
  hyphenation is still repaired.
- **正文被判成表格单元后整段消失.** `_looks_like_table_cell` treated any short
  line containing a digit as table furniture, so
  `supervised 3D reconstruction. Concretely, E-RayZer pre-` was classified
  `table` and hidden. Cells are now rejected when they contain punctuation
  *between* words followed by lowercase, or when they carry more than six
  tokens; `pre-` counts as a word when the digit rule is applied.
- **`(cid:N)` 残片被当成正文.** pdfminer prints glyphs it cannot map as
  `(cid:1)`, and those runs became one-line paragraphs
  (`tgt )(cid:1).`, `ψ ), and rendering (f rend`). They are now typed as
  formulas, as are short bracket-riddled runs with no sentence punctuation.
- **表格列头混进正文.** `Self-supervised?`, `Percep. Encoder [7]`,
  `Pose-sup. Baseline` were shown as paragraphs. A short line with no ordinary
  lowercase word is now a table cell even when it contains an abbreviation.
- **标题吞掉下一段.** Merging checked only the incoming line's font size, so
  `1. Introduction` (12 pt) absorbed `Pre-training with self-supervision…`
  (10 pt). Both sides are now measured against the body size.
- **跨栏合并后的框覆盖整页.** The overlay rectangle of a merged cross-column
  block was the union of both columns. It is now anchored to the column that
  holds most of the text.
- **图片显示不了.** Figures were cropped in the plugin with pdf.js, which does
  not work inside Zotero's reader iframe, so every figure fell back to
  "图片需要回到 PDF 查看". Cropping moved to the service: `pypdfium2` renders the
  page and `Pillow` cuts the region.

Measured on E-RayZer (17 pages, 444 segments), before → after:

| Metric | Before | After |
| --- | --- | --- |
| Prose segments | 130 | **86** |
| Median prose length | 245 chars | **337 chars** |
| Paragraphs starting lowercase | 28 | **2** |
| Paragraphs not ending a sentence | 35 | **9** |

The two remaining lowercase starts and most of the nine are reading-order
defects (a figure or a table column extracted out of order), not merge failures.

### Added

- `GET /v1/documents/{document_id}/page/{page}.png?width=&bbox=` — renders a
  page (or a crop of it) as PNG, `Cache-Control: private, max-age=3600`.
  Returns 400 `bad_bbox` / `render_failed`, 503 `render_unavailable` when
  `pypdfium2` is missing.
- `capabilities.render.available`, surfaced in the 自检 panel as
  **页面渲染（图片裁切）**.
- `service/paperloom_service/pdf/render.py` (`render_available`,
  `render_page_png`, `parse_bbox`).
- 10 layout tests (`tests/test_layout.py`) built from the real coordinates
  above, and 6 rendering tests (`tests/test_render.py`) that skip when
  `pypdfium2` / `Pillow` are absent. They also pin the equation split, the
  run-in label and the `(cid:N)` debris.

### Changed

- `PARSER_VERSION` is now `8`. Re-parsing keeps existing translations by
  matching source text, so bumping it no longer discards your work. Expect fewer
  reused translations after this one — paragraphs were merged, so their source
  text changed.
- New service dependencies: `pypdfium2`, `pillow`.

## [0.1.9] - 2026-11-18

### Fixed

- **Controls off-screen in a narrow reader pane.** The sidebar used a fixed
  `min-width: 300px` and the saved width as-is, so when the reader pane was
  narrower than the saved width its left edge went past the viewport — the
  leftmost controls (tabs, the first items in a row) simply could not be
  clicked. The width is now clamped to `min(var(--pl-width), 100vw)` and the
  reading layer uses the same clamp, so the two never disagree.
- **`--pl-width` never reached the sidebar.** The variable was set on `<body>`,
  but the host element is a child of `<html>` and custom properties only inherit
  downwards: `var(--pl-width, 380px)` silently fell back to 380px, so the saved
  width did nothing and the reading layer's right offset stopped matching the
  sidebar. It is now set on `<html>` and `<body>` both.
- Every control re-declares `pointer-events: auto`. `.pl-root` is
  `pointer-events: none` so empty space still forwards clicks to the PDF, and
  nothing underneath an element with `pointer-events: none` is hit-testable
  unless it opts back in — a wrapper change could otherwise leave buttons
  visible but dead.

### Added

- **全部按钮可点击** self-test step. It hit-tests the centre of every control in
  the sidebar (descending into shadow roots) and names the element that
  intercepted it, e.g. `双语 被 DIV#cover-test 遮挡`. Verified by injecting a
  transparent covering layer: all 14 controls were reported, then cleared when
  the layer was removed.

## [0.1.8] - 2026-11-18

### Fixed

- **A transparent layer could cover the sidebar.** `.pl-sidebar` had
  `z-index: auto` while the reading layer had `z-index: 6`, so wherever the two
  overlapped the reading view painted on top — the fields below it looked
  covered by invisible glass and could not be clicked. The sidebar is now
  explicitly above it, and the composer sits in its own layer inside the sidebar.
- The host element is appended to `<html>` instead of `<body>`, and carries its
  hit-testing properties inline (`position`, `inset`, `pointer-events`,
  `z-index: 2147483647`). If Zotero's reader puts a stacking context or a
  higher-specificity rule on `<body>`, a large `z-index` inside it would be
  confined to that context and could still be covered by a sibling.
- Clicking a text field now focuses the field itself, not just the reader
  iframe: `iframeWindow.focus()` makes the document eligible for keys but does
  not move the caret into the input.

### Added

- `ui/probe.ts` and two new self-test steps — **输入框可点击** and **阅读器键盘焦点**.
  The first walks `elementFromPoint` down through shadow roots and names the
  element that actually receives the pointer, so "有一层东西挡住" becomes a
  concrete element name instead of a guess. The second reports whether the
  reader document owns the keyboard.

## [0.1.7] - 2026-11-18

### Fixed

- **The question box could not be typed into inside Zotero.** The textarea's
  value came straight from the shared store, so every keystroke depended on the
  store echoing the new text back. When that round trip did not return — which
  is what happens in the reader iframe — React restored the value it last saw
  and the box behaved like it was read-only. The draft is now owned locally and
  mirrored into the store, so typing sticks whether or not the echo arrives, and
  the send button is driven by the same local value. Verified by deliberately
  breaking the echo in the harness: text still types, Enter still sends.
- Text fields explicitly take keyboard focus from the reader iframe
  (`-moz-user-focus: normal`, plus a capture-phase `pointerdown` on the sidebar
  that calls `iframeWindow.focus()`). In Zotero the sidebar lives inside that
  iframe; if the main window keeps focus, clicks land but keys go to the item
  list instead.
- The first click and the first keystroke in the sidebar are logged once each.
  Together with the service request log this answers the only question that
  matters when a button "does nothing": did the event arrive at all?

## [0.1.6] - 2026-11-18

### Added

- **"运行自检" in the settings panel.** It calls exactly what the buttons call
  and prints a pass/fail line for each: local service, instance token, API key,
  paper parsing, translation status, the chat stream (SSE), and page rendering.
  A feature that "does nothing" now says which step fails and why, instead of
  leaving the user to guess.
- Plugin diagnostics reach disk. The sidebar runs inside the reader iframe,
  where `Zotero.debug` does not exist — so `debug()` silently produced nothing
  and a failed click left no trace anywhere. Lines are now buffered (visible in
  设置) and shipped to `POST /v1/client-log`, which appends them to
  `<dataDir>/logs/plugin.log` with rotation.
- The service logs every request (`GET /v1/status -> 200 (7ms)`) and every
  rejected token. That is the only way to tell "the button did nothing" from
  "the request never arrived".

### Fixed

- 论文对比 no longer requires selecting papers in the Zotero main window: when
  nothing is selected it falls back to the papers already registered (each was
  parsed when it was opened once). The old behaviour — silently refusing with a
  one-line error — is what "对比用不了" looked like.
- The error banner has a close button. It used to stay on screen for the rest
  of the session after a single failure.
- Uncaught errors and unhandled rejections inside the reader iframe are recorded
  instead of disappearing.

### Verified

- 162 service tests (5 new for the log endpoint and request logging), 17 plugin
  tests, `ruff` clean. The self-test was exercised against the live service: all
  seven steps pass on a healthy install.

## [0.1.5] - 2026-11-18

### Added

- **Figures and tables are shown in the reading view.** A paper about image
  generation is unreadable without its pictures, and the Markdown view had
  silently dropped them. The service now finds the area each caption refers to
  (`figure` segments, `PARSER_VERSION` 6) and the plugin cuts that region out of
  the rendered page, so the reader sees the real picture — exact colours, axes,
  sub-labels — between the caption and the surrounding text.
- Region detection absorbs a table cell by cell instead of stopping at the first
  row, prefers the tighter of the two candidate sides (stacked tables used to
  steal each other's body), and refuses anything ambiguous: no text inside the
  region, no crop thinner than 55pt, none covering more than 80% of the page.

### Changed

- The reading view fills the sidebar. A centred 78-character column left a dead
  strip on both sides; long paragraphs also wrapped more than the width allowed.
- `SIDEBAR_MAX_WIDTH` is 960px instead of 620px, in the CSS and in the drag
  clamp, so a wide screen can actually be used for reading.

### Fixed

- Prose that merely mentions a table ("Table 1 shows results of …") was typed as
  a caption and printed at caption size. A caption now needs a separator right
  after the label.
- `97/96 段已译`: the two numbers were counted over different sets (references
  keep translations). Both are now counted over the same segments, and pictures
  are excluded.

### Verified

- 157 service tests (up from 150, including 7 for figure regions) and 17 plugin
  tests (including `pageRect` mapping). On the 21-page sample paper 10 of 13
  captions get a crop; every one was rendered to PNG and inspected.

## [0.1.4] - 2026-11-18

### Changed

- **The sidebar now shows a reading view instead of a layout replica.** Every
  paragraph is printed as the English original followed by the Chinese
  translation, in normal document flow. Re-creating the PDF layout inside a
  narrow sidebar was fragile (text had to be squeezed into boxes designed for a
  different column width) and it is not how anyone reads. The page-accurate view
  is still available behind the `版式` toggle.
- Markdown is the single output format: the sidebar, `复制 Markdown` and
  `存为笔记` all use the same server-side renderer, so what is exported is
  exactly what was read.

### Added

- `paperloom_service/markdown.py` and `GET /v1/documents/{id}/markdown`:
  renders a translated paper as Markdown — H1 is the paper's own title,
  `##`/`###` come from section numbers, paragraphs are English / blank line /
  Chinese, `<!-- pN -->` marks page boundaries, references are optional.
- Sidebar: copy the Markdown to the clipboard, or save it as a Zotero note
  attached to the item (saving again overwrites the same note instead of
  piling up duplicates).
- `scripts/export_markdown.py`: export a registered paper to a `.md` file from
  the command line.
- Translations survive re-parsing: when the parser version changes (or
  `重新解析` is used) translations are matched back by their source text, so a
  free segmentation improvement no longer destroys paid translations. The
  response reports how many were kept (`keptTranslations`).

### Fixed

- Author affiliations above the abstract (`2 Zhipu AI`, `1 Tsinghua
  University`) matched the section-number pattern and appeared as fake chapters.
  Short segments before the abstract on page 1 are now `meta`.
- The H1 was the Zotero attachment title (`Zheng 等 - 2024 - CogView3`)
  followed by the real title. The paper's own title is used, once.
- Figure captions and equation fragments that start with a number
  (`1024 (bottom). All prompts …`, `0 + σtϵ, t, ctext)`) were headings. Section
  headings now require a small section number followed by a capitalised word,
  and bibliographic-looking text never qualifies.
- Reference entries (`1. Achiam, J., …`) are classified as `reference` even
  when they look like numbered headings.

### Verified

- 150 service tests (up from 136) and 13 plugin tests; a live job on a 21-page
  paper: 99/99 segments, 37.7k characters of Markdown, 4 030 English words,
  6 045 Chinese characters, 18 headings — all of them real section headings.

## [0.1.3] - 2026-11-17

### Fixed

- **Translation quality: paragraphs are now real paragraphs.** Three defects
  combined to make every translation a fragment:
  - rotated margin stamps (the arXiv/Elsevier download marker) were never
    filtered, because the rotation lives on each glyph's matrix while the code
    checked the text line's matrix — which is empty. The stamp's single
    characters were emitted one per line, interleaved between body lines, so
    they both broke paragraph merging and got glued onto sentence ends
    ("… in terms of computational 1").
  - paragraph continuation was compared against the *first* line of the group,
    so the next paragraph's indented first line was accepted as a continuation
    and paragraphs merged into one another.
  - end-of-line hyphens were always removed, turning `text-` + `to-image` into
    `textto-image` and destroying the very terms these papers are about. They
    are now resolved with the document's own vocabulary (and compound
    continuations such as `state-of-the-` are recognised), with a second repair
    pass over the merged text.
- Display type (titles, section headings) is merged on size and spacing instead
  of left-edge alignment, so a wrapped title is one segment instead of two
  fragments ("CogView3: Finer and Faster Text-to-Image" + "Generation via
  Relay Diffusion" previously translated as a garbled half-sentence).
- Reference lists, display equations, table cells and figure labels are no
  longer sent to the translator: a `References` heading switches the section to
  `reference`, `=`-style fragments become `formula`, and runs of terse cells
  become `table`. This removes garbage output and most of the wasted tokens.
- Segmentation changes are versioned (`PARSER_VERSION`); a document parsed by an
  older version is rebuilt transparently and the sidebar says so.

### Changed

- Translation prompt rewritten for completeness, term consistency, academic
  register, and for reconstructing words broken across lines. Each batch now
  receives the paper title and the previous paragraph as read-only context.
- Model output is validated (`too_short` / `no_chinese` / `untranslated` /
  `truncated`) and retried per segment, so a lazy or truncated answer no longer
  replaces a paragraph with a two-word "translation".
- `is_translatable()` is the single rule shared by the job pipeline and the
  translation-status endpoint; fragments shorter than 12 characters are skipped.
- Prompt version bumped to 3, so existing translations are reported as outdated
  and can be refreshed with one click.

### Added

- `scripts/check_segmentation.py` (paragraph/merge quality report),
  `scripts/check_translation_quality.py` (runs a real job and prints
  source/translation pairs with quality flags), `scripts/preview_overlay_png.py`
  (renders the bilingual view to a PNG offline) and `scripts/overlay_layout.py`
  (the shared text-fitting rules).

### Fixed (bilingual overlay rendering)

- **A cross-page paragraph produced a page-sized box.** Merging a paragraph that
  continues onto the next page mixed the coordinates of both pages, so the box
  covered the whole sheet and the opaque panel painted over figures and every
  other paragraph. The text is still joined (one complete sentence), but the box
  now stays on the page holding most of it, and any box taller than 70% of the
  page is rejected as a safety net.
- Overlay panels are opaque. At 93% opacity the English showed through and the
  page looked like it had doubled text.
- The translation is now fitted to its box: the largest font size at which the
  whole paragraph fits is chosen (down to 5px), instead of a fixed size that
  clipped the tail of long paragraphs. If nothing fits, the overlay is skipped
  rather than showing a truncated sentence.
- Lines are wrapped with the same rules as the offline preview: Latin words and
  numbers are never split (`C / ogView3`), and closing punctuation never starts
  a line (CJK typesetting rule).
- Text is top-aligned to the paragraph start instead of floating in the middle
  of the box.

## [0.1.2] - 2026-11-17

### Added

- Image-preserving bilingual view: the real PDF page is rendered with the
  reader's pdf.js instance and translated paragraphs are placed on their
  original bounding boxes, so figures, formulas, tables and layout survive.
  Dual mode shows original and translated pages side by side (stacked in narrow
  sidebars); clicking a paragraph jumps to and highlights it in the PDF.
- Translation status is tracked per generation (model / base URL / prompt
  version / glossary / output limit / document hash); stale translations are
  reported and can be re-translated by an explicit action.
- Layout status is tracked separately from text translation
  (`succeeded` / `failed` / `missing` / `skipped`) and shown in the sidebar.
- `GET /v1/documents/{id}/translation-status` and `babeldoc_timeout` setting.
- `scripts/verify_live.py`, `scripts/check_overlay.py` and
  `scripts/preview_overlay.py` for live-API and overlay verification.
- Plugin unit tests for the overlay geometry, wired into CI.

### Changed

- Base URL handling is centralized: the chat endpoint, the OpenAI-compatible
  `/v1` base used by BabelDOC and the status message now agree, and pasted
  endpoint URLs are normalized instead of producing `/v1/v1`.
- Reading state writes accumulate instead of overwriting, are serialized to
  prevent stale writes, survive sidebar teardown, and are validated on restore.
- Python discovery runs each candidate interpreter, requires 3.10+ and skips the
  Microsoft Store alias; a failed start now reports the service's own `--check`
  output instead of a bare timeout.

### Fixed

- BabelDOC subprocess: one deadline covering output draining, process-tree kill
  on timeout/cancel/shutdown, per-job output directory, artifact validation,
  key redaction in logs and deletion of the temporary config file.
- Uppercase `[[SEG:…]]` citation markers bypassed validation and leaked into
  answers.
- Author/affiliation lines and single-character fragments were sent for
  translation; they are now classified as `meta` / `noise`.
- `selection` could never be cleared, and invalid page/sidebar values were
  accepted by the reading-state endpoint.

## [0.1.1] - 2026-11-17

### Added

- Figure/formula annotation questions can send the captured image to
  `deepseek-flash` (vision) as a Data URL; falls back to captions and nearby
  text with an explicit note when Zotero exposes no image data.
- Translation artifacts (BabelDOC mono/dual PDF) are verified (`%PDF-` header)
  and imported as Zotero child attachments; duplicates are skipped.
- Per-conversation model selector, token/cost display, glossary injection into
  Q&A prompts, page-range translation input, and "save whole conversation" notes.
- Reading state now persists the current selection, and the last analysis is
  restored when reopening a paper.

### Changed

- Service version and `/v1/status` report `llm=live|fake` for honest demo mode.
- Narrow reader windows collapse the bilingual view to a single column.

## [0.1.0] - 2026-11-17

### Added

- Repository skeleton: plugin/service split, JSON schemas, CI workflows, docs.
- Zotero plugin (TypeScript + React, esbuild) with `bootstrap.js` lifecycle,
  reader sidebar, selection popup actions, note creation and page jump.
- Local FastAPI service with SQLite storage, FTS5 search, instance-token auth,
  SSE streaming, DeepSeek client with retry/backoff and cancel support.
- PDF paragraph extraction and paragraph-level alignment between source and
  translation; scanned-PDF detection.
- Translation job pipeline with caching, progress, cancellation and resume.
- Contextual chat (selection / section / whole paper) with citation markers.
- Glossary management (paper-local and global).
- Research analysis templates: reading card, experiment, novelty, limitations,
  comparison, presentation outline.
- Reading state and conversation persistence keyed by library/item/attachment
  and file hash.
- Windows packaging scripts and release workflow producing XPI + service zip.

### Known limitations

- BabelDOC/pdf2zh-next is optional and must be installed separately (AGPL-3.0);
  layout-preserving PDF output is unavailable until it is installed.
- Paragraph alignment is text-block level, not glyph level. Cross-column
  paragraphs may be merged; the UI reports the actual alignment quality.
- Image-internal text is not re-rendered (figure images are kept as-is).
- Real DeepSeek calls were not exercised in CI or in the development environment
  (no API key); the protocol is covered by a fake LLM transport.
- Interactive UI flows in Zotero require manual acceptance; plugin startup and
  registration were verified on Zotero 10.0.8.
