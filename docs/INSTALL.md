# 安装与配置

PaperLoom 由两部分组成：**Zotero 插件（XPI）** 与 **本地服务（Python）**。两者都只在你的电脑上运行；
论文、对话和密钥不会上传到 PaperLoom 的服务器（只有显式调用 DeepSeek 的文本会发送给 DeepSeek）。

## 1. 环境要求

| 组件 | 要求 |
| --- | --- |
| Zotero | 7.0 – 10.x（已在 **10.0.8 / Firefox 140 ESR** 实测启动） |
| Python | 3.10+，推荐 3.12 |
| 系统 | Windows 10/11（主要目标）；macOS/Linux 理论可用但未测试 |
| 磁盘 | 服务约 60 MB；翻译产物按论文大小另计 |

## 2. 安装本地服务

### 方式 A：仓库内安装（开发/自用）

```powershell
# 在仓库根目录
.\scripts\install_service.ps1
# 或手动：
python -m venv .venv
.\.venv\Scripts\python -m pip install -e "service[dev]"
```

如果 PowerShell 阻止 `npm`，请使用 `npm.cmd` 或执行
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`。

### 方式 B：解压服务包

从 Release 下载 `paperloom-service-<version>.zip`，解压后在本目录运行：

```powershell
scripts\install_service.ps1                 # 自动建 .venv 并安装
# 或手动：
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

> 服务包**不包含 Python 运行时**，只包含服务源码、`pyproject.toml` 与安装脚本。
> 请先自行安装 Python 3.10+（勾选 “Add python.exe to PATH”）。

### 让 Zotero 找到 Python

插件会依次尝试：设置里的路径 → PATH 中的 `python.exe`（自动跳过 Microsoft Store 的
`WindowsApps` 别名）→ 常见安装目录（`%LOCALAPPDATA%\Programs\Python\*`、conda 等）。
每个候选解释器都会被**实际运行**并校验版本（需 3.10+），不是只看文件是否存在。

若自动探测失败，在 Zotero 的 `about:config`（设置 → 高级）中添加：

```
extensions.paperloom.pythonPath = D:\path\to\python.exe
```

启动失败时侧边栏会直接显示原因（例如 `No module named paperloom_service`），
也可在服务目录手动自检：

```powershell
python -m paperloom_service --check
```

> 服务只监听 `127.0.0.1`，端口从 23124 起自动探测；每次安装生成
> `%APPDATA%\PaperLoom\token` 作为实例令牌。

## 3. 安装插件

1. 打开 Zotero → **工具 → 插件**（Add-ons）。
2. 点击齿轮 → **Install Add-on From File…**，选择 `paperloom-<version>.xpi`。
3. 重启 Zotero（或点击“立即重启”）。

### 开发模式（免打包）

1. 关闭 Zotero。
2. 在 profile 的 `extensions/` 目录创建文件 `paperloom@peeker.dev`，内容为
   `D:\document\PaperLoom\plugin` 的绝对路径（不带引号）。
3. 在 `prefs.js` 中删除 `extensions.lastAppVersion`、`extensions.lastAppBuildId` 行。
4. 以 `-purgecaches` 启动 Zotero。

开发模式与 XPI 二选一，不要同时存在。

## 4. 配置 DeepSeek

打开任意 PDF → 右侧 PaperLoom 侧边栏 → 齿轮 **设置**，或 **工具 → PaperLoom 设置…**。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| Base URL | `https://api.deepseek.com` | 官方 OpenAI 兼容地址 |
| 翻译模型 | `deepseek-flash` | 1M 上下文，支持图片；翻译时关闭思考模式 |
| 问答模型 | `deepseek-flash` | 可改为 `deepseek-v4-pro` |
| 分析模型 | `deepseek-v4-pro` | 推理更强，不支持图片 |
| API Key | 空 | 使用 Windows DPAPI 加密保存在服务目录 |

点击 **测试连接** 验证；错误会按 401 / 402 / 429 / 超时 / 断流分别提示。
也可以用环境变量 `DEEPSEEK_API_KEY` 提供密钥（优先级低于界面配置）。

首次使用：Zotero 侧边栏会显示配置引导；未配置 Key 时如果服务以
`PAPERLOOM_FAKE_LLM=1` 启动，界面会明确标注“演示模式”。

## 5. 可选：排版保留 PDF（BabelDOC）

BabelDOC / PDFMathTranslate-next 采用 **AGPL-3.0**，本仓库不捆绑、不再分发。
需要“保留公式/图表版式的双语 PDF”时自行安装：

```powershell
uv tool install --python 3.12 "BabelDOC==0.7.1"
babeldoc --help
```

建议锁定版本（开发时参考的最新版为 0.7.1）；升级前先确认 PaperLoom 的适配测试。

安装后 PaperLoom 会在翻译任务结束时以独立进程调用它，产物作为额外的
Zotero 附件候选；不安装只影响版式 PDF，不影响到段落级双语阅读。

> 注意：AGPL-3.0 对再分发有传染性要求。若你要把 PaperLoom 与 BabelDOC
> 一起打包分发，请自行评估并遵守其许可证。

## 6. 数据与卸载

| 路径 | 内容 |
| --- | --- |
| `%APPDATA%\PaperLoom\` | 服务配置、加密密钥、SQLite、日志、翻译产物 |
| `%APPDATA%\PaperLoom\token` | 实例令牌（不要分享） |
| `%APPDATA%\PaperLoom\logs\service.log` | 服务日志（不含 API Key） |
| `%APPDATA%\Zotero\...\extensions\` | 插件本体 |

卸载插件不会删除论文库或笔记。要彻底清理，删除 `%APPDATA%\PaperLoom`
目录即可；已保存的 Zotero 笔记会保留。

## 7. 更新

- 插件 `manifest.json` 的 `update_url` 指向仓库根目录的 `updates.json`。
  每次发布需同步更新该文件（`scripts/pack.py` 会生成 `dist/updates.json`）。
- 服务与插件通过 `/health` 的 `apiVersion` 校验兼容性，不匹配时侧边栏会提示升级，
  而不是带着错误继续运行。
