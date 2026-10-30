#!/usr/bin/env python3
"""Generate static pages from Markdown sources.

每页独立生成规则 + 每页独立模板（2026-08-25 Allan 要求）：
- index.html                <- README.md                (GitHub API 更新时间, 倒序)
- links.html                <- links.md                 (源顺序)
- cloud_drive_collection.html <- cloud_drive_collection.md (## box + ### 子节)
- comfyui_opt.html          <- comfyui_opt.md           (## box + 【】链接行)
- logs.html + logs/*.html   <- log-analysis/ 原始日志    (指标抽取 + 时间倒排列表)
- group.html                <- 静态

每页的解析/渲染函数独立私有（_index_*/_links_*/_cloud_*/_opt_*/_logs_*）；
每页的 HTML 模板完全独立（INDEX_HTML / LINKS_HTML / CLOUD_HTML / OPT_HTML / LOGS_INDEX_HTML / GROUP_HTML），
调整某页的结构不影响其他页的生成。共享仅限纯工具
（正则、split_sections、URL 提取、nav_html/badge_html）。

log-analysis/ 只读：脚本从原始 .txt 抽指标，不写任何中间文件进去。

Usage:
  python generate_pages.py --index [--token GH_TOKEN] [--out-dir DIR]
  python generate_pages.py --links [--out-dir DIR]
  python generate_pages.py --logs [--out-dir DIR]
  python generate_pages.py --index --links --cloud-drive --opt --logs --group
"""
import argparse
import html as _html
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

TZ_CN = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# 纯工具（共享，无页面语义）
# ---------------------------------------------------------------------------

URL_RE = re.compile(r"https?://[^\s)\]]+")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def fetch_repo_updated(repo, path, token, retries=3):
    """Last default-branch commit time for a repo, optionally restricted to a path.

    失败会短暂退避重试：网络抖动（如 SSL EOF）单次失败就丢更新时间，
    会让 index 卡片的倒序排列整体错乱。
    """
    url = "https://api.github.com/repos/%s/commits?per_page=1" % repo
    if path:
        url += "&path=%s" % path
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer %s" % token
    req = urllib.request.Request(url, headers=headers)
    last_exc = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and "commit" in data[0]:
                    return data[0]["commit"]["committer"]["date"] or ""
                return ""
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    print("[warn] API query failed for %s%s: %s"
          % (repo, ("/" + path) if path else "", last_exc), file=sys.stderr)
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
    ("logs.html", "执行日志"),
    ("group.html", "互助社群"),
]

# 站外导航（chips 末尾追加，新标签页打开）
EXTERNAL_NAV = [
    ("生态日报", "https://blog.blackwood.cv/news/latest"),
]


def nav_html(active, prefix=""):
    """Chips navigation, 'active' highlighted; 站内 tab + 站外链接（新标签页）。

    prefix：子目录页面（如 logs/<slug>.html）传 "../"，使相对链接回到站根。
    默认空串，站根页面输出与历史版本逐字节一致。
    """
    out = []
    for href, label in NAV_TABS:
        if href == active:
            out.append('      <span class="chip chip-active">%s</span>' % label)
        else:
            out.append('      <a class="chip" href="%s%s">%s</a>' % (prefix, href, label))
    for label, url in EXTERNAL_NAV:
        out.append('      <a class="chip" href="%s" target="_blank" rel="noopener">%s ↗</a>' % (url, label))
    return "\n".join(out)


def badge_html(tags):
    """Tag → 徽章。

    dg2 / bmg 属同一类「指定卡（特定架构）」标签，沿用原 badge-card 浅红样式。
    注意：此处**不可**用 `if t in cls` 过滤——曾因过滤导致 README 里的 dg2/bmg
    徽章被静默丢弃（2026-10-23 修复）。未知标签改为按默认样式渲染并打 warn。
    """
    cls = {
        "官方": "badge-official",
        "社群": "badge-community",
        "fork": "badge-fork",
        "dg2": "badge-card",   # A 系列 / DG2
        "bmg": "badge-card",   # B 系列 / Battlemage
        "指定卡": "badge-card",  # 旧写法，保留兼容
    }
    out = []
    for t in tags:
        if t not in cls:
            print("[warn] 未登记的 Tag：%r（已按默认样式渲染，建议补进 badge_html 映射）" % t,
                  file=sys.stderr)
        out.append('<span class="badge %s">%s</span>' % (cls.get(t, "badge-fork"), t))
    return "".join(out)


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
    font-size: 30px; font-weight: 700; color: var(--intel-blue);
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

  .sort-banner {
    margin: 28px 0 18px;
    background: linear-gradient(90deg, #e8f1fb, #f0f7fd);
    border: 1px solid #c8e0f5; border-radius: 10px;
    padding: 10px 16px; font-size: 13px; color: var(--intel-blue-dark);
    text-align: center; line-height: 1.8;
  }
  .sort-banner .dot {
    width: 8px; height: 8px; border-radius: 50%; background: #2da44e;
    display: inline-block; vertical-align: middle; margin-right: 6px;
  }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(460px, 100%), 1fr)); gap: 16px; }

  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    padding: 18px 20px; display: flex; flex-direction: column; gap: 10px;
    box-shadow: 0 1px 3px rgba(31,35,40,0.06);
    transition: box-shadow 0.15s ease;
  }
  .card:hover { box-shadow: 0 4px 12px rgba(31,35,40,0.12); }

  .card-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
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
    margin-left: auto;
  }
  .card-desc { font-size: 13px; color: var(--text-muted); flex: 1; }
  .card-desc a { color: var(--intel-blue); text-decoration: none; }
  .card-desc a:hover { text-decoration: underline; }

  .card-footer {
    display: flex; align-items: center; justify-content: space-between;
    gap: 8px; flex-wrap: wrap;
    padding-top: 10px; border-top: 1px solid #eef0f2;
  }
  .author { font-size: 13px; color: var(--text-muted); }
  .author a { color: var(--intel-blue); text-decoration: none; font-weight: 600; }
  .links { display: flex; gap: 8px; flex-wrap: wrap; }
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

<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "f0680eba26ee45eda7de7340d6dfde65"}'></script><!-- End Cloudflare Web Analytics -->
</head>
<body>
<div class="container">

  <header>
    <h1>IntelGpu-ComfyUI-Collection</h1>
    <p class="note">以下项目多数由社群中作者维护，少量是Intel官方维护（官方的这几个项目需要紧盯）</p>
    <div class="chips">
__NAV__
    </div>
  </header>

  <div class="sort-banner">
    <span class="dot"></span> 项目按「最后更新时间」自动排序，每 2 小时刷新，下次刷新时间：<span id="next-refresh">—</span>
  </div>

  <div class="grid">

__CARDS__

  </div>

  <footer>
    由 <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection" target="_blank">IntelGpu-ComfyUI-Collection</a> 自动生成 ·
    <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/blob/main/README.md" target="_blank">README 源文件</a> ·
    最新生成时间：__GEN_TIME__
  </footer>

