# 测试记录

环境：Windows 11 · Zotero **10.0.8**（Firefox 140 ESR，`D:\app\zetero`）·
Python **3.14.6**（项目 `.venv`）· Node **24.19.0** / npm **11.17.0**。
真实 DeepSeek 调用已用临时 Key 验证过一次（Key 未写入仓库，见文末安全提示）。

## 自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest service/tests -q
# 180 passed in ~10s

.\\.venv\\Scripts\\python.exe -m ruff check service scripts
# All checks passed!

cd plugin
node node_modules/typescript/bin/tsc --noEmit   # 通过
node test/overlay.test.mjs                      # 17 passed
node esbuild.config.mjs                         # content/plugin.js ~269 KB
```

> 测试通过 `PAPERLOOM_FAKE_LLM=1` 使用本地假 LLM，**不会访问网络**，也不需要 API Key。

### 服务端覆盖（180 项）

| 测试文件 | 覆盖内容 | 结果 |
| --- | --- | --- |
| `test_service.py` | 鉴权、注册/缓存、任务（进度/取消/重试）、SSE 问答、引用校验、六种分析模板、术语、FTS5、按页翻译 | ✅ |
| `test_pdf.py` | 段落合并、双栏阅读顺序、扫描件识别、`meta`/`noise` 分类、coverage 上限、**旋转水印过滤**、**连字符接续（`im-`+`plementing` vs `text-`+`to-image`）**、缩进首行分新段、公式/表格/参考文献分类、**摘要前的机构行不当标题**、`PARSER_VERSION` 记录 | ✅ 15 项 |
| `test_markdown.py` | 英文在前中文在后、Markdown 标题层级、非正文（公式/表格/噪声/机构行）排除、参考文献可选、页面标记为注释、只原文/只译文、未译段落仍显示原文、换行展平、统计与文件名清理、**论文自身标题胜过 Zotero 文件名** | ✅ 11 项 |
| `test_reparse.py` | 重解析按原文保留已付费译文、可显式丢弃 | ✅ 2 项 |
| `test_figures.py` | 图/表区域检测：相邻文本块定界、过窄间隙拒绝、区域内正文拒绝、**表格逐格吸收**、**同页两张表各取自己那一张**、``Table 1 shows …`` 不当题注、图片排在题注之前 | ✅ 7 项 |
| `test_layout.py` | 版面切分回归：**同一行被拆成两个对象后重新拼合**、**跨栏跨页接续**、短行结束段落、标题不吞下一段、跨栏 bbox 只锚定主体列、`E-`+`RayZer` 不加空格、连字符与复合词区分、**公式打断的句子重新接上**、**小节标签不再劈开句子**、**`(cid:N)` 残片判为公式** | ✅ 10 项 |
| `test_render.py` | 页面渲染：整页 PNG、`bbox` 裁切尺寸、畸形 bbox 拒绝、页码越界拒绝、未知文档 404、`capabilities.render` 上报、**8 线程并发渲染不弄崩 pdfium**、**相同请求命中缓存**（缺 `pypdfium2` 时自动跳过） | ✅ 8 项 |
| `test_client_log.py` | 插件日志落盘、需鉴权、单次最多 200 行、成功请求写 `METHOD path -> status`、令牌错误写 401 | ✅ 5 项 |
| `test_babeldoc.py` | 子进程超时/取消/启动失败/退出码/空产物/非法 PDF/密钥脱敏/临时配置清理/参数为列表（无 shell） | ✅ 15 项（假引擎，无需安装 BabelDOC） |
| `test_translation_config.py` | 生成配置身份、过期判定、无出处历史行按需重译 | ✅ |
| `test_urls.py` | Base URL 归一化、`/v1` 只出现一次、粘贴完整端点时的纠正 | ✅ |
| `test_context.py` | 上下文范围（选区/章节/整篇）、未知引用剔除 | ✅ |
| `test_reading.py` | 阅读状态合并、选区清除、非法页码/宽度拒绝、按文档隔离 | ✅ |
| `test_translate.py` | `is_translatable` 统一规则（公式/表格/参考文献/过短片段不译）、译文完整性校验（`too_short`/`no_chinese`/`untranslated`）、上下文注入位置 | ✅ 10 项 |

### 插件侧（17 项）

`plugin/test/overlay.test.mjs` 用 esbuild 打包 `src/ui/overlay.ts` 后由 `node` 运行，
覆盖：x 保留 / y 翻转、随宽度缩放、字号随框高填充且不溢出、过小框拒绝、逆序/畸形 bbox 拒绝、
旋转页拒绝、越界框拒绝、**整页 bbox 拒绝**（跨页合并 bug 的回归）、空译文跳过、
**拉丁词不断行**、**行首禁则标点**、字号收缩到不可行时放弃、`fitPage` 宽高比，
以及 `pageRect` 的图片裁切映射（1:1、缩放、HiDPI、旋转/逆序/空框拒绝）。

`service/tests/test_overlay_layout.py`（4 项）验证 Python 预览与插件规则一致：
同一段译文在同样尺寸下都能放进框、字号收缩与放弃、拉丁词不断、行首无禁则标点。

## 真实 API 验证（DeepSeek）

使用临时 Key（未落盘到仓库）通过 `scripts/verify_live.py` 实测：

| 项目 | 结果 |
| --- | --- |
| `POST /v1/settings/test` 连接测试 | ✅ 680ms |
| 单页翻译任务 | ✅ `succeeded 27/27`，7.3s，1694 prompt / 820 completion token，约 $0.0015 |
| 流式问答 + 引用 | ✅ `[[SEG:…]]` 标记全部通过校验并渲染为可点击引用 |
| 连续追问、会话持久化 | ✅ |
| 阅读状态写入与恢复 | ✅ |
| 翻译时效性（历史 23 段无出处） | ✅ `staleOnly` 任务重译完成，之后 `{total:23, current:23, stale:0}` |

真实调用中发现并修复的问题（已包含在 0.1.2）：

- 大写 `[[SEG:…]]` 标记绕过校验并泄漏到回答中。
- 作者/单位行与单字符碎片被送去翻译（现归为 `meta` / `noise`）。
- 只有标题没有正文的段落导致覆盖率为 0 且不扩段；`coverage` 超过 1.0 未截断。

## 分段质量（译文质量的前提）

同一个 21 页真实论文（CogView3），修复前后对比：

```powershell
.\.venv\Scripts\python.exe scripts\check_segmentation.py "<paper>.pdf"
```

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| 总分段数 | 421 | 370 |
| 可翻译段 | 243（含整页参考文献、表格单元、公式碎片） | 146（prose 58） |
| prose 中位长度 | 56 字符（≈ 单行） | 381 字符（真实段落） |
| 以句末标点结尾的 prose | 43% | 78% |
| 正文之间未合并的断句 | 74 | 2 |
| 残留断词连字符 | 145 | 0 |
| 泄漏的页面水印 | 有（arXiv 编号逐字插入正文） | 0 |

关键原因：① 页边距的 90° 水印逐字符成行、插在正文行之间；② 缩进判断拿"组首行"比较，
导致下一段被当作续行；③ 行尾连字符被一律删除（`text-`+`to-image` → `textto-image`）。
现在水印按**字符矩阵**过滤，连字符依据全文词表判定（复合词保留、断词合并），
并在合并后做一次词表修复。

`RESULT: PASS` 表示：prose 结尾标点 ≥75%、正文断句 ≤15%、无残留断词、无泄漏水印。
（约 22% 的 prose 合法地在公式或分页处被切断——正文围绕公式线性抽取，重排会破坏与
PDF 的位置对应。）

### 真实译文对照

```powershell
.\.venv\Scripts\python.exe scripts\check_translation_quality.py --pdf "<paper>.pdf" --pages 1-4
```

修复前（第 1 页摘要被切成 10 段，逐行翻译）：

```
SRC: Abstract. Recent advancements in text-to-image generative systems
DST: 摘要。近期文本到图像生成系统的进展
SRC: have been largely driven by diffusion models. However, single-stage text-
DST: 在很大程度上由扩散模型推动。然而，单阶段文本-
```

修复后（整段一次翻译，术语与引用完整）：

```
DST: 摘要。近期文本到图像生成系统的进展在很大程度上由扩散模型驱动。然而，单阶段文本到
     图像扩散模型在计算效率和图像细节精修方面仍面临挑战。为解决该问题，我们提出 CogView3，
     一种创新的级联框架，可增强文本到图像扩散的性能。CogView3 是首个在文本到图像生成领域
     实现接力扩散（relay diffusion）的模型……推理时间仅需其约 1/2。
