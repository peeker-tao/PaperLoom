# Troubleshooting

## The service does not start

1. Open **Tools → PaperLoom Settings → Service → Show diagnostics**.
2. The sidebar already shows the reason: the plugin runs the candidate
   interpreter itself, requires Python 3.10+, and on failure calls
   `python -m paperloom_service --check` to surface the real cause (for example
   `No module named paperloom_service`).
3. Check the service log at `%APPDATA%\PaperLoom\logs\service.log`.
4. Verify Python:
   ```powershell
   python --version
   python -c "import fastapi, pydantic, pdfminer; print('ok')"
   python -m paperloom_service --check
   ```
5. Start the service manually to see the error:
   ```powershell
   cd service
   python -m paperloom_service --port 23124
   ```

### "No module named paperloom_service"

The interpreter found on PATH is not the one with the dependencies. Either run
`scripts\install_service.ps1` (creates `.venv` and installs the service) or set
`extensions.paperloom.pythonPath` to `.venv\Scripts\python.exe`.

### The Store alias opens the Microsoft Store

`%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe` is a stub, not an
interpreter. PaperLoom skips `WindowsApps` directories and validates every
candidate by running it, so this alias is never launched.

### Port already in use

PaperLoom probes ports 23124-23140 and remembers the chosen port in
`%APPDATA%\PaperLoom\service.json`. If another program occupies the port, the
probe moves on automatically. A stale `service.json` is detected by the
`/health` version check and rewritten.

### Token mismatch (HTTP 401)

The instance token lives in `%APPDATA%\PaperLoom\token`. Deleting it while the
service runs causes 401s: stop the service and let the plugin regenerate it.

## DeepSeek errors

| Symptom | Meaning | Action |
| --- | --- | --- |
| `401` / `AuthenticationError` | key invalid or revoked | re-enter the key in settings |
| `402` / `Insufficient Balance` | account balance exhausted | top up |
| `429` / `RateLimit` | request rate too high | lower concurrency/QPS |
| `context_length_exceeded` | selection + context too large | switch context scope to "selection" |
| stream ends with `finish_reason=length` | output truncated | raise max output tokens |

All retries use exponential backoff with jitter and are capped (default 3).
Cancelling a request aborts the HTTP stream; retries are not performed for
user-cancelled requests.

## Translation produces empty or identical text

- `deepseek-flash` runs in *thinking* mode by default. PaperLoom explicitly
  disables thinking for translation requests. If you typed a custom model name,
  make sure it supports `chat/completions` with `thinking: {"type": "disabled"}`.
- Segments shorter than 12 characters are skipped by design, as are display
  equations, table cells, author blocks and reference lists: translating them
  produces invented text rather than information.
- If the whole PDF has almost no extractable text, it is probably a scanned
  document: the job fails with `scanned_pdf` and suggests OCR.

## The translation reads like fragments, not paragraphs

That is a segmentation problem, not a model problem, and 0.1.3 fixes the three
known causes:

1. **Margin stamps** (the arXiv/Elsevier download marker) are set at 90 degrees.
   They used to be emitted one glyph per line and spliced between body lines,
   which both broke paragraph merging and got glued onto sentence ends
   ("… in terms of computational 1"). They are now filtered by inspecting each
   glyph's text matrix.
2. **Indentation**: the next paragraph's indented first line used to be accepted
   as a continuation of the previous paragraph.
3. **End-of-line hyphens** were always removed, turning `text-` + `to-image`
   into `textto-image`. They are now resolved with the document vocabulary.

Inspect a paper without translating anything:

```powershell
python scripts/check_segmentation.py <paper>.pdf
# prose length median=381  prose ends .,!?=78%  leftover hyphens=0 ... RESULT: PASS
```

Then check actual output for a few pages:

```powershell
python scripts/check_translation_quality.py --pdf <paper>.pdf --pages 1-2
```

If a document was parsed by an older version, PaperLoom re-parses it
automatically on the next open and tells you in the sidebar. Translations whose
source text did not change are carried over (the response reports
`keptTranslations`), so you only translate what actually changed.

0.2.0 adds five more causes, all found by reading real coordinates rather than
guessing:

4. **One visual line split into two objects.** pdfminer sometimes emits the left
   and right halves of a line separately; on E-RayZer page 2 that produced
   `…operates directly in 3D space,` and `learning self-` at the same baseline
   (`y = 401.84`), so a paragraph started in the middle of a word.
5. **A paragraph that crosses the column break.** Bottom-of-left-column to
   top-of-right-column has a huge vertical gap, so the two halves were never
   joined.
6. **An equation inside a sentence.** `"…as self-supervision:"` / `[equation]` /
   `"where Percep denotes …"` — anything sitting between two halves of a
   sentence used to separate them for good. The continuation is now searched for
   past the interruption, and a colon counts as an opening tail because it is
   what introduces an equation.
7. **A run-in label laid out in the middle of a sentence.** `"…results of
   E-RayZer"` / `"Datasets."` / `"trained on both …"`. The label is lifted out of
   the flow and the sentence rejoined.
8. **A heading swallowing the next paragraph**, because only the incoming line's
   font size was checked.

Also in 0.2.0: `E-RayZer` no longer becomes `E- RayZer`, `(cid:1)` glyph debris
is no longer printed as a paragraph, and text containing a digit is no longer
mistaken for table furniture (that bug hid whole paragraphs from the reading
view). To confirm on your own PDF:

```powershell
python scripts/check_segmentation.py <paper>.pdf
# prose length median=337  prose ends .,!?=60%  leftover hyphens=0
```
A high share of prose segments starting with a lowercase letter is the tell-tale
sign of an unmerged continuation. On E-RayZer it went from 28 of 130 paragraphs
to 2 of 86, and the median paragraph from 245 to 337 characters.

A short line that ends a sentence is a legitimate paragraph end even if the next
line is indented — the parser deliberately does not glue those together.

## 「在 PDF 中查看」没反应

0.2.2 前这是一个真实的 bug，不是环境问题。`jumpToPage` 先调用
`reader.navigate()`——它只是给 reader iframe 发一条消息，**不会抛错**，于是函数在
第一个分支就 `return true`，下面真正管用的 pdf.js 分支从来没被执行到。侧边栏记下了
新页码、看起来成功，PDF 却没动。

现在的顺序是：pdf.js `pdfViewer.currentPageNumber`（同步生效，与图片渲染用的是同一个
viewer）→ `getPageView().div.scrollIntoView()` → 文档化的 `reader.navigate()`
（会 await）。跳转是否真的发生会被检查，失败时侧边栏提示
**「无法自动定位到第 N 页，请在 PDF 中手动翻页」**，不再静默。

如果仍然失败，先在 **设置 → 自检** 里跑一遍，再打开插件日志：

```powershell
Get-Content "$env:APPDATA\PaperLoom\logs\plugin.log" -Tail 30
# 关注 jumpToPage failed / figure image failed to load / figure render via service failed
```

## 图片位置是空白，既没有图也没有提示

0.2.2 前 `<img>` 没有 `onError`：图片被 reader 的 CSP 拦掉（`blob:` URL）或响应被截断时，
`failed` 仍是 `false`，于是既没有图片也没有「回到 PDF 查看」按钮，只剩一块空白。
现在裁切图以 `data:` URL 传递（reader 一定允许），加载失败会退回可点击的按钮。

## 翻译报错「本地服务无响应」

先看服务是否还活着：

```powershell
(Invoke-RestMethod http://127.0.0.1:23151/health).version
```

如果连接被拒，说明进程已退出。0.2.0 以前的一个真实故障是：**读一篇多图论文时，
服务会在中途消失**——日志在同一秒的三条 `GET …/page/N.png` 之后就断了，端口只剩
`TIME_WAIT`，stderr 里没有任何 traceback。这不是 Python 异常，是 pdfium 的段错误：
`pypdfium2` 不是线程安全的，而 FastAPI 会把每个 `def` 端点放到线程池里，一页上的
几张图就会同时进入 pdfium。

0.2.1 起渲染被一把模块级锁串行化，并缓存了已渲染的页/裁切。判定方法：