</div>
<script>
  (function () {
    function pad(n) { return String(n).padStart(2, "0"); }
    var now = new Date();
    // cron 计划: UTC 00/02/04/.../22 (每 2 小时, GitHub Actions 用 UTC)。
    // getTime() 本身就是 UTC 时间戳，用 getUTC* 计算下一个刷新点，
    // Date.UTC 构造出绝对时间，再用本地 get* 显示（自动转本地时区）。
    var nextUtcHour = Math.floor(now.getUTCHours() / 2) * 2 + 2;
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
    gen_time = datetime.now(TZ_CN).strftime("%Y/%m/%d %H:%M:%S")
    return (INDEX_HTML
            .replace("__NAV__", nav_html("index.html"))
            .replace("__CARDS__", cards)
            .replace("__GEN_TIME__", gen_time))


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
            # href/文字都是纯 URL；说明文字（如"（目录：...）"）放在链接外
            u = URL_RE.search(val)
            if u:
                url = u.group(0)
                suffix = val[len(url):].strip()
                pairs.append((label, url, url, suffix))
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
        '<div class="addr-row">%s<a href="%s" target="_blank">%s</a>%s</div>'
        % ('<span class="label">%s：</span>' % lbl if lbl else "", u, t,
           (" " + suf) if suf else "")
        for lbl, u, t, suf in item["urls"]
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
    font-size: 30px; font-weight: 700; color: var(--intel-blue);
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

<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "f0680eba26ee45eda7de7340d6dfde65"}'></script><!-- End Cloudflare Web Analytics -->
</head>
<body>
<div class="container">

  <header>
    <h1>IntelGpu-ComfyUI-Collection</h1>
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
        # 引用块：' > <img ...>' 图片直接显示（去引用前缀）；' > 文本' 转 blockquote
        mq = re.match(r"^>\s*(.+)$", h)
        if mq:
            content = mq.group(1).strip()
            if content.startswith("<img"):
                # 点击图片 -> 新标签页打开全尺寸原图
                mimg = re.search(r"src=\"([^\"]+)\"", content)
                if mimg:
                    content = '<a href="%s" target="_blank" class="img-link">%s</a>' % (mimg.group(1), content)
                parts.append(content + "<br>")
            else:
                parts.append('<blockquote>%s</blockquote><br>' % content)
            continue
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
    font-size: 30px; font-weight: 700; color: var(--intel-blue);
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
  .card-desc a { color: var(--intel-blue); text-decoration: none; }
  .card-desc a:hover { text-decoration: underline; }
  .card-desc blockquote {
    border-left: 3px solid var(--intel-blue); background: #f0f6fc;
    margin: 6px 0; padding: 6px 10px; border-radius: 6px;
  }
  .card-desc img { width: 1200px; max-width: 100%; height: auto; }
  .card-desc .img-link img { cursor: zoom-in; }
  .card-desc .img-link img:hover { opacity: 0.92; }

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

<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "f0680eba26ee45eda7de7340d6dfde65"}'></script><!-- End Cloudflare Web Analytics -->
</head>
<body>
<div class="container">

  <header>
    <h1>IntelGpu-ComfyUI-Collection</h1>
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
    font-size: 30px; font-weight: 700; color: var(--intel-blue);
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

<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "f0680eba26ee45eda7de7340d6dfde65"}'></script><!-- End Cloudflare Web Analytics -->
</head>
<body>
<div class="container">

  <header>
    <h1>IntelGpu-ComfyUI-Collection</h1>
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
      <img alt="group_logo" src="https://raw.githubusercontent.com/allanmeng/IntelGpu-ComfyUI-Collection/main/assets/group_logo_630.jpg">
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
    font-size: 30px; font-weight: 700; color: var(--intel-blue);
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
    max-width: 700px; margin: 40px auto; text-align: center;
    background: var(--card); border: 1px solid var(--border); border-radius: 16px;
    padding: 32px 28px; box-shadow: 0 1px 3px rgba(31,35,40,0.06);
  }
  .group-hero img { width: 630px; height: 630px; max-width: 100%; object-fit: cover; border-radius: 12px; }
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

<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "f0680eba26ee45eda7de7340d6dfde65"}'></script><!-- End Cloudflare Web Analytics -->
</head>
<body>
<div class="container">

  <header>
    <h1>IntelGpu-ComfyUI-Collection</h1>
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
# logs.html + logs/<slug>.html —— 执行日志库独立规则 + 独立模板
#
# 设计要点（2026-10-26 Allan 定）：
# - 原始日志本体留在 log-analysis/，本模块只读不写，不生成任何中间文件；
# - 页面产物 = 站根 logs.html（索引）+ logs/<slug>.html（单份详情）；
# - 指标全部从日志正文正则抽取，不依赖人工标注；文件名仅提供对比轴（工作流/方案/卡/内存）；
# - 本地绝对路径在**渲染时**脱敏，原始 txt 保持原样。
# ---------------------------------------------------------------------------

LOGS_DIRNAME = "log-analysis"

# 日志格式固定，指标用正则直取（不引第三方解析器）
_RE_PROMPT_SPLIT = re.compile(r"^\[INFO\] got prompt\s*$", re.M)
_RE_EXEC = re.compile(
    r"Prompt executed in (?:(\d+):(\d+):(\d+)|(\d+):(\d+)|([\d.]+) seconds)")
_RE_PROGRESS = re.compile(
    r"(\d+)/(\d+) \[[\d:]+<[\d:]+,?\s*([\d.]+)(s/it|it/s)(?=[,\]])")
_RE_STAGED = re.compile(r"prepared for dynamic VRAM loading\.\s*(\d+)MB Staged")
_RE_VRAM_FREE = re.compile(r"VRAMdebug: freed memory:\s*([\d,]+)")
_RE_ATTN = re.compile(r"attention (CUTE(?:_[A-Za-z0-9_]+)?|fallback)")
_RE_QUANT = re.compile(r"Native ops:\s*(.*?)\s*,\s*emulated ops:\s*(.*)")
# 模型清单：原生日志打印 storage policy 真实路径；OmniXPU 路径不打印，退化为类名
_RE_MODEL_POLICY = re.compile(r"Model storage policy:[^\n]*?paths=\[([^\]]*)\]")
_RE_QUOTED = re.compile(r"'([^']+)'")
_RE_LOAD = re.compile(r"Requested to load ([A-Za-z0-9_]+)")
# 形如 D:\\ComfyUI-intel-aki-v1.1\\ComfyUI\\models\\vae\\x.safetensors（日志内为字面双反斜杠）
_RE_LPATH = re.compile(r"[A-Za-z]:\\\\[^\s'\"\],)]*")

