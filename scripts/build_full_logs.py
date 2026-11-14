#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""full-logs 聚合页 + 档案同步（纯标准库）。

⚠️ 两个项目，别混：
    ComfyUI-FullLog 插件  —— **通用方案**，任何 ComfyUI 用户都能装。它在 logs/ 里
                             产出 `<基名>.full_log.json` + `.full_log.html` + 产物，
                             单文件可分发、不含任何站内链接/导航/配色约定。
                             它不知道本站存在，也不该知道。
    本脚本（本站专属）    —— 只服务 allanmeng 的 IntelGpu-ComfyUI-Collection：
                             **单向**从插件 logs/ 读取（只读），复制进 full-logs/，
                             再补站点头部、生成聚合页。
所以「要不要给插件加个功能」和「站点怎么展示」是两个独立问题：
插件侧只对「档案本身」负责，站点侧的排版/导航/删改一律在这里解决。

背景：exelog 走远端生成（推 txt → Action 出 html），full-logs 反过来——
插件在本地产出 json / html / 产物，人工挑选后同步进仓库，页面也在本地渲染。
远端只接收静态文件，不跑任何生成逻辑；本脚本不碰 logs.html、logs/、
log-analysis/，也不碰 scripts/generate_pages.py。

    python scripts/build_full_logs.py                  # 列出待同步（等同 --list）
    python scripts/build_full_logs.py --list --names   # 只列「序号 + 完整档案名」，方便复制
    python scripts/build_full_logs.py --sync 1,3       # 按序号同步，然后重建页面
    python scripts/build_full_logs.py --sync 202611031216_xxx_16G_测试
                                                       # 按完整档案名同步（永不漂移）
    python scripts/build_full_logs.py --sync-all       # 同步全部，然后重建页面
    python scripts/build_full_logs.py --build          # 只重建聚合页
    python scripts/build_full_logs.py --restyle        # 只重灌详情页头部（返回 + 导航）
    python scripts/build_full_logs.py --families       # 只读：审计「底模 → family」映射
    python scripts/build_full_logs.py --rm 1,3         # 预览：要从站点移除哪几份
    python scripts/build_full_logs.py --rm 1,3 --yes   # 真删（移到 _trash，可还原）

六个命令的边界（容易混，写死在这里）：

    --list   **只读**：列出源目录里的档案与同步状态，供挑选序号用。
             不写任何文件，聚合页一个字节都不变。
    --sync   把选中档案从插件 logs/ **复制**到 full-logs/（原件不动），
             顺带注入站点头部，末尾自动调一次 --build 重建聚合页。
             所以「--sync 完再跑 --build」是多余的，两者本来就是一步。
    --build  只按 full-logs/ 现有内容重建 full-logs.html，不碰任何档案。
    --restyle 只改详情页头部，不动 json / 产物 / 插件原件。
    --rm     从**站点**移除档案（撤销发布），插件 logs/ 里的原件一概不动——
             上不上站点本来就是人工决定的，删站内副本不该牵连源档案。
             文件不真删，移到 full-logs/_trash/<时间戳>/（已 gitignore），
             拷回 full-logs/ 再跑 --build 即可还原。不加 --yes 只打印清单。
    --families **只读**：列站点每份档案的「底模 → family」以及未归类清单。
             映射表是 scripts/model_families.json，只服务本站筛选器；
             插件 ComfyUI-FullLog 不读它，产物里也不带 family。

⚠️ --rm 的序号来自**站点现存档案**，与 --list/--sync 的**插件源**列表不是一回事，
   两边档数常常不同（源里常有没发布的）。所以 --rm 与 --sync 不允许同时给。

选择串两种模式（--sync / --rm 通用，同一串可混写）：
    ① 序号       1,3,5 / 1-3,7     本次列表里的位置。快，但档案增删后会整体漂移。
    ② 完整档案名 202611031216_xxx_16G_测试
                                    精确匹配，永不漂移，可写进脚本/隔天执行；
                                    也认 .full_log / .full_log.json / .html 后缀。
    **不做前缀匹配**：前缀只到分钟，同分钟同参数跑两次会存成 `...-2`，前缀会命中两份。
    匹配不上就报错并给最接近的候选，绝不猜。

三个位置别混淆：
    插件 logs/      源：ComfyUI 里另存出来的原件（本脚本只读）
    full-logs/      站内副本：json + html + 产物（--sync 拷进来，--rm 挪走）
    full-logs.html  站内聚合页（--build / --sync / --rm 末尾生成）

站点头部（返回按钮 + 导航 chips）不写进插件产物，而是在「同步进 full-logs/」这一步
注入，并用 <!--fl-chrome:start/end--> 包住。所以改头部只要跑一次 --restyle，
不用重新生成任何档案、也不用重启 ComfyUI：
    * 本地插件 logs/ 里的原件保持纯净（单文件可分发、无站内链接）；
    * 剥掉标记块后与原件逐字节相同，已是最新时 --restyle 不写盘（幂等）。

可选：
    --src DIR            插件日志目录（默认见 DEFAULT_SRC，可用 FULLLOG_SRC 覆盖）
    --names              配合 --list：只打印「序号 + 完整档案名」，方便复制粘贴
    --max-video-mb N     视频超过 N MB 就不随档案发布（0 = 不限，默认 20）
    --dry-run            只打印计划，不写任何文件
