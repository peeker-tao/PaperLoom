# 测试记录

环境：Windows 11 · Zotero **10.0.8**（Firefox 140 ESR，`D:\app\zetero`）·
Python **3.14.6**（本地）· Node 24.19 / npm 11.17 · DeepSeek Key：**未配置**。

## 自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest service/tests -q
# 32 passed in 1.92s

cd plugin
node node_modules/typescript/bin/tsc --noEmit   # 通过
node esbuild.config.mjs                          # content/plugin.js 223 KB, content/prefs.js 15 KB
```

覆盖内容：

| 测试 | 结果 |
| --- | --- |
| 鉴权（缺失/错误令牌、Bearer） | ✅ |
| 文档注册、重复注册缓存、非法路径 | ✅ |
| PDF 段落合并、双栏阅读顺序、扫描件识别 | ✅ |
| 翻译任务（假 LLM）：进度、事件回放、产物、段落译文 | ✅ |
| 取消/重试/中断恢复语义 | ✅ |
| SSE 问答：delta、引用校验、消息持久化 | ✅ |
| 六种分析模板（card/experiment/novelty/limitations/compare/outline） | ✅ |
| 术语 CRUD、阅读状态、FTS5 检索 | ✅ |
| 上下文范围（选区/章节/整篇）与未知引用剔除 | ✅ |
| 加密存储不回显明文密钥 | ✅ |

> 测试通过 `PAPERLOOM_FAKE_LLM=1` 使用本地假 LLM，**不会访问网络**，也不需要 API Key。

## Zotero 实测

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| 插件在 Zotero 10.0.8 加载 | ✅ | `%APPDATA%\PaperLoom\plugin-startup.json` 写入 `zotero: 10.0.8` |
| 扩展注册状态 | ✅ | `extensions.json`: `active=true, userDisabled=false` |
| 生命周期 startup/shutdown 清理 | ✅（代码路径） | 卸载/禁用时注销 reader 监听、卸载 React 根、移除菜单项 |
| XPI 结构与路径 | ✅ | `manifest.json` 位于压缩包根，`content/plugin.js` 可被 bootstrap 加载 |
| 侧边栏、选区弹窗、双语视图的实际鼠标交互 | ⚠️ 未完成自动化 | 当前会话的 GUI 自动化被系统反复最小化，需人工确认 |
| DeepSeek 真实调用（连接/翻译/流式追问） | ⚠️ 未验证 | 环境中无 `DEEPSEEK_API_KEY`；已用假 LLM 覆盖协议与错误路径 |
| BabelDOC 排版 PDF | ⚠️ 未安装 | 未安装时任务成功并记录 `warnings`，界面提示“未安装（可选）” |

### 人工验收步骤（建议）

1. 打开一篇带文本层的英文 PDF，确认右侧出现 PaperLoom 侧边栏。
2. 设置 DeepSeek Key → 测试连接 → 点击“本页”翻译，观察进度与段落译文。
3. 选中一句话 → 弹窗“解释” → 连续追问 → “保存笔记” → 在条目的“笔记”中查看页码链接。
4. 关闭 Zotero 重开，确认页码、侧边栏宽度、对话与译文恢复。
5. 断网或填写错误 Key，确认报错分类正确且可重试。

## 已知限制

- 段落对齐为文本块级；双栏、跨页、公式密集页可能合并过度，界面会显示实际对齐级别。
- 扫描件在翻译前即被拦截（`scanned_pdf`），需要用户先 OCR。
- 图表解释目前基于图注与邻近正文；图片像素不会直接发送（DeepSeek Flash 支持视觉，
  可在后续版本开启 image 上传）。
- 模型返回的用量缺失时标记为估算；价格表可通过 `%APPDATA%\PaperLoom\pricing.json` 更新。
