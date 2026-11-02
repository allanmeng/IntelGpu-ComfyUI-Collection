#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""full-logs 聚合页 + 档案同步（纯标准库）。

背景：exelog 走远端生成（推 txt → Action 出 html），full-logs 反过来——
插件在本地产出 json / html / 产物，人工挑选后同步进仓库，页面也在本地渲染。
远端只接收静态文件，不跑任何生成逻辑；本脚本不碰 logs.html、logs/、
log-analysis/，也不碰 scripts/generate_pages.py。

    python scripts/build_full_logs.py                  # 列出待同步（等同 --list）
    python scripts/build_full_logs.py --sync 1,3       # 按序号同步，然后重建页面
    python scripts/build_full_logs.py --sync-all       # 同步全部，然后重建页面
    python scripts/build_full_logs.py --build          # 只重建聚合页
    python scripts/build_full_logs.py --restyle        # 只重灌详情页头部（返回 + 导航）

站点头部（返回按钮 + 导航 chips）不写进插件产物，而是在「同步进 full-logs/」这一步
注入，并用 <!--fl-chrome:start/end--> 包住。所以改头部只要跑一次 --restyle，
不用重新生成任何档案、也不用重启 ComfyUI：
    * 本地插件 logs/ 里的原件保持纯净（单文件可分发、无站内链接）；
    * 剥掉标记块后与原件逐字节相同，已是最新时 --restyle 不写盘（幂等）。

可选：
    --src DIR            插件日志目录（默认见 DEFAULT_SRC，可用 FULLLOG_SRC 覆盖）
    --max-video-mb N     视频超过 N MB 就不随档案发布（0 = 不限，默认 20）
    --dry-run            只打印计划，不写任何文件