```

同一任务：30 段、3905 prompt / 1581 completion token、约 $0.0031；长度比中位 0.33
（英译中正常范围），无 `too_short` / `no_chinese` 标记。

## Markdown 阅读视图（默认视图）

同一篇 21 页论文整篇翻译后导出（`scripts/export_markdown.py`）：

```powershell
.\.venv\Scripts\python.exe scripts\export_markdown.py --document-id <id> --out cogview3.md
# wrote cogview3.md (37674 chars, 50871 bytes)
#   english words: 4030  chinese chars: 6045  segments: 381
```

标题层级全部为真实章节标题（18 个）：

```
# CogView3: Finer and Faster Text-to-Image Generation via Relay Diffusion
## Introduction
## 2 Background
### 2.1 Text-to-Image Diffusion Models
### 2.2 Relay Diffusion Models
### 2.3 Diffusion Distillation
## 3 Method
...
## 5 Conclusion
## References
```

正文为「英文一段 + 空行 + 中文一段」，可直接渲染成两个段落：

```
Diffusion models, as defined by Ho et al . [8], establish a forward diffusion pr
ocess that gradually adds Gaussian noise to corrupt real data x0 as follows:

由 Ho 等人 [8] 定义的扩散模型建立了一个前向扩散过程，该过程逐步添加高斯噪声以破
坏真实数据 x0，如下所示：
```

页边界用 `<!-- pN -->` 注释标记（渲染时不显示），参考文献默认不导出；
图片/表格不是文本，Markdown 里不出现（阅读视图里则以原页裁切图显示）。

## 图与表的裁切（阅读视图内联显示）

同一篇论文（21 页，页面 413.9 × 615.1 pt）自动检到 **10 个图/表区域**，
全部与题注配对，裁切结果逐张目视核对：

| 题注 | 页码 | 区域 (pt) | 裁切尺寸 | 结果 |
| --- | --- | --- | --- | --- |
| Figure 1 | 2 | 398.8 – 582.7 | 691 × 368 | ✅ 完整首图宫格 |
| Figure 2 | 5 | 177.9 – 412.7 | 691 × 470 | ✅ |
| Figure 3 | 6 | 363.5 – 569.2 | 691 × 412 | ✅ 流水线左右两栏均完整 |
| Table 1 | 10 | 222.0 – 314.6 | 691 × 186 | ✅ 表头与分组线完整 |
| Table 2 | 10 | 67.2 – 179.2 | 691 × 224 | ✅ 与 Table 1 不重叠 |
| Figure 4 | 11 | 341.9 – 472.6 | 691 × 261 | ✅ |
| Figure 5 | 11 | 152.8 – 311.0 | 691 × 316 | ✅ |
| Table 3 | 12 | 89.6 – 218.9 | 691 × 259 | ✅ |
| Figure 8 | 13 | 77.3 – 306.2 | 691 × 458 | ✅ |
| Figure 9 | 14 | 261.3 – 449.7 | 702 × 377 | ✅ |

未检出的 3 个题注（Fig. 6、Fig. 7、Algorithm 1）故意放弃：它们要么与正文
块交叠、要么是同排子图的小题注，算不准就不裁——错误裁切比没有图更难发现。

裁切使用与插件相同的坐标换算：`scripts` 侧的 pdfium 渲染 ↔ 插件侧
`pageRect()`（`plugin/test/overlay.test.mjs` 覆盖 1:1、缩放、HiDPI、旋转页拒绝）。
阅读视图在 Zotero 内用 pdf.js 渲染同一页，再按区域裁切，不需要额外依赖。

## 真实论文的叠层几何校验

对同一篇 21 页真实论文执行：

```powershell
.\.venv\Scripts\python.exe scripts\check_overlay.py --document-id <id> --token <token>
# PASS: every bbox maps to a valid overlay inside the page
```

结论：所有带译文的段落 bbox 都在页面范围内，按 `scale = 渲染宽度 / 页面宽度` 换算后
不越界、不小于可读尺寸。公式碎片、表格单元与参考文献不参与翻译，
双语视图只叠放已译段落。

`scripts/preview_overlay.py` 可生成同时含原页与译文叠层的独立 HTML，用于人工视觉核对；
注意 VS Code 内置浏览器无法完成 pdf.js 画布渲染（页面空白是该环境限制），
请用桌面浏览器打开。

### 叠层渲染的可视化核对（无需 Zotero、无需浏览器）

```powershell
.\.venv\Scripts\python.exe scripts\preview_overlay_png.py --document-id <id> --pages 1,3
# page 1: 6/13 segments translated, 6 overlays drawn, 0 skipped
# -> %TEMP%\paperloom-preview\page-1.png
```

该脚本用 pdfium 栅格化真实页面，再用与插件**完全相同**的规则
（`scripts/overlay_layout.py` ↔ `plugin/src/ui/overlay.ts`）把译文画进原段落框，
因此图中所见即插件所示。实测（CogView3 第 1/3 页）：

| 检查点 | 结果 |
| --- | --- |
| 英文/作者块/页边水印 | 保持原样，不被译文覆盖 |
| 公式 (1)(2) | 原样保留，未参与翻译 |
| 段落译文 | 填满原段落区域（字号自适应，无裁断） |
| 拉丁词/数字 | 不在词中间断行（`CogView3`、`77.0%` 完整） |
| 行首标点 | 无（行首禁则） |
| 整页白框 | 无（跨页合并 bbox 已修，另有 70% 页高防御） |

真实 API 全文任务：96/99 段、22510 prompt / 7312 completion token、约 $0.0155，
质量标记 0/96 命中。

## Zotero 实测

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| 插件在 Zotero 10.0.8 加载 | ✅ | `%APPDATA%\PaperLoom\plugin-startup.json` 写入 `zotero: 10.0.8` |
| 扩展注册状态 | ✅ | `extensions.json`: `active=true, userDisabled=false` |
| 生命周期 startup/shutdown 清理 | ✅（代码路径） | 注销 reader 监听、卸载 React 根、清理页面位图缓存与定时器 |
| XPI 结构与路径 | ✅ | `manifest.json` 位于压缩包根，`content/plugin.js` 可被 bootstrap 加载 |
| 插件与服务的连接（发现/拉起/重连） | ✅ | 用插件相同的命令行参数实测：`python -m paperloom_service --port … --data-dir …` 启动后写 `service.json` + `token`，`/health` 200 |
| 侧边栏、选区弹窗、叠层视图的实际鼠标交互 | ⚠️ 未完成自动化 | 需要人工点击确认（见下方步骤） |
| 真实 BabelDOC 引擎 | ⚠️ 未安装 | 未安装时任务照常成功，`layout.state = missing`，界面显示“无排版引擎” |

### 人工验收步骤（建议）

1. 打开一篇带文本层的英文 PDF，确认右侧出现 PaperLoom 侧边栏。
2. 设置 DeepSeek Key → 测试连接 → “本页”翻译 → 观察进度与段落译文。
3. 切到“双语”并确认 `版式` 模式：页面图片/公式仍在，译文叠在原文位置，点击段落能回到 PDF 对应页。
4. 选中一句话 → “解释” → 追问 → “保存笔记” → 在条目“笔记”中查看页码链接。
5. 关闭 Zotero 重开，确认页码、侧边栏宽度、对照模式、对话与译文都恢复。
6. 断网或填入错误 Key，确认报错可读、可重试；把 `pythonPath` 指向一个不存在或过旧的解释器，确认提示明确指出原因。

## 关于“测试卡住”

`pytest` 全量运行多次均为 ~9s 完成，未能复现卡死。为便于日后定位：

- `pyproject.toml` 设置 `faulthandler_timeout = 60`，任何一次运行若某测试阻塞超过 60 秒，
  会打印全线程栈，可直接看出阻塞在哪个调用（此前只能看到“无输出”）。
- 子进程类测试（BabelDOC）统一带 `timeout` 与超时后杀进程树，不会有残留进程。

## 已知限制

- 段落对齐为文本块级；双栏、跨页、公式密集页可能合并过度，界面显示实际对齐级别。
- 叠层视图对**旋转页**直接回退为纯文本双栏（简单缩放+翻转无法复现 pdf.js 的旋转矩阵）。
- 若 pdf.js 在 8 秒内未完成渲染，会取消并回退为纯文本双栏，避免界面永久等待。
- 图内文字不重绘（图片原样保留）；需要重绘请安装 BabelDOC。
- 扫描件在翻译前即被拦截（`scanned_pdf`），需要先 OCR。
- 模型返回的用量缺失时标记为估算；价格表可通过 `%APPDATA%\PaperLoom\pricing.json` 更新。

## 安全提示

验证期间使用的 DeepSeek Key 曾出现在对话中。若该 Key 仍在有效期内，建议在
DeepSeek 控制台**轮换/吊销**；本机可通过设置页清空（`POST /v1/settings` 传空 `apiKey`）
以删除 DPAPI 加密保存的 `secret.bin`。