_RE_DATE = re.compile(r"^(20\d{6})$")
_RE_DATE_TIME = re.compile(r"^(20\d{6})-?(\d{2})(\d{2})$")
_RE_VRAM = re.compile(r"^\d+\s?G(?:B)?$", re.I)  # 系统内存（64G），非显存；字段名沿用历史命名
_RE_CARD = re.compile(r"^(?:A|B)\d{2,4}$", re.I)
_RE_PRECISION = re.compile(r"^(?:int|fp|bf|nf|w)\d+[a-z0-9_]*$", re.I)

_LOGS_SCHEME_HINTS = ("omnixpu", "pytorch", "torch", "原生", "加速", "aimdo")
_LOGS_TEST_HINTS = ("冷启", "热启", "首跑", "实测", "对比")


def _esc(v):
    """HTML 文本转义（日志正文含 < > & 等字符）。"""
    return _html.escape("" if v is None else str(v), quote=True)



def _logs_sanitize(text):
    """把 Windows 绝对路径收敛成 <ComfyUI>/... —— 仅在渲染阶段做，源文件不动。

    模型不一定放在 ComfyUI 目录树里（实测存在 E:\\model\\xxx.safetensors 这种外部
    模型目录），这类路径退化成 <本地路径>/<文件名>：目录结构隐藏，文件名保留，
    否则日志正文里连加载的是哪个模型都看不出来。
    """
    def _repl(m):
        raw = m.group(0).replace("\\\\", "\\")
        idx = raw.lower().find("\\comfyui\\")
        if idx >= 0:
            return "<ComfyUI>/" + raw[idx + len("\\comfyui\\"):].replace("\\", "/")
        base = raw.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        if base and "." in base:
            return "<本地路径>/" + base
        return "<本地路径>"
    return _RE_LPATH.sub(_repl, text)


def _logs_expand_parts(parts):
    """拆开 h3_FL2VA-B70 这类「工作流-卡」粘连段。

    仅当段内 token 命中强模式（显卡/内存/精度/日期）时才拆，
    且只用强模式 token 判断，避免把 comfy-aimdo-xpu 这类工作流名误拆。

    ⚠️ 第 5 段（如 `64G`）是**系统内存**，不是显存：2026-10-30 Allan 确认，
    B580 实际 xpu_total≈11.7GB、B70 为 32GB，都不可能标 64G。字段名沿用
    历史变量名 vram / 正则 _RE_VRAM，但对外文案一律写「内存」。
    """
    out = []
    for p in parts:
        if (_RE_CARD.match(p) or _RE_VRAM.match(p) or _RE_PRECISION.match(p)
                or _RE_DATE.match(p) or _RE_DATE_TIME.match(p)):
            out.append(p)
            continue
        toks = p.split("-")
        if len(toks) > 1 and any(_RE_CARD.match(t) or _RE_VRAM.match(t) for t in toks):
            out.extend(t for t in toks if t)
        else:
            out.append(p)
    return out


def _logs_parse_name(stem):
    """文件名 → 对比轴。字段位置不限，靠内容识别；识别不了的片段拼回工作流名。

    已支持的写法：
      推荐    20261026-2157_Krea2Edit_omnixpu加速_B70_64G_冷启+热启   （带时刻，横线分隔）
      兼容    202610271640_Qwenimage2.1_omnixpu加速_B70_64G_冷启+热启  （时刻连写，命中同名情况）
      新规范  20261026_Krea2Edit_omnixpu加速_B70_64G_冷启+热启        （无时刻）
      只跑一次 20261028_SeedVR超分放大_omnixpu加速_B70_64G_冷启         （单次：只写实际跑过的）
      只跑一次 20261028_SeedVR超分放大_omnixpu加速_B70_64G_热启         （同上，这次是热启）
      旧写法  omnixpu加速_Krea2Edit_B70_64G_冷启+热启                 （字段顺序任意）
    下划线会切断 h3_FL2VA 这类名字，因此识别不了的片段用 _ 拼回，而不是丢弃。
    「测试类型」段必须照实写：只跑了一次就只写那一次的真实身份（冷启 或 热启），
    不要补 +热启。同一份日志里只有一次执行时，页面无法从日志正文看出它到底是
    冷启还是热启（正文没有「本次是第几次」的信息），完全依赖这段关键词。
    """
    meta = {"date": "", "time": "", "workflow": "", "scheme": "", "card": "",
            "vram": "", "precision": "", "test": ""}
    leftovers = []
    for part in _logs_expand_parts([p for p in stem.split("_") if p]):
        dtm = _RE_DATE_TIME.match(part)
        if not meta["date"] and dtm:
            meta["date"] = dtm.group(1)
            meta["time"] = "%s:%s" % (dtm.group(2), dtm.group(3))
        elif not meta["date"] and _RE_DATE.match(part):
            meta["date"] = part
        elif not meta["vram"] and _RE_VRAM.match(part):
            meta["vram"] = part.upper().replace(" ", "")
        elif not meta["card"] and _RE_CARD.match(part):
            meta["card"] = part.upper()
        elif not meta["precision"] and _RE_PRECISION.match(part):
            meta["precision"] = part.lower()
        elif not meta["test"] and any(h in part for h in _LOGS_TEST_HINTS):
            meta["test"] = part
        elif not meta["scheme"] and any(h in part.lower() for h in _LOGS_SCHEME_HINTS):
            meta["scheme"] = part
        else:
            leftovers.append(part)
    meta["workflow"] = "_".join(leftovers)
    return meta


def _logs_scan_segment(seg):
    """单次执行（两次 got prompt 之间）→ 指标。"""
    seconds = None
    m = _RE_EXEC.search(seg)
    if m:
        # 两种写法并存：老版打印 `1234.56 seconds`；新版长任务打印 `00:19:14`
        # （20261028 的 SeedVR 日志实测），也兼容 `19:14`。
        if m.group(1) is not None:
            seconds = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        elif m.group(4) is not None:
            seconds = int(m.group(4)) * 60 + int(m.group(5))
        else:
            seconds = float(m.group(6))

    steps = sec_per_it = None
    prog = _RE_PROGRESS.findall(seg)
    if prog:
        # tqdm 有两种收尾写法：`1.88s/it`（已有）与 `1.76it/s`（20261027 日志实测），
        # 后者取倒数换算成 s/it，保持表格同一单位。
        _, total, rate, unit = prog[-1]
        rate = float(rate)
        if unit == "it/s":
            sec_per_it = round(1.0 / rate, 2) if rate else None
        else:
            sec_per_it = rate
        # total==1 时那不是「步数」，是分块任务的一块（20261028 SeedVR 的超分是
        # 8 个 chunk 各自 `1/1` 进度条）。写 1 会误导，留空更诚实；s/it 仍然保留，
        # 它是最后一块的真实速率。
        total = int(total)
        steps = total if total > 1 else None

    staged = [int(x) for x in _RE_STAGED.findall(seg)]
    freed = [int(x.replace(",", "")) for x in _RE_VRAM_FREE.findall(seg)]

    attn = {}
    for name in _RE_ATTN.findall(seg):
        attn[name] = attn.get(name, 0) + 1

    native = emulated = ""
    m = _RE_QUANT.search(seg)
    if m:
        native = " ".join(m.group(1).split())
        emulated = " ".join(m.group(2).split())

    return {
        "seconds": seconds,
        "steps": steps,
        "sec_per_it": sec_per_it,
        "staged_mb": max(staged) if staged else None,
        "freed_mb": round(sum(freed) / 1048576.0, 1) if freed else None,
        "attn": attn,
        "native_ops": native,
        "emulated_ops": emulated,
    }


