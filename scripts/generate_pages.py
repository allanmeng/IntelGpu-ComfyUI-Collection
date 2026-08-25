#!/usr/bin/env python3
"""Generate static pages from Markdown sources.

每页独立生成规则 + 每页独立模板（2026-08-25 Allan 要求）：
- index.html                <- README.md                (GitHub API 更新时间, 倒序)
- links.html                <- links.md                 (源顺序)
- cloud_drive_collection.html <- cloud_drive_collection.md (## box + ### 子节)
- comfyui_opt.html          <- comfyui_opt.md           (## box + 【】链接行)
- group.html                <- 静态

每页的解析/渲染函数独立私有（_index_*/_links_*/_cloud_*/_opt_*）；
每页的 HTML 模板完全独立（INDEX_HTML / LINKS_HTML / CLOUD_HTML / OPT_HTML / GROUP_HTML），
调整某页的结构不影响其他页的生成。共享仅限纯工具
（正则、split_sections、URL 提取、nav_html/badge_html）。

Usage:
  python generate_pages.py --index [--token GH_TOKEN] [--out-dir DIR]
  python generate_pages.py --links [--out-dir DIR]
  python generate_pages.py --index --links --cloud-drive --opt --group
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
# 纯工具（共享，无页面语义）
# ---------------------------------------------------------------------------

URL_RE = re.compile(r"https?://[^\s)\]]+")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def fetch_repo_updated(repo, path, token):
    """Last default-branch commit time for a repo, optionally restricted to a path."""
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


def clean_title(title):
    """Display title: keep leading icon (📖) exactly as in README, strip [fork]."""
    return re.sub(r"\s*\[fork\]\s*$", "", title).strip()


def clean_name(title):
    """Pure name for data-name: strip icon and [fork]."""
    name = re.sub(r"^📖\s*", "", title).strip()
    name = re.sub(r"\s*\[fork\]\s*$", "", name).strip()
    return name


def repo_from_url(url):
    """Extract 'owner/repo' from a github.com URL ('/tree/...' stripped)."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)", url or "")
    if m:
        return "%s/%s" % (m.group(1), m.group(2))
    return ""


