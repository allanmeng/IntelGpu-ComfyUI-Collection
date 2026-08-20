#!/usr/bin/env python3
"""Generate static pages from Markdown sources.

- index.html  <- README.md   (sorted by repo pushed_at, every repo queried via GitHub API)
- links.html  <- links.md    (same order as source, no sorting)

Usage:
  python generate_pages.py --index [--token GH_TOKEN] [--out-dir DIR]
  python generate_pages.py --links [--out-dir DIR]
  python generate_pages.py --index --links
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

TZ_CN = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def fetch_repo_updated(repo, path, token):
    """Last default-branch commit time for a repo, optionally restricted to a path.

    path=''      -> whole repo (latest commit on default branch)
    path='dir/'  -> latest commit that touched that directory
    Returns ISO string ('' on failure).
    """
    url = "https://api.github.com/repos/%s/commits?per_page=1" % repo
    if path:
        url += "&path=%s" % path
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer %s" % token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and "commit" in data[0]:
                return data[0]["commit"]["committer"]["date"] or ""
            return ""
    except Exception as exc:  # noqa: BLE001
        print("[warn] API query failed for %s%s: %s"
              % (repo, ("/" + path) if path else "", exc), file=sys.stderr)
        return ""


def fmt_cn(iso):
    """'2026-08-21T03:00:00Z' -> '2026/08/21-11:00:00' (UTC+8)."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ_CN)
        return dt.strftime("%Y/%m/%d-%H:%M:%S")
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

URL_RE = re.compile(r"https?://[^\s)\]]+")


def split_sections(md_text):
    """Split markdown into sections starting at '## ' headers."""
    sections = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^##\s+(.*)$", lines[i])
        if m:
            title = m.group(1).strip()
            body = []
            i += 1
            while i < len(lines) and not re.match(r"^##\s+", lines[i]) and lines[i].strip() != "---":
                body.append(lines[i])
                i += 1
            sections.append((title, body))
        else:
            i += 1
    return sections


def clean_name(title):
    """'📖 ComfyUI-XPUSYS-Monitor' -> 'ComfyUI-XPUSYS-Monitor'; drop [fork] suffix."""
    name = re.sub(r"^📖\s*", "", title).strip()
    name = re.sub(r"\s*\[fork\]\s*$", "", name).strip()
    return name


def extract_author(body):
    """Find '作者：[@name](url)' -> (name, url) or None."""
    for line in body:
        m = re.match(r"^\s*作者[：:]\s*\[@([^\]]+)\]\(([^)]+)\)\s*$", line)
        if m:
            return m.group(1), m.group(2)
    return None


def extract_tags(body):
    """Find 'Tag: 官方,fork' -> ['官方', 'fork']."""
    for line in body:
        m = re.match(r"^\s*Tag\s*[：:]\s*(.+?)\s*$", line)
        if m:
            return [t.strip() for t in m.group(1).split(",") if t.strip()]
    return []


def extract_urls(body):
    """Collect (label, url) pairs from body lines: 'label：url' or '| 📄 在线指南 | url |'."""
    pairs = []
    for line in body:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            for cell in cells:
                for u in URL_RE.findall(cell):
                    pairs.append(("", u))
            continue
        m = re.match(r"^([^：:\s][^：:]*?)\s*[：:]\s*(https?://\S+)\s*$", s)
        if m:
            label = m.group(1).strip()
            url = m.group(2).strip().rstrip("，。,")
            pairs.append((label, url))
    return pairs