_RE_TE_NAME = re.compile(
    r"(?:^|[_\-.])t5(?:$|[_\-.x])|text_encoder|clip"
    r"|qwen\d(?:\.\d)*vl|qwen\d(?:\.\d)+|umt5|gemma|bert|(?:^|[_\-.])llm")

# 正文里被引号包住的模型文件名（无反斜杠/斜杠）。用于 policy 的 paths=[] 时兜底：
# 20261030 的 h3_FL2AV 就是靠 mmproj 报错里的 'qwen3vl_32b_minimax_h3-Q4_K_M.gguf'
# 才拿到 TE 真名，否则只能显示类名 MiniMaxH3TEModel_。
_RE_ANYFILE = re.compile(
    r"'([^'\\/\r\n]+\.(?:gguf|safetensors|ckpt|pth|pt|bin))'")


def _logs_model_role(path_lower):
    """按模型目录判定角色（路径已统一成反斜杠小写）。

    ⚠️ 底模不一定放在 models\\diffusion_models\\ 下：实测 20261026 那份日志的
    `Model storage policy` 打印的是 E:\\model\\krea2_turbo_int8_convrot.safetensors
    （模型放在 ComfyUI 目录树之外、目录是单数 model），只认 diffusion_model / unet
    会把底模判成空角色并整行丢掉。

    同理，放在树外的 TE 也没有 text_encoder 目录线索：20261027 的
    `E:\\model\\qwen3vl_8b_int8_convrot.safetensors` 曾因此被误判成底模，
    结果是底模出现两个文件名、TE 退化成类名 `QwenImage21TEModel_`。
    因此目录线索全落空时，再按文件名关键字兜底：
      vl 系列 `qwen3vl_8b` / 带小数的 `qwen3.5_9b`（Moss 的 TE）/ t5 / gemma …
    ⚠️ 不能靠「policy 行后紧跟的 Requested to load 类名」定角色：实测 20261027 的
    Qwen 日志里 WanVAE 的 Requested 出现在 TE 那行 policy 之后，顺序不可信。
    """
    name = re.split(r"[\\/]", path_lower)[-1]
    if "lora" in path_lower:
        return "lora"
    if ("text_encoder" in path_lower or "clip" in path_lower
            or _RE_TE_NAME.search(name)):
        return "te"
    if "vae" in path_lower:
        return "vae"
    if ("diffusion_model" in path_lower or "unet" in path_lower
            or "checkpoint" in path_lower or "\\model\\" in path_lower
            or "\\models\\" in path_lower):
        # `\models\` 是兜底：底模也可能放在自定义子目录里（20261028 的 SeedVR2 就在
        # models\SEEDVR2\seedvr2_3b_int8_convrot.safetensors，既没有 diffusion_model
        # 也没有单数 \model\）。vae / text_encoder / lora 更靠前的判断已经先命中，
        # 能走到这里的就是底模。
        return "base"
    return ""


def _logs_model_role_class(name):
    """模型类名 → 角色。OmniXPU 日志只有类名，靠命名约定归类。"""
    n = name.lower()
    if "vae" in n:
        return "vae"
    if "temodel" in n or "clip" in n:
        return "te"
    return "base"


def _logs_extract_models(text):
    """底模 / TE / VAE / LoRA 清单。

    优先 Model storage policy 里的真实文件名（只有 pytorch 原生日志打印这一行）；
    OmniXPU 日志不打印，退化为 Requested to load 的模型类名——精度较低但不留空。
    LoRA 在两种日志里都不出现文件名，取不到就留空、页面不显示该行。

    兜底按「角色」逐个补而不是按「整份日志」补：只要某个角色没取到文件名就用类名顶上，
    避免因为某个目录没认出来导致整行（例如底模）从卡片上消失。
    """
    out = {"base": [], "te": [], "vae": [], "lora": [], "from_file": False}
    for paths in _RE_MODEL_POLICY.findall(text):
        for raw in _RE_QUOTED.findall(paths):
            p = raw.replace("\\\\", "\\")
            role = _logs_model_role(p.replace("/", "\\").lower())
            if not role:
                continue
            name = re.split(r"[\\/]", p)[-1]
            if name not in out[role]:
                out[role].append(name)
                out["from_file"] = True
    # policy 的 paths 可能整个是空的（模型已在显存里，不再打印路径），但正文别处
    # 仍可能带出文件名。只填空缺的角色，不覆盖 policy 已给出的结果。
    for name in _RE_ANYFILE.findall(text):
        role = _logs_model_role(name.lower())
        if role and not out[role] and name not in out[role]:
            out[role].append(name)
            out["from_file"] = True
    missing = [k for k in ("base", "te", "vae") if not out[k]]
    if missing:
        for cls in sorted(set(_RE_LOAD.findall(text))):
            role = _logs_model_role_class(cls)
            if role in missing and cls not in out[role]:
                out[role].append(cls)
    return out


def _logs_fmt_date(d):
    """20261026 -> 2026-10-26；识别不了就原样返回。"""
    d = d or ""
    if re.fullmatch(r"20\d{6}", d):
        return "%s-%s-%s" % (d[:4], d[4:6], d[6:])
    return d


def _logs_git_added_at(rel_path):
    """文件首次入库时间 → ("YYYYMMDD", "HH:MM")；取不到返回空串对。

    用 --follow + --diff-filter=A 穿透 git mv 的重命名，拿到最初入库那个 commit。
    ⚠️ CI 里 actions/checkout 默认 fetch-depth: 1 只有一条提交，查不到历史 →
       logs-page.yml 必须显式写 fetch-depth: 0，否则这里永远返回空。
    """
    try:
        proc = subprocess.run(
            ["git", "log", "--follow", "--diff-filter=A", "--format=%aI", "--", rel_path],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            universal_newlines=True, timeout=20)
    except Exception:  # noqa: BLE001  git 缺失 / 超时 / 非仓库
        return "", ""
    if proc.returncode != 0:
        return "", ""
    lines = [x.strip() for x in (proc.stdout or "").splitlines() if x.strip()]
    if not lines:
        return "", ""
    iso = lines[-1]                      # 最早一条 = 首次入库
    if len(iso) < 16:
        return "", ""
    return iso[0:4] + iso[5:7] + iso[8:10], iso[11:16]