def repo_path_from_url(url):
    """Return (owner/repo, subpath) from a github.com URL."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)(?:/tree/[^/]+/(.+?))?(?:[/#?].*)?$", url or "")
    if m:
        repo = "%s/%s" % (m.group(1), m.group(2))
        path = (m.group(3) or "").rstrip("/")
        return repo, path
    return "", ""


NAV_TABS = [
    ("index.html", "项目收集"),
    ("links.html", "组件下载"),
    ("cloud_drive_collection.html", "资源聚合"),
    ("comfyui_opt.html", "工作台优化"),
    ("group.html", "互助社群"),
]


def nav_html(active):
    """Chips navigation, 'active' highlighted."""
    out = []
    for href, label in NAV_TABS:
        if href == active:
            out.append('      <span class="chip chip-active">%s</span>' % label)
        else:
            out.append('      <a class="chip" href="%s">%s</a>' % (href, label))
    return "\n".join(out)


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


# ---------------------------------------------------------------------------
# index.html —— README.md 独立规则 + 独立模板 INDEX_HTML
# ---------------------------------------------------------------------------

def _index_extract_author(body):
    for line in body:
        m = re.match(r"^\s*(作者|维护者)[：:]\s*(.+?)\s*$", line)
        if m:
            label = m.group(1)
            content = m.group(2)
            m2 = re.match(r"\[@([^\]]+)\]\(([^)]+)\)", content)
            if m2:
                return m2.group(1), m2.group(2), label
            if content.startswith("@"):
                return content[1:], "", label
    return None


def _index_extract_tags(body):
    for line in body:
        m = re.match(r"^\s*Tag\s*[：:]\s*(.+?)\s*$", line)
        if m:
            return [t.strip() for t in m.group(1).split(",") if t.strip()]
    return []


def _index_extract_urls(body):
    """index 页地址提取：裸 URL 行与表格行；描述区【链接】行绝不提取。"""
    pairs = []
    for line in body:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            for cell in cells:
                for u in URL_RE.findall(cell):
                    pairs.append(("", u))
            continue
        m = re.match(r"^([^：:\s\[【][^：:]*?)\s*[：:]\s*(https?://\S+)\s*$", s)
        if m:
            label = m.group(1).strip()
            if label.startswith(("作者", "维护者", "Tag")):
                continue
            pairs.append((label, m.group(2).strip().rstrip("，。,")))
    return pairs


def _index_render_desc(body):
    parts = []
    for line in body:
        s = line.strip()
        if not s:
            parts.append("<br>")
            continue
        if s.startswith("|"):
            continue
        if re.match(r"^\s*(项目地址|地址|作者|维护者|Tag)\s*[：:]", s):
            break
        if re.match(r"^[^：:\s][^：:]*?[：:]\s*https?://\S+$", s):
            break
        h = MD_LINK_RE.sub(r'<a href="\2" target="_blank">\1</a>', s)
        h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
        parts.append(h + "<br>")
    text = "".join(parts)
    text = re.sub(r"^(<br>)+|(<br>)+$", "", text)
    return text


def _index_card(item):
    tags = item["tags"]
    updated = item.get("updated") or "—"
    author_html = ""
    if item.get("author"):
        name, url, label = item["author"]
        if url:
            author_html = ('<div class="author">%s：<a href="%s" target="_blank">@%s</a></div>'
                           % (label, url, name))
        else:
            author_html = '<div class="author">%s：@%s</div>' % (label, name)
    return """    <article class="card" data-repo="%(repo)s" data-name="%(name)s">
      <div class="card-top">
        <div class="card-name"><a href="%(link)s" target="_blank">%(display)s</a>%(badges)s</div>
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
        "display": item["display"],
        "link": item["link"],
        "badges": badge_html(tags),
        "updated": updated,
        "desc": item["desc"],
        "author": author_html,
    }


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
    width: 100px; height: 100px; border-radius: 6px;
    object-fit: contain; display: inline-block; vertical-align: middle;
  }
  header h1 .logo-group {
    width: 100px; height: 100px; border-radius: 6px;
    object-fit: contain; display: inline-block; vertical-align: middle;
  }
  header h1 .logo-link { display: inline-flex; align-items: center; }
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
  .card-desc a { color: var(--intel-blue); text-decoration: none; }
  .card-desc a:hover { text-decoration: underline; }

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
    <h1><a class="logo-link" href="group.html"><img class="logo-group" src="assets/group_logo_150.png" alt="Group"></a>IntelGpu-ComfyUI-Collection<img class="logo" src="assets/Intel_Graphics_logo.png" alt="Intel Graphics"></h1>
    <p class="note">以下项目多数由社群中作者维护，少量是Intel官方维护（官方的这几个项目需要紧盯）</p>
    <div class="chips">
__NAV__
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
    // cron 计划: UTC 00/06/12/18 (每 6 小时, GitHub Actions 用 UTC)。
    // getTime() 本身就是 UTC 时间戳，用 getUTC* 计算下一个刷新点，
    // Date.UTC 构造出绝对时间，再用本地 get* 显示（自动转本地时区）。
    var nextUtcHour = Math.floor(now.getUTCHours() / 6) * 6 + 6;
    var next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), nextUtcHour));
    document.getElementById("next-refresh").textContent =
      next.getFullYear() + "年" + pad(next.getMonth() + 1) + "月" + pad(next.getDate()) +
      "日  " + pad(next.getHours()) + "时 : " + pad(next.getMinutes()) + "分 : " + pad(next.getSeconds()) + "秒";
  })();
