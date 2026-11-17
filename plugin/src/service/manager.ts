import { debug, errorText } from "../log";
import type { Endpoint } from "./client";
import { ServiceClient, ServiceError } from "./client";

const PORT_RANGE_START = 23124;
const PORT_RANGE_END = 23140;
const API_VERSION = 1;

export function dataDirectory(): string {
  try {
    const appData = Services.dirsvc.get("AppData", Ci.nsIFile);
    return PathUtils.join(appData.path, "PaperLoom");
  } catch {
    const home = Services.dirsvc.get("Home", Ci.nsIFile);
    return PathUtils.join(home.path, ".paperloom");
  }
}

function tokenPath(dir: string): string {
  return PathUtils.join(dir, "token");
}

async function readToken(dir: string): Promise<string | null> {
  try {
    const value = await IOUtils.readUTF8(tokenPath(dir));
    return value.trim() || null;
  } catch {
    return null;
  }
}

async function pathExists(path: string): Promise<boolean> {
  try {
    return await IOUtils.exists(path);
  } catch {
    return false;
  }
}

export class ServiceManager {
  readonly dataDir = dataDirectory();
  readonly client: ServiceClient;
  endpoint: Endpoint | null = null;
  status: any = null;
  lastError = "";
  private starting: Promise<void> | null = null;
  private childProcess: any = null;
  private childPid = 0;

  constructor(private readonly prefs: { get(key: string, fallback: unknown): unknown }) {
    this.client = new ServiceClient(() => this.endpoint);
  }

  async ensure(): Promise<Endpoint> {
    if (this.endpoint && (await this.ping(this.endpoint.baseUrl))) {
      return this.endpoint;
    }
    this.endpoint = null;
    if (this.starting) {
      await this.starting.catch(() => undefined);
      if (this.endpoint) {
        return this.endpoint;
      }
    }
    this.starting = this.bootstrap();
    try {
      await this.starting;
    } finally {
      this.starting = null;
    }
    if (!this.endpoint) {
      throw new ServiceError(this.lastError || "本地服务不可用", 0, "service_down", true);
    }
    return this.endpoint;
  }

  private async bootstrap(): Promise<void> {
    this.lastError = "";
    // 1. A previously recorded instance.
    const recorded = await this.readServiceFile();
    if (recorded?.port && (await this.tryUse(recorded.port))) {
      return;
    }
    // 2. Any PaperLoom instance in the default range (handles restarts).
    for (let port = PORT_RANGE_START; port <= PORT_RANGE_END; port += 1) {
      if (await this.tryUse(port, false)) {
        return;
      }
    }
    // 3. Start our own.
    const autoStart = this.prefs.get("extensions.paperloom.autoStart", true) !== false;
    if (!autoStart) {
      this.lastError = "本地服务未运行，且已关闭自动启动";
      return;
    }
    await this.spawn();
  }

  private async tryUse(port: number, record = true): Promise<boolean> {
    const baseUrl = `http://127.0.0.1:${port}`;
    if (!(await this.ping(baseUrl))) {
      return false;
    }
    const token = await readToken(this.dataDir);
    if (!token) {
      this.lastError = `发现端口 ${port} 上的 PaperLoom 服务，但缺少实例令牌文件`;
      return false;
    }
    try {
      const response = await fetch(`${baseUrl}/v1/status`, {
        headers: { "X-PaperLoom-Token": token },
        signal: AbortSignal.timeout(3000),
      });
      if (!response.ok) {
        this.lastError = response.status === 401 ? "实例令牌不匹配，请重启服务" : `服务状态异常 (${response.status})`;
        return false;
      }
      const status = await response.json();
      if (status.apiVersion !== API_VERSION) {
        this.lastError = `服务接口版本 ${status.apiVersion} 与插件 (${API_VERSION}) 不兼容，请升级组件`;
        return false;
      }
      this.endpoint = { baseUrl, token };
      this.status = status;
      if (record) {
        this.rememberPort(port);
      }
      debug("using service on", baseUrl, "version", status.version);
      return true;
    } catch (error) {
      this.lastError = `连接服务失败：${errorText(error)}`;
      return false;
    }
  }

