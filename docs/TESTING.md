# 测试记录

环境：Windows 11 · Zotero **10.0.8**（Firefox 140 ESR，`D:\app\zetero`）·
Python **3.14.6**（项目 `.venv`）· Node **24.19.0** / npm **11.17.0**。
真实 DeepSeek 调用已用临时 Key 验证过一次（Key 未写入仓库，见文末安全提示）。

## 自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest service/tests -q
# 118 passed in ~9s

.\.venv\Scripts\python.exe -m ruff check service scripts
# All checks passed!

cd plugin
node node_modules/typescript/bin/tsc --noEmit   # 通过
node test/overlay.test.mjs                      # 8 passed
node esbuild.config.mjs                         # content/plugin.js ~241 KB, content/prefs.js ~15 KB
```

> 测试通过 `PAPERLOOM_FAKE_LLM=1` 使用本地假 LLM，**不会访问网络**，也不需要 API Key。

### 服务端覆盖（118 项）

| 测试文件 | 覆盖内容 | 结果 |
| --- | --- | --- |
| `test_service.py` | 鉴权、注册/缓存、任务（进度/取消/重试）、SSE 问答、引用校验、六种分析模板、术语、FTS5、按页翻译 | ✅ |
| `test_pdf.py` | 段落合并、双栏阅读顺序、扫描件识别、`meta`/`noise` 分类、coverage 上限 | ✅ |
| `test_babeldoc.py` | 子进程超时/取消/启动失败/退出码/空产物/非法 PDF/密钥脱敏/临时配置清理/参数为列表（无 shell） | ✅ 15 项（假引擎，无需安装 BabelDOC） |
| `test_translation_config.py` | 生成配置身份、过期判定、无出处历史行按需重译 | ✅ |
| `test_urls.py` | Base URL 归一化、`/v1` 只出现一次、粘贴完整端点时的纠正 | ✅ |
| `test_context.py` | 上下文范围（选区/章节/整篇）、未知引用剔除 | ✅ |
| `test_reading.py` | 阅读状态合并、选区清除、非法页码/宽度拒绝、按文档隔离 | ✅ |

### 插件侧（8 项）

`plugin/test/overlay.test.mjs` 用 esbuild 打包 `src/ui/overlay.ts` 后由 `node --test` 运行，
覆盖：x 保留 / y 翻转、随宽度缩放、字号随框高、过小框拒绝、逆序/畸形 bbox 拒绝、
旋转页拒绝、越界框拒绝、`fitPage` 保持宽高比。

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

## 真实论文的叠层几何校验

对一篇 21 页、421 段的真实论文（CogView3）执行：

```powershell
.\.venv\Scripts\python.exe scripts\check_overlay.py --document-id <id> --token <token>
# segments per page: min=1 max=97
# kinds: {'title':1,'noise':221,'heading':28,'meta':5,'body':143,'abstract':1,'caption':22}
# translated: 23/421
# PASS: every bbox maps to a valid overlay inside the page
```

结论：所有带译文的段落 bbox 都在页面范围内，按 `scale = 渲染宽度 / 页面宽度` 换算后
不越界、不小于可读尺寸。`noise` 段（公式碎片、行号）不参与翻译，默认在界面隐藏。

`scripts/preview_overlay.py` 可生成同时含原页与译文叠层的独立 HTML，用于人工视觉核对；
注意 VS Code 内置浏览器无法完成 pdf.js 画布渲染（页面空白是该环境限制），
请用桌面浏览器打开。

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