</script>
</body>
</html>
"""


def build_index(readme_path, token):
    with open(readme_path, encoding="utf-8") as f:
        md = f.read()
    items = []
    for title, body in split_sections(md):
        name = clean_name(title)
        urls = _index_extract_urls(body)
        if not urls:
            continue
        link = urls[0][1]
        repo, subpath = repo_path_from_url(link)
        if "allanmeng.github.io" in link:
            repo = "allanmeng/IntelGpu-ComfyUI-Collection"
            path = link.rstrip("/").split("/")[-1]
        elif repo in ("allanmeng/IntelGpu-ComfyUI-Collection", ""):
            repo = "allanmeng/IntelGpu-ComfyUI-Collection"
            path = name
        else:
            path = subpath
        items.append({
            "name": name,
            "display": clean_title(title),
            "desc": _index_render_desc(body),
            "link": link,
            "repo": repo,
            "path": path,
            "author": _index_extract_author(body),
            "tags": _index_extract_tags(body),
            "updated": "",
        })
    for it in items:
        it["updated"] = fmt_cn(fetch_repo_updated(it["repo"], it["path"], token))
    items.sort(key=lambda x: x["updated"], reverse=True)
    cards = "\n\n".join(_index_card(it) for it in items)
    return (INDEX_HTML
            .replace("__NAV__", nav_html("index.html"))
            .replace("__CARDS__", cards))


# ---------------------------------------------------------------------------
# links.html —— links.md 独立规则 + 独立模板 LINKS_HTML
# ---------------------------------------------------------------------------

def _links_extract_author(body):
    for line in body:
        m = re.match(r"^\s*(作者|维护者)[：:]\s*(.+?)\s*$", line)
        if m:
            label = m.group(1)
            content = m.group(2)
            m2 = re.match(r"\[@([^\]]+)\]\(([^)]+)\)", content)
            if m2:
                return m2.group(1), m2.group(2), label
            if content.startswith("@"):
                return content[1:], "", label
    return None


def _links_extract_urls(body):
    """links 页地址提取：'label：url[ 说明文字]' 行与表格行（URL 后可能带说明）。"""
    pairs = []
    for line in body:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            for cell in cells:
                for u in URL_RE.findall(cell):
                    pairs.append(("", u, u))
            continue
        m = re.match(r"^([^：:\s\[【][^：:]*?)\s*[：:]\s*(.+?)\s*$", s)
        if not m:
            continue
        label = m.group(1).strip()
        if label.startswith(("作者", "维护者", "Tag")):
            continue
        val = m.group(2).strip()
        if val.startswith("http"):
            # href 必须是纯 URL；显示文字保留"URL + 说明"（如"（目录：...）"）
            u = URL_RE.search(val)
            if u:
                pairs.append((label, u.group(0), val.rstrip("，。,")))
    return pairs


def _links_render_desc(body):
    parts = []
    for line in body:
        s = line.strip()
        if not s:
            parts.append("<br>")
            continue
        if s.startswith("|"):
            continue
        if re.match(r"^\s*(项目地址|地址|作者|维护者|Tag)\s*[：:]", s):
            break
        if re.match(r"^[^：:\s][^：:]*?[：:]\s*https?://\S+$", s):
            break
        h = MD_LINK_RE.sub(r'<a href="\2" target="_blank">\1</a>', s)
        h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
        parts.append(h + "<br>")
    text = "".join(parts)
    text = re.sub(r"^(<br>)+|(<br>)+$", "", text)
    return text


def _links_card(item):
    author_html = ""
    if item.get("author"):
        name, url, label = item["author"]
        if url:
            author_html = ('<div class="author-row">%s：<a href="%s" target="_blank">@%s</a></div>'
                           % (label, url, name))
        else:
            author_html = '<div class="author-row">%s：@%s</div>' % (label, name)
    addr_rows = "".join(
        '<div class="addr-row">%s<a href="%s" target="_blank">%s</a></div>'
        % ('<span class="label">%s：</span>' % lbl if lbl else "", u, t)
        for lbl, u, t in item["urls"]
    )
    return """    <article class="card">
      <div class="card-name"><a href="%(link)s" target="_blank">%(display)s</a></div>
      <div class="card-desc">%(desc)s</div>
      <div class="card-meta">
