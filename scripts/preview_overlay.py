"""Generate a standalone HTML preview of the bilingual page-overlay view.

It renders a real PDF page with pdf.js and draws the real translations on top,
using the same geometry rules as ``plugin/src/ui/overlay.ts``. Useful for
visual QA without launching Zotero.

Open the generated file in a normal desktop browser. The PDF is inlined as a
data URL, so ``file://`` works; pdf.js itself is loaded from a CDN (network
required). Note that VS Code's integrated browser cannot complete a pdf.js
canvas render, so the page stays blank there — that is an environment limit,
not a bug in PaperLoom.

Usage:
    python scripts/preview_overlay.py --document-id <id> --page 1
    # writes <tmp>/paperloom-preview/index.html and prints the path
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import sqlite3
import sys
import tempfile
import urllib.request
from pathlib import Path

HEADERS: dict[str, str] = {}
MIN_W, MIN_H = 16.0, 6.0


def api(base: str, path: str) -> dict:
    request = urllib.request.Request(f"{base}{path}", headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def local_pdf_path(document_id: str) -> str:
    for candidate in (
        Path(os.environ.get("APPDATA", "")) / "PaperLoom" / "paperloom.sqlite",
        Path.home() / ".local" / "share" / "PaperLoom" / "paperloom.sqlite",
    ):
        if not candidate.is_file():
            continue
        with sqlite3.connect(candidate) as conn:
            row = conn.execute(
                "SELECT pdf_path FROM documents WHERE id=?", (document_id,)
            ).fetchone()
            if row and row[0]:
                return str(row[0])
    return ""


def build_html(document: dict, segments: list[dict], pdf_bytes: bytes, page: int) -> str:
    page_segments = [s for s in segments if int(s["page"]) == page and s.get("translation")]
    payload = [
        {
            "id": s["id"],
            "kind": s["kind"],
            "bbox": s["bbox"],
            "text": s["text"],
            "translation": s["translation"],
        }
        for s in page_segments
    ]
    title = html.escape(document.get("title", ""))
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>PaperLoom 双语页面预览 · {title}</title>
<style>
  :root {{ --pl-accent: #2d6a4f; --pl-accent-weak: #e3efe8; --pl-border: #e2e0d8; --pl-muted: #6b746e; }}
  body {{ margin: 0; font-family: "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif;
         background: #f4f2ec; color: #14181b; }}
  header {{ padding: 10px 18px; background: #fff; border-bottom: 1px solid var(--pl-border); }}
  h1 {{ font-size: 15px; margin: 0 0 4px; }}
  .hint {{ font-size: 12px; color: var(--pl-muted); }}
  .stage {{ display: flex; gap: 18px; padding: 16px; align-items: flex-start; }}
  .col {{ flex: 1; min-width: 0; }}
  .col-head {{ font-size: 11px; letter-spacing: .6px; color: var(--pl-muted);
               text-transform: uppercase; margin-bottom: 6px; }}
  .frame {{ position: relative; overflow: hidden; background: #fff; border: 1px solid var(--pl-border);
            border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .frame img, .frame canvas {{ display: block; width: 100%; height: 100%; }}
  .pl-seg-overlay {{ position: absolute; display: block; margin: 0; padding: 0 1px; overflow: hidden;
      border: 0; border-radius: 2px; text-align: left; cursor: pointer; color: #14181b;
      background: rgba(253,252,248,.93); box-shadow: 0 0 0 1px rgba(45,106,79,.14);
      word-break: break-word; white-space: normal; font-family: inherit; }}
  .pl-seg-overlay:hover {{ background: #fff; box-shadow: 0 0 0 1px var(--pl-accent); z-index: 3; }}
  .pl-seg-overlay.highlight {{ background: var(--pl-accent-weak); box-shadow: 0 0 0 2px var(--pl-accent); }}
  .pl-seg-box {{ position: absolute; border-radius: 2px; pointer-events: none; }}
  .pl-seg-box.highlight {{ background: rgba(45,106,79,.16); box-shadow: 0 0 0 2px var(--pl-accent); }}
  #status {{ padding: 8px 18px; font-size: 12px; color: var(--pl-muted); }}
</style></head>
<body>
<header>
  <h1>{title} · 第 {page} 页</h1>
  <div class="hint">左：原文页面位图　右：译文按原坐标叠放（悬停查看全文，点击查看定位效果）</div>
</header>
<div class="stage">
  <div class="col"><div class="col-head">原文</div><div class="frame" id="left"></div></div>
  <div class="col"><div class="col-head">译文 · 保留版式</div><div class="frame" id="right"></div></div>
</div>
<div id="status">loading pdf.js…</div>
<script type="module">
const PAGE = {page};
const SEGMENTS = {json.dumps(payload, ensure_ascii=False)};
const MIN_W = {MIN_W}, MIN_H = {MIN_H};
const status = document.getElementById('status');

function overlayBox(bbox, image) {{
  if (!(bbox && bbox.length >= 4)) return null;
  const [x0, y0, x1, y1] = bbox.map((v) => Number(v) || 0);
  if (!(x1 > x0) || !(y1 > y0)) return null;
  const ratio = image.width / image.pageWidth;
  const w = (x1 - x0) * ratio, h = (y1 - y0) * ratio;
  if (w < MIN_W || h < MIN_H) return null;
  const left = x0 * ratio, top = (image.pageHeight - y1) * ratio;
  if (left < -1 || top < -1) return null;
  return {{ left, top, width: w, height: h,
           fontSize: Math.max(5.5, Math.min(14, h * 0.62)), lineHeight: 1.16 }};
}}

(async () => {{
  try {{
    const pdfjs = await import('https://cdn.jsdelivr.net/npm/pdfjs-dist@4.6.82/build/pdf.min.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc =
      'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.6.82/build/pdf.worker.min.mjs';
    const raw = atob('{base64.b64encode(pdf_bytes).decode("ascii")}');
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
    const doc = await pdfjs.getDocument({{ data: bytes, isEvalSupported: false }}).promise;
    const pdfPage = await doc.getPage(PAGE);
    const base = pdfPage.getViewport({{ scale: 1 }});
    const columnWidth = Math.max(220, Math.floor((window.innerWidth - 60) / 2));
    const scale = columnWidth / base.width;
    const viewport = pdfPage.getViewport({{ scale }});
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    const hi = pdfPage.getViewport({{ scale: scale * ratio }});

    const make = (container) => {{
      const canvas = document.createElement('canvas');
      canvas.width = hi.width; canvas.height = hi.height;
      canvas.style.width = viewport.width + 'px';
      canvas.style.height = viewport.height + 'px';
      container.style.width = viewport.width + 'px';
      container.style.height = viewport.height + 'px';
      container.appendChild(canvas);
      return canvas;
    }};
    const leftCanvas = make(document.getElementById('left'));
    await pdfPage.render({{ canvasContext: leftCanvas.getContext('2d'), viewport: hi }}).promise;
    const right = document.getElementById('right');
    const rightCanvas = make(right);
    await pdfPage.render({{ canvasContext: rightCanvas.getContext('2d'), viewport: hi }}).promise;

    const image = {{ width: viewport.width, height: viewport.height,
                    pageWidth: base.width, pageHeight: base.height }};
    let drawn = 0, skipped = 0;
    for (const segment of SEGMENTS) {{
      const box = overlayBox(segment.bbox, image);
      if (!box) {{ skipped += 1; continue; }}
      const button = document.createElement('button');
      button.className = 'pl-seg-overlay';
      button.style.left = box.left + 'px'; button.style.top = box.top + 'px';
      button.style.width = box.width + 'px'; button.style.height = box.height + 'px';
      button.style.fontSize = box.fontSize + 'px'; button.style.lineHeight = String(box.lineHeight);
      button.textContent = segment.translation;
      button.title = segment.translation;
      button.onclick = () => {{
        document.querySelectorAll('.pl-seg-box').forEach((n) => n.remove());
        const left = document.getElementById('left');
        const box2 = document.createElement('div');
        box2.className = 'pl-seg-box highlight';
        box2.style.left = box.left + 'px'; box2.style.top = box.top + 'px';
        box2.style.width = box.width + 'px'; box2.style.height = box.height + 'px';
        left.appendChild(box2);
      }};
      right.appendChild(button);
      drawn += 1;
    }}
    status.textContent = `已渲染 ${{drawn}} 个译文叠层，跳过 ${{skipped}} 个（过小/旋转/无译文）· 页面 ${{Math.round(base.width)}}x${{Math.round(base.height)}}pt`;
    document.title = `OK ${{drawn}}/${{SEGMENTS.length}}`;
  }} catch (error) {{
    status.textContent = 'FAILED: ' + error.message;
    document.title = 'FAIL: ' + error.message;
  }}
}})();
</script>
</body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--port", type=int, default=23151)
    parser.add_argument("--token", default="")
    parser.add_argument("--pdf", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    if args.token:
        HEADERS["X-PaperLoom-Token"] = args.token

    document = api(base, f"/v1/documents/{args.document_id}")["document"]
    segments = api(base, f"/v1/documents/{args.document_id}/segments")["segments"]
    pdf_path = Path(args.pdf or local_pdf_path(args.document_id))
    if not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    out_dir = Path(args.out or Path(tempfile.gettempdir()) / "paperloom-preview")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "index.html"
    target.write_text(
        build_html(document, segments, pdf_path.read_bytes(), args.page), encoding="utf-8"
    )
    translated = sum(1 for s in segments if s.get("translation"))
    print(f"document={document['id']} pages={document['pages']} translated={translated}")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