def _logs_when(path, name_date, name_time=""):
    """日期 + 时刻。**完全不使用文件 mtime。**

    优先级：
      1) 文件名里的 -HHMM   推荐写法，跨机器 / CI 完全一致
      2) git 首次入库时间    自动兜底，零人工维护

    mtime 弃用实证（2026-10-26）：四份 20261023 日志的 mtime 是
    20:27:54.603 / .604 / .605 / .606 —— 毫秒级连续，那是批量拷贝/解压的时刻，
    不是运行时刻；CI 的 checkout 还会把它重置成检出时刻。两个来源都不可信。
    """
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    if name_date:
        if name_time:
            return name_date, name_time, "name"
        return name_date, _logs_git_added_at(rel)[1], "git"
    gdate, gtime = _logs_git_added_at(rel)
    return gdate, gtime, "git"


def _logs_single_label(test):
    """单次执行日志的冷/热标签：由文件名「测试类型」段决定。

    一份日志里只有一次执行时，**不能**按位置断言「第 1 次 = 冷启」——那次的
    真实身份取决于跑之前 ComfyUI 有没有刚启动过：
      · 刚启动 → 冷启
      · 已跑过别的任务 → 热启（内存/权重已经热了）
    这种情况只能靠文件名标注，所以测试类型段要照实写（冷启 / 热启）。
    含「热启」且不含「冷启」判为热启，其余（含只写 冷启、或没写）按冷启。
    """
    return "热启" if ("热启" in test and "冷启" not in test) else "冷启"


def _logs_analyze(path):
    """读一份日志 → 条目（含逐次执行指标 + 脱敏全文）。"""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()

    body = _logs_sanitize(text)
    segs = _RE_PROMPT_SPLIT.split(text)
    if _RE_PROMPT_SPLIT.search(text):
        # split 产生的首段是首个 got prompt 之前的内容（启动日志），丢弃后配对
        segs = segs[1:]
    else:
        segs = [text]

    fname = os.path.basename(path)
    entry = _logs_parse_name(os.path.splitext(fname)[0])

    runs = []
    for i, seg in enumerate(segs):
        st = _logs_scan_segment(seg)
        st["label"] = "冷启" if i == 0 else "热启"
        runs.append(st)
    runs = [r for r in runs if r["seconds"] is not None]
    # 只有一次执行时不能按位置断言冷启：这次可能是热启（接在别的执行之后跑）。
    # 由文件名「测试类型」段决定，见 _logs_single_label()。
    if len(runs) == 1:
        runs[0]["label"] = _logs_single_label(entry.get("test", ""))

    date, time_str, time_src = _logs_when(path, entry["date"], entry.get("time", ""))
    entry.update({
        "file": fname,
        "runs": runs,
        "body": body,
        "size": len(text.encode("utf-8")),
        "models": _logs_extract_models(text),
        "date": date,
        "date_display": _logs_fmt_date(date),
        "time": time_str,
        "time_source": time_src,
    })
    entry["slug"] = ""
    entry["title"] = " / ".join(
        x for x in [entry["workflow"], entry["scheme"], entry["card"], entry["vram"]] if x
    ) or os.path.splitext(fname)[0]
    entry["cold"] = next((r["seconds"] for r in runs if r["label"] == "冷启"), None)
    entry["warm"] = next((r["seconds"] for r in runs if r["label"] == "热启"), None)
    return entry


def _logs_collect(logs_dir):
    """扫目录 → 日志条目列表（按日期 + 时间倒排，新→旧）。只收 .txt，不再处理截图。"""
    entries = []
    if not os.path.isdir(logs_dir):
        return entries
    for fname in sorted(os.listdir(logs_dir)):
        path = os.path.join(logs_dir, fname)
        if os.path.isfile(path) and fname.lower().endswith(".txt"):
            entries.append(_logs_analyze(path))
    # 日期 → 时刻 → 工作流/方案。时刻缺失的用 "00:00"，倒序时落到该日期末尾。
    entries.sort(key=lambda e: (e["date"], e["time"] or "00:00",
                                e["workflow"], e["scheme"]), reverse=True)
    return entries


def _logs_uniq_slug(entries):
    """详情页文件名。**只有时刻来自文件名时才把时刻拼进去。**

    理由：文件名里的时刻是稳定的（跟着文件走），拼进 slug 后同一天跑两次同组合也不会撞名；
    而 git 兜底时刻会随重命名/历史变化而漂移，若拼进 slug 会让已发布的 URL 失效、
    并在 logs/ 里留下孤儿文件。存量日志因此保持原有 slug 不变。
    """
    seen = {}
    for e in entries:
        date_part = e["date"]
        if date_part and e.get("time") and e.get("time_source") == "name":
            date_part = "%s-%s" % (date_part, e["time"].replace(":", ""))
        base = "-".join(x for x in [date_part, e["workflow"], e["scheme"],
                                    e["card"], e["vram"]] if x)
        # 乘号转 x：`(768×1376)` 直接过滤会变成 `-768-1376-`，可读性差。
        base = base.replace("×", "x").replace("✕", "x")
        base = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5._-]+", "-", base)
        base = re.sub(r"-{2,}", "-", base).strip("-.") or "log"
        n = seen.get(base, 0) + 1
        seen[base] = n
        e["slug"] = base if n == 1 else "%s-%d" % (base, n)
    return entries


def _logs_fmt_sec(v):
    if v is None:
        return "—"
    return ("%.2f s" % v) if v >= 100 else ("%.2f s" % v)


def _logs_stat_pills(run, skip=()):
    """一次执行的关键指标 → 徽章组。skip 用于详情页表格里去掉已单独成列的项。"""
    out = []
    if run.get("sec_per_it") and "sec_per_it" not in skip:
        out.append('<span class="pill"><b>%.2f</b> s/it</span>' % run["sec_per_it"])
    if run.get("steps") and "steps" not in skip:
        out.append('<span class="pill"><b>%d</b> steps</span>' % run["steps"])
    if run.get("staged_mb") and "staged_mb" not in skip:
        out.append('<span class="pill"><b>%s</b> MB staged</span>' % format(run["staged_mb"], ","))
    if run.get("freed_mb"):
        out.append('<span class="pill"><b>%s</b> MB freed</span>' % format(run["freed_mb"], ","))
    for name, cnt in sorted((run.get("attn") or {}).items(), key=lambda kv: -kv[1]):
        out.append('<span class="pill pill-attn">%s ×%d</span>' % (_esc(name), cnt))
    return "".join(out)


_LOGS_MODEL_LABELS = [("base", "底模"), ("te", "TE"), ("vae", "VAE"), ("lora", "LoRA")]