%(addr)s%(author)s      </div>
    </article>""" % {
        "link": item["urls"][0][1] if item["urls"] else "#",
        "display": item["display"],
        "name": item["name"],
        "desc": item["desc"],
        "addr": addr_rows,
        "author": author_html,
    }


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
    width: 100px; height: 100px; border-radius: 6px;
    object-fit: contain; display: inline-block; vertical-align: middle;
  }
  header h1 .logo-group {
    width: 100px; height: 100px; border-radius: 6px;
    object-fit: contain; display: inline-block; vertical-align: middle;
  }
  header h1 .logo-link { display: inline-flex; align-items: center; }
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
  .card-desc a { color: var(--intel-blue); text-decoration: none; }
  .card-desc a:hover { text-decoration: underline; }

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
    <h1><a class="logo-link" href="group.html"><img class="logo-group" src="assets/group_logo_150.png" alt="Group"></a>IntelGpu-ComfyUI-Collection<img class="logo" src="assets/Intel_Graphics_logo.png" alt="Intel Graphics"></h1>
    <p class="note">Intel XPU 重要组件下载地址</p>
    <div class="chips">
__NAV__
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


def build_links(links_path):
    with open(links_path, encoding="utf-8") as f:
        md = f.read()
    items = []
    for title, body in split_sections(md):
        name = clean_name(title)
        desc = _links_render_desc(body)
        urls = _links_extract_urls(body)
        if not urls and not desc:
            continue
        items.append({
            "name": name,
            "display": clean_title(title),
            "desc": desc,
            "urls": urls,
            "author": _links_extract_author(body),
        })
    cards = "\n\n".join(_links_card(it) for it in items)
    return (LINKS_HTML
            .replace("__NAV__", nav_html("links.html"))
            .replace("__CARDS__", cards))


# ---------------------------------------------------------------------------
# cloud_drive_collection.html —— 独立规则 + 独立模板 CLOUD_HTML
# ---------------------------------------------------------------------------

def _cloud_split_subsections(body):
    subs = []
    cur_title = None
    cur = []
    for line in body:
        m = re.match(r"^###\s+(.*)$", line)
        if m:
            if cur_title is not None or any(cur):
                subs.append((cur_title, cur))
            cur_title = m.group(1).strip()
            cur = []
        else:
            cur.append(line)
    if cur_title is not None or any(cur):
        subs.append((cur_title, cur))
    return subs


def _cloud_extract_author(body):
    for line in body:
        m = re.match(r"^\s*(作者|维护者)[：:]\s*(.+?)\s*$", line)
        if m:
            label = m.group(1)
            content = m.group(2)
            m2 = re.match(r"\[@([^\]]+)\]\(([^)]+)\)", content)
            if m2:
                return m2.group(1), m2.group(2), label
            if content.startswith("@"):
                return content[1:], "", label
    return None


def _cloud_extract_urls(body):
    """cloud 页地址提取：裸 URL / [text](url) / 【[a](u1)】【[b](u2)】。"""
    pairs = []
    for line in body:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            for cell in cells:
                for u in URL_RE.findall(cell):
                    pairs.append(("", u, u, False))
            continue
        m = re.match(r"^([^：:\s\[【][^：:]*?)\s*[：:]\s*(.+?)\s*$", s)
        if not m:
            continue
        label = m.group(1).strip()
        if label.startswith(("作者", "维护者", "Tag")):
            continue
        val = m.group(2).strip()
        links = MD_LINK_RE.findall(val)
        if links:
            bracket = "【" in val
            for i, (text, url) in enumerate(links):
                pairs.append((label if i == 0 else "", url, text, bracket))
        elif val.startswith("http"):
            pairs.append((label, val.rstrip("，。,"), val.rstrip("，。,"), False))
    return pairs


def _cloud_render_desc(body):
    parts = []
    for line in body:
        s = line.strip()
        if not s:
            parts.append("<br>")
            continue
        if s.startswith("|"):
            continue
        if re.match(r"^\s*(项目地址|地址|作者|维护者|Tag)\s*[：:]", s):
            break
        if re.match(r"^[^：:\s][^：:]*?[：:]\s*https?://\S+$", s):
            break
        h = MD_LINK_RE.sub(r'<a href="\2" target="_blank">\1</a>', s)
        h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
        parts.append(h + "<br>")
    text = "".join(parts)
    text = re.sub(r"^(<br>)+|(<br>)+$", "", text)
    return text


def _cloud_render_addr_rows(urls):
    """cloud 页地址行渲染：裸 URL 逐行；【】链接合并成一行【a】【b】。"""
    rows = []
    bracket_lbl = next((lbl for lbl, u, t, b in urls if b and lbl), "")
    bracket = [(u, t) for lbl, u, t, b in urls if b]
    plain = [(lbl, u, t) for lbl, u, t, b in urls if not b]
    if bracket:
        inner = "".join(
            '<a href="%s" target="_blank">【%s】</a>' % (u, t)
            for u, t in bracket
        )
        label_span = '<span class="label">%s：</span>' % bracket_lbl if bracket_lbl else ""
        rows.append('<div class="addr-row">%s%s</div>' % (label_span, inner))
    for lbl, u, t in plain:
        label_span = '<span class="label">%s：</span>' % lbl if lbl else ""
        rows.append('<div class="addr-row">%s<a href="%s" target="_blank">%s</a></div>'
                    % (label_span, u, t))
    return "".join(rows)


def _cloud_sub_block(sub):
    """cloud 页：'### ' 子节渲染。"""
    title, body = sub
    desc = _cloud_render_desc(body)
    urls = _cloud_extract_urls(body)
    author = _cloud_extract_author(body)
    addr_rows = _cloud_render_addr_rows(urls)
    author_html = ""
    if author:
        name, url, label = author
        if url:
            author_html = ('<div class="author-row">%s：<a href="%s" target="_blank">@%s</a></div>'
                           % (label, url, name))
        else:
            author_html = '<div class="author-row">%s：@%s</div>' % (label, name)
    return ('<div class="sub-block">'
            '<div class="sub-title">%s</div>'
            '<div class="card-desc">%s</div>'
            '<div class="card-meta">%s%s</div>'
            '</div>') % (title, desc, addr_rows, author_html)


def _cloud_card(item):
    """cloud 页卡片：普通卡或 '## ' box 含 '### ' 子节。"""
    if not item.get("subs"):
        author_html = ""
        if item.get("author"):
            name, url, label = item["author"]
            if url:
                author_html = ('<div class="author-row">%s：<a href="%s" target="_blank">@%s</a></div>'
                               % (label, url, name))
            else:
                author_html = '<div class="author-row">%s：@%s</div>' % (label, name)
        addr_rows = _cloud_render_addr_rows(item["urls"])
        return """    <article class="card">
      <div class="card-name"><a href="%(link)s" target="_blank">%(display)s</a></div>
      <div class="card-desc">%(desc)s</div>
      <div class="card-meta">
