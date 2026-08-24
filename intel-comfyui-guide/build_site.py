# -*- coding: utf-8 -*-
"""渲染指南 md → 精装 HTML（宽屏两栏版，部署用）

用法: python build_site.py [md_path]
- 不带参数：自动选择本目录下日期最新的 `Intel GPU 的 ComfyUI 系统优化指南-YYYYMMDD.md`
- 带参数：渲染指定的 md（如 `python build_site.py "xxx.md"`）
- 输出：index.html（带左侧固定目录 + 顶部下载按钮）
"""
import markdown, re, glob, os, sys

DIR = os.path.dirname(os.path.abspath(__file__))
html_path = os.path.join(DIR, 'index.html')

if len(sys.argv) > 1:
    md_path = sys.argv[1]
else:
    mds = glob.glob(os.path.join(DIR, 'Intel GPU 的 ComfyUI 系统优化指南-*.md'))
    if not mds:
        print('[错误] 未找到指南 md 文件（Intel GPU 的 ComfyUI 系统优化指南-YYYYMMDD.md）')
        sys.exit(1)
    def date_key(p):
        m = re.search(r'-(\d{8})\.md$', p)
        return m.group(1) if m else '0'
    mds.sort(key=date_key)
    md_path = mds[-1]  # YYYYMMDD 最大 = 日期最新
    print('自动选择最新 md:', os.path.basename(md_path))

md_text = open(md_path, encoding='utf-8').read()

title = re.search(r'^# (.+)$', md_text, re.M).group(1).strip()

md = markdown.Markdown(extensions=['tables', 'fenced_code', 'toc'],
                       extension_configs={'toc': {'toc_depth': '2-3'}})
body = md.convert(md_text)
toc = md.toc

page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif; color:#222; line-height:1.75; background:#f5f6f8; }}
.header {{ background:#1a2d5c; color:#fff; padding:28px 20px; text-align:center; }}
.header h1 {{ font-size:26px; font-weight:600; margin-bottom:6px; }}
.header p {{ font-size:13px; opacity:.8; }}
.download-btn {{ display:inline-block; margin-top:18px; background:#ff7a1a; color:#fff; text-decoration:none; padding:16px 40px; border-radius:10px; font-size:18px; font-weight:700; box-shadow:0 4px 16px rgba(255,122,26,.45); transition:transform .15s, background .15s; }}
.download-btn:hover {{ background:#e96a0a; transform:translateY(-2px); box-shadow:0 6px 20px rgba(255,122,26,.55); }}
.wrap {{ max-width:1720px; margin:0 auto; padding:24px 32px 60px; display:flex; gap:32px; align-items:flex-start; }}
.sidebar {{ flex:0 0 260px; position:sticky; top:20px; max-height:calc(100vh - 40px); overflow-y:auto; }}
.main {{ flex:1 1 auto; min-width:0; }}
.toc {{ background:#fff; border:1px solid #e3e6ea; border-radius:10px; padding:16px 20px; }}
.toc .toc-title {{ font-weight:600; font-size:15px; margin-bottom:8px; color:#1a2d5c; }}
.toc ul {{ list-style:none; padding-left:12px; margin:4px 0; }}
.toc a {{ color:#185fa5; text-decoration:none; font-size:12px; line-height:1.7; display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.toc a:hover {{ text-decoration:underline; }}
.content {{ background:#fff; border:1px solid #e3e6ea; border-radius:10px; padding:28px 32px; }}
.content h2 {{ font-size:22px; margin:28px 0 12px; padding-bottom:8px; border-bottom:2px solid #1a2d5c; color:#1a2d5c; }}
.content h3 {{ font-size:17px; margin:22px 0 10px; color:#333; }}
.content h4 {{ font-size:15px; margin:18px 0 8px; }}
.content p {{ margin:10px 0; font-size:14.5px; }}
.content ul, .content ol {{ margin:10px 0 10px 22px; font-size:14.5px; }}
.content li {{ margin:4px 0; }}
.content blockquote {{ border-left:4px solid #ff7a1a; background:#fff7ef; padding:10px 14px; margin:12px 0; border-radius:0 6px 6px 0; font-size:14px; }}
.content blockquote p {{ margin:4px 0; }}
.content code {{ background:#f0f2f5; border-radius:4px; padding:1px 5px; font-size:13px; font-family:Consolas,monospace; }}
.content pre {{ background:#f6f8fa; border:1px solid #e3e6ea; border-radius:8px; padding:14px 16px; margin:12px 0; overflow-x:auto; }}
.content pre code {{ background:none; padding:0; font-size:13px; line-height:1.6; }}
.content table {{ border-collapse:collapse; margin:14px 0; width:100%; font-size:14px; }}
.content th {{ background:#1a2d5c; color:#fff; padding:8px 12px; text-align:left; }}
.content td {{ border:1px solid #e3e6ea; padding:8px 12px; }}
.content tr:nth-child(even) td {{ background:#f8f9fb; }}
hr {{ border:none; border-top:1px solid #e3e6ea; margin:28px 0; }}
@media (max-width:900px) {{
  .wrap {{ flex-direction:column; }}
  .sidebar {{ flex:none; position:static; max-height:none; }}
  .content {{ padding:18px 14px; }}
  .content h2 {{ font-size:19px; }}
}}
</style>
</head>
<body>
<div class="header">
  <h1>{title}</h1>
  <p>Intel Arc 显卡 ComfyUI 加速方案 · 完整安装包与指南</p>
  <a class="download-btn" href="https://pan.quark.cn/s/ba0d8aa09638" target="_blank" rel="noopener">📦 下载完整安装包（夸克网盘）</a>
</div>
<div class="wrap">
  <div class="sidebar">
    <div class="toc">
      <div class="toc-title">📖 目录</div>
      {toc}
    </div>
  </div>
  <div class="main">
    <div class="content">
      {body}
    </div>
  </div>
</div>
</body>
</html>"""

open(html_path, 'w', encoding='utf-8').write(page)
print('index.html 已生成:', html_path, f'({len(page)//1024}KB)')