def _logs_break_name(name):
    """长模型文件名给浏览器优先断行点。

    断点优先级：扩展名前 > 下划线后。前者保证 .safetensors 不被劈成 'safe'/'tensors'；
    后者让 `krea2_turbo_int8_convrot` 在 `_` 处换行，而不是从单词中间硬切。
    """
    safe = _esc(name)
    for ext in (".safetensors", ".gguf", ".ckpt", ".pth", ".bin", ".pt"):
        safe = safe.replace(ext, "<wbr>" + ext)
    return safe.replace("_", "_<wbr>")


def _logs_model_rows(models):
    """底模 / TE / VAE / LoRA 行；取不到的类别直接不渲染（LoRA 通常没有）。

    值可能是真文件名，也可能是类名兜底（日志没打印 storage policy 时）。
    后者用弱化样式 + title 标出来，避免读者把 `Krea2` 当成文件名。
    """
    rows = []
    for key, label in _LOGS_MODEL_LABELS:
        vals = (models or {}).get(key) or []
        if not vals:
            continue
        cells = []
        for v in vals:
            if re.search(r"\.[A-Za-z0-9]{2,16}$", v):
                cells.append(_logs_break_name(v))
            else:
                cells.append('<span class="model-cls" title="该日志未打印文件名，'
                             '此处为模型类名">%s</span>' % _esc(v))
        rows.append('<div class="model-row"><i>%s</i><span>%s</span></div>'
                    % (label, " /<wbr> ".join(cells)))
    return "\n          ".join(rows)


LOGS_GPU_IMG = {"B70": "assets/b70.jpg", "B580": "assets/b580.jpg"}


def _logs_gpu_img(card):
    """按显卡型号返回右列配图 HTML；未登记的型号不插图。"""
    m = re.search(r"B(?:70|580)", (card or "").upper())
    if not m:
        return ""
    name = m.group(0)
    src = LOGS_GPU_IMG.get(name)
    if not src:
        return ""
    return ('        <img class="log-gpu" src="%s" alt="Intel Arc %s" title="%s">\n'
            % (src, name, name))


def _logs_card(e):
    """单份日志卡片：三列 —— 左=日期时间，中=内容，右=标签（右上）+ 显卡图（居中）。"""
    tags = []
    if e["scheme"]:
        tags.append('<span class="tag tag-scheme">%s</span>' % _esc(e["scheme"]))
    if e["card"]:
        tags.append('<span class="tag tag-card" title="显卡">%s</span>' % _esc(e["card"]))
    if e["vram"]:
        tags.append('<span class="tag tag-vram" title="内存">%s</span>' % _esc(e["vram"]))

    nums = []
    for r in e["runs"]:
        nums.append('<span class="st"><i>%s</i><b>%s</b></span>'
                    % (_esc(r["label"]), _logs_fmt_sec(r["seconds"])))
    if not nums:
        nums.append('<span class="st"><i>耗时</i><b>—</b></span>')

    models_html = _logs_model_rows(e["models"])
    models_block = ('        <div class="log-models">\n          %s\n        </div>\n'
                    % models_html) if models_html else ""

    when = ('<div class="log-when">'
            '<span class="log-date">%s</span>'
            '<span class="log-time">%s</span>'
            '</div>' % (
                _esc(e.get("date_display") or "—"),
                _esc(e.get("time") or "—")))

    return (
        '    <a class="log-card" href="logs/%s.html">\n'
        '      %s\n'
        '      <div class="log-main">\n'
        '        <div class="log-wf">%s</div>\n'
        '        <div class="log-nums">%s</div>\n'
        '%s'
        '        <div class="log-file">%s</div>\n'
        '      </div>\n'
        '      <div class="log-side">\n'
        '        <div class="log-tags">%s</div>\n'
        '%s'
        '      </div>\n'
        '    </a>' % (
            _esc(e["slug"]), when, _esc(e["workflow"] or "未命名"), "".join(nums),
            models_block, _esc(e["file"]), "".join(tags), _logs_gpu_img(e["card"])))