%(addr)s%(author)s      </div>
    </article>""" % {
            "link": item["urls"][0][1] if item["urls"] else "#",
            "display": item["display"],
            "desc": item["desc"],
            "addr": addr_rows,
            "author": author_html,
        }
    subs_html = "".join(_cloud_sub_block(s) for s in item["subs"])
    return """    <article class="card">
      <div class="card-name">%(display)s</div>
      %(subs)s
    </article>""" % {
        "display": item["display"],
        "subs": subs_html,
    }


CLOUD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IntelGpu-ComfyUI-Collection - Intel XPU 网盘聚合</title>
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
    width: 100px; height: 100px; border-radius: 6px;
    object-fit: contain; display: inline-block; vertical-align: middle;
  }
  header h1 .logo-group {
    width: 100px; height: 100px; border-radius: 6px;
    object-fit: contain; display: inline-block; vertical-align: middle;
  }
  header h1 .logo-link { display: inline-flex; align-items: center; }
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
  .card-desc a { color: var(--intel-blue); text-decoration: none; }
  .card-desc a:hover { text-decoration: underline; }

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

  .sub-block {
    border-top: 1px solid var(--border); margin-top: 14px; padding-top: 12px;
    padding-left: 16px;
  }
  .sub-block:first-child { border-top: none; margin-top: 0; padding-top: 0; }
  .sub-title { font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 6px; }
  .sub-block .card-meta { margin-top: 8px; }
  footer { text-align: center; margin-top: 40px; font-size: 12px; color: var(--text-muted); }
  footer a { color: var(--intel-blue); text-decoration: none; }
</style>
</head>
<body>
<div class="container">

  <header>
    <h1><a class="logo-link" href="group.html"><img class="logo-group" src="assets/group_logo_150.png" alt="Group"></a>IntelGpu-ComfyUI-Collection<img class="logo" src="assets/Intel_Graphics_logo.png" alt="Intel Graphics"></h1>
    <p class="note">Intel XPU 网盘聚合</p>
    <div class="chips">
__NAV__
    </div>
  </header>

  <div class="grid">

__CARDS__

  </div>

  <footer>
    由 <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection" target="_blank">IntelGpu-ComfyUI-Collection</a> 自动生成 ·
    <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/blob/main/cloud_drive_collection.md" target="_blank">cloud_drive_collection.md 源文件</a>
  </footer>

</div>
</body>
</html>
"""


def build_cloud_drive(cloud_path):
    """cloud_drive_collection.html（独立模板 CLOUD_HTML，结构与其他页无关）。"""
    with open(cloud_path, encoding="utf-8") as f:
        md = f.read()
    items = []
    for title, body in split_sections(md):
        name = clean_name(title)
        display = clean_title(title)
        subs = _cloud_split_subsections(body)
        if subs and subs[0][0] is not None:
            items.append({"name": name, "display": display, "subs": subs})
            continue
        desc = _cloud_render_desc(body)
        urls = _cloud_extract_urls(body)
        if not urls and not desc:
            continue
        items.append({
            "name": name,
            "display": display,
            "desc": desc,
            "urls": urls,
            "author": _cloud_extract_author(body),
        })
    cards = "\n\n".join(_cloud_card(it) for it in items)
    return (CLOUD_HTML
            .replace("__NAV__", nav_html("cloud_drive_collection.html"))
            .replace("__CARDS__", cards))


# ---------------------------------------------------------------------------
# comfyui_opt.html —— 独立规则 + 独立模板 OPT_HTML
# ---------------------------------------------------------------------------