```powershell
# 复现：并发请求 17 页；修复前会出现 500 甚至进程消失
foreach ($p in 1..17) {
  Start-Job { Invoke-WebRequest "http://127.0.0.1:23151/v1/documents/<id>/page/$using:p.png" `
    -Headers @{'X-PaperLoom-Token'=(Get-Content "$env:APPDATA\PaperLoom\token")} } | Out-Null
}
(Invoke-RestMethod http://127.0.0.1:23151/health).version   # 仍然要能返回
```

如果服务确实没在跑，重新拉起即可（插件在下次操作时也会自动重启它）：

```powershell
Start-Process -FilePath '<仓库>\.venv\Scripts\python.exe' `
  -ArgumentList '-m','paperloom_service','--port','23151','--data-dir',"$env:APPDATA\PaperLoom" `
  -WindowStyle Hidden
```

排查时更有用的两个位置：`%APPDATA%\PaperLoom\logs\service.log`（每个请求的
`METHOD path -> status`）与插件的 **设置 → 自检**（逐项测试并显示耗时）。

## A figure says "图片需要回到 PDF 查看"

Figure cropping used to run in the plugin with pdf.js, which is not reachable
from the sidebar's iframe inside Zotero, so it always fell back to that text.
Since 0.2.0 the service renders the page instead. Check the capability first:

```powershell
curl -H "X-PaperLoom-Token: $(Get-Content $env:APPDATA\PaperLoom\token)" `
     http://127.0.0.1:23151/v1/status
# capabilities: { "render": { "available": true } }
```

If `available` is `false`, the optional renderer is missing — reinstall the
service dependencies:

```powershell
.\\.venv\\Scripts\\python.exe -m pip install pypdfium2 pillow
```

Then restart the service. The 自检 panel's **页面渲染（图片裁切）** step requests a
real crop and reports the byte count, so you do not have to guess.

Two related behaviours are intentional: only captions that pair with a real
image region get a crop (an algorithm listing or a figure whose region touches
prose is skipped), and tables stay as text in the flow — they are not cropped.

## Where do the translations go when I export?

The sidebar's default view and both export paths use the same server-side
Markdown renderer, so what you read is what you copy:

- `复制 Markdown` puts the whole document on the clipboard;
- `存为笔记` writes it into a Zotero note attached to the item (saving again
  overwrites that note instead of creating duplicates);
- `scripts/export_markdown.py --document-id <id> --out paper.md` writes a file
  without opening Zotero (the service must be running).

Options: `--original` / `--translation` (default: both), `--no-pages` to drop
the `<!-- pN -->` markers, `--references` to include the bibliography (skipped
by default because translating a reference list helps nobody). The sidebar's
reading view shows figure crops inline, but the exported Markdown is text only —
no image files are written, so equations and tables remain PDF-only.

## The Markdown has no Chinese

The document is not translated yet, or the translation is stale
(`/v1/documents/{id}/translation-status` reports `missing` / `stale`).

## Bilingual view says "alignment: page"

Paragraph merging failed for that page (common with two-column layouts or
equation-heavy pages). The UI still lets you jump to the page, but the
paragraph-level highlight is unavailable. Install BabelDOC for a
layout-preserving PDF, or translate page ranges separately.

## The layout (overlay) view falls back to plain text

The sidebar opens in the reading view (English paragraph, then Chinese). The
`版式` button switches to the page-accurate overlay, which renders the real page
bitmap and anchors translations to their original boxes. That view falls back to
the text columns when:

- the page is **rotated** — a plain scale + y-flip cannot reproduce pdf.js's
  rotation matrix, so the overlay would land on the wrong text;
- pdf.js does not finish rendering within 8 seconds (the task is cancelled
  instead of leaving the view hanging);
- `PDFViewerApplication.pdfDocument` is not ready yet — switch pages and back,
  or reopen the reader.

The underlying translations are unaffected: the text layout always works.

The footer also shows the layout PDF status independently of the translation:
`无排版引擎` means BabelDOC is not installed (optional, AGPL-3.0),
`排版PDF失败` means it ran and failed (the message is in the tooltip).

## Zotero does not show the sidebar

- Confirm the plugin version in **Tools → Add-ons** matches `manifest.json`.
- Open **Help → Debug Output Logging → View Output** and look for
  `PaperLoom:` lines.
- Zotero 10 changed several internal APIs; PaperLoom targets
  `strict_max_version: 10.0.*`. On a newer major version the plugin is disabled
  until updated.