LOGS_CSS = """  :root {
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
    background: var(--bg); color: var(--text); line-height: 1.6;
  }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px 20px 48px; }
  header { text-align: center; padding: 40px 0 24px; }
  header h1 { font-size: 30px; font-weight: 700; color: var(--intel-blue); }
  header .note { margin-top: 12px; font-size: 14px; color: var(--text-muted); }
  .chips { margin-top: 14px; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
  .chip {
    font-size: 12px; padding: 5px 12px; border-radius: 999px;
    background: #e8f1fb; color: var(--intel-blue-dark); border: 1px solid #c8e0f5;
    text-decoration: none; display: inline-block;
  }
  .chip-active { background: var(--intel-blue); color: #fff; border-color: var(--intel-blue); }
  .sec-title { font-size: 17px; font-weight: 600; margin: 32px 0 14px; }
  .sort-banner {
    margin: 28px 0 8px; background: linear-gradient(90deg, #e8f1fb, #f0f7fd);
    border: 1px solid #c8e0f5; border-radius: 10px; padding: 10px 16px;
    font-size: 13px; color: var(--intel-blue-dark); text-align: center; line-height: 1.8;
  }
  .mx-block {
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    padding: 16px 18px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(31,35,40,0.06);
  }
  .mx-wrap { overflow-x: auto; }
  table.mx { width: 100%; border-collapse: collapse; font-size: 13px; white-space: nowrap; }
  table.mx th {
    text-align: left; font-weight: 600; color: var(--text-muted); font-size: 12px;
    padding: 6px 10px; border-bottom: 1px solid var(--border);
  }
  table.mx th.mx-num { text-align: right; }
  table.mx td { padding: 7px 10px; border-bottom: 1px solid #eef0f2; }
  table.mx tr:last-child td { border-bottom: none; }
  table.mx a { color: var(--intel-blue); text-decoration: none; }
  table.mx a:hover { text-decoration: underline; }
  .mx-num { text-align: right; font-variant-numeric: tabular-nums; }
  .log-grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
  .log-card {
    display: grid; grid-template-columns: 88px minmax(0, 1fr) auto; gap: 0 16px;
    align-items: start;
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    padding: 16px 18px; text-decoration: none; color: inherit;
    box-shadow: 0 1px 3px rgba(31,35,40,0.06);
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
  }
  .log-when {
    display: flex; flex-direction: column; gap: 2px; padding-right: 14px;
    border-right: 1px solid #eef0f2; text-align: right; font-variant-numeric: tabular-nums;
  }
  .log-date { font-size: 13px; font-weight: 600; color: var(--text); }
  .log-time { font-size: 12px; color: var(--text-muted); }
  .log-main { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .log-side {
    display: flex; flex-direction: column; gap: 10px; align-items: center;
    align-self: stretch;
  }
  .log-card:hover { box-shadow: 0 4px 12px rgba(31,35,40,0.12); border-color: #c8e0f5; }
  .log-wf { font-size: 15px; font-weight: 600; }
  .log-side .log-tags {
    align-self: flex-end; display: flex; gap: 6px; flex-wrap: nowrap;
    justify-content: flex-end; align-items: center;
  }
  .log-gpu {
    display: block; width: 112px; height: 112px; object-fit: cover;
    border-radius: 8px; box-shadow: 0 1px 4px rgba(31,35,40,0.18);
    margin-top: auto; margin-bottom: auto;
  }
  .tag {
    font-size: 12px; line-height: 18px; padding: 1px 8px; border-radius: 6px;
    background: #f3f4f6; border: 1px solid #e5e7eb; color: var(--text-muted);
    white-space: nowrap;
  }
  .tag-scheme {
    color: var(--intel-blue-dark); background: #e8f1fb; border-color: #c8e0f5;
  }
  .tag-card {
    color: #6b3fc4; background: #f4efff; border-color: #ddd0fa;
  }
  .tag-vram {
    color: #9a5b00; background: #fff5e2; border-color: #f2dcaf;
  }
  .log-nums { display: flex; gap: 18px; flex-wrap: wrap; }
  .log-nums .st { display: flex; flex-direction: column; }
  .log-nums .st i { font-style: normal; font-size: 11px; color: var(--text-muted); }
  .log-nums .st b { font-size: 17px; font-variant-numeric: tabular-nums; }
  .log-models {
    display: flex; flex-direction: column; gap: 3px;
    padding-top: 10px; border-top: 1px dashed #e5e7eb;
  }
  .model-row { display: flex; gap: 8px; font-size: 12px; align-items: baseline; }
  .model-row i {
    font-style: normal; color: var(--text-muted); flex: 0 0 auto;
    min-width: 32px; font-size: 11px;
  }
  .model-row span {
    color: var(--text); overflow-wrap: anywhere; word-break: normal;
    font-family: "Cascadia Mono", Consolas, monospace; font-size: 11px; line-height: 1.5;
  }
  .model-row span.model-cls { color: var(--text-muted); font-style: italic; cursor: help; }
  .pill {
    font-size: 11px; color: var(--text-muted); background: #f3f4f6;
    border: 1px solid #e5e7eb; border-radius: 999px; padding: 2px 8px;
  }
  .pill b { color: var(--text); font-weight: 600; }
  .pill-attn { background: #f0f7fd; border-color: #c8e0f5; color: var(--intel-blue-dark); }
  .log-file { font-size: 11px; color: #8c959f; overflow-wrap: anywhere; word-break: normal; }
  @media (max-width: 700px) {
    .log-card { grid-template-columns: 88px minmax(0, 1fr); }
    .log-side {
      grid-column: 1 / -1; flex-direction: row-reverse; align-items: center;
      justify-content: space-between; gap: 12px;
      border-top: 1px solid #eef0f2; padding-top: 10px; margin-top: 10px;
    }
    .log-side .log-tags {
      align-self: center; flex-wrap: wrap; justify-content: flex-end;
    }
    .log-gpu { width: 88px; height: 88px; margin: 0; }
  }
  .empty { text-align: center; color: var(--text-muted); font-size: 14px; padding: 48px 0; }
  footer { text-align: center; margin-top: 40px; font-size: 12px; color: var(--text-muted); }
  footer a { color: var(--intel-blue); text-decoration: none; }
  .back { display: inline-block; margin-bottom: 18px; font-size: 13px; color: var(--intel-blue); text-decoration: none; }
  .back:hover { text-decoration: underline; }
  .stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(150px, 100%), 1fr)); gap: 10px; margin: 18px 0 8px; }
  .stat-box { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }
  .stat-box i { font-style: normal; display: block; font-size: 11px; color: var(--text-muted); }
  .stat-box b { font-size: 18px; font-variant-numeric: tabular-nums; }
  .runs-note { margin-top: 6px; font-size: 12px; color: var(--text-muted); }
  .raw { margin-top: 10px; background: var(--card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
  .raw summary { cursor: pointer; padding: 12px 16px; font-size: 14px; font-weight: 600; background: #fafbfc; }
  .raw pre {
    margin: 0; padding: 14px 16px; font-size: 12px; line-height: 1.55;
    font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
    overflow-x: auto; white-space: pre; color: #24292f; max-height: 720px; overflow-y: auto;
  }
  .lg-info { color: #57606a; }
  .lg-warn { color: #9a6700; background: #fff8e5; display: block; width: max-content; min-width: 100%; }
  .lg-err { color: #a40e26; background: #fdecee; display: block; width: max-content; min-width: 100%; }
  .lg-omni { color: #005a99; }
  .lg-prog { color: #8c959f; }
"""


LOGS_INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IntelGpu-ComfyUI-Collection - 执行日志</title>
<style>
__CSS__
</style>
</head>
<body>
<div class="container">

  <header>
    <h1>IntelGpu-ComfyUI-Collection</h1>
    <p class="note">从 ComfyUI 运行日志中自动抽取的性能指标</p>
    <div class="chips">
__NAV__
    </div>
  </header>

  <div class="sort-banner">
    <span class="dot"></span>按日期与时刻倒排（新 → 旧） · 指标由脚本从原始日志正则抽取 · 日期与时刻取自文件名（<code>YYYYMMDD-HHMM</code>），未标时刻时回退到首次入库时间 · 点击日志进入全文
  </div>

  <h2 class="sec-title">全部日志</h2>
  <div class="log-grid">
__CARDS__
  </div>

  <footer>
    由 <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection" target="_blank">IntelGpu-ComfyUI-Collection</a> 自动生成 ·
    <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/tree/main/log-analysis" target="_blank">log-analysis/ 原始日志</a>
  </footer>

</div>
</body>
</html>
"""


LOG_DETAIL_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__PAGETITLE__ - 执行日志</title>
<style>
__CSS__
</style>
</head>
<body>
<div class="container">

  <header>
    <h1>IntelGpu-ComfyUI-Collection</h1>
    <p class="note">__SUBTITLE__</p>
    <div class="chips">
__NAV__
    </div>
  </header>

  <a class="back" href="../logs.html">← 返回执行日志</a>

__STATS__

__RUNS__

  <details class="raw" open>
    <summary>原始日志全文（已脱敏本地路径）</summary>
    <pre>__BODY__</pre>
  </details>

  <footer>
    由 <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection" target="_blank">IntelGpu-ComfyUI-Collection</a> 自动生成 ·
    <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/blob/main/log-analysis/__FILEURL__" target="_blank">__FILENAME__ 源文件</a>
  </footer>

</div>
</body>
</html>
"""