def _opt_split_subsections(body):
    subs = []
    cur_title = None
    cur = []
    for line in body:
        m = re.match(r"^###\s+(.*)$", line)
        if m:
            if cur_title is not None or any(cur):
                subs.append((cur_title, cur))
            cur_title = m.group(1).strip()
            cur = []
        else:
            cur.append(line)
    if cur_title is not None or any(cur):
        subs.append((cur_title, cur))
    return subs


def _opt_extract_author(body):
    for line in body:
        m = re.match(r"^\s*(作者|维护者)[：:]\s*(.+?)\s*$", line)
        if m:
            label = m.group(1)
            content = m.group(2)
            m2 = re.match(r"\[@([^\]]+)\]\(([^)]+)\)", content)
            if m2:
                return m2.group(1), m2.group(2), label
            if content.startswith("@"):
                return content[1:], "", label
    return None


def _opt_extract_urls(body):
    """opt 页地址提取：裸 URL / [text](url) / 【】多链接（独立规则）。"""
    pairs = []
    for line in body:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            for cell in cells:
                for u in URL_RE.findall(cell):
                    pairs.append(("", u, u, False))
            continue
        m = re.match(r"^([^：:\s\[【][^：:]*?)\s*[：:]\s*(.+?)\s*$", s)
        if not m:
            continue
        label = m.group(1).strip()
        if label.startswith(("作者", "维护者", "Tag")):
            continue
        val = m.group(2).strip()
        links = MD_LINK_RE.findall(val)
        if links:
            bracket = "【" in val
            for i, (text, url) in enumerate(links):
                pairs.append((label if i == 0 else "", url, text, bracket))
        elif val.startswith("http"):
            pairs.append((label, val.rstrip("，。,"), val.rstrip("，。,"), False))
    return pairs


def _opt_render_desc(body):
    parts = []
    for line in body:
        s = line.strip()
        if not s:
            parts.append("<br>")
            continue
        if s.startswith("|"):
            continue
        if re.match(r"^\s*(项目地址|地址|作者|维护者|Tag)\s*[：:]", s):
            break
        if re.match(r"^[^：:\s][^：:]*?[：:]\s*https?://\S+$", s):
            break
        h = MD_LINK_RE.sub(r'<a href="\2" target="_blank">\1</a>', s)
        h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
        parts.append(h + "<br>")
    text = "".join(parts)
    text = re.sub(r"^(<br>)+|(<br>)+$", "", text)
    return text


def _opt_render_addr_rows(urls):
    """opt 页地址行渲染：【】链接合并一行 + 保留 '地址：' 标签。"""
    rows = []
    bracket_lbl = next((lbl for lbl, u, t, b in urls if b and lbl), "")
    bracket = [(u, t) for lbl, u, t, b in urls if b]
    plain = [(lbl, u, t) for lbl, u, t, b in urls if not b]
    if bracket:
        inner = "".join(
            '<a href="%s" target="_blank">【%s】</a>' % (u, t)
            for u, t in bracket
        )
        label_span = '<span class="label">%s：</span>' % bracket_lbl if bracket_lbl else ""
        rows.append('<div class="addr-row">%s%s</div>' % (label_span, inner))
    for lbl, u, t in plain:
        label_span = '<span class="label">%s：</span>' % lbl if lbl else ""
        rows.append('<div class="addr-row">%s<a href="%s" target="_blank">%s</a></div>'
                    % (label_span, u, t))
    return "".join(rows)


def _opt_sub_block(sub):
    """opt 页：'### ' 子节渲染。"""
    title, body = sub
    desc = _opt_render_desc(body)
    urls = _opt_extract_urls(body)
    author = _opt_extract_author(body)
    addr_rows = _opt_render_addr_rows(urls)
    author_html = ""
    if author:
        name, url, label = author
        if url:
            author_html = ('<div class="author-row">%s：<a href="%s" target="_blank">@%s</a></div>'
                           % (label, url, name))
        else:
            author_html = '<div class="author-row">%s：@%s</div>' % (label, name)
    return ('<div class="sub-block">'
            '<div class="sub-title">%s</div>'
            '<div class="card-desc">%s</div>'
            '<div class="card-meta">%s%s</div>'
            '</div>') % (title, desc, addr_rows, author_html)