"""

import argparse
import glob
import html
import json
import os
import re
import shutil
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST_DIR = os.path.join(ROOT, "full-logs")
PAGE = os.path.join(ROOT, "full-logs.html")

DEFAULT_SRC = r"F:/ComfyUI-aki-v3/ComfyUI/custom_nodes/ComfyUI-FullLog/logs"

JSON_SUFFIX = ".full_log.json"
HTML_SUFFIX = ".full_log.html"

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".opus"}

# 建模文件后缀：卡片上「模型」一行只认这些结尾的输入值
MODEL_EXTS = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".sft")

ROLE_ORDER = ("base", "text_encoder", "vae", "lora", "controlnet", "upscaler", "other")
ROLE_LABELS = {
    "base": "底模",
    "text_encoder": "TE",
    "vae": "VAE",
    "lora": "LoRA",
    "controlnet": "ControlNet",
    "upscaler": "放大",
    "other": "其他",
}


# ------------------------------------------------------------------ 小工具
def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def soft(name):
    """文件名里的分隔符后插 <wbr>，长文件名才能换行而不是撑破卡片。"""
    return re.sub(r"([_\-\./])", r"\1<wbr>", esc(name))


def url_of(rel):
    """只转义会破坏 URL 的字符；中文原样保留（与 logs.html 的既有做法一致）。"""
    out = []
    for ch in rel:
        if ch in ' #?%&"<>\\^`{|}[]':
            out.append("%%%02X" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def gpu_img(card):
    """显卡缩略图：assets/<卡型号小写>.jpg，站点里没有这张图就不显示。"""
    if not card:
        return ""
    name = re.sub(r"[^a-z0-9]", "", card.lower()) + ".jpg"
    if os.path.exists(os.path.join(ROOT, "assets", name)):
        return "assets/" + name
    return ""


def human(n):
    if n is None:
        return "—"
    n = float(n)
    if n < 1024:
        return "%d B" % n
    for unit in ("KB", "MB", "GB"):
        n /= 1024.0
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
    return "%.1f GB" % n


def dwidth(s):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def pad(s, width):
    return s + " " * max(0, width - dwidth(s))


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # 坏档案不该让整页生成失败
        sys.stderr.write("[warn] 读不了 %s：%s\n" % (os.path.basename(path), exc))
        return {}


def media_kind(path, rec):
    d = rec.get("deliverable") or {}
    kind = (d.get("media") or "").lower()
    if kind in ("image", "video", "audio"):
        return kind
    ext = os.path.splitext(path or "")[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    return "file"


# ------------------------------------------------------------------ 扫描
def scan_src(src):
    """返回 {base: {"base","json","html","media"}}，按 base 排序。"""
    try:
        names = os.listdir(src)
    except OSError:
        return {}, "源目录不存在：%s" % src
    items = {}
    for n in sorted(names):
        if not n.endswith(JSON_SUFFIX):
            continue
        base = n[: -len(JSON_SUFFIX)]
        item = {"base": base, "json": os.path.join(src, n), "html": None, "media": None}
        h = os.path.join(src, base + HTML_SUFFIX)
        if os.path.exists(h):
            item["html"] = h
        # 产物：同基名、非档案本体、非备份
        for m in sorted(names):
            if not m.startswith(base + "."):
                continue
            if m.endswith((".json", ".html", ".bak")):
                continue
            item["media"] = os.path.join(src, m)
            break
        items[base] = item
    return items, None


def stamp_of(base, rec):
    """档案时间：优先取档案名前 12 位（YYYYMMDDHHMM），退化用 started_at。"""
    m = re.match(r"^(\d{12})", base)
    if m:
        s = m.group(1)
        return "%s-%s-%s" % (s[:4], s[4:6], s[6:8]), "%s:%s" % (s[8:10], s[10:12]), s
    iso = ((rec.get("run") or {}).get("started_at")) or rec.get("generated_at") or ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", iso)
    if m:
        y, mo, d, hh, mm = m.groups()
        return "%s-%s-%s" % (y, mo, d), "%s:%s" % (hh, mm), y + mo + d + hh + mm
    return "", "", ""


def title_of(base, rec=None):
    """卡片上那行大标题 = `<12位时间>_<工作流名>`（保留时间戳）。

    档案名是手工可定义的，约定写法 `<12位时间>_<工作流名>[_<方案>_<卡>_<显存>_<类型>]`，
    所以标题取「档案名的开头 + 第一个 _ 或 + 之前」那段：
        202611021124_ZIT基础文生图                          → 202611021124_ZIT基础文生图
        202611021127_ZIT文生图_omnixpu加速_B580_16G_重载    → 202611021127_ZIT文生图
        202611022310_Moss文生图8步+TE2b优化                 → 202611022310_Moss文生图8步

    保留时间戳是刻意的：卡片左侧的日期列只有 MM-DD，同名工作流跑多次时靠前缀
    才能区分（例如 21:56 / 23:10 / 23:13 三份 Moss）。

    为什么不读 json 的 tags.workflow：它来自 SaveImage 的 filename_prefix，
    默认前缀下几份档案全是 "ComfyUI"，与实际工作流完全脱节。
    """
    s = (base or "").strip()
    # 先切出 12 位时间前缀（原样保留），只在余下部分找第一个分隔符，
    # 否则时间戳后面的那个 _ 会直接把标题截成纯数字
    m = re.match(r"^(\d{12})[_\-\s]+", s)
    prefix, rest = (m.group(1) + "_", s[m.end():]) if m else ("", s)
    for sep in ("_", "+", "（", "("):
        i = rest.find(sep)
        if i > 0:
            rest = rest[:i]
    rest = rest.strip()
    if rest:
        return prefix + rest
    tags = (rec or {}).get("tags") or {}
    stamp = (tags.get("stamp") or "").strip()
    name = (tags.get("workflow") or "").strip() or "未命名工作流"
    return ("%s_%s" % (stamp, name)) if stamp else name


def summarize(item, rec, max_video_mb):
    """把一份档案压成列表/卡片要用的字段。"""
    d = rec.get("deliverable") or {}
    m = rec.get("metrics") or {}
    run = rec.get("run") or {}
    tags = rec.get("tags") or {}

    media_path = item.get("media")
    kind = media_kind(media_path, rec) if media_path else (d.get("media") or "")
    size = os.path.getsize(media_path) if media_path else None
    over = bool(kind == "video" and max_video_mb > 0 and size
                and size > max_video_mb * 1024 * 1024)
    # 档案里记着产物、插件 logs 目录里却没有这个文件。两种成因要分开说：
    #   present=true  → 另存为时原文件还在，只是勾了「只存档案，不搬图」，
    #                   所以插件目录本来就没有它（同步的取数边界就是插件目录，不回溯 output/）
    #   present=false → 另存那一刻原文件就已经不在原路径了
    missing = bool(not media_path and d.get("filename"))
    missing_kind = ""
    if missing:
        missing_kind = "gone" if d.get("present") is False else "unmoved"

    date, clock, stamp = stamp_of(item["base"], rec)
    return {
        "base": item["base"],
        "json": item["json"],
        "html": item.get("html"),
        "media": media_path,
        "media_kind": kind,
        "media_size": size,
        "media_skip": over,
        "media_missing": missing,
        "media_missing_kind": missing_kind,
        "date": date,
        "clock": clock,
        "stamp": stamp,
        "workflow": title_of(item["base"], rec),
        "scheme": (tags.get("scheme") or "").strip(),
        "card": (tags.get("card") or "").strip(),
        "memory": (tags.get("memory") or "").strip(),
        "test": (run.get("label") or tags.get("test") or "").strip(),
        "status": (run.get("status") or "").strip(),
        "duration_s": run.get("duration_s"),
        "sec_per_it": m.get("sec_per_it"),
        "steps": m.get("steps"),
        "total_steps": m.get("total_steps"),
        "models": m.get("models") or [],
        "graph_models": graph_models(rec),
        "deliverable_name": d.get("filename") or "",
    }


def collect(src, max_video_mb):
    items, err = scan_src(src)
    if err:
        return [], err
    rows = []
    for base, item in items.items():
        rec = read_json(item["json"])
        rows.append(summarize(item, rec, max_video_mb))
    # 时间倒序；同刻按基名
    rows.sort(key=lambda r: (r["stamp"], r["base"]), reverse=True)
    return rows, None


def dst_state(base):
    """目标目录里这份档案的状态：new / exist。"""
    return "exist" if os.path.exists(os.path.join(DST_DIR, base + JSON_SUFFIX)) else "new"


# ------------------------------------------------------------------ --list
def cmd_list(rows, src, max_video_mb):
    if not rows:
        print("源目录里没有档案：%s" % src)
        print("（插件在 ComfyUI 里另存一份完整日志后，这里才会出现条目）")
        return

    head = ["#", "状态", "时间", "工作流", "方案", "卡", "内存", "类型", "产物", "总体积"]
    table = [head]
    for i, r in enumerate(rows, 1):
        if r["media_missing"]:
            prod = "未搬图" if r["media_missing_kind"] == "unmoved" else "原件已失"
        else:
            prod = {"image": "图片", "video": "视频", "audio": "音频"}.get(r["media_kind"], "无")
            if r["media_skip"]:
                prod += " ⚠超限"
        total = (os.path.getsize(r["json"]) if os.path.exists(r["json"]) else 0)
        total += os.path.getsize(r["html"]) if r["html"] else 0
        total += r["media_size"] or 0
        table.append([
            str(i),
            "已同步" if dst_state(r["base"]) == "exist" else "新增",
            ("%s %s" % (r["date"], r["clock"])).strip() or "—",
            r["workflow"],
            r["scheme"] or "—",
            r["card"] or "—",
            r["memory"] or "—",
            "—" if r["media_missing"] else {
                "image": "image", "video": "video", "audio": "audio"}.get(r["media_kind"], "—"),
            prod,
            human(total),
        ])

    widths = [max(dwidth(row[c]) for row in table) for c in range(len(head))]
    for idx, row in enumerate(table):
        print("  ".join(pad(cell, widths[c]) for c, cell in enumerate(row)).rstrip())
        if idx == 0:
            print("  ".join("-" * w for w in widths))

    new_n = sum(1 for r in rows if dst_state(r["base"]) == "new")
    skip_n = sum(1 for r in rows if r["media_skip"])
    print()
    print("共 %d 份档案：新增 %d，已同步 %d。视频上限 %.0f MB%s" % (
        len(rows), new_n, len(rows) - new_n, max_video_mb,
        ("，%d 份视频超限不会拷" % skip_n) if skip_n else ""))
    if new_n:
        print("下一步：python scripts/build_full_logs.py --sync 1,3,5   （只挑要发布的序号）")


# ------------------------------------------------------------------ --sync
def parse_picks(text, upper):
    picks = []
    for chunk in re.split(r"[,\s]+", (text or "").strip()):
        if not chunk:
            continue
        if re.match(r"^\d+-\d+$", chunk):
            a, b = chunk.split("-")
            picks.extend(range(int(a), int(b) + 1))
        elif chunk.isdigit():
            picks.append(int(chunk))
        else:
            raise SystemExit("看不懂的序号：%s" % chunk)
    bad = [p for p in picks if p < 1 or p > upper]
    if bad:
        raise SystemExit("序号超范围：%s（1..%d）" % (bad, upper))
    return sorted(set(picks))


def same_file(a, b):
    """两个文件是否逐字节相同（先比大小、再分块比内容）。

    只比大小是不够的：档案的 json/html 经常是「改了内容但字节数恰好不变」
    （例如同长度的时间戳、等长的模型名替换），那时会被误判成已同步而静默跳过。
    """
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                x = fa.read(1 << 20)
                y = fb.read(1 << 20)
                if x != y:
                    return False
                if not x:
                    return True
    except OSError:
        return False


def copy_one(src, dst, dry):
    if not src or not os.path.exists(src):
        return "missing"
    if os.path.exists(dst) and same_file(src, dst):
        return "same"
    if dry:
        return "would-copy"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return "copied"


# ---------------------------------------------------------------- 站点头(可重建)
# 详情页 html 由插件生成、单文件可分发，本身不带站点头部。发布到 full-logs/ 时
# 在这里补一段「返回 + 导航」，并用标记包起来 —— 于是改头部只要跑 --restyle，
# 不需要重新生成任何档案，也不需要插件参与（插件产物保持纯净）。
CHROME_START = "<!--fl-chrome:start-->"
CHROME_END = "<!--fl-chrome:end-->"
# 剥头部时连插入时补的那个换行一起吃掉，剥完才能和插件原件逐字节相等
CHROME_RE = re.compile(r"\n?" + re.escape(CHROME_START) + r".*?" + re.escape(CHROME_END) + r"\n?",
                       re.S)

CHROME_CHIPS = (
    ("../index.html", "项目收集", 0),
    ("../links.html", "环境依赖", 0),
    ("../cloud_drive_collection.html", "资源聚合", 0),
    ("../comfyui_opt.html", "工作台优化", 0),
    ("../logs.html", "执行日志", 0),
    ("../full-logs.html", "完整日志", 1),
    ("../group.html", "互助社群", 0),
    ("https://blog.blackwood.cv/news/latest", "生态日报 ↗", 2),
)

# 头部说明行：固定文案，不随档案变化（档案名/时间在分割线下面的正文标题里）
CHROME_NOTE = ("每份档案 = 一次执行的完整上下文：运行环境、模型加载、时间轴、"
               "原始日志、工作流结构、产物")


def chrome_block():
    """exelog 详情页同款头部，下面一条分割线，再下面是插件原样的档案正文。

    结构 = <header>站点名 + 一行说明 + 胶囊 chips</header> → <hr> → 返回链接
    → 原正文（原 h1 档案名 / sub / badges / kpi / 各区块一律不动）。

    CSS 值直接取自 logs/20261023-*.html 的 header / .note / .chips / .chip /
    .back，保证与 exelog 详情页逐项一致；类名也沿用 exelog 的 note / chips /
    chip / back，只在 .fl-chrome 作用域内生效，不污染插件自己的样式。
    """
    chips = []
    for href, label, kind in CHROME_CHIPS:
        if kind == 2:  # 外链
            chips.append('<a class="chip" href="%s" target="_blank" rel="noopener">%s</a>'
                         % (esc(href), esc(label)))
        elif kind == 1:  # 当前页
            chips.append('<span class="chip chip-active">%s</span>' % esc(label))
        else:
            chips.append('<a class="chip" href="%s">%s</a>' % (esc(href), esc(label)))
    note_html = '\n      <p class="note">%s</p>' % esc(CHROME_NOTE)
    return """%s
