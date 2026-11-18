# PaperLoom · 文织

> An AI-powered Zotero plugin for bilingual paper reading, contextual conversations,
> and research notes. Powered by DeepSeek.

PaperLoom 在 Zotero 内完成「翻译 → 对照阅读 → 选中提问 → 保存带出处的笔记 → 恢复进度」的完整链路。
界面为浅色紧凑的学术阅读风格：左侧缩略图（复用 Zotero 原生），中间原文/译文对照阅读视图，右侧可收起、可调宽度的 AI 侧边栏。

## 功能状态

| 模块 | 状态 |
| --- | --- |
| Zotero 7–10 插件骨架、生命周期、卸载清理 | ✅ 已实现 |
| 阅读器侧边栏（对话/笔记/分析）、可收起、可调宽 | ✅ 已实现 |
| 选区捕获（文本/公式框选）、解释/提问/存笔记 | ✅ 已实现 |
| PDF 段落抽取、段落级中英对齐、扫描件检测 | ✅ 已实现（段落级，非字形级） |
| 分段质量（过滤页边水印、修复断词、剔除参考文献/公式/表格） | ✅ 已实现（v0.1.3） |
| DeepSeek 翻译任务（进度、取消、重试、缓存、断点） | ✅ 已实现 |
| 流式问答、连续追问、停止生成、引用回跳 | ✅ 已实现 |
| Zotero 子笔记（原文/译文/回答/批注/页码/模型） | ✅ 已实现 |
| 术语表（当前论文 + 全局） | ✅ 已实现 |
| 阅读进度与对话恢复 | ✅ 已实现 |
| 阅读卡片 / 实验 / 创新 / 不足 / 多篇对比 / 汇报提纲 | ✅ 已实现 |
| 中英对照阅读视图（每段英文在上、中文在下，默认视图） | ✅ 已实现（v0.1.4） |
| Markdown 导出（复制到剪贴板 / 存为 Zotero 笔记 / 命令行） | ✅ 已实现（v0.1.4） |
| 保留版式的图文视图（页面位图 + 译文叠放，可切换） | ✅ 已实现（可选视图） |
| 译文时效性（模型/术语/提示词变了会提示重译） | ✅ 已实现 |
| BabelDOC 排版保留 PDF（双语/中文） | ⚙️ 可选依赖，需用户自行安装 |
| 图内文字重绘 | ⛔ 后续版本 |

## 安装

前置条件：**Zotero 7–10** 与 **Python 3.10+**。Windows 服务包只含服务源码与安装脚本，
**不捆绑 Python 运行时**；Zotero 插件会自动探测可用解释器（跳过 Microsoft Store 别名），
也可在设置里手动指定 `extensions.paperloom.pythonPath`。

见 [docs/INSTALL.md](docs/INSTALL.md)。简要步骤：

1. 安装 Python 依赖并启动本地服务（或解压 Windows 服务包后运行
   `scripts\install_service.ps1`）。
2. 在 Zotero 中 `Tools → Add-ons → Install Add-on From File...` 选择 `paperloom-*.xpi`。
3. 打开 **Tools → PaperLoom 设置**，填写 DeepSeek API Key 并点击「测试连接」。

## 开发

```powershell
.\scripts\check.ps1     # 类型检查 + 单元测试 + 构建
.\scripts\build.ps1     # 生成 dist/paperloom-<version>.xpi 与服务包
```

架构说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，开发细节见
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)，故障排查见
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

## 验证状态

- 服务端：**150 项**自动化测试全部通过（假 LLM，无网络）；`ruff check` 通过。
- 插件：TypeScript 严格模式、esbuild 构建通过；叠层几何有 13 项 Node 单元测试；
  已在 **Zotero 10.0.8** 实际加载启动（`%APPDATA%\PaperLoom\plugin-startup.json`）。
- 真实 DeepSeek 调用已验证：连接 680ms；单页翻译 `succeeded 27/27`（7.3s，
  1694 提示 / 820 完成 token，约 $0.0015）；流式问答引用标记通过校验；追问与
  会话持久化正常。
- 真实论文（21 页，CogView3）整篇翻译：`succeeded 99/99`，Markdown 输出 37.7k 字符
  （4030 英文词 / 6045 汉字），18 个标题全部为真实章节标题。
- 真实论文（21 页）分段质量：prose 中位长度 **381 字符**（修复前 56，即单行），
  以句末标点结尾 78%（修复前 43%），正文间未合并断句 2（修复前 74），
  残留断词 0（修复前 145），页边水印泄漏 0。详见 [docs/TESTING.md](docs/TESTING.md)。
- 真实论文叠层几何校验：所有带译文段落的 bbox 均落在页面范围内
  且换算后不越界（`scripts/check_overlay.py` 全部 PASS）。
- 尚未验证：BabelDOC 排版 PDF（本机未安装）、图内文字重绘，以及需要人工鼠标操作的
  侧边栏交互细节。详见 [docs/TESTING.md](docs/TESTING.md)。

## 设计约束

- 仅监听回环地址，使用安装实例令牌认证；API Key 只保存在本机服务配置中。
- 论文正文被视为**不可信内容**，提示词中显式隔离，引用标记经过服务端校验。
- PDF 对齐为**段落级**；无法可靠合并时界面显示实际回退级别（`page`），不假装精确。
- 主阅读视图不复制 PDF 版式：每段英文原文后紧跟中文译文，保持正常文本流。
  这比在窄侧边栏里重建两栏版式更稳（文字不必被塞进按另一种栏宽设计的框里），
  也能一键导出为 Markdown（剪贴板 / Zotero 笔记 / `.md` 文件）。
- 可选的“保留版式”视图渲染真实页面位图并把译文叠在原坐标上，因此图片、公式、
  表格不会被重排丢失；无法渲染（旋转页/超时）时自动回退为纯文本双栏并在界面说明。
- BabelDOC / PDFMathTranslate-next 为 AGPL-3.0，本仓库不捆绑、不再分发，由用户自行安装并以独立进程调用。

## License

MIT（本仓库代码）。第三方依赖见 [LICENSE](LICENSE) 末尾说明。