def repo_from_url(url):
    """Extract 'owner/repo' from a github.com URL ('/tree/...' stripped)."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)", url or "")
    if m:
        return "%s/%s" % (m.group(1), m.group(2))
    return ""


def repo_path_from_url(url):
    """Return (owner/repo, subpath) from a github.com URL.

    'https://github.com/intel/llm-scaler/tree/main/omni' -> ('intel/llm-scaler', 'omni')
    'https://github.com/Blackwood416/Aila'                -> ('Blackwood416/Aila', '')
    """
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)(?:/tree/[^/]+/(.+?))?(?:[/#?].*)?$", url or "")
    if m:
        repo = "%s/%s" % (m.group(1), m.group(2))
        path = (m.group(3) or "").rstrip("/")
        return repo, path
    return "", ""


def collect_desc(body, skip_prefixes):
    """Join body lines that are not address/author/tag/table lines into a paragraph."""
    parts = []
    for line in body:
        s = line.strip()
        if not s:
            continue
        if s.startswith("|"):
            continue
        if re.match(r"^\s*(项目地址|地址|作者|Tag)\s*[：:]", s):
            continue
        if re.match(r"^[^：:\s][^：:]*?[：:]\s*https?://", s):
            continue
        parts.append(s)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Card HTML builders
# ---------------------------------------------------------------------------

def md_inline(text):
    """Convert **bold** markdown to <b> tags."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def badge_html(tags):
    cls = {
        "官方": "badge-official",
        "社群": "badge-community",
        "fork": "badge-fork",
        "指定卡": "badge-card",
    }
    return "".join(
        '<span class="badge %s">%s</span>' % (cls.get(t, "badge-fork"), t)
        for t in tags if t in cls
    )


def index_card(item):
    tags = item["tags"]
    updated = item.get("updated") or "—"
    author_html = ""
    if item.get("author"):
        name, url = item["author"]
        author_html = ('<div class="author">作者：<a href="%s" target="_blank">@%s</a></div>'
                       % (url, name))
    return """    <article class="card" data-repo="%(repo)s" data-name="%(name)s">
      <div class="card-top">
        <div class="card-name"><a href="%(link)s" target="_blank">📖 %(name)s</a>%(badges)s</div>
        <span class="updated">更新：<span class="upd-time">%(updated)s</span></span>
      </div>
      <div class="card-desc">%(desc)s</div>
      <div class="card-footer">
        %(author)s
        <div class="links">
          <a class="btn btn-primary" href="%(link)s" target="_blank">项目地址</a>
        </div>
      </div>
    </article>""" % {
        "repo": item["repo"],
        "name": item["name"],
        "link": item["link"],
        "badges": badge_html(tags),
        "updated": updated,
        "desc": md_inline(item["desc"]),
        "author": author_html,
    }


def links_card(item):
    author_html = ""
    if item.get("author"):
        name, url = item["author"]
        author_html = ('<div class="author-row">作者：<a href="%s" target="_blank">@%s</a></div>'
                       % (url, name))
    addr_rows = "".join(
        '<div class="addr-row"><span class="label">%s：</span><a href="%s" target="_blank">%s</a></div>'
        % (label, url, url)
        for label, url in item["urls"]
    )
    return """    <article class="card">
      <div class="card-name"><a href="%(link)s" target="_blank">📖 %(name)s</a></div>
      <div class="card-desc">%(desc)s</div>
      <div class="card-meta">
%(addr)s%(author)s      </div>
    </article>""" % {
        "link": item["urls"][0][1] if item["urls"] else "#",
        "name": item["name"],
        "desc": md_inline(item["desc"]),
        "addr": addr_rows,
        "author": author_html,
    }


# ---------------------------------------------------------------------------
# Page templates
# ---------------------------------------------------------------------------

INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IntelGpu-ComfyUI-Collection - Intel GPU ComfyUI 项目集</title>
<style>
  :root {
    --intel-blue: #0071c5;
    --intel-blue-dark: #005a99;
    --bg: #f6f8fa;
    --card: #ffffff;
    --text: #24292f;
    --text-muted: #57606a;
    --border: #d0d7de;
    --amber-bg: #faf3e0;
    --amber-text: #854f0b;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
  }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px 20px 48px; }

  header { text-align: center; padding: 40px 0 24px; }
  header h1 {
    font-size: 30px; font-weight: 700; color: var(--text);
    display: inline-flex; align-items: center; gap: 10px;
  }
  header h1 .logo {
    width: 34px; height: 34px; border-radius: 8px;
    background: var(--intel-blue);
    display: inline-flex; align-items: center; justify-content: center;
    color: #fff; font-size: 18px; font-weight: 700;
  }
  header .note {
    margin-top: 12px; font-size: 14px; color: var(--text-muted);
  }
  .chips { margin-top: 14px; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
  .chip {
    font-size: 12px; padding: 5px 12px; border-radius: 999px;
    background: #e8f1fb; color: var(--intel-blue-dark); border: 1px solid #c8e0f5;
    cursor: pointer; text-decoration: none; display: inline-block;
  }
  .chip-active {
    background: var(--intel-blue); color: #fff; border-color: var(--intel-blue);
  }

  .group-card {
    margin: 20px auto 0; max-width: 520px;
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    padding: 20px; display: flex; flex-direction: column; align-items: center; gap: 14px;
    box-shadow: 0 1px 3px rgba(31,35,40,0.06);
  }
  .group-card img {
    width: 240px; height: 240px; border-radius: 12px; object-fit: cover;
  }
  .group-card .g-title { font-size: 15px; font-weight: 600; text-align: center; }
  .group-card .g-sub { font-size: 13px; color: var(--text-muted); margin-top: 2px; text-align: center; }
  .group-card .g-sub a { color: var(--intel-blue); text-decoration: none; font-weight: 600; }

  .sort-banner {
    margin: 28px 0 18px;
    background: linear-gradient(90deg, #e8f1fb, #f0f7fd);
    border: 1px solid #c8e0f5; border-radius: 10px;
    padding: 10px 16px; font-size: 13px; color: var(--intel-blue-dark);
    display: flex; align-items: center; gap: 8px; justify-content: center;
  }
  .sort-banner .dot {
    width: 8px; height: 8px; border-radius: 50%; background: #2da44e; display: inline-block;
  }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(460px, 1fr)); gap: 16px; }

  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    padding: 18px 20px; display: flex; flex-direction: column; gap: 10px;
    box-shadow: 0 1px 3px rgba(31,35,40,0.06);
    transition: box-shadow 0.15s ease;
  }
  .card:hover { box-shadow: 0 4px 12px rgba(31,35,40,0.12); }

  .card-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
  .card-name { font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .card-name a { color: var(--text); text-decoration: none; }
  .card-name a:hover { color: var(--intel-blue); }
  .badge {
    font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 500;
    white-space: nowrap;
  }
  .badge-official { background: #e8f1fb; color: #0c447c; border: 1px solid #c8e0f5; }
  .badge-community { background: #e6f4ea; color: #1a7f37; border: 1px solid #c3e6cb; }
  .badge-fork { background: var(--amber-bg); color: var(--amber-text); border: 1px solid #ead9b8; }
  .badge-card { background: #fdecea; color: #b3261e; border: 1px solid #f5c6c2; }
  .updated {
    font-size: 12px; color: var(--text-muted); white-space: nowrap;
    background: #f3f4f6; border-radius: 6px; padding: 3px 8px;
  }
  .card-desc { font-size: 13px; color: var(--text-muted); flex: 1; }

  .card-footer {
    display: flex; align-items: center; justify-content: space-between;
    padding-top: 10px; border-top: 1px solid #eef0f2;
  }
  .author { font-size: 13px; color: var(--text-muted); }
  .author a { color: var(--intel-blue); text-decoration: none; font-weight: 600; }
  .links { display: flex; gap: 8px; }
  .btn {
    font-size: 12px; text-decoration: none; padding: 5px 12px; border-radius: 8px;
    border: 1px solid var(--border); color: var(--text); background: #fff;
    transition: all 0.12s ease;
  }
  .btn:hover { border-color: var(--intel-blue); color: var(--intel-blue); }
  .btn-primary { background: var(--intel-blue); border-color: var(--intel-blue); color: #fff; }
  .btn-primary:hover { background: var(--intel-blue-dark); color: #fff; }

  footer { text-align: center; margin-top: 40px; font-size: 12px; color: var(--text-muted); }
  footer a { color: var(--intel-blue); text-decoration: none; }
</style>
</head>
<body>
<div class="container">

  <header>
    <h1><span class="logo">I</span>IntelGpu-ComfyUI-Collection</h1>
    <p class="note">以下项目均来自官方和社群</p>
    <div class="chips">
      <span class="chip chip-active">项目收集</span>
      <a class="chip" href="links.html">组件下载</a>
    </div>
    <div class="group-card">
      <img alt="group_logo" src="https://github.com/user-attachments/assets/9ce95b55-f980-4b3e-bb23-e8d24f37aba7">
      <div>
        <div class="g-title">《Intel GPU &amp; ComfyUI 折腾群》</div>
        <div class="g-sub">标记为<span class="badge badge-community">社群</span>的项目来自群友作品 · QQ群：<a href="https://qm.qq.com/q/gls9aI3lgA" target="_blank">220819365</a></div>
      </div>
    </div>
  </header>

  <div class="sort-banner">
    <span class="dot"></span> 项目按「最后更新时间」自动排序，每 6 小时刷新，下次刷新时间：<span id="next-refresh">—</span>
  </div>

  <div class="grid">

__CARDS__

  </div>

  <footer>
    由 <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection" target="_blank">IntelGpu-ComfyUI-Collection</a> 自动生成 ·
    <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/blob/main/README.md" target="_blank">README 源文件</a>
  </footer>

</div>
<script>
  (function () {
    function pad(n) { return String(n).padStart(2, "0"); }
    var now = new Date();
    var next = new Date(now);
    next.setHours(Math.floor(now.getHours() / 6) * 6 + 6, 0, 0, 0);
    document.getElementById("next-refresh").textContent =
      next.getFullYear() + "年" + pad(next.getMonth() + 1) + "月" + pad(next.getDate()) +
      "日  " + pad(next.getHours()) + "时 : " + pad(next.getMinutes()) + "分 : " + pad(next.getSeconds()) + "秒";
  })();
</script>
</body>
</html>
"""

LINKS_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IntelGpu-ComfyUI-Collection - Intel XPU 组件下载</title>
<style>
  :root {
    --intel-blue: #0071c5;
    --intel-blue-dark: #005a99;
    --bg: #f6f8fa;
    --card: #ffffff;
    --text: #24292f;
    --text-muted: #57606a;
    --border: #d0d7de;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
  }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px 20px 48px; }

  header { text-align: center; padding: 40px 0 24px; }
  header h1 {
    font-size: 30px; font-weight: 700; color: var(--text);
    display: inline-flex; align-items: center; gap: 10px;
  }
  header h1 .logo {
    width: 34px; height: 34px; border-radius: 8px;
    background: var(--intel-blue);
    display: inline-flex; align-items: center; justify-content: center;
    color: #fff; font-size: 18px; font-weight: 700;
  }
  header .note {
    margin-top: 12px; font-size: 14px; color: var(--text-muted);
  }
  .chips { margin-top: 14px; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
  .chip {
    font-size: 12px; padding: 5px 12px; border-radius: 999px;
    background: #e8f1fb; color: var(--intel-blue-dark); border: 1px solid #c8e0f5;
    cursor: pointer; text-decoration: none; display: inline-block;
  }
  .chip-active {
    background: var(--intel-blue); color: #fff; border-color: var(--intel-blue);
  }

  .grid { display: grid; grid-template-columns: 1fr; gap: 16px; }

  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    padding: 18px 20px; display: flex; flex-direction: column; gap: 10px;
    box-shadow: 0 1px 3px rgba(31,35,40,0.06);
    transition: box-shadow 0.15s ease;
  }
  .card:hover { box-shadow: 0 4px 12px rgba(31,35,40,0.12); }

  .card-name { font-size: 16px; font-weight: 600; }
  .card-name a { color: var(--text); text-decoration: none; }
  .card-name a:hover { color: var(--intel-blue); }
  .card-desc { font-size: 13px; color: var(--text-muted); }

  .card-meta {
    display: flex; flex-direction: column; gap: 4px;
    padding-top: 10px; border-top: 1px solid #eef0f2;
  }
  .addr-row { font-size: 13px; color: var(--text-muted); word-break: break-all; }
  .addr-row .label { color: var(--text); margin-right: 4px; }
  .addr-row a { color: var(--intel-blue); text-decoration: none; word-break: break-all; }
  .addr-row a:hover { text-decoration: underline; }
  .author-row { font-size: 13px; color: var(--text-muted); }
  .author-row a { color: var(--intel-blue); text-decoration: none; font-weight: 600; }

  footer { text-align: center; margin-top: 40px; font-size: 12px; color: var(--text-muted); }
  footer a { color: var(--intel-blue); text-decoration: none; }
</style>
</head>
<body>
<div class="container">

  <header>
    <h1><span class="logo">I</span>IntelGpu-ComfyUI-Collection</h1>
    <p class="note">Intel XPU 重要组件下载地址</p>
    <div class="chips">
      <a class="chip" href="index.html">项目收集</a>
      <span class="chip chip-active">组件下载</span>
    </div>
  </header>

  <div class="grid">

__CARDS__

  </div>

  <footer>
    由 <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection" target="_blank">IntelGpu-ComfyUI-Collection</a> 自动生成 ·
    <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/blob/main/links.md" target="_blank">links.md 源文件</a>
  </footer>

</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------

def build_index(readme_path, token):
    with open(readme_path, encoding="utf-8") as f:
        md = f.read()
    items = []
    for title, body in split_sections(md):
        name = clean_name(title)
        urls = extract_urls(body)
        if not urls:
            continue
        link = urls[0][1]
        repo, subpath = repo_path_from_url(link)
        # 子目录项目（如 intel-comfyui-guide 是主仓库内的目录，或
        # intel/llm-scaler/tree/main/omni 这类 /tree/ 路径）：
        # 无法用仓库级 API 拿到目录自己的更新时间，改用 commits?path= 查询
        if "allanmeng.github.io" in link or repo in ("allanmeng/IntelGpu-ComfyUI-Collection", ""):
            repo = "allanmeng/IntelGpu-ComfyUI-Collection"
            path = name
        else:
            path = subpath
        items.append({
            "name": name,
            "desc": collect_desc(body, ("项目地址", "地址", "作者", "Tag")),
            "link": link,
            "repo": repo,
            "path": path,
            "author": extract_author(body),
            "tags": extract_tags(body),
            "updated": "",
        })
    for it in items:
        it["updated"] = fmt_cn(fetch_repo_updated(it["repo"], it["path"], token))
    items.sort(key=lambda x: x["updated"], reverse=True)
    cards = "\n\n".join(index_card(it) for it in items)
    return INDEX_HTML.replace("__CARDS__", cards)


def build_links(links_path):
    with open(links_path, encoding="utf-8") as f:
        md = f.read()
    items = []
    for title, body in split_sections(md):
        name = clean_name(title)
        urls = [(lbl or "地址", u) for lbl, u in extract_urls(body)]
        if not urls:
            continue
        items.append({
            "name": name,
            "desc": collect_desc(body, ("地址", "作者")),
            "urls": urls,
            "author": extract_author(body),
        })
    cards = "\n\n".join(links_card(it) for it in items)
    return LINKS_HTML.replace("__CARDS__", cards)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true", help="generate index.html from README.md")
    ap.add_argument("--links", action="store_true", help="generate links.html from links.md")
    ap.add_argument("--token", default="", help="GitHub token for API queries")
    ap.add_argument("--out-dir", default="", help="output directory (default: repo root)")
    args = ap.parse_args()

    out_dir = args.out_dir or ROOT
    os.makedirs(out_dir, exist_ok=True)
    readme_path = os.path.join(ROOT, "README.md")
    links_path = os.path.join(ROOT, "links.md")

    if args.index:
        html = build_index(readme_path, args.token)
        with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print("[ok] index.html written (%d bytes)" % len(html.encode("utf-8")))

    if args.links:
        html = build_links(links_path)
        with open(os.path.join(out_dir, "links.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print("[ok] links.html written (%d bytes)" % len(html.encode("utf-8")))


if __name__ == "__main__":
    main()