"""

import argparse
import datetime
import difflib
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
# --rm 不直接删文件，一律先挪进这里（按时间戳分目录）。
# 放在 full-logs 下而不是项目根：删的东西和它在同一处，找回来直观；
# 已在 .gitignore 里排除，不会被 git 跟踪，也不会被 scan_src 当成档案
# （scan_src 只列一级目录、只认 *.full_log.json 结尾）。
TRASH_DIR = os.path.join(DST_DIR, "_trash")

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


def deliverables_of(rec):
    """读出档案里的全部产物，统一成列表（与插件 fulllog_core.deliverables_of 同义）。

    新档案有复数 `deliverables`；存量档案只有单数 `deliverable`。
    """
    lst = (rec or {}).get("deliverables")
    if isinstance(lst, list) and lst:
        return [dict(x) for x in lst if isinstance(x, dict)]
    one = (rec or {}).get("deliverable")
    if isinstance(one, dict) and one:
        return [dict(one)]
    return []


def locate_local(d, base, src_dir, names, idx=None):
    """定位一个产物在 src_dir 里的实际文件名。

    三级兜底，**优先信档案里的记录**，不靠文件名猜：
      ① d["archive_name"] —— 插件搬图时回写的真实落盘名，最权威
      ② `<base>_<n><ext>` —— 新规则（单图也带 _1），应对 archive_name 缺失
      ③ `<base><ext>` —— 老规则（存量 8 份都是这个名字）
    三条都落空 = 真的没有图（没搬图 / 被移走），返回 None。

    ⚠️ 不靠「以 base 开头」去模糊匹配：`unique_path` 撞名时会生成
    `<base>_1-2.png` 这种带 `-2` 的名字，模糊匹配可能认错；而且
    `<base>_1.png` 与 `<base>_10.png` 用 startswith 会互相干扰。

    ⚠️ 即便只有一张产物也要试 `<base>_1<ext>`：插件的新规则**单张也带 _1**，
    只有老档案才是 `<base><ext>`。idx 为 None 时按第 1 张处理。
    """
    fn = (d or {}).get("filename") or ""
    ext = os.path.splitext(fn)[1]
    idx = 0 if idx is None else idx
    cands = []
    if d.get("archive_name"):
        cands.append(d["archive_name"])
    if base and ext:
        cands.append("%s_%d%s" % (base, idx + 1, ext))
        cands.append(base + ext)
    if fn:
        cands.append(fn)          # 产物被原样拷进来、没改名的情况
    for c in cands:
        if c and c in names:
            return c
    return None


def media_kind(path, rec=None):
    """产物类型：先看档案里记的 media，再按扩展名兜底。"""
    if isinstance(rec, dict):
        kind = (rec.get("media") or "").lower()
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
    """返回 {base: {"base","json","html","deliverables"}}，按 base 排序。

    产物定位见 locate_local()：先信 json 里的 archive_name，再按文件名兜底。
    一份档案可以有 0~N 个产物（一次执行批量出图就是 N>1）。
    """
    try:
        names = os.listdir(src)
    except OSError:
        return {}, "源目录不存在：%s" % src
    nameset = set(names)
    items = {}
    for n in sorted(names):
        if not n.endswith(JSON_SUFFIX):
            continue
        base = n[: -len(JSON_SUFFIX)]
        item = {"base": base, "json": os.path.join(src, n), "html": None, "deliverables": []}
        h = os.path.join(src, base + HTML_SUFFIX)
        if os.path.exists(h):
            item["html"] = h
        rec = read_json(item["json"])
        dels = deliverables_of(rec)
        for i, d in enumerate(dels):
            # idx 一律传 i：单产物也按第 1 张处理（新规则单张也叫 _1.png）
            local = locate_local(d, base, src, nameset, i)
            kind = media_kind(local, d)
            item["deliverables"].append({
                "d": d,
                "local": local,
                "path": os.path.join(src, local) if local else None,
                "kind": kind,
                "name": d.get("filename") or "",
                "size": (os.path.getsize(os.path.join(src, local)) if local else None),
            })
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

    档案名是手工可定义的，约定写法 `<12位时间>_<工作流名>[_<方案>_<卡>_<内存>_<类型>]`，
    ⚠️ 第 5 段是 psutil **物理内存**（如 16G），不是显存；显存在 `env.devices[].total_memory_mb`
       （B580 上报 11946 MB），两者数值和含义都不同，别混。
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


# ------------------------------------------------------------------ 底模 family
# 只给站点筛选器用：插件 ComfyUI-FullLog 不读这张表，产物里也不带 family。
FAMILIES_JSON = os.path.join(ROOT, "scripts", "model_families.json")
UNKNOWN_FAMILY = "未归类"
_FAMILIES = None


def norm_key(s):
    """模型路径的比对键：小写 + **去掉所有非字母数字字符**（分隔符、下划线、点全删）。

    `ext\\qwen_image_2.1-viggle-4-steps-turbo_Q4_K_M.gguf`
      → `extqwenimage21viggle4stepsturboq4kmgguf`

    为什么是「删干净」而不是「折成空格」：文件名里 CamelCase 和数字紧挨着，
    折成空格后 `REDZimageTurbo2.0` 会变成 `redzimageturbo2 0`，与
    `zimage turbo` 隔着 camelCase 边界对不上。删干净后 `redzimageturbo20…`
    里直接含 `zimageturbo`，一条 match 就能命中。

    - 量化后缀（Q4_K_M → Q3_K_M）删完分别是 q4km / q3km，词干不受影响
    - 子目录名保留在键里：`Illustrious\\IL-Gembyte…` 的文件名不含 Illustrious，
      全靠目录名命中
    """
    s = unicodedata.normalize("NFKC", (s or "").replace("\\", "/")).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s)


def load_families():
    """读 model_families.json → (families, exact)。文件缺了只警告，不阻断发布。"""
    global _FAMILIES
    if _FAMILIES is not None:
        return _FAMILIES
    data = {}
    if os.path.exists(FAMILIES_JSON):
        try:
            with open(FAMILIES_JSON, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print("⚠ %s 读取失败（%s）→ 本次全部按「%s」处理" % (FAMILIES_JSON, e, UNKNOWN_FAMILY))
    else:
        print("⚠ 找不到 %s → 全部按「%s」处理" % (FAMILIES_JSON, UNKNOWN_FAMILY))
    fams = []
    for x in data.get("families") or []:
        name = (x.get("family") or "").strip()
        if not name:
            continue
        phrases = [norm_key(p) for p in (x.get("match") or []) if p]
        phrases = [p for p in phrases if p]
        fams.append((name, phrases))
    exact = {norm_key(k): v for k, v in (data.get("exact") or {}).items()}
    _FAMILIES = (fams, exact)
    return _FAMILIES


def base_model_paths(rec):
    """这份档案的底模文件（含子目录，相对 models/ 的写法原样保留）。

    **图优先**：GGUF 工作流的 `metrics.models` 里 base 的 file 是空的
    （policy 行 paths=[]），只有工作流结构里还剩 unet_name。
    """
    out = []
    for x in graph_models(rec):
        if x.get("role") == "base" and x.get("file"):
            out.append(x["file"])
    if not out:
        for m in ((rec.get("metrics") or {}).get("models") or []):
            if m.get("role") == "base" and m.get("file"):
                out.append(m["file"])
    seen, uniq = set(), []
    for p in out:
        k = norm_key(p)
        if k and k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def family_of(paths):
    """底模路径 → family 列表（去重保序）。命中不了就是空列表。"""
    fams, exact = load_families()
    out = []
    for p in paths:
        k = norm_key(p)
        hit = exact.get(k)
        if not hit:
            for name, phrases in fams:      # 声明顺序即优先级，命中第一个就停
                if any(ph in k for ph in phrases):
                    hit = name
                    break
        if hit and hit not in out:
            out.append(hit)
    return out


def unknown_base_models(rows):
    """有底模文件、但一个 family 都没命中的路径（去重）。

    只报「真的认不出来」的：完全没有底模记录的档案不在此列，免得每次构建刷屏。
    """
    bad = []
    for r in rows:
        if r.get("families"):
            continue
        for p in r.get("base_models") or []:
            if p not in bad:
                bad.append(p)
    return bad


def warn_unknown(rows):
    bad = unknown_base_models(rows)
    if not bad:
        return
    print()
    print("⚠ 未归类的底模（不影响发布，筛选器里会落在「%s」）：" % UNKNOWN_FAMILY)
    for p in bad:
        print("    %s" % p)
    print("  → 确认它属于哪个 family 后，加进 %s" % show_path(FAMILIES_JSON))


def summarize(item, rec, max_video_mb):
    """把一份档案压成列表/卡片要用的字段。

    产物分两层：
      * `media_*`    —— 第一个产物（兼容既有调用方：卡片缩略图、--list 产物列）
      * `media_list` —— 全部产物，每项 {path,name,kind,size,skip,missing,missing_kind,local}
    一次执行批量出图时 media_list 有 N 项，其它字段（耗时/步数/模型）仍是同一份。
    """
    m = rec.get("metrics") or {}
    run = rec.get("run") or {}
    tags = rec.get("tags") or {}

    media_list = []
    for x in item.get("deliverables") or []:
        d = x.get("d") or {}
        path = x.get("path")
        kind = x.get("kind") or "file"
        size = x.get("size")
        over = bool(kind == "video" and max_video_mb > 0 and size
                    and size > max_video_mb * 1024 * 1024)
        # 档案里记着产物、插件 logs 目录里却没有这个文件。两种成因要分开说：
        #   present=true  → 另存为时原文件还在，只是勾了「只存档案，不搬图」，
        #                   所以插件目录本来就没有它（同步的取数边界就是插件目录，不回溯 output/）
        #   present=false → 另存那一刻原文件就已经不在原路径了
        missing = bool(not path and (x.get("name") or d.get("filename")))
        missing_kind = ""
        if missing:
            missing_kind = "gone" if d.get("present") is False else "unmoved"
        media_list.append({
            "path": path,
            "local": x.get("local"),
            "name": x.get("name") or d.get("filename") or "",
            "kind": kind,
            "size": size,
            "skip": over,
            "missing": missing,
            "missing_kind": missing_kind,
        })

    # 第一个「能用」的产物当作代表：优先有文件的，全都没有就取第一个（用于展示缺失原因）
    head = next((x for x in media_list if x["path"]), media_list[0] if media_list else None)
    media_path = head["path"] if head else None
    kind = head["kind"] if head else ""
    size = head["size"] if head else None

    date, clock, stamp = stamp_of(item["base"], rec)
    base_files = base_model_paths(rec)
    fams = family_of(base_files)
    return {
        "base": item["base"],
        "json": item["json"],
        "html": item.get("html"),
        "media": media_path,
        "media_kind": kind,
        "media_size": size,
        "media_skip": bool(head["skip"]) if head else False,
        "media_missing": bool(head["missing"]) if head else False,
        "media_missing_kind": head["missing_kind"] if head else "",
        "media_list": media_list,
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
        # 筛选器用的底模家族。families 是列表（理论上可能一次执行用两个底模），
        # family 取第一个供卡片/下拉直接用；全认不出来落「未归类」。
        "base_models": base_files,
        "families": fams,
        "family": fams[0] if fams else UNKNOWN_FAMILY,
        "deliverable_name": (head["name"] if head else ""),
        "deliverable_count": len(media_list),
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


# ------------------------------------------------------------------ --rm
def show_path(p):
    """给人看的路径：能相对就相对，不能（跨盘符）就用绝对，绝不抛异常。

    os.path.relpath 在 Windows 上跨驱动器会 ValueError（比如项目在 D:、
    目标在 C:），生产路径虽然同盘，但打印路径这种小事不值得让它把删除流程打断。
    """
    try:
        r = os.path.relpath(p, ROOT)
        return p if r.startswith("..") else r
    except ValueError:
        return p


def scan_dst():
    """列出**站点里已有**的档案，顺序与聚合页一致（时间倒序）。

    --rm 必须用这份列表而不是 scan_src(插件源)：上不上站点是人工决定的，
    两边档案数并不相同（源里常有没发布的），用源的序号删站点会张冠李戴。
    """
    items, err = scan_src(DST_DIR)
    if err:
        return [], err
    rows = [summarize(it, read_json(it["json"]), 20.0) for it in items.values()]
    rows.sort(key=lambda r: (r["stamp"], r["base"]), reverse=True)
    return rows, None


def files_of(r):
    """一份档案在站点上占用的全部文件（绝对路径）。

    三部分：json、html、逐个产物。产物靠 summarize 的 media_list
    （已由 locate_local 三级兜底定位），所以老档案的 `<基名>.png`
    和新档案的 `<基名>_N.png` 都能准确收全，不会漏也不会误伤别的档案。
    """
    out = []
    for name in (r["base"] + JSON_SUFFIX, r["base"] + HTML_SUFFIX):
        p = os.path.join(DST_DIR, name)
        if os.path.exists(p):
            out.append(p)
    for m in r.get("media_list") or []:
        if m.get("local"):
            p = os.path.join(DST_DIR, m["local"])
            if os.path.exists(p):
                out.append(p)
    return out


def cmd_rm(picks_text, dry):
    """从站点移除选中的档案：移到 _trash/<时间戳>/，然后重建聚合页。

    dry=True 时只打印清单，一个字节都不动。
    """
    rows, err = scan_dst()
    if err:
        print(err)
        return 1
    if not rows:
        print("站点里没有档案可删：%s" % DST_DIR)
        return 0

    picks = parse_picks(picks_text, rows)
    if not picks:
        print("没有选中任何档案。可删的序号见下方清单。")
        picks = []

    # 先不管有没有选中都把清单打出来，省得用户回头再查一遍序号。
    # 基名不截断：--rm 现在既收序号也收完整名，截断了就没法复制粘贴。
    print("站点现有档案（%d 份）：" % len(rows))
    width = max(len(r["base"]) for r in rows)
    for i, r in enumerate(rows, 1):
        mark = "→" if i in picks else " "
        print("  %s %-2d  %-8s  %-*s %d 个产物" % (
            mark, i, ("%s %s" % (r["date"], r["clock"])).strip() or "—",
            width, r["base"], r["deliverable_count"]))
    if not picks:
        print()
        print("用法：--rm 1,3  或  --rm <完整档案名>        （只看清单）")
        print("      --rm 1,3 --yes                        （真的移到 _trash）")
        return 0

    total_files, total_bytes = 0, 0
    plan = []
    for i in picks:
        r = rows[i - 1]
        fs = files_of(r)
        # 档案里记着产物、站点上却没有对应文件：如实说，不假装删干净了
        missing = [m["name"] for m in (r.get("media_list") or [])
                   if not m.get("local")]
        plan.append((r, fs, missing))
        total_files += len(fs)
        total_bytes += sum(os.path.getsize(p) for p in fs)

    print()
    print("将移除 %d 份档案，共 %d 个文件（%s）：" % (
        len(plan), total_files, human(total_bytes)))
    for r, fs, missing in plan:
        print("  [%s]" % r["base"])
        for p in fs:
            print("      %s  (%s)" % (os.path.basename(p), human(os.path.getsize(p))))
        for n in missing:
            print("      ⚠ %s 档案里记着但站点上没有，跳过" % n)

    if dry:
        print()
        print("以上为预览。确认无误后加 --yes 真正执行（文件移到 %s）。"
              % show_path(TRASH_DIR))
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_dir = os.path.join(TRASH_DIR, stamp)
    os.makedirs(dest_dir, exist_ok=True)
    moved, failed = 0, []
    for r, fs, missing in plan:
        for p in fs:
            dst = os.path.join(dest_dir, os.path.basename(p))
            try:
                shutil.move(p, dst)
                moved += 1
            except Exception as e:
                failed.append((os.path.basename(p), repr(e)))
    print()
    print("已移到 %s：%d 个文件" % (show_path(dest_dir), moved))
    if failed:
        print("⚠ 有 %d 个文件没能移动：" % len(failed))
        for n, e in failed:
            print("    %s: %s" % (n, e))
        return 1
    print("要还原：把 %s 里的文件拷回 full-logs/ 再跑一次 --build"
          % show_path(dest_dir))
    print()
    return cmd_build(False)


# ------------------------------------------------------------------ --list
def cmd_list(rows, src, max_video_mb, names=False):
    if not rows:
        print("源目录里没有档案：%s" % src)
        print("（插件在 ComfyUI 里另存一份完整日志后，这里才会出现条目）")
        return

    # --names：只吐「序号 + 完整基名」两列，方便直接复制给 --sync / --rm。
    # 宽表那一列「工作流」是被拆过的短名（方案/卡/内存各占一列），不是基名，
    # 照抄过去匹配不上——要写进脚本时用这个，别用宽表。
    if names:
        for i, r in enumerate(rows, 1):
            print("%-3d %s" % (i, r["base"]))
        print()
        print("复制上面的完整名：python scripts/build_full_logs.py --sync <完整档案名>")
        return

    head = ["#", "状态", "时间", "工作流", "方案", "卡", "内存", "类型", "产物", "总体积"]
    table = [head]
    for i, r in enumerate(rows, 1):
        mlist = r.get("media_list") or []
        present = [x for x in mlist if x["path"]]
        # 产物列：有图时写类型 + 张数（多图时明示）；一张都没有时说清原因
        if present:
            kinds = {x["kind"] for x in present}
            base_kind = {"image": "图片", "video": "视频", "audio": "音频"}.get(
                r["media_kind"], "文件")
            prod = base_kind if len(kinds) == 1 else "混合"
            if len(present) > 1:
                prod += " ×%d" % len(present)
            if any(x["skip"] for x in present):
                prod += " ⚠超限"
            type_cell = "—" if len(kinds) > 1 else r["media_kind"]
        else:
            prod = ("未搬图" if r["media_missing_kind"] == "unmoved"
                    else "原件已失") if r["media_missing"] else "无"
            type_cell = "—"
        total = (os.path.getsize(r["json"]) if os.path.exists(r["json"]) else 0)
        total += os.path.getsize(r["html"]) if r["html"] else 0
        total += sum(x["size"] or 0 for x in present)
        table.append([
            str(i),
            "已同步" if dst_state(r["base"]) == "exist" else "新增",
            ("%s %s" % (r["date"], r["clock"])).strip() or "—",
            r["workflow"],
            r["scheme"] or "—",
            r["card"] or "—",
            r["memory"] or "—",
            type_cell,
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
        print("        序号会随档案增删漂移；要写进脚本就用 --list --names 取完整档案名")


# ------------------------------------------------------------------ --sync
def norm_pick(s):
    """把用户写的档案名归一成基名（`base`）。

    容忍三种写法，剥掉后缀后等价：
        202611031216_Moss文生图8步+TE2b优化                    ← 裸基名（--list --names 直接给这个）
        202611031216_Moss文生图8步+TE2b优化.full_log           ← 半截后缀
        202611031216_Moss文生图8步+TE2b优化.full_log.json      ← 完整文件名
    顺手容忍：整条路径（粘贴时带目录）、首尾引号、Windows 反斜杠。
    """
    t = (s or "").strip().strip('"').strip("'")
    t = os.path.basename(t.replace("\\", "/"))
    for suf in (JSON_SUFFIX, HTML_SUFFIX, ".full_log"):
        if t.lower().endswith(suf):
            t = t[: -len(suf)]
            break
    return t.strip()


def parse_picks(text, rows):
    """把选择串解析成 1-based 行号列表。**两种模式，不混用**：

        ① 序号      `1,3,5` / `1-3,7`  —— 本次列表里的位置。快，但会随档案增删漂移，
                                          所以只适合「先 --list 紧接着 --sync」。
        ② 完整档案名 `202611031216_Moss文生图8步+TE2b优化`
                                      —— 精确匹配，永不漂移，可写进脚本或隔天执行。
                                          允许带 .full_log / .full_log.json / .html 后缀。

    **不做前缀匹配**：前缀只能精确到分钟，同一分钟内同工作流同参数的两次执行会撞名
    （插件侧会存成 `...-2`），前缀就会命中两份。宁可报错让人补全，也不猜。
    同一串里可以混写：`--sync 1,202611031055_Illustrious-XL文生图`。
    """
    text = (text or "").strip()
    # 有逗号就只按逗号切（档案名里万一带空格也不会被切碎）；没逗号才退回空白分隔
    chunks = text.split(",") if "," in text else re.split(r"\s+", text)

    index = {}                     # casefold(base) -> [行号…]（Windows 文件名不分大小写）
    for i, r in enumerate(rows, 1):
        index.setdefault(r["base"].casefold(), []).append(i)

    picks, unknown = [], []
    ranges, singles = [], []        # 数字分两种收：区间只认位置，单值可退回名字匹配
    for chunk in chunks:
        tok = chunk.strip()
        if not tok:
            continue
        m = re.match(r"^(\d+)-(\d+)$", tok)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                raise SystemExit("区间写反了：%s（应写成 小的-大的）" % tok)
            ranges.extend(range(a, b + 1))
        elif tok.isdigit():
            singles.append(int(tok))
        else:
            hit = index.get(norm_pick(tok).casefold()) or []
            if len(hit) == 1:
                picks.append(hit[0])
            else:
                # 0 命中（写错/已不存在）或 >1（理论上完整名唯一，撞了就如实报）
                unknown.append(norm_pick(tok))

    upper = len(rows)
    bad = [p for p in ranges if p < 1 or p > upper]
    if bad:
        raise SystemExit("序号超范围：%s（1..%d）" % (bad, upper))
    picks.extend(ranges)

    # 纯数字但超出 1..N：很可能是被截断的档案名（只打了日期 `202611031216` 之类），
    # 这一支退回名字匹配，别让「序号超范围」把真实原因盖住。
    for n in singles:
        if 1 <= n <= upper:
            picks.append(n)
            continue
        hit = index.get(str(n).casefold()) or []
        if len(hit) == 1:
            picks.append(hit[0])
        else:
            unknown.append(str(n))

    if unknown:
        print("认不出这些选择（既不是 1..%d 的序号，也不是档案名）：" % upper)
        for name in unknown:
            print("  × %s" % name)
            for n in difflib.get_close_matches(name, [r["base"] for r in rows],
                                               n=3, cutoff=0.4):
                print("      是不是要：%s" % n)
        print()
        print("--list --names 可列出全部完整档案名（完整名永不漂移，推荐写这个）")
        raise SystemExit(1)
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
    ("https://blog.blackwood.cv/news/latest", "Intel GPU生态日报 ↗", 2),
    ("https://comfyui-wiki.com/zh/news", "ComfyUI新闻动态 ↗", 2),
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
        # 产物：一次执行可能有多张（批量出图），逐张处理。
        # 目标文件名沿用源名（`<基名>_N.png` / 老档案的 `<基名>.png`），
        # 这样档案里的 archive_name 与站点上的实际文件名保持一致，详情页的
        # <img src> 不用改写就能直接用。
        mlist = r.get("media_list") or []
        if mlist:
            for item in mlist:
                nm = os.path.basename(item["path"]) if item["path"] else item["name"]
                if item["skip"]:
                    print("    %-5s 跳过：%s（%.1f MB，超过 %.0f MB 上限）" % (
                        "产物", nm, (item["size"] or 0) / 1048576.0, max_video_mb))
                elif item["path"]:
                    res = copy_one(item["path"],
                                   os.path.join(DST_DIR, os.path.basename(item["path"])), dry)
                    print("    %-5s %s%s" % ("产物", {
                        "copied": "已拷贝 ",
                        "same": "内容一致，跳过 ",
                        "missing": "源文件缺失 ",
                        "would-copy": "将拷贝 ",
                    }[res], os.path.basename(item["path"])))
                elif item["missing"]:
                    if item["missing_kind"] == "unmoved":
                        print("    %-5s 无：%s 另存时选了「只存档案，不搬图」，插件目录本来就没有它"
                              % ("产物", item["name"]))
                    else:
                        print("    %-5s 无：另存那一刻 %s 就已不在原路径"
                              % ("产物", item["name"]))
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
  /* 筛选后卡片变少 → 页面可能短到不出滚动条 → 视口宽度凭空多 15px，
     整页会向右跳一下，重置后又跳回去。常驻预留滚动条槽位，消除这次位移。 */
  html { scrollbar-gutter: stable; }
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
  /* 筛选器：整条做成一张胶囊卡片（白底 / 细边 / 轻投影 / 大圆角）。
     左侧「标签 + 下拉」三组，右侧「找到 x 条 共 N 条 + ↻ 重置」。
     窄屏自然换行，靠 margin-left:auto 保证换行后状态仍贴右。 */
  .filter-bar {
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px 18px; flex-wrap: wrap;
    margin: 32px 0; padding: 10px 18px;
    background: var(--card);
    border: 1px solid var(--border); border-radius: 14px;
    box-shadow: 0 1px 2px rgba(16, 42, 67, 0.05);
  }
  .filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 22px; }
  .f-item { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-muted); }
  .f-item select {
    font: inherit; font-size: 13px; padding: 5px 10px;
    /* 三个下拉等宽：宽度随最长选项（MiniMax-H3-Image）自动伸缩时，三项宽度不一，
       切换取值还会微调。160 是放下最长选项所需的最小整数宽度。窄屏另放开，见媒体查询 */
    width: 160px; min-width: 100px; max-width: 46vw;
    border: 1px solid var(--border); border-radius: 8px; background: var(--card);
    color: var(--text); cursor: pointer;
  }
  .f-item select:hover { border-color: #a8cff0; }
  .f-item select:focus { outline: 2px solid #a8cff0; outline-offset: 1px; }
  /* 每段包一层 span：flex 会把裸文本切成独立的匿名 flex item，
     10px gap 会插进「找到 / 6 / 条」中间，字距被撑开 */
  .filter-state {
    display: flex; align-items: center; gap: 10px; margin-left: auto;
    font-size: 13px; color: var(--text-muted); font-variant-numeric: tabular-nums;
  }
  .filter-state b { color: var(--intel-blue-dark); font-size: 14px; }
  /* 「重置」按设计稿做成文字链接样式：无边框无底色，只有图标 + 蓝字，hover 才出浅底 */
  .f-clear {
    display: inline-flex; align-items: center; gap: 4px; margin-left: 2px;
    font: inherit; font-size: 13px; line-height: 1.5; padding: 3px 7px; cursor: pointer;
    border: 0; border-radius: 8px; background: none; color: var(--intel-blue-dark);
  }
  .f-clear svg { display: block; }
  .f-clear:hover { background: #eaf3fc; }
  .f-clear:focus-visible { outline: 2px solid #a8cff0; outline-offset: 1px; }
  .fl-empty { text-align: center; color: var(--text-muted); font-size: 14px; padding: 40px 0; }
  /* 这几处自己写了 display，会盖掉 [hidden] 的 UA 默认 display:none，必须显式声明 */
  .log-card[hidden], .filter-bar[hidden], .fl-empty[hidden] { display: none; }
  .log-grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 32px; }
  /* 有筛选条时由 .filter-bar 自己的 margin-bottom 负责间距，别叠加 */
  .filter-bar ~ .log-grid { margin-top: 0; }
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
  /* 缩略图容器：多张产物时在首图右下角压一个「N 张」角标。
     容器用 inline-block 让角标贴着图片边界，而不是贴着右侧栏宽度。 */
  .thumb-wrap { position: relative; display: inline-block; line-height: 0; }
  .thumb-count {
    position: absolute; right: 6px; bottom: 6px;
    background: rgba(15,23,32,0.72); color: #eaf2fa;
    font-size: 11px; line-height: 1.6; padding: 0 6px; border-radius: 999px;
    pointer-events: none;
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
    /* 筛选条：胶囊卡片的内边距与栏距一起收紧，窄屏才放得下三组下拉 */
    .filter-bar { padding: 10px 12px; gap: 8px 12px; }
    .filters { gap: 8px 14px; }
    /* 等宽在窄屏没意义（三项本来就折行），放开自然宽度，免得长选项被原生 select 截断 */
    .f-item select { width: auto; }
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
      <a class="chip" href="https://blog.blackwood.cv/news/latest" target="_blank" rel="noopener">Intel GPU生态日报 ↗</a>
      <a class="chip" href="https://comfyui-wiki.com/zh/news" target="_blank" rel="noopener">ComfyUI新闻动态 ↗</a>"""


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
    """从 API 图（完整日志的「工作流结构」部分）枚举所有被引用的模型文件，按图里顺序返回。

    为什么不能只看工作流执行日志：它只打印真正触发加载的 `Requested to load`，
    而 LoRA 是打补丁（apply/merge）不是 load 一个 ModelPatcher，执行日志里根本不出现；
    多输入加载器（例如 MossCLIPLoader 的 clip_name + adapter 两个 TE）在执行日志里
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
    # ② 执行日志里记着、但图里找不到对应加载节点的（间接加载）补在后面，不丢信息。
    #    ⚠️ 只有 file 为空时**绝不**退回类名：`QwenImage21` / `WanVAE` 这类是模型包装类，
    #    不是文件名，写成"模型"会让卡片出现「底模：QwenImage21」这种令人困惑的行。
    #    GGUF 工作流的 policy 行是 paths=[]，**执行日志里**没有文件名，
    #    但**完整日志里有**（工作流结构部分的 unet_name / clip_name），所以图里已经有真名。
    for m in models or []:
        if m.get("file"):
            add(m.get("role"), m.get("file"))

    out = []
    seen = set()
    for role in ROLE_ORDER:
        names = by_role.get(role)
        if not names:
            continue
        # 同一个文件名只留在**优先级最高**的那一行：checkpoint（一体化模型，如
        # Illustrious / SDXL 的 CheckpointLoaderKJ）的 base / TE / VAE 是三次加载，
        # 但共用同一个 .safetensors 文件。卡片是索引，重复写两遍只是噪音。
        # 详情页那张表不做这个去重 —— 那里要看清三次加载各自的 MB / 耗时。
        keep = [n for n in names if n not in seen]
        if not keep:
            continue
        seen.update(keep)
        out.append(
            '<div class="model-row"><i>%s</i><span>%s</span></div>'
            % (esc(ROLE_LABELS.get(role, role)), " / ".join(soft(n) for n in keep))
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


# ------------------------------------------------------------------ 筛选器
# 维度 key 必须与 card_html 写进卡片的 data-f-* 一一对应。
# 只有这三个（Allan 2026-11-14 定）；「测试类型」有意不做：冷启含加载、
# 重载/热启是纯采样，混在一个筛选里对比耗时容易得出错误结论。
FACETS = (("family", "模型"), ("card", "显卡"), ("memory", "内存"))

# 「重置」按钮的 ↻ 图标（Feather rotate-ccw，viewBox 24 缩到 12px）。
# 内联 SVG 而不是用文字字符「⟲」：字符在不同字体下大小/基线都不一样，
# 会跟「重置」两个字对不齐。
RESET_ICON = ('<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true" '
              'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round"><path d="M1 4v6h6"/>'
              '<path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>')

# 前端只做「显隐开关」，不取数、不渲染：卡片内容照旧全部烘在 HTML 里，
# 所以无 JS / 爬虫 / Ctrl+F 都照常工作。降级时筛选条整体不显示（hidden）。
SCRIPT = """(function () {
  var bar = document.getElementById('fl-bar');
  if (!bar) return;                        // 页面没有筛选条（空档案）→ 不启用
  var cards = [].slice.call(document.querySelectorAll('.log-card'));
  var sels = [].slice.call(bar.querySelectorAll('select'));
  var cnt = document.getElementById('fl-cnt');
  var empty = document.getElementById('fl-empty');

  function keyOf(sel) { return sel.getAttribute('data-f'); }

  function apply() {
    var shown = 0;
    cards.forEach(function (c) {
      var ok = true;
      for (var i = 0; i < sels.length; i++) {
        var v = sels[i].value;
        if (v && c.getAttribute('data-f-' + keyOf(sels[i])) !== v) { ok = false; break; }
      }
      c.hidden = !ok;
      if (ok) shown++;
    });
    if (cnt) cnt.textContent = shown;
    if (empty) empty.hidden = shown > 0;

    // 反写地址栏：刷新不丢、链接可分享。file:// 下 replaceState 可能抛错，忽略即可。
    var qs = [];
    sels.forEach(function (s) {
      if (s.value) qs.push(encodeURIComponent(keyOf(s)) + '=' + encodeURIComponent(s.value));
    });
    try {
      history.replaceState(null, '', location.pathname + (qs.length ? '?' + qs.join('&') : ''));
    } catch (e) {}
  }

  // 从 URL 恢复：值必须真的在 <option> 里才采用，
  // 否则一个手改脏的参数会把筛选弄成 0 命中，看起来像页面坏了。
  var qp = new URLSearchParams(location.search);
  sels.forEach(function (s) {
    var v = qp.get(keyOf(s));
    if (!v) return;
    for (var i = 0; i < s.options.length; i++) {
      if (s.options[i].value === v) { s.value = v; break; }
    }
  });

  sels.forEach(function (s) { s.addEventListener('change', apply); });
  var clear = document.getElementById('fl-clear');
  if (clear) clear.addEventListener('click', function () {
    sels.forEach(function (s) { s.value = ''; });
    apply();
  });

  // 整行一起放出来：没有 JS 时它一直是 hidden，页面直接从 sort-banner 跳到卡片
  var wrap = document.getElementById('fl-wrap');
  if (wrap) wrap.hidden = false;
  apply();
})();"""


def filters_html(rows):
    """返回筛选条整行（左下拉 + 右状态）。一行档案都没有时返回空串。

    三个维度**始终都出**（Allan 2026-11-14 定：模型 / 显卡 / 内存 要固定三个）：
    即使某项只有一个取值，下拉也照常渲染——位置固定、习惯稳定，用户不用每次
    猜「今天哪几个下拉在」。唯一的例外是某维度一条取值都没有（字段全空），
    这种下拉点开只有「全部」，替不了任何筛选，直接跳过。

    下拉里**不写数量**（Allan 2026-11-14 定）：选项只放名字，条数统一由
    右侧「找到 x 条，共 N 条」表达。排序仍按条数降序，常用的排前面。
    """
    parts = []
    for key, label in FACETS:
        counts = {}
        for r in rows:
            v = (r.get(key) or "").strip()
            if v:
                counts[v] = counts.get(v, 0) + 1
        if not counts:
            continue
        opts = ['<option value="">全部</option>']
        for v in sorted(counts, key=lambda x: (-counts[x], x)):
            opts.append('<option value="%s">%s</option>' % (esc(v), esc(v)))
        parts.append(
            '<label class="f-item">%s<select data-f="%s" aria-label="按%s筛选">%s</select></label>'
            % (esc(label), key, esc(label), "".join(opts)))
    if not parts:
        return ""

    n = len(rows)
    # 整行一起 hidden：无 JS 时不留空白，也不留空 flex 容器的间距
    return ('  <div class="filter-bar" id="fl-wrap" hidden>\n'
            '    <div class="filters" id="fl-bar">%s</div>\n'
            '    <div class="filter-state" id="fl-state">'
            '<span>找到 <b id="fl-cnt">%d</b> 条</span>'
            '<span>共 %d 条</span>'
            '<button type="button" class="f-clear" id="fl-clear">%s重置</button>'
            '</div>\n'
            '  </div>\n'
            '  <div class="fl-empty" id="fl-empty" hidden>没有符合筛选条件的档案。</div>\n'
            % ("".join(parts), n, n, RESET_ICON))


def card_html(r):
    base = r["base"]
    href = None
    if r["html"] and os.path.exists(os.path.join(DST_DIR, base + HTML_SUFFIX)):
        href = "full-logs/" + url_of(base + HTML_SUFFIX)
    tag = "a" if href else "div"
    attrs = ' class="log-card" href="%s"' % esc(href) if href else ' class="log-card is-flat"'
    # 筛选器的判据属性。JS 只按这几个 data-f-* 做显隐，不碰卡片内容本身：
    # 内容照旧全部烘在 HTML 里，无 JS / 爬虫 / Ctrl+F 都不受影响。
    attrs += ' data-f-family="%s" data-f-card="%s" data-f-memory="%s"' % (
        esc(r.get("family") or ""), esc(r["card"]), esc(r["memory"]))

    tags = []
    # 冷启/重载/热启 放在最前：它决定这张卡的性能基线，比方案/卡/内存更靠前读
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

    # 缩略图：产物图按原始比例缩放（不做裁切）；显卡图挪到左列日期下方。
    # 多张产物只在卡片上放**首图**，右上角标张数——卡片是索引，
    # 全部图片和逐张信息去详情页看（详情页有 slide 可切换）。
    thumbs = []
    mlist = r.get("media_list") or []
    imgs = [x for x in mlist if x["path"] and x["kind"] == "image"]
    if imgs:
        first = imgs[0]
        badge = ('<span class="thumb-count">%d 张</span>' % len(imgs)) if len(imgs) > 1 else ""
        thumbs.append(
            '<span class="thumb-wrap"><img class="log-thumb" src="%s" alt="%s" loading="lazy">%s</span>'
            % (esc("full-logs/" + url_of(os.path.basename(first["path"]))),
               esc(first["name"] or base), badge))
    elif any(x["kind"] in ("video", "audio") for x in mlist):
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


def _pad(s, width):
    """按显示宽度补空格：CJK 字符占 2 列，`%-13s` 会把中文表格错位。"""
    n = sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)
    return s + " " * max(0, width - n)


def _cut(s, width):
    """按显示宽度截断（不是字符数）：档案名里的中文按 2 列算。"""
    out, n = [], 0
    for ch in s:
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if n + w > width:
            return "".join(out) + "…" if out else ""
        out.append(ch)
        n += w
    return "".join(out)


def cmd_families():
    """只读审计：站点每份档案的「底模 → family」，以及未归类清单。

    这张映射表是筛选器的唯一依据，写错就会筛错，所以必须能一眼核完。
    """
    if not os.path.isdir(DST_DIR):
        print("目录不存在：%s" % DST_DIR)
        return 1
    items, err = scan_src(DST_DIR)
    if err:
        print(err)
        return 1
    rows = []
    for base, item in items.items():
        rows.append(summarize(item, read_json(item["json"]), 20.0))
    rows.sort(key=lambda r: (r["stamp"], r["base"]), reverse=True)

    fams, exact = load_families()
    print("family 表：%s（match %d 组 / exact %d 条）"
          % (show_path(FAMILIES_JSON), len(fams), len(exact)))
    print()
    print("  %s%s%s" % (_pad("family", 20), _pad("档案", 52), "底模"))
    print("  %s%s%s" % (_pad("-" * 18, 20), _pad("-" * 50, 52), "-" * 30))
    for r in rows:
        fam = r["family"] if r["families"] else UNKNOWN_FAMILY
        files = " / ".join(r["base_models"]) or "(无底模记录)"
        print("  %s%s%s" % (_pad(fam, 20), _pad(_cut(r["base"], 50), 52), files))

    cnt = {}
    for r in rows:
        k = r["family"] if r["families"] else UNKNOWN_FAMILY
        cnt[k] = cnt.get(k, 0) + 1
    print()
    print("汇总：%s" % " · ".join("%s %d" % (k, v)
                                 for k, v in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))))
    warn_unknown(rows)
    return 0


def cmd_build(dry):
    if not os.path.isdir(DST_DIR):
        print("目录不存在：%s（先跑 --sync 同步至少一份档案）" % DST_DIR)
        return 1
    # 直接复用 scan_src：产物定位规则（archive_name → 名字_N → 名字）只写一处，
    # 免得 --build 与 --sync 对「哪张图算这份档案的」判断不一致。
    items, err = scan_src(DST_DIR)
    if err:
        print(err)
        return 1
    rows = []
    for base, item in items.items():
        rec = read_json(item["json"])
        rows.append(summarize(item, rec, 20.0))
    rows.sort(key=lambda r: (r["stamp"], r["base"]), reverse=True)
    warn_unknown(rows)

    if rows:
        body = '<div class="log-grid">\n%s  </div>' % "".join(card_html(r) for r in rows)
        fbar = filters_html(rows)
    else:
        body = '<div class="empty">还没有任何档案。在 ComfyUI 里另存一份完整日志后，' \
               '用 <code>--sync</code> 同步进来。</div>'
        fbar = ""
    # 没有筛选器就不插脚本：省得页面里挂一段必然 return 的死代码
    script_block = ("<script>\n%s\n</script>\n" % SCRIPT) if fbar else ""

    page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IntelGpu-ComfyUI-Collection - 完整日志</title>
<style>%(css)s</style>
</head>
<body>
<div class="container">

  <header>
    <h1>IntelGpu-ComfyUI-Collection</h1>
    <p class="note">每份档案 = 一次执行的完整上下文：运行环境、模型加载、时间轴、原始日志、工作流结构、产物</p>
    <div class="chips">
%(chips)s
    </div>
  </header>

  <div class="sort-banner">
    共 %(n)d 份档案 · 按时间倒排（新 → 旧）· 由本地脚本从各档案的 <code>.full_log.json</code> 渲染，远端不参与生成 · 点击卡片进入完整档案
  </div>

%(filters)s%(body)s

  <footer>
    <a href="https://github.com/allanmeng/IntelGpu-ComfyUI-Collection" target="_blank">IntelGpu-ComfyUI-Collection</a> ·
    <a href="full-logs/" target="_blank">full-logs/ 档案目录</a>
  </footer>

</div>
%(script)s</body>
</html>
""" % {"css": CSS, "chips": CHIPS, "n": len(rows),
       "filters": fbar, "body": body, "script": script_block}

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
    ap.add_argument("--list", action="store_true",
                    help="只读：列出源目录里的档案与同步状态（不写任何文件）")
    ap.add_argument("--names", action="store_true",
                    help="配合 --list：只打印「序号 + 完整档案名」，方便复制给 --sync / --rm")
    ap.add_argument("--sync", default="", metavar="1,3 或 完整档案名",
                    help="同步这些档案（序号或完整档案名，可混写），末尾自动重建聚合页")
    ap.add_argument("--sync-all", action="store_true",
                    help="同步全部档案，末尾自动重建聚合页")
    ap.add_argument("--build", action="store_true", help="只重建 full-logs.html，不动档案")
    ap.add_argument("--families", action="store_true",
                    help="只读：审计「底模 → family」映射（含未归类清单），不写任何文件")
    # nargs="?"：裸 --rm 直接列站点清单（挑序号用），带参数才进预览/删除流程。
    # 少了这个，`--rm` 不带值会被 argparse 判成「缺少参数」直接报错退出。
    ap.add_argument("--rm", nargs="?", default=None, const="", metavar="1,3 或 完整档案名",
                    help="从站点移除这些档案（移到 _trash，可还原）；不给则只列清单，"
                         "不加 --yes 只预览")
    ap.add_argument("--yes", action="store_true",
                    help="确认执行不可逆操作（目前只有 --rm 需要）")
    ap.add_argument("--restyle", action="store_true",
                    help="只重灌详情页的站点头部（返回 + 导航），不碰 json/产物/本地原件")
    ap.add_argument("--src", default=os.environ.get("FULLLOG_SRC") or DEFAULT_SRC,
                    help="插件日志目录")
    ap.add_argument("--max-video-mb", type=float, default=20.0,
                    help="视频超过该体积就不随档案发布（0 = 不限）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写文件")
    a = ap.parse_args(argv)

    if a.families:
        return cmd_families()

    # --rm 最先处理：它走的是**站点**列表，与 --sync/--list 的源列表序号不是一回事，
    # 两者同时给容易把序号搞混，直接拒绝。
    # 用 is not None 判："" 是「裸 --rm，只列清单」，与「没给这个参数」不是一回事
    if a.rm is not None:
        if a.sync or a.sync_all:
            print("--rm 与 --sync 不能同时用：两者的序号来自不同列表"
                  "（--rm 按站点现存档案，--sync 按插件源目录）。")
            return 2
        # 裸 --rm 只列清单：dry 强制为 True，连 --yes 也不执行
        return cmd_rm(a.rm, dry=True if not a.rm else (a.dry_run or not a.yes))

    if a.restyle and not (a.sync or a.sync_all):
        return cmd_restyle(a.dry_run)

    if a.build and not (a.sync or a.sync_all):
        return cmd_build(a.dry_run)

    rows, err = collect(a.src, a.max_video_mb)
    if err:
        print(err)
        return 2

    if not (a.sync or a.sync_all):
        cmd_list(rows, a.src, a.max_video_mb, names=a.names)
        return 0

    if a.sync_all:
        picks = list(range(1, len(rows) + 1))
    else:
        picks = parse_picks(a.sync, rows)
    if not picks:
        print("没有选中任何档案。")
        return 0

    cmd_sync(rows, picks, a.max_video_mb, a.dry_run)
    print()
    return cmd_build(a.dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