<style>
/* 站点头部：照抄 exelog 详情页（居中 30px 蓝色站名 / 一行说明 / 胶囊 chips） */
.fl-chrome header{text-align:center;padding:40px 0 24px}
.fl-chrome h1{font-size:30px;font-weight:700;color:#0071c5;margin:0;letter-spacing:.2px}
.fl-chrome .note{margin:12px 0 0;font-size:14px;color:#57606a;overflow-wrap:anywhere}
.fl-chrome .chips{margin-top:14px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
.fl-chrome .chip{
  font-size:12px;padding:5px 12px;border-radius:999px;background:#e8f1fb;
  color:#005a99;border:1px solid #c8e0f5;text-decoration:none;display:inline-block;white-space:nowrap;
}
.fl-chrome .chip:hover{background:#dbe9fb;border-color:#a9cff0}
.fl-chrome .chip-active{background:#0071c5;color:#fff;border-color:#0071c5}
/* 分割线：隔开「站点头部」与「档案正文」 */
.fl-chrome .rule{border:0;height:1px;background:#d0d7de;margin:0 0 18px}
/* 返回链接：位置与样式同 exelog 的 .back（头部下方、左对齐、13px 蓝色） */
.fl-chrome .back{display:inline-block;margin-bottom:18px;font-size:13px;color:#0071c5;text-decoration:none}
.fl-chrome .back:hover{text-decoration:underline}
/* 不设窄屏断点：站名与全站一致固定 30px（窄屏折行是既有设计，别的页一样） */
</style>
<div class="fl-chrome">
  <header>
    <h1>IntelGpu-ComfyUI-Collection</h1>%s
    <div class="chips">%s</div>
  </header>
  <hr class="rule">
  <a class="back" href="../full-logs.html">&#8592; 返回档案列表</a>
</div>
%s""" % (CHROME_START, note_html, "".join(chips), CHROME_END)


def decorate_text(s):
    """把站点头部插进详情页 <main>，返回 (新文本, 状态)。

    状态：ok（需要写）/ same（已是注入态）/ no-anchor（页面里找不到 <main>）。
    与落盘分开，好让 dry-run 用源文件内容预演 —— dry-run 时目标文件还没拷过去。
    """
    orig = s
    s = CHROME_RE.sub("", s)
    if "<main>" not in s:
        return orig, "no-anchor"
    if CHROME_START in s:  # 只可能出现在正文里，别乱插
        return orig, "no-anchor"
    s = s.replace("<main>", "<main>\n" + chrome_block(), 1)
    if s == orig:
        return orig, "same"
    return s, "ok"


def decorate_html(path, dry=False):
    """把站点头部注入已存在的详情页；已注入则先剥旧块再写，保证幂等。"""
    if not os.path.exists(path):
        # 调用方没先拷文件就来了（旧版 --sync N --dry-run 就是这么崩的）：
        # 明确回报，别再往上抛 FileNotFoundError。
        return "missing"
    with open(path, encoding="utf-8") as f:
        s = f.read()
    new, st = decorate_text(s)
    if st != "ok":
        return st
    if dry:
        return "would-write"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    return "written"


def cmd_restyle(dry):
    if not os.path.isdir(DST_DIR):
        raise SystemExit("找不到 %s" % DST_DIR)
    pages = sorted(glob.glob(os.path.join(DST_DIR, "*" + HTML_SUFFIX)))
    if not pages:
        raise SystemExit("%s 里还没有详情页" % DST_DIR)
    print("重建站点头部：%d 个详情页%s" % (len(pages), "  （dry-run，不落盘）" if dry else ""))
    print()
    stat = {}
    for p in pages:
        res = decorate_html(p, dry)
        stat[res] = stat.get(res, 0) + 1
        print("  %-8s %s" % ({
            "written": "已写入",
            "same": "无变化",
            "would-write": "将写入",
            "no-anchor": "⚠ 找不到 <main>",
        }[res], os.path.basename(p)))
    print()
    print("合计：" + " · ".join("%s %d" % (k, v) for k, v in sorted(stat.items())))
    return 0 if "no-anchor" not in stat else 1


def html_matches(src, dst):
    """dst 是不是 src 的等价副本（忽略已注入的站点头部）。"""
    # src 可能是 None：插件没生成 html 的档案（渲染失败 / 手工删了）也会出现在列表里，
    # 不挡住的话 os.path.exists(None) 会抛 TypeError 把整次 --sync 打断。
    if not (src and dst and os.path.exists(src) and os.path.exists(dst)):
        return False
    with open(src, encoding="utf-8") as f:
        a = f.read()
    with open(dst, encoding="utf-8") as f:
        b = f.read()
    b = CHROME_RE.sub("", b)
    return a == b


def cmd_sync(rows, picks, max_video_mb, dry):
    if not os.path.isdir(DST_DIR) and not dry:
        os.makedirs(DST_DIR, exist_ok=True)
    print("同步到 %s%s" % (DST_DIR, "  （dry-run，不落盘）" if dry else ""))
    print()
    done = 0
    for i in picks:
        r = rows[i - 1]
        base = r["base"]
        print("[%d] %s" % (i, base))
        for label, src, dst in (
            ("json", r["json"], os.path.join(DST_DIR, base + JSON_SUFFIX)),
            ("html", r["html"], os.path.join(DST_DIR, base + HTML_SUFFIX)),
        ):
            if label == "html":
                # 目标 html 可能带着已注入的头部，逐字节比会永远不相等，
                # 所以先用「剥掉头部再比」判断内容是否等价，等价就不必重拷。
                res = "same" if html_matches(src, dst) else copy_one(src, dst, dry)
            else:
                res = copy_one(src, dst, dry)
            print("    %-5s %s" % (label, {
                "copied": "已拷贝",
                "same": "内容一致，跳过",
                "missing": "源文件缺失",
                "would-copy": "将拷贝",
            }[res]))
            if label != "html" or res not in ("copied", "same", "would-copy"):
                continue
            if res in ("copied", "same"):
                # 已落盘：直接对目标文件做幂等注入（已有头部时返回 same）
                d = decorate_html(dst, dry)
            else:
                # dry-run 且目标还不存在：拿源文件内容预演，不碰磁盘
                with open(src, encoding="utf-8") as f:
                    _new, st = decorate_text(f.read())
                d = {"ok": "would-write", "same": "same", "no-anchor": "no-anchor"}[st]
            print("    %-5s %s" % ("头部", {
                "written": "已注入返回 + 导航",
                "would-write": "将注入返回 + 导航",
                "no-anchor": "⚠ 页面里找不到 <main>，未注入",
                "same": "已是最新",
                "missing": "⚠ 目标文件不存在，未注入",
            }.get(d, d)))
        if r["media"]:
            if r["media_skip"]:
                print("    %-5s 跳过：%s（%.1f MB，超过 %.0f MB 上限）" % (
                    "产物", os.path.basename(r["media"]),
                    (r["media_size"] or 0) / 1048576.0, max_video_mb))
            else:
                res = copy_one(r["media"], os.path.join(DST_DIR, os.path.basename(r["media"])), dry)
                print("    %-5s %s%s" % ("产物", {
                    "copied": "已拷贝 ",
                    "same": "内容一致，跳过 ",
                    "missing": "源文件缺失 ",
                    "would-copy": "将拷贝 ",
                }[res], os.path.basename(r["media"])))
        elif r["media_missing"]:
            if r["media_missing_kind"] == "unmoved":
                print("    %-5s 无：%s 另存时选了「只存档案，不搬图」，插件目录本来就没有它"
                      % ("产物", r["deliverable_name"]))
            else:
                print("    %-5s 无：另存那一刻 %s 就已不在原路径"
                      % ("产物", r["deliverable_name"]))
        else:
            print("    %-5s 无" % "产物")
        done += 1
    print()
    print("完成 %d 份。" % done)


# ------------------------------------------------------------------ --build
CSS = """
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
  .sort-banner {
    margin: 28px 0 8px; background: linear-gradient(90deg, #e8f1fb, #f0f7fd);
    border: 1px solid #c8e0f5; border-radius: 10px; padding: 10px 16px;
    font-size: 13px; color: var(--intel-blue-dark); text-align: center; line-height: 1.8;
  }
  .sec-title { font-size: 17px; font-weight: 600; margin: 32px 0 14px; }
  .log-grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
  .log-card {
    display: grid; grid-template-columns: 88px minmax(0, 1fr) auto; gap: 0 16px;
    align-items: start;
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    /* 最小高度 + 松内边距：卡片内容多寡不一（有的没模型行/没有图），太矮会显局促 */
    min-height: 216px; padding: 20px 22px; text-decoration: none; color: inherit;
    box-shadow: 0 1px 3px rgba(31,35,40,0.06);
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
  }
  .log-card:hover { box-shadow: 0 4px 12px rgba(31,35,40,0.12); border-color: #c8e0f5; }
  .log-card.is-flat { cursor: default; }
  .log-when {
    display: flex; flex-direction: column; gap: 2px; padding-right: 14px;
    border-right: 1px solid #eef0f2; text-align: right; font-variant-numeric: tabular-nums;
    align-items: flex-end;
    /* 卡片是 align-items:start，这里单独拉满整行高度，显卡图才能用 margin-top:auto 贴底 */
    align-self: stretch;
  }
  .log-date { font-size: 13px; font-weight: 600; color: var(--text); }
  .log-time { font-size: 12px; color: var(--text-muted); }
  .log-main { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  .log-side {
    display: flex; flex-direction: column; gap: 10px; align-items: center;
    align-self: stretch;
  }
  .log-wf { font-size: 15px; font-weight: 600; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; overflow-wrap: anywhere; }
  .log-side .log-tags {
    align-self: flex-end; display: flex; gap: 6px; flex-wrap: wrap;
    justify-content: flex-end; align-items: center;
  }
  .log-thumbs {
    display: flex; align-items: center; justify-content: center;
    margin-top: auto; margin-bottom: auto; max-width: 100%;
  }
  /* 产物图按原始比例缩放：只限最大宽高，不裁切、不拉伸
     可用高度算不出来就取不到最大：右侧栏宽度由 tags 撑到 232px，
     卡片内高 199 − tags 22 − 间距 10 = 167 → 图上限取 160，再大就会把卡片撑高 */
  .log-thumb {
    display: block; width: auto; height: auto;
    max-width: 160px; max-height: 160px; object-fit: contain;
    border-radius: 8px; box-shadow: 0 1px 4px rgba(31,35,40,0.18);
    background: #f3f4f6;
  }
  /* 显卡图在左列：日期时间下方，靠底对齐 */
  .log-gpu {
    display: block; width: 64px; height: 64px; object-fit: cover;
    border-radius: 8px; box-shadow: 0 1px 4px rgba(31,35,40,0.18);
    margin-top: auto; margin-bottom: 2px;
  }
  .log-thumb.flat {
    display: flex; align-items: center; justify-content: center;
    width: 160px; aspect-ratio: 4 / 3; height: auto; max-height: none;
    font-size: 12px; color: var(--text-muted); box-shadow: none;
    border: 1px dashed var(--border);
  }
  .tag {
    font-size: 12px; line-height: 18px; padding: 1px 8px; border-radius: 6px;
    background: #f3f4f6; border: 1px solid #e5e7eb; color: var(--text-muted);
    /* 标题区是粗体，不显式压回 400 的话 .tag 会继承父级 font-weight 变粗 */
    font-weight: 400;
    white-space: nowrap;
  }
  .tag-scheme { color: var(--intel-blue-dark); background: #e8f1fb; border-color: #c8e0f5; }
  .tag-card { color: #6b3fc4; background: #f4efff; border-color: #ddd0fa; }
  .tag-vram { color: #9a5b00; background: #fff5e2; border-color: #f2dcaf; }
  .tag-err { color: #a40e26; background: #fdecee; border-color: #f5c2c7; }
  /* 冷启/重载/热启 一套独立的冷热度色阶，与右侧三色 tag 无关（同详情页 badge） */
  .tag-cold { color: #1f6feb; background: #e8f1fb; border-color: #c9dffb; }
  .tag-reload { color: #0f766e; background: #e3f4f2; border-color: #bfe3df; }
  .tag-warm { color: #b45309; background: #fff2dc; border-color: #f7d9a4; }
  .log-nums { display: flex; gap: 34px; flex-wrap: wrap; }
  .log-nums .st { display: flex; flex-direction: column; gap: 2px; }
  .log-nums .st i { font-style: normal; font-size: 11px; color: var(--text-muted); }
  .log-nums .st b { font-size: 17px; font-variant-numeric: tabular-nums; }
  .log-models {
    display: flex; flex-direction: column; gap: 3px;
    padding-top: 10px; border-top: 1px dashed #e5e7eb;
  }
  /* 档案文件名（含后缀）单独占最后一行，样式对齐 logs.html 的同名行 */
  .log-file { font-size: 11px; color: #8c959f; overflow-wrap: anywhere; word-break: normal; }
  .model-row { display: flex; gap: 8px; font-size: 12px; align-items: baseline; }
  .model-row i {
    font-style: normal; color: var(--text-muted); flex: 0 0 auto;
    min-width: 32px; font-size: 11px;
  }
  .model-row span {
    color: var(--text); overflow-wrap: anywhere; word-break: normal;
    font-family: "Cascadia Mono", Consolas, monospace; font-size: 11px; line-height: 1.5;
  }
  @media (max-width: 700px) {
    .log-card { grid-template-columns: 88px minmax(0, 1fr); }
    .log-side {
      grid-column: 1 / -1; flex-direction: row-reverse; align-items: center;
      justify-content: space-between; gap: 12px;
      border-top: 1px solid #eef0f2; padding-top: 10px; margin-top: 10px;
    }
    .log-side .log-tags { align-self: center; flex-wrap: wrap; justify-content: flex-end; }
    /* 窄屏主列实际只有 ~187px（375 − 页面 40 − 日期列 88 − 卡片内边距 44 − 栅格 16），
       4 字标签 + 17px 数值三项放不下（实测「采样步数」会掉到第二行）：
       数值降到 15px、栏距 12px，三项稳在一行；桌面不受影响 */
    .log-nums { gap: 12px; }
    .log-nums .st b { font-size: 15px; }
    .log-thumb { max-width: 84px; max-height: 104px; margin: 0; }
    /* 占位框是 4:3，比竖版产物图矮；窄屏单独放开 max-width，否则会被 84 卡成又矮又窄 */
    .log-thumb.flat { width: 96px; max-width: none; }
    .log-gpu { width: 48px; height: 48px; }
  }
  .empty { text-align: center; color: var(--text-muted); font-size: 14px; padding: 48px 0; }
  footer { text-align: center; margin-top: 40px; font-size: 12px; color: var(--text-muted); }
  footer a { color: var(--intel-blue); text-decoration: none; }
"""

CHIPS = """      <a class="chip" href="index.html">项目收集</a>
      <a class="chip" href="links.html">环境依赖</a>
      <a class="chip" href="cloud_drive_collection.html">资源聚合</a>
      <a class="chip" href="comfyui_opt.html">工作台优化</a>
      <a class="chip" href="logs.html">执行日志</a>
      <span class="chip chip-active">完整日志</span>
      <a class="chip" href="group.html">互助社群</a>
      <a class="chip" href="https://blog.blackwood.cv/news/latest" target="_blank" rel="noopener">生态日报 ↗</a>"""


def role_by_key(key, value):
    """按输入键名 + 文件名猜角色。与插件 fulllog_html._role_by_key 保持同一套规则。

    键名优先：「lora_name」比文件名可靠得多（很多 LoRA 文件名里根本没有 lora 字样）。
    """
    k = (key or "").lower()
    blob = ("%s %s" % (key or "", value or "")).lower()
    if "lora" in blob:
        return "lora"
    if "control" in blob:
        return "controlnet"
    if "vae" in blob:
        return "vae"
    if any(k2 in blob for k2 in ("upscal", "esrgan", "ultrasharp", "swinir", "realesr")):
        return "upscaler"
    # 底模的**强信号键名**排在 TE 关键词之前：`unet_name = ext\qwen_image_2.1-...gguf`
    # 同时含 "unet"（底模）与 "qwen"（TE 关键词），先判 TE 会把底模说成文本编码器。
    # 键名是加载器自己声明的，比文件名里的厂商前缀可靠。
    if any(k2 in k for k2 in ("unet", "ckpt", "diffusion")):
        return "base"
    if any(k2 in blob for k2 in ("clip", "text_encoder", "temodel", " t5", "_t5", "umt5",
                                 "qwen", "llama", "gemma")):
        return "text_encoder"
    if any(k2 in blob for k2 in ("model", "unet", "diffusion")):
        return "base"
    return "other"


def graph_models(rec):
    """从 API 图（prompt）枚举所有被引用的模型文件，按图里的顺序返回。

    为什么不能只看日志：执行日志只打印真正触发加载的 `Requested to load`，
    而 LoRA 是打补丁（apply/merge）不是 load 一个 ModelPatcher，日志里根本不出现；
    多输入加载器（例如 MossCLIPLoader 的 clip_name + adapter 两个 TE）在日志里
    也可能只落一条。所以「卡片上有哪些模型」以图为唯一权威来源。
    """
    out = []
    for nid, n in (rec.get("prompt") or {}).items():
        if not isinstance(n, dict):
            continue
        cls = n.get("class_type") or n.get("type") or "?"
        for k, v in (n.get("inputs") or {}).items():
            if not isinstance(v, str):
                continue
            s = v.strip()
            if not s or s.lower() in ("none", "null"):
                continue
            if not s.lower().endswith(MODEL_EXTS):
                continue
            out.append({"role": role_by_key(k, s), "file": s, "node": nid, "loader": cls,
                        "key": k})
    return out


def model_rows(models, graph=None):
    """卡片上的「模型」块：一角色一行，同角色多个文件在同一行用 / 隔开。

    同行合并是卡片特有的取舍——卡片是索引，只需要「这次用了哪些模型」；
    详情页那张表是一处引用一行（不合并），两者用途不同。
    """
    by_role = {}

    def add(role, name):
        name = os.path.basename((name or "").replace("\\", "/"))
        if not name:
            return
        bucket = by_role.setdefault(role or "other", [])
        if name not in bucket:  # 同一文件被多个节点引用只算一次
            bucket.append(name)

    # ① 工作流结构（API 图）优先：它是唯一包含 LoRA 与多输入加载器的来源
    for g in graph or []:
        add(g.get("role"), g.get("file"))
    # ② 日志里记着、但图里找不到对应加载节点的（间接加载）补在后面，不丢信息。
    #    ⚠️ 只有 file 为空时**绝不**退回类名：`QwenImage21` / `WanVAE` 这类是模型包装类，
    #    不是文件名，写成"模型"会让卡片出现「底模：QwenImage21」这种令人困惑的行。
    #    GGUF 工作流的 policy 行是 paths=[]，日志里本来就没有文件名，此时图里已经有真名。
    for m in models or []:
        if m.get("file"):
            add(m.get("role"), m.get("file"))

    out = []
    for role in ROLE_ORDER:
        names = by_role.get(role)
        if not names:
            continue
        out.append(
            '<div class="model-row"><i>%s</i><span>%s</span></div>'
            % (esc(ROLE_LABELS.get(role, role)), " / ".join(soft(n) for n in names))
        )
    return "".join(out)


def num_cells(r):
    cells = []
    if r["duration_s"] is not None:
        # 两位小数：与日志 `Prompt executed in X seconds` 逐字对得上，一位小数会显示成 102.0
        cells.append(("总耗时", "%.2f s" % r["duration_s"]))
    if r["sec_per_it"]:
        # 名字与详情页 KPI 对齐：「每步采样」= 纯采样循环的每步耗时，不含加载/解码
        cells.append(("每步采样", "%.2f s/it" % r["sec_per_it"]))
    if r["steps"] is not None:
        steps = "%s" % r["steps"]
        if r["total_steps"] and r["total_steps"] != r["steps"]:
            steps = "%s / %s" % (r["steps"], r["total_steps"])
        cells.append(("采样步数", steps))
    return "".join(
        '<span class="st"><i>%s</i><b>%s</b></span>' % (esc(k), esc(v)) for k, v in cells
    )


def card_html(r):
    base = r["base"]
    href = None
    if r["html"] and os.path.exists(os.path.join(DST_DIR, base + HTML_SUFFIX)):
        href = "full-logs/" + url_of(base + HTML_SUFFIX)
    tag = "a" if href else "div"
    attrs = ' class="log-card" href="%s"' % esc(href) if href else ' class="log-card is-flat"'

    tags = []
    # 冷启/重载/热启 放在最前：它决定这张卡的性能基线，比方案/卡/显存更靠前读
    if r["test"]:
        lcls = {"冷启": "tag-cold", "重载": "tag-reload", "热启": "tag-warm"}.get(r["test"], "tag")
        tags.append('<span class="tag %s" title="测试类型">%s</span>' % (lcls, esc(r["test"])))
    if r["scheme"]:
        tags.append('<span class="tag tag-scheme" title="加速方案">%s</span>' % esc(r["scheme"]))
    if r["card"]:
        tags.append('<span class="tag tag-card" title="显卡">%s</span>' % esc(r["card"]))
    if r["memory"]:
        tags.append('<span class="tag tag-vram" title="内存">%s</span>' % esc(r["memory"]))
    if r["status"] and r["status"] != "success":
        # 聚合页只收录成功档案，success 徽章没有信息量 → 不显示；
        # 异常状态（error / interrupted）仍然打出来，免得漏掉问题档案
        tags.append('<span class="tag tag-err" title="状态">%s</span>' % esc(r["status"]))

    head_tags = ""
    if not href:
        head_tags += '<span class="tag tag-err" title="缺少 html">缺 html</span>'

    # 缩略图：产物图按原始比例缩放（不做裁切）；显卡图挪到左列日期下方
    thumbs = []
    if r["media"] and r["media_kind"] == "image":
        thumbs.append('<img class="log-thumb" src="%s" alt="%s" loading="lazy">' % (
            esc("full-logs/" + url_of(os.path.basename(r["media"]))),
            esc(r["deliverable_name"] or base)))
    elif r["media_kind"] in ("video", "audio"):
        note = "视频" if r["media_kind"] == "video" else "音频"
        tip = ("视频超过体积上限，未随档案发布" if r["media_skip"] else note)
        thumbs.append('<div class="log-thumb flat" title="%s">%s</div>' % (esc(tip), esc(note)))
    elif r["media_missing"]:
        tip = ("另存为时选了「只存档案，不搬图」，档案目录里本来就没有这张产物"
               if r["media_missing_kind"] == "unmoved" else "原文件已不在原路径")
        thumbs.append('<div class="log-thumb flat" title="%s">不显示</div>' % esc(tip))
    side_thumb = ('<div class="log-thumbs">%s</div>' % "".join(thumbs)) if thumbs else ""

    gpu = gpu_img(r["card"])
    gpu_tag = ('<img class="log-gpu" src="%s" alt="%s" title="%s" loading="lazy">'
               % (esc(gpu), esc(r["card"]), esc(r["card"]))) if gpu else ""

    models = model_rows(r["models"], r.get("graph_models"))
    models_block = '<div class="log-models">%s</div>' % models if models else ""

    return (
        '    <%s%s>\n'
        '      <div class="log-when"><span class="log-date">%s</span>'
        '<span class="log-time">%s</span>%s</div>\n'
        '      <div class="log-main">\n'
        '        <div class="log-wf">%s%s</div>\n'
        '        <div class="log-nums">%s</div>\n'
        '        %s\n'
        '        <div class="log-file">%s</div>\n'
        '      </div>\n'
        '      <div class="log-side"><div class="log-tags">%s</div>%s</div>\n'
        '    </%s>\n'
    ) % (
        tag, attrs,
        esc(r["date"] or "—"), esc(r["clock"] or ""), gpu_tag,
        esc(r["base"]), head_tags,
        num_cells(r),
        models_block,
        esc(base + JSON_SUFFIX),
        "".join(tags), side_thumb,
        tag,
    )


def dir_size(path):
    total = 0
    if not os.path.isdir(path):
        return 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def cmd_build(dry):
    if not os.path.isdir(DST_DIR):
        print("目录不存在：%s（先跑 --sync 同步至少一份档案）" % DST_DIR)
        return 1
    rows = []
    for n in sorted(os.listdir(DST_DIR)):
        if not n.endswith(JSON_SUFFIX):
            continue
        base = n[: -len(JSON_SUFFIX)]
        rec = read_json(os.path.join(DST_DIR, n))
        media = None
        for f in os.listdir(DST_DIR):
            if f.startswith(base + ".") and not f.endswith((".json", ".html", ".bak")):
                media = os.path.join(DST_DIR, f)
                break
        rows.append(summarize(
            {"base": base, "json": os.path.join(DST_DIR, n),
             "html": (os.path.join(DST_DIR, base + HTML_SUFFIX)
                      if os.path.exists(os.path.join(DST_DIR, base + HTML_SUFFIX)) else None),
             "media": media},
            rec, 20.0))
    rows.sort(key=lambda r: (r["stamp"], r["base"]), reverse=True)

    if rows:
        body = '<div class="log-grid">\n%s  </div>' % "".join(card_html(r) for r in rows)
    else:
        body = '<div class="empty">还没有任何档案。在 ComfyUI 里另存一份完整日志后，' \
               '用 <code>--sync</code> 同步进来。</div>'

    page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IntelGpu-ComfyUI-Collection - 完整日志</title>
<style>%s</style>
</head>
<body>
<div class="container">

  <header>
    <h1>IntelGpu-ComfyUI-Collection</h1>
    <p class="note">每份档案 = 一次执行的完整上下文：运行环境、模型加载、时间轴、原始日志、工作流结构、产物</p>
    <div class="chips">
%s
    </div>
  </header>

  <div class="sort-banner">
    共 %d 份档案 · 按时间倒排（新 → 旧）· 由本地脚本从各档案的 <code>.full_log.json</code> 渲染，远端不参与生成 · 点击卡片进入完整档案
  </div>

  <h2 class="sec-title">全部档案</h2>
%s

  <footer>
    <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection" target="_blank">IntelGpu-ComfyUI-Collection</a> ·
    <a href="full-logs/" target="_blank">full-logs/ 档案目录</a>
  </footer>

</div>
</body>
</html>
""" % (CSS, CHIPS, len(rows), body)

    if dry:
        print("[dry-run] 将写入 %s（%d 份档案）" % (PAGE, len(rows)))
        return 0
    with open(PAGE, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("已生成 %s：%d 份档案，%s" % (PAGE, len(rows), human(os.path.getsize(PAGE))))
    total = dir_size(DST_DIR)
    print("full-logs/ 合计 %s%s" % (
        human(total), "  ⚠ 已超 500 MB，建议按年份清理旧档案" if total > 500 * 1048576 else ""))
    return 0


def main(argv):
    ap = argparse.ArgumentParser(
        description="full-logs 聚合页生成 + 档案同步", add_help=True)
    ap.add_argument("--list", action="store_true", help="列出源目录里的档案与同步状态")
    ap.add_argument("--sync", default="", metavar="1,3,5", help="按序号同步这些档案")
    ap.add_argument("--sync-all", action="store_true", help="同步全部档案")
    ap.add_argument("--build", action="store_true", help="只重建 full-logs.html")
    ap.add_argument("--restyle", action="store_true",
                    help="只重灌详情页的站点头部（返回 + 导航），不碰 json/产物/本地原件")
    ap.add_argument("--src", default=os.environ.get("FULLLOG_SRC") or DEFAULT_SRC,
                    help="插件日志目录")
    ap.add_argument("--max-video-mb", type=float, default=20.0,
                    help="视频超过该体积就不随档案发布（0 = 不限）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写文件")
    a = ap.parse_args(argv)

    if a.restyle and not (a.sync or a.sync_all):
        return cmd_restyle(a.dry_run)

    if a.build and not (a.sync or a.sync_all):
        return cmd_build(a.dry_run)

    rows, err = collect(a.src, a.max_video_mb)
    if err:
        print(err)
        return 2

    if not (a.sync or a.sync_all):
        cmd_list(rows, a.src, a.max_video_mb)
        return 0

    if a.sync_all:
        picks = list(range(1, len(rows) + 1))
    else:
        picks = parse_picks(a.sync, len(rows))
    if not picks:
        print("没有选中任何档案。")
        return 0

    cmd_sync(rows, picks, a.max_video_mb, a.dry_run)
    print()
    return cmd_build(a.dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