def _logs_highlight(body):
    """原始日志按级别染色；纯文本渲染，保持每行原貌（进度条长行靠横向滚动）。"""
    out = []
    for line in body.split("\n"):
        esc = _esc(line)
        if line.startswith("[WARNING]"):
            out.append('<span class="lg-warn">%s</span>' % esc)
        elif "[ERROR]" in line or line.startswith("Error") or "Traceback" in line:
            out.append('<span class="lg-err">%s</span>' % esc)
        elif "[OmniXPU]" in line:
            out.append('<span class="lg-omni">%s</span>' % esc)
        elif line.startswith("[INFO]"):
            out.append('<span class="lg-info">%s</span>' % esc)
        elif "s/it]" in line or "%|" in line:
            out.append('<span class="lg-prog">%s</span>' % esc)
        else:
            out.append(esc)
    return "\n".join(out)


def _logs_detail(e):
    """单份日志详情页（独立模板 LOG_DETAIL_HTML）。

    runs 条数 = 日志里实际出现 Prompt executed 的次数，可以是 1 条：有些工作流
    只跑一次（如 SeedVR 超分放大单次要十几分钟）。这一次可能是冷启、也可能是
    热启（接在别的执行之后跑），标签由文件名决定，页面照着渲染——不出现另一种
    标签的字样，也不留空位，只在指标区补一句说明。
    """
    first = e["runs"][0] if e["runs"] else {}

    boxes = []
    if e["cold"] is not None:
        boxes.append('<div class="stat-box"><i>冷启</i><b>%s</b></div>' % _logs_fmt_sec(e["cold"]))
    if e["warm"] is not None:
        boxes.append('<div class="stat-box"><i>热启</i><b>%s</b></div>' % _logs_fmt_sec(e["warm"]))
        if e["cold"] and e["warm"]:
            boxes.append('<div class="stat-box"><i>热启 vs 冷启</i><b>%.2f×</b></div>'
                         % (e["cold"] / e["warm"]))
    if first.get("sec_per_it"):
        boxes.append('<div class="stat-box"><i>每步耗时</i><b>%.2f s/it</b></div>' % first["sec_per_it"])
    if first.get("staged_mb"):
        boxes.append('<div class="stat-box"><i>峰值 staged</i><b>%s MB</b></div>'
                     % format(first["staged_mb"], ","))
    if first.get("freed_mb"):
        boxes.append('<div class="stat-box"><i>显存回收</i><b>%s MB</b></div>'
                     % format(first["freed_mb"], ","))
    stats = ('  <div class="stat-grid">\n    %s\n  </div>' % "\n    ".join(boxes)) if boxes \
        else '  <p class="empty">这份日志里没有抽到可用的耗时指标。</p>'
    if len(e["runs"]) == 1:
        only = e["runs"][0]["label"]
        other = "热启" if only == "冷启" else "冷启"
        stats += ('\n  <p class="runs-note">该工作流仅执行 1 次（%s），没有%s对比数据。</p>'
                  % (only, other))

    rows = []
    for i, r in enumerate(e["runs"]):
        rows.append(
            "          <tr><td>%s</td><td class=\"mx-num\">%s</td><td class=\"mx-num\">%s</td>"
            "<td class=\"mx-num\">%s</td><td class=\"mx-num\">%s</td><td>%s</td></tr>" % (
                _esc(r["label"]), _logs_fmt_sec(r["seconds"]),
                ("%d" % r["steps"]) if r.get("steps") else "—",
                ("%.2f" % r["sec_per_it"]) if r.get("sec_per_it") else "—",
                format(r["staged_mb"], ",") if r.get("staged_mb") else "—",
                _logs_stat_pills(r, skip=("sec_per_it", "steps", "staged_mb")) or "—"))

    runs_tbl = ""
    if rows:
        runs_tbl = (
            '  <h2 class="sec-title">逐次执行</h2>\n'
            '    <div class="mx-block">\n'
            '      <div class="mx-wrap">\n'
            '        <table class="mx">\n'
            '          <thead><tr><th>阶段</th><th class="mx-num">耗时</th>'
            '<th class="mx-num">步数</th><th class="mx-num">s/it</th>'
            '<th class="mx-num">staged MB</th><th>其他指标</th></tr></thead>\n'
            '          <tbody>\n%s\n'
            '          </tbody>\n'
            '        </table>\n'
            '      </div>\n'
            '    </div>' % "\n".join(rows))

    stamp = " ".join(x for x in [e.get("date_display"), e.get("time")] if x)
    subtitle = "%s · %s" % (e["file"], stamp) if stamp else e["file"]

    return (LOG_DETAIL_HTML
            .replace("__CSS__", LOGS_CSS)
            .replace("__NAV__", nav_html("logs.html", prefix="../"))
            .replace("__PAGETITLE__", _esc(e["title"]))
            .replace("__SUBTITLE__", _esc(subtitle))
            .replace("__STATS__", stats)
            .replace("__RUNS__", runs_tbl)
            .replace("__BODY__", _logs_highlight(e["body"]))
            .replace("__FILEURL__", _esc(urllib.parse.quote(e["file"])))
            .replace("__FILENAME__", _esc(e["file"])))


def build_logs(logs_dir, out_dir):
    """生成 logs.html（索引）+ logs/<slug>.html（详情），返回写出的文件数。"""
    entries = _logs_collect(logs_dir)
    _logs_uniq_slug(entries)

    if entries:
        cards = "\n".join(_logs_card(e) for e in entries)
    else:
        cards = '    <p class="empty">log-analysis/ 下还没有日志。</p>'

    index = (LOGS_INDEX_HTML
             .replace("__CSS__", LOGS_CSS)
             .replace("__NAV__", nav_html("logs.html"))
             .replace("__CARDS__", cards))

    written = 0
    with open(os.path.join(out_dir, "logs.html"), "w", encoding="utf-8") as f:
        f.write(index)
    written += 1
    print("[ok] logs.html written (%d bytes)" % len(index.encode("utf-8")))

    detail_dir = os.path.join(out_dir, "logs")
    os.makedirs(detail_dir, exist_ok=True)
    for e in entries:
        page = _logs_detail(e)
        with open(os.path.join(detail_dir, e["slug"] + ".html"), "w", encoding="utf-8") as f:
            f.write(page)
        written += 1
        print("[ok] logs/%s.html written (%d bytes)"
              % (e["slug"], len(page.encode("utf-8"))))
    return written


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
    ap.add_argument("--logs", action="store_true", help="generate logs.html + logs/*.html from log-analysis/")
    ap.add_argument("--token", default="", help="GitHub token for API queries")
    ap.add_argument("--out-dir", default="", help="output directory (default: repo root)")
    args = ap.parse_args()

    out_dir = args.out_dir or ROOT
    os.makedirs(out_dir, exist_ok=True)
    readme_path = os.path.join(ROOT, "README.md")
    links_path = os.path.join(ROOT, "links.md")
    cloud_path = os.path.join(ROOT, "cloud_drive_collection.md")
    opt_path = os.path.join(ROOT, "comfyui_opt.md")
    logs_path = os.path.join(ROOT, LOGS_DIRNAME)

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

    if args.logs:
        build_logs(logs_path, out_dir)


if __name__ == "__main__":
    main()