  private async ping(baseUrl: string): Promise<boolean> {
    try {
      const response = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(1200) });
      if (!response.ok) {
        return false;
      }
      const body = await response.json();
      return body?.service === "paperloom";
    } catch {
      return false;
    }
  }

  private async readServiceFile(): Promise<{ port?: number } | null> {
    try {
      const raw = await IOUtils.readUTF8(PathUtils.join(this.dataDir, "service.json"));
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  private rememberPort(port: number): void {
    try {
      (this.prefs as any).set?.("extensions.paperloom.servicePort", port);
    } catch {
      // Prefs are best-effort; discovery still works without them.
    }
  }

  private async spawn(): Promise<void> {
    const python = await findPython(this.prefs);
    if (!python) {
      this.lastError =
        "未找到 Python。请安装 Python 3.10+ 并执行 `pip install -e service`，" +
        "或在 Zotero 设置 extensions.paperloom.pythonPath 中填写 python.exe 的绝对路径。";
      return;
    }
    const port = await this.firstFreePort();
    if (!port) {
      this.lastError = `端口 ${PORT_RANGE_START}-${PORT_RANGE_END} 均被占用`;
      return;
    }
    const args = [
      "-m",
      "paperloom_service",
      "--port",
      String(port),
      "--data-dir",
      this.dataDir,
    ];
    debug("spawning service", python, args.join(" "));
    try {
      if (!(await pathExists(PathUtils.join(this.dataDir)))) {
        await IOUtils.makeDirectory(this.dataDir, { ignoreExisting: true });
      }
      this.childProcess = launchProcess(python, args);
      this.childPid = this.childProcess?.pid || 0;
    } catch (error) {
      this.lastError = `启动本地服务失败：${errorText(error)}`;
      return;
    }
    const deadline = Date.now() + 30000;
    let delay = 250;
    while (Date.now() < deadline) {
      await sleep(delay);
      delay = Math.min(1500, delay + 150);
      if (await this.tryUse(port, false)) {
        this.rememberPort(port);
        return;
      }
    }
    this.lastError =
      `本地服务在 30 秒内未就绪。请查看日志 ${PathUtils.join(this.dataDir, "logs", "service.log")}` +
      "，或手动运行 `python -m paperloom_service --check`。";
  }

  private async firstFreePort(): Promise<number | null> {
    for (let port = PORT_RANGE_START; port <= PORT_RANGE_END; port += 1) {
      if (!(await this.ping(`http://127.0.0.1:${port}`))) {
        // A non-PaperLoom listener would also answer, so confirm "no listener"
        // by attempting a real request and requiring a transport error.
        const free = await looksFree(port);
        if (free) {
          return port;
        }
      }
    }
    return null;
  }

  async restart(): Promise<void> {
    try {
      if (this.childProcess && typeof this.childProcess.kill === "function") {
        this.childProcess.kill();
      }
    } catch {
      // Process already exited.
    }
    this.childProcess = null;
    this.endpoint = null;
    this.status = null;
    await this.ensure();
  }

  async refreshStatus(): Promise<void> {
    try {
      this.status = await this.client.status();
    } catch (error) {
      this.lastError = errorText(error);
    }
  }

  /** Stop only the process this plugin spawned; discovered instances keep running. */
  shutdown(): void {
    try {
      this.childProcess?.kill?.();
    } catch {
      // Already exited.
    }
    this.childProcess = null;
    this.endpoint = null;
  }

  get pid(): number {
    return this.childPid;
  }
}

function launchProcess(command: string, args: string[]): any {
  try {
    const file = Cc["@mozilla.org/file/local;1"].createInstance(Ci.nsIFile);
    file.initWithPath(command);
    const process = Cc["@mozilla.org/process/util;1"].createInstance(Ci.nsIProcess);
    process.init(file);
    process.runw(false, args, args.length);
    return { pid: process.pid, kill: () => process.kill() };
  } catch (error) {
    debug("nsIProcess failed, falling back to Subprocess", errorText(error));
    const { Subprocess } = ChromeUtils.importESModule(
      "resource://gre/modules/Subprocess.sys.mjs",
    );
    let child: any = null;
    Subprocess.call({ command, arguments: args }).then((proc: any) => {
      child = proc;
    });
    return {
      get pid() {
        return child?.pid || 0;
      },
      kill: () => child?.kill?.(),
    };
  }
}

async function looksFree(port: number): Promise<boolean> {
  try {
    await fetch(`http://127.0.0.1:${port}/`, { signal: AbortSignal.timeout(400) });
    return false;
  } catch {
    return true;
  }
}

async function findPython(prefs: { get(key: string, fallback: unknown): unknown }): Promise<string | null> {
  const configured = String(prefs.get("extensions.paperloom.pythonPath", "") || "").trim();
  if (configured) {
    return (await pathExists(configured)) ? configured : null;
  }
  const exe = Services.appinfo.OS === "WINNT" ? "python.exe" : "python3";
  const candidates: string[] = [];
  const pathVar = safeEnv("PATH");
  for (const dir of pathVar.split(Services.appinfo.OS === "WINNT" ? ";" : ":")) {
    if (dir.trim()) {
      candidates.push(PathUtils.join(dir.trim(), exe));
    }
  }
  const known = [
    safeEnv("LOCALAPPDATA") && PathUtils.join(safeEnv("LOCALAPPDATA"), "Programs", "Python"),
    safeEnv("USERPROFILE") && PathUtils.join(safeEnv("USERPROFILE"), "miniconda3", exe),
    safeEnv("USERPROFILE") && PathUtils.join(safeEnv("USERPROFILE"), "anaconda3", exe),
    "C:\\ProgramData\\miniconda3\\python.exe",
    "C:\\Python312\\python.exe",
    "C:\\Python311\\python.exe",
    "C:\\Python310\\python.exe",
  ].filter(Boolean) as string[];
  candidates.push(...known);
  for (const candidate of candidates) {
    if (candidate.endsWith(".exe") && (await pathExists(candidate))) {
      return candidate;
    }
  }
  // Directory scan of Python installs (LOCALAPPDATA\Programs\Python\Python3xx).
  const pythonRoot = safeEnv("LOCALAPPDATA")
    ? PathUtils.join(safeEnv("LOCALAPPDATA"), "Programs", "Python")
    : "";
  if (pythonRoot && (await pathExists(pythonRoot))) {
    try {
      const children = await IOUtils.getChildren(pythonRoot);
      for (const child of children.reverse()) {
        const candidate = PathUtils.join(child, "python.exe");
        if (await pathExists(candidate)) {
          return candidate;
        }
      }
    } catch {
      // Ignore listing failures.
    }
  }
  return null;
}

function safeEnv(name: string): string {
  try {
    return Services.env.get(name) || "";
  } catch {
    return "";
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