def _opt_card(item):
    """opt 页卡片：普通卡或 '## ' box 含 '### ' 子节。"""
    if not item.get("subs"):
        author_html = ""
        if item.get("author"):
            name, url, label = item["author"]
            if url:
                author_html = ('<div class="author-row">%s：<a href="%s" target="_blank">@%s</a></div>'
                               % (label, url, name))
            else:
                author_html = '<div class="author-row">%s：@%s</div>' % (label, name)
        addr_rows = _opt_render_addr_rows(item["urls"])
        return """    <article class="card">
      <div class="card-name"><a href="%(link)s" target="_blank">%(display)s</a></div>
      <div class="card-desc">%(desc)s</div>
      <div class="card-meta">
%(addr)s%(author)s      </div>
    </article>""" % {
            "link": item["urls"][0][1] if item["urls"] else "#",
            "display": item["display"],
            "desc": item["desc"],
            "addr": addr_rows,
            "author": author_html,
        }
    subs_html = "".join(_opt_sub_block(s) for s in item["subs"])
    return """    <article class="card">
      <div class="card-name">%(display)s</div>
      %(subs)s
    </article>""" % {
        "display": item["display"],
        "subs": subs_html,
    }


OPT_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IntelGpu-ComfyUI-Collection - 工作台优化</title>
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
    width: 100px; height: 100px; border-radius: 6px;
    object-fit: contain; display: inline-block; vertical-align: middle;
  }
  header h1 .logo-group {
    width: 100px; height: 100px; border-radius: 6px;
    object-fit: contain; display: inline-block; vertical-align: middle;
  }
  header h1 .logo-link { display: inline-flex; align-items: center; }
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
  .card-desc a { color: var(--intel-blue); text-decoration: none; }
  .card-desc a:hover { text-decoration: underline; }

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

  .sub-block {
    border-top: 1px solid var(--border); margin-top: 14px; padding-top: 12px;
    padding-left: 16px;
  }
  .sub-block:first-child { border-top: none; margin-top: 0; padding-top: 0; }
  .sub-title { font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 6px; }
  .sub-block .card-meta { margin-top: 8px; }
  footer { text-align: center; margin-top: 40px; font-size: 12px; color: var(--text-muted); }
  footer a { color: var(--intel-blue); text-decoration: none; }
</style>
</head>
<body>
<div class="container">

  <header>
    <h1><a class="logo-link" href="group.html"><img class="logo-group" src="assets/group_logo_150.png" alt="Group"></a>IntelGpu-ComfyUI-Collection<img class="logo" src="assets/Intel_Graphics_logo.png" alt="Intel Graphics"></h1>
    <p class="note">面向 Intel GPU ComfyUI 的优化建议</p>
    <div class="chips">
__NAV__
    </div>
  </header>

  <div class="grid">

__CARDS__

  </div>

  <footer>
    由 <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection" target="_blank">IntelGpu-ComfyUI-Collection</a> 自动生成 ·
    <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/blob/main/comfyui_opt.md" target="_blank">comfyui_opt.md 源文件</a>
  </footer>

</div>
</body>
</html>
"""


def build_comfyui_opt(opt_path):
    """comfyui_opt.html（独立模板 OPT_HTML，结构与其他页无关）。"""
    with open(opt_path, encoding="utf-8") as f:
        md = f.read()
    items = []
    for title, body in split_sections(md):
        name = clean_name(title)
        display = clean_title(title)
        subs = _opt_split_subsections(body)
        if subs and subs[0][0] is not None:
            items.append({"name": name, "display": display, "subs": subs})
            continue
        desc = _opt_render_desc(body)
        urls = _opt_extract_urls(body)
        if not urls and not desc:
            continue
        items.append({
            "name": name,
            "display": display,
            "desc": desc,
            "urls": urls,
            "author": _opt_extract_author(body),
        })
    cards = "\n\n".join(_opt_card(it) for it in items)
    return (OPT_HTML
            .replace("__NAV__", nav_html("comfyui_opt.html"))
            .replace("__CARDS__", cards))


# ---------------------------------------------------------------------------
# group.html —— 静态页独立规则 + 独立模板 GROUP_HTML
# ---------------------------------------------------------------------------

GROUP_CARD_HTML = """    <div class="group-hero">
      <img alt="group_logo" src="https://github.com/user-attachments/assets/40a6707f-a438-4139-8efa-c7248d0ccb9d">
      <h2>《Intel GPU &amp; ComfyUI 折腾群》</h2>
      <p>标记为<span class="badge badge-community">社群</span>的项目来自群友作品</p>
      <p>QQ群：<a href="https://qm.qq.com/q/gls9aI3lgA" target="_blank">220819365</a></p>
      <a class="btn btn-primary btn-lg" href="https://qm.qq.com/q/gls9aI3lgA" target="_blank">加入群聊</a>
    </div>"""


GROUP_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IntelGpu-ComfyUI-Collection - 互助社群</title>
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
    width: 100px; height: 100px; border-radius: 6px;
    object-fit: contain; display: inline-block; vertical-align: middle;
  }
  header h1 .logo-group {
    width: 100px; height: 100px; border-radius: 6px;
    object-fit: contain; display: inline-block; vertical-align: middle;
  }
  header h1 .logo-link { display: inline-flex; align-items: center; }
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
  .card-desc a { color: var(--intel-blue); text-decoration: none; }
  .card-desc a:hover { text-decoration: underline; }

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

  .group-hero {
    max-width: 520px; margin: 40px auto; text-align: center;
    background: var(--card); border: 1px solid var(--border); border-radius: 16px;
    padding: 32px 28px; box-shadow: 0 1px 3px rgba(31,35,40,0.06);
  }
  .group-hero img { width: 220px; height: 220px; border-radius: 12px; object-fit: cover; }
  .group-hero h2 { margin: 16px 0 8px; font-size: 20px; }
  .group-hero p { font-size: 14px; color: var(--text-muted); margin: 6px 0; }
  .group-hero p a { color: var(--intel-blue); text-decoration: none; font-weight: 600; }
  .group-hero .btn-lg { display: inline-block; margin-top: 14px; padding: 10px 32px; font-size: 15px; }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 500; white-space: nowrap; }
  .badge-community { background: #e6f4ea; color: #1a7f37; border: 1px solid #c3e6cb; }
  .btn { font-size: 13px; text-decoration: none; padding: 5px 12px; border-radius: 8px; border: 1px solid var(--border); color: var(--text); background: #fff; }
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
    <h1><a class="logo-link" href="group.html"><img class="logo-group" src="assets/group_logo_150.png" alt="Group"></a>IntelGpu-ComfyUI-Collection<img class="logo" src="assets/Intel_Graphics_logo.png" alt="Intel Graphics"></h1>
    <p class="note">Intel GPU &amp; ComfyUI 互助社群</p>
    <div class="chips">
__NAV__
    </div>
  </header>

  <div class="grid">

__CARDS__

  </div>

  <footer>
    由 <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection" target="_blank">IntelGpu-ComfyUI-Collection</a> 自动生成 ·
    group 页面（静态）
  </footer>

</div>
</body>
</html>
"""


def build_group():
    """group.html：静态社群页（独立模板 GROUP_HTML，结构与其他页无关）。"""
    return (GROUP_HTML
            .replace("__NAV__", nav_html("group.html"))
            .replace("__CARDS__", GROUP_CARD_HTML))


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true", help="generate index.html from README.md")
    ap.add_argument("--links", action="store_true", help="generate links.html from links.md")
    ap.add_argument("--cloud-drive", action="store_true", help="generate cloud_drive_collection.html from cloud_drive_collection.md")
    ap.add_argument("--group", action="store_true", help="generate group.html (static)")
    ap.add_argument("--opt", action="store_true", help="generate comfyui_opt.html from comfyui_opt.md")
    ap.add_argument("--token", default="", help="GitHub token for API queries")
    ap.add_argument("--out-dir", default="", help="output directory (default: repo root)")
    args = ap.parse_args()

    out_dir = args.out_dir or ROOT
    os.makedirs(out_dir, exist_ok=True)
    readme_path = os.path.join(ROOT, "README.md")
    links_path = os.path.join(ROOT, "links.md")
    cloud_path = os.path.join(ROOT, "cloud_drive_collection.md")
    opt_path = os.path.join(ROOT, "comfyui_opt.md")

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

    if args.cloud_drive:
        html = build_cloud_drive(cloud_path)
        with open(os.path.join(out_dir, "cloud_drive_collection.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print("[ok] cloud_drive_collection.html written (%d bytes)" % len(html.encode("utf-8")))

    if args.group:
        html = build_group()
        with open(os.path.join(out_dir, "group.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print("[ok] group.html written (%d bytes)" % len(html.encode("utf-8")))

    if args.opt:
        html = build_comfyui_opt(opt_path)
        with open(os.path.join(out_dir, "comfyui_opt.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print("[ok] comfyui_opt.html written (%d bytes)" % len(html.encode("utf-8")))


if __name__ == "__main__":
    main()
