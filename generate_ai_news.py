#!/usr/bin/env python3
"""
AI News Daily Generator
- Fetches AI news from AI HOT API (aihot.virxact.com)
- Synthesizes top 5 with DeepSeek LLM for WeChat Work push
- Generates full dashboard HTML from AI HOT daily endpoint
"""

import os
import sys
import json
import time
import html as html_lib
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============ Configuration ============
AI_HOT_ITEMS_API = "https://aihot.virxact.com/api/public/items"
AI_HOT_DAILY_API = "https://aihot.virxact.com/api/public/daily"
DEEPSEEK_API = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
MAX_NEWS_ITEMS = 40

SECTION_META = {
    "模型发布/更新": {"icon": "M", "color": "#6366f1", "bg": "#eef2ff"},
    "产品发布/更新": {"icon": "P", "color": "#ec4899", "bg": "#fdf2f8"},
    "行业动态":     {"icon": "I", "color": "#f59e0b", "bg": "#fffbeb"},
    "论文研究":     {"icon": "R", "color": "#10b981", "bg": "#ecfdf5"},
    "技巧与观点":   {"icon": "T", "color": "#06b6d4", "bg": "#ecfeff"},
}


# ============ Data Fetching ============

def fetch_ai_hot_news():
    """Fetch curated AI news from AI HOT items API (past 24h)."""
    now_utc = datetime.now(timezone.utc)
    since = (now_utc - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(
            AI_HOT_ITEMS_API, headers=headers,
            params={"mode": "selected", "since": since, "take": 50}, timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        print(f"[AI HOT] selected: {len(items)} items")
    except Exception as e:
        print(f"[AI HOT] selected fetch failed: {e}")
        items = []

    if len(items) < 8:
        try:
            resp2 = requests.get(
                AI_HOT_ITEMS_API, headers=headers,
                params={"mode": "all", "since": since, "take": 50}, timeout=30,
            )
            resp2.raise_for_status()
            extra = resp2.json().get("items", [])
            seen = {it["id"] for it in items}
            for it in extra:
                if it["id"] not in seen:
                    items.append(it)
                    seen.add(it["id"])
            print(f"[AI HOT] after all-mode merge: {len(items)} items")
        except Exception as e:
            print(f"[AI HOT] all-mode fetch failed: {e}")

    return items[:MAX_NEWS_ITEMS]


def fetch_ai_hot_daily():
    """Fetch AI HOT daily report (full structured data with 5 sections)."""
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(AI_HOT_DAILY_API, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        total = sum(len(s.get("items", [])) for s in data.get("sections", []))
        print(f"[AI HOT Daily] date={data.get('date')}, {total} items in {len(data.get('sections', []))} sections")
        return data
    except Exception as e:
        print(f"[AI HOT Daily] fetch failed: {e}")
        return None


# ============ DeepSeek Synthesis ============

def format_news_items(items):
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(
            f"[{i}] 标题: {item.get('title', 'N/A')}\n"
            f"来源: {item.get('source', 'N/A')}\n"
            f"分类: {item.get('category', 'N/A')} | 热度: {item.get('score', 0)}\n"
            f"摘要: {item.get('summary', 'N/A')}\n"
            f"链接: {item.get('url', '')}\n"
        )
    return "\n".join(lines)


def synthesize_with_deepseek(news_text, date_display, item_count):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("[ERROR] DEEPSEEK_API_KEY not set")
        return None

    system_prompt = (
        "你是一名AI行业资讯编辑，擅长从海量信息中筛选最有价值的内容。\n\n"
        "任务：\n"
        "1. 从提供的新闻列表中挑选5条对AI从业者和创业者最有价值的资讯\n"
        "2. 每条包含：标题、来源、简要摘要（2-3句话）、以及对AI从业者/创业者的启示\n"
        "3. 优先选择：大模型动态、AI产品发布、行业应用案例、技术突破、政策法规\n"
        "4. 语言用中文，风格简洁实用\n"
        "5. 可以合并多条相关新闻为一个条目，但总共保持5条\n"
        "7. 启示部分要有深度和具体行动建议，不要泛泛而谈\n\n"
        "输出格式：\n"
        f"# AI 行业日报 — {date_display}\n\n"
        "> 精选5条今日最有价值的AI资讯\n\n---\n\n"
        "## 1. [标题]\n\n**来源：** [来源]\n\n[摘要2-3句]\n\n**启示：** [2-4句具体启示]\n\n---\n\n"
        "## 2. [标题]\n...\n\n---\n\n"
        "> **今日关键词：** [3-5个关键词用×分隔]\n\n> 数据来源：AI HOT (aihot.virxact.com) 等"
    )

    user_prompt = f"以下是今天（{date_display}）从AI HOT平台获取的{item_count}条AI行业新闻。请挑选5条最有价值的，按指定格式输出：\n\n{news_text}"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 4096, "temperature": 0.7, "stream": False,
    }

    try:
        print("[DeepSeek] Calling API...")
        resp = requests.post(DEEPSEEK_API, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        print(f"[DeepSeek] OK. tokens: prompt={usage.get('prompt_tokens', '?')}, completion={usage.get('completion_tokens', '?')}")
        return content
    except Exception as e:
        print(f"[ERROR] DeepSeek API failed: {e}")
        try:
            print(f"[ERROR] Response: {resp.text[:500]}")
        except Exception:
            pass
        return None


# ============ Dashboard HTML Generation ============

def fmt_time_beijing(iso_str):
    if not iso_str:
        return ""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    beijing = dt.astimezone(timezone(timedelta(hours=8)))
    return beijing.strftime("%m月%d日 %H:%M")


def fmt_window(start, end):
    s = fmt_time_beijing(start)
    e = fmt_time_beijing(end)
    return f"{s} — {e} (北京时间)"


def truncate(text, max_len=60):
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def generate_dashboard_html(daily_data, deepseek_report=None):
    """Generate a full single-file HTML dashboard from AI HOT daily data."""
    date = daily_data.get("date", "")
    window = fmt_window(daily_data.get("windowStart"), daily_data.get("windowEnd"))
    sections = daily_data.get("sections", [])
    total = sum(len(s.get("items", [])) for s in sections)
    generated = fmt_time_beijing(daily_data.get("generatedAt"))

    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        date_display = f"{dt.year}年{dt.month}月{dt.day}日"
        weekday = ["周一","周二","周三","周四","周五","周六","周日"][dt.weekday()]
    except Exception:
        date_display = date
        weekday = ""

    # Section stats
    stats_html = ""
    for s in sections:
        label = s.get("label", "")
        count = len(s.get("items", []))
        meta = SECTION_META.get(label, {"color": "#6366f1", "bg": "#f0f0f0", "icon": "?"})
        stats_html += f"""<div class="stat-chip" style="background:{meta['bg']};border-color:{meta['color']}">
            <span class="stat-icon" style="background:{meta['color']}">{meta['icon']}</span>
            <div class="stat-text"><span class="stat-count" style="color:{meta['color']}">{count}</span><span class="stat-label">{label}</span></div>
        </div>"""

    # Nav
    nav_html = ""
    for s in sections:
        label = s.get("label", "")
        anchor = f"sec-{label.replace('/', '')}"
        meta = SECTION_META.get(label, {"color": "#6366f1"})
        nav_html += f'<a href="#{anchor}" class="nav-link" style="border-color:{meta["color"]};color:{meta["color"]}">{label}</a>'

    # Sections with cards
    sections_html = ""
    global_num = 0
    for s in sections:
        label = s.get("label", "")
        items = s.get("items", [])
        anchor = f"sec-{label.replace('/', '')}"
        meta = SECTION_META.get(label, {"color": "#6366f1", "bg": "#f0f0f0", "icon": "?"})
        count = len(items)

        cards_html = ""
        for item in items:
            global_num += 1
            title = html_lib.escape(item.get("title", ""))
            source = html_lib.escape(item.get("sourceName", ""))
            source_url = item.get("sourceUrl", "")
            summary = html_lib.escape(truncate(item.get("summary", ""), 60))

            cards_html += f"""<article class="card" onclick="window.open('{source_url}','_blank','noopener,noreferrer')">
                <div class="card-num" style="background:{meta['color']}">{global_num}</div>
                <div class="card-body">
                    <h3 class="card-title">{title}</h3>
                    <div class="card-source"><span class="source-chip" style="background:{meta['bg']};color:{meta['color']}">{source}</span></div>
                    <p class="card-summary">{summary}</p>
                    <a href="{source_url}" target="_blank" rel="noopener noreferrer" class="card-link" style="color:{meta['color']}">阅读原文 →</a>
                </div>
            </article>"""

        sections_html += f"""<section id="{anchor}" class="news-section">
            <div class="section-header" style="border-left-color:{meta['color']}">
                <span class="section-icon" style="background:{meta['color']}">{meta['icon']}</span>
                <h2 class="section-title">{label}</h2>
                <span class="section-count" style="background:{meta['bg']};color:{meta['color']}">{count} 条</span>
            </div>
            <div class="card-grid">{cards_html}</div>
        </section>"""

    # DeepSeek 5-pick section (if available)
    deepseek_html = ""
    if deepseek_report:
        ds_cards = parse_news_cards(deepseek_report)
        if ds_cards[1]:  # has cards
            _, cards, keywords = ds_cards
            card_colors = ["#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#e67e22"]
            ds_items_html = ""
            for i, card in enumerate(cards):
                color = card_colors[i % len(card_colors)]
                ds_items_html += f"""<article class="card deepseek-card" style="border-left:4px solid {color}">
                    <div class="card-num" style="background:{color}">{i+1}</div>
                    <div class="card-body">
                        <h3 class="card-title">{html_lib.escape(card['title'])}</h3>
                        <div class="card-source"><span class="source-chip" style="background:{color}22;color:{color}">{html_lib.escape(card['source'])}</span></div>
                        <p class="card-summary">{html_lib.escape(card['summary'])}</p>
                        <div class="card-insight-box"><span class="insight-label" style="color:{color}">启示</span><p class="card-insight-text">{html_lib.escape(card['insight'])}</p></div>
                    </div>
                </article>"""

            kw_html = ""
            if keywords:
                kw_items = "".join(f'<span class="keyword">{html_lib.escape(k.strip())}</span>' for k in keywords.split("×"))
                kw_html = f'<div class="keywords">{kw_items}</div>'

            deepseek_html = f"""<section class="news-section deepseek-section">
                <div class="section-header" style="border-left-color:#8b5cf6">
                    <span class="section-icon" style="background:#8b5cf6">★</span>
                    <h2 class="section-title">DeepSeek 精选 5 条</h2>
                    <span class="section-count" style="background:#f5f3ff;color:#8b5cf6">AI 深度解读</span>
                </div>
                <div class="card-grid">{ds_items_html}</div>
                {kw_html}
            </section>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI 晨报 — {date_display}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;background:#f8fafc;color:#1e293b;line-height:1.7}}
.container{{max-width:960px;margin:0 auto;padding:16px}}
.hero{{background:linear-gradient(135deg,#1e293b 0%,#334155 50%,#475569 100%);border-radius:20px;padding:40px 32px;color:#fff;text-align:center;margin-bottom:24px;position:relative;overflow:hidden}}
.hero::before{{content:"";position:absolute;top:-60%;right:-20%;width:400px;height:400px;background:radial-gradient(circle,rgba(99,102,241,0.15) 0%,transparent 70%);border-radius:50%}}
.hero-date{{font-size:32px;font-weight:800;letter-spacing:-0.5px;margin-bottom:6px}}
.hero-weekday{{font-size:14px;color:#94a3b8;margin-bottom:20px}}
.hero-total{{display:inline-flex;align-items:baseline;gap:6px;background:rgba(255,255,255,0.1);border-radius:12px;padding:10px 24px;margin-bottom:24px}}
.hero-total-num{{font-size:36px;font-weight:800;color:#818cf8}}
.hero-total-label{{font-size:14px;color:#cbd5e1}}
.hero-window{{font-size:12px;color:#64748b;margin-top:12px}}
.stats{{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;margin-top:20px}}
.stat-chip{{display:flex;align-items:center;gap:10px;padding:10px 18px;border-radius:12px;border:1.5px solid}}
.stat-icon{{width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;font-weight:700;flex-shrink:0}}
.stat-text{{display:flex;flex-direction:column;line-height:1.3}}
.stat-count{{font-size:20px;font-weight:800}}
.stat-label{{font-size:11px;color:#64748b}}
.nav{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-bottom:28px;padding:16px;background:#fff;border-radius:14px;box-shadow:0 1px 3px rgba(0,0,0,0.06);position:sticky;top:8px;z-index:100}}
.nav-link{{padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600;text-decoration:none;border:1.5px solid;transition:all 0.2s}}
.nav-link:hover{{opacity:0.8;transform:translateY(-1px)}}
.news-section{{margin-bottom:36px;scroll-margin-top:80px}}
.section-header{{display:flex;align-items:center;gap:12px;padding:12px 18px;border-left:4px solid;background:#fff;border-radius:0 12px 12px 0;margin-bottom:16px;box-shadow:0 1px 2px rgba(0,0,0,0.04)}}
.section-icon{{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;font-weight:700}}
.section-title{{font-size:18px;font-weight:700;color:#1e293b;flex:1}}
.section-count{{padding:3px 12px;border-radius:12px;font-size:12px;font-weight:600}}
.card-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}
.card{{background:#fff;border-radius:14px;padding:20px;cursor:pointer;transition:all 0.2s;border:1px solid #f1f5f9;display:flex;gap:14px}}
.card:hover{{box-shadow:0 4px 20px rgba(0,0,0,0.08);transform:translateY(-2px);border-color:#e2e8f0}}
.card-num{{width:28px;height:28px;border-radius:8px;flex-shrink:0;display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;font-weight:700}}
.card-body{{flex:1;min-width:0}}
.card-title{{font-size:14px;font-weight:600;color:#1e293b;line-height:1.5;margin-bottom:8px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-source{{margin-bottom:8px}}
.source-chip{{display:inline-block;padding:2px 10px;border-radius:6px;font-size:11px;font-weight:500;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.card-summary{{font-size:12px;color:#64748b;line-height:1.6;margin-bottom:10px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-link{{font-size:12px;font-weight:600;text-decoration:none;display:inline-flex;align-items:center;gap:2px}}
.card-insight-box{{background:#f8f9fa;border-radius:8px;padding:10px 14px;margin-top:8px}}
.insight-label{{display:inline-block;font-size:11px;font-weight:600;margin-bottom:4px}}
.card-insight-text{{font-size:12px;color:#666;line-height:1.6}}
.deepseek-card{{border-left-width:4px}}
.keywords{{padding:16px;text-align:center}}
.keyword{{display:inline-block;margin:4px;padding:4px 14px;background:#f0f2f5;border-radius:20px;font-size:13px;color:#666}}
.footer{{text-align:center;padding:24px;font-size:12px;color:#94a3b8;border-top:1px solid #e2e8f0;margin-top:20px}}
.footer a{{color:#6366f1;text-decoration:none}}
@media(max-width:640px){{.hero{{padding:28px 20px}}.hero-date{{font-size:24px}}.card-grid{{grid-template-columns:1fr}}.stats{{flex-direction:column;align-items:center}}.nav{{position:static}}}}
</style>
</head>
<body>
<div class="container">
    <div class="hero">
        <div class="hero-date">{date_display}</div>
        <div class="hero-weekday">{weekday} · AI 晨报仪表盘</div>
        <div class="hero-total"><span class="hero-total-num">{total}</span><span class="hero-total-label">条资讯精选</span></div>
        <div class="stats">{stats_html}</div>
        <div class="hero-window">数据时间窗：{window}</div>
    </div>
    <nav class="nav">{nav_html}</nav>
    {sections_html}
    {deepseek_html}
    <div class="footer">共 {total} 条 · 数据来源：<a href="https://aihot.virxact.com" target="_blank" rel="noopener noreferrer">AI HOT</a> · 生成时间：{generated}</div>
</div>
</body>
</html>"""


# ============ Markdown Report Parsing (for WeChat push) ============

def parse_news_cards(md_text):
    lines = md_text.strip().split("\n")
    cards = []
    current = None
    keywords = ""
    title = ""

    for line in lines:
        s = line.strip()
        if s.startswith("# AI"):
            title = s.lstrip("# ").strip()
        elif s.startswith("## "):
            if current:
                cards.append(current)
            current = {"title": s[3:].strip(), "source": "", "summary": "", "insight": ""}
        elif current is not None:
            if s.startswith("**来源"):
                current["source"] = s.replace("**", "").replace("来源：", "").replace("来源:", "").strip()
            elif s.startswith("**启示"):
                current["insight"] = s.replace("**", "").replace("启示：", "").replace("启示:", "").strip()
            elif s and not s.startswith("---") and not s.startswith(">") and not s.startswith("#"):
                if current["insight"]:
                    if not s.startswith("**"):
                        current["insight"] += s
                elif not current["summary"]:
                    current["summary"] = s
                else:
                    current["summary"] += s
        elif "今日关键词" in s:
            keywords = s.replace(">", "").replace("**", "").replace("今日关键词：", "").strip()

    if current:
        cards.append(current)
    return title, cards, keywords


# ============ WeChat Work Push ============

def send_webhook(content, webhook_url, html_url=None):
    """Send full report to WeChat Work in 3 messages with font colors."""
    title, cards, keywords = parse_news_cards(content)
    num_colors = ["warning", "info", "info", "warning", "info"]

    def _send(md_text):
        payload = {"msgtype": "markdown", "markdown": {"content": md_text}}
        resp = requests.post(webhook_url, json=payload, timeout=15)
        print(f"[Webhook] Status: {resp.status_code}, Resp: {resp.text[:200]}")
        return resp

    # Message 1: Header + first 2 cards
    msg1 = f"# {title}\n> 精选5条今日最有价值的AI资讯\n\n"
    for i, card in enumerate(cards[:2]):
        c = num_colors[i]
        msg1 += f"## <font color=\"{c}\">{i+1}. {card['title']}</font>\n"
        msg1 += f"<font color=\"comment\">来源：{card['source']}</font>\n"
        msg1 += f"{card['summary']}\n\n"
        msg1 += f"<font color=\"warning\">启示：</font>{card['insight']}\n\n"
    _send(msg1)
    time.sleep(1)

    # Message 2: Cards 3-4
    msg2 = ""
    for i, card in enumerate(cards[2:4], 3):
        c = num_colors[i-1]
        msg2 += f"## <font color=\"{c}\">{i}. {card['title']}</font>\n"
        msg2 += f"<font color=\"comment\">来源：{card['source']}</font>\n"
        msg2 += f"{card['summary']}\n\n"
        msg2 += f"<font color=\"warning\">启示：</font>{card['insight']}\n\n"
    _send(msg2)
    time.sleep(1)

    # Message 3: Card 5 + keywords + link
    msg3 = ""
    if len(cards) >= 5:
        card = cards[4]
        c = num_colors[4]
        msg3 += f"## <font color=\"{c}\">5. {card['title']}</font>\n"
        msg3 += f"<font color=\"comment\">来源：{card['source']}</font>\n"
        msg3 += f"{card['summary']}\n\n"
        msg3 += f"<font color=\"warning\">启示：</font>{card['insight']}\n\n"
    if keywords:
        msg3 += f"<font color=\"info\">今日关键词：{keywords}</font>\n\n"
    if html_url:
        msg3 += f"> 📄 完整仪表盘：[点击查看]({html_url})"
    _send(msg3)


# ============ Main ============

def main():
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    date_str = now.strftime("%Y-%m-%d")
    date_display = now.strftime("%Y年%m月%d日")

    print(f"=== AI News Daily Generator ===")
    print(f"Date: {date_display} (UTC+8)\n")

    output_dir = os.environ.get("OUTPUT_DIR", ".")

    # Step 1: Fetch items for DeepSeek synthesis
    print("[1/5] Fetching AI news items...")
    items = fetch_ai_hot_news()
    if not items:
        print("[ERROR] No news fetched. Exiting.")
        sys.exit(1)
    print(f"  -> {len(items)} items\n")

    # Step 2: DeepSeek synthesis (5 picks for WeChat push)
    print("[2/5] Synthesizing with DeepSeek...")
    news_text = format_news_items(items)
    report = synthesize_with_deepseek(news_text, date_display, len(items))
    if not report:
        print("[ERROR] Synthesis failed. Exiting.")
        sys.exit(1)

    # Step 3: Save markdown report
    print("[3/5] Saving markdown report...")
    md_filepath = Path(output_dir) / f"ai_news_{date_str}.md"
    md_filepath.parent.mkdir(parents=True, exist_ok=True)
    md_filepath.write_text(report, encoding="utf-8")
    print(f"  -> {md_filepath}")

    # Step 4: Fetch daily data + generate dashboard HTML
    print("[4/5] Generating dashboard HTML...")
    daily_data = fetch_ai_hot_daily()
    if daily_data:
        html_content = generate_dashboard_html(daily_data, deepseek_report=report)
    else:
        # Fallback: use markdown_to_html if daily API fails
        html_content = generate_dashboard_html_fallback(report, date_display)

    html_filepath = Path(output_dir) / f"ai_news_{date_str}.html"
    html_filepath.write_text(html_content, encoding="utf-8")
    print(f"  -> {html_filepath}\n")

    # Step 5: Push to WeChat Work
    print("[5/5] Pushing to WeChat Work...")
    html_url = os.environ.get("HTML_BASE_URL", "")
    if html_url:
        html_url = html_url.rstrip("/") + f"/ai_news_{date_str}.html"

    webhook_url = os.environ.get("WEBHOOK_URL", "")
    if webhook_url:
        send_webhook(report, webhook_url, html_url)

    print("\n=== Done! ===\n")
    print("=" * 60)
    print(report)
    print("=" * 60)


def generate_dashboard_html_fallback(md_text, date_display):
    """Fallback HTML if daily API is unavailable."""
    title, cards, keywords = parse_news_cards(md_text)
    card_colors = ["#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#e67e22"]
    cards_html = ""
    for i, card in enumerate(cards):
        color = card_colors[i % len(card_colors)]
        cards_html += f"""<article class="card" style="border-left:4px solid {color}">
            <div class="card-num" style="background:{color}">{i+1}</div>
            <div class="card-body">
                <h3 class="card-title">{html_lib.escape(card['title'])}</h3>
                <div class="card-source"><span class="source-chip" style="background:{color}22;color:{color}">{html_lib.escape(card['source'])}</span></div>
                <p class="card-summary">{html_lib.escape(card['summary'])}</p>
                <div class="card-insight-box"><span class="insight-label" style="color:{color}">启示</span><p class="card-insight-text">{html_lib.escape(card['insight'])}</p></div>
            </div>
        </article>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI 行业日报 — {html_lib.escape(date_display)}</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:#f8fafc;color:#1e293b;line-height:1.7}}.container{{max-width:720px;margin:0 auto;padding:16px}}.hero{{background:linear-gradient(135deg,#1e293b 0%,#334155 50%,#475569 100%);border-radius:20px;padding:36px;text-align:center;color:#fff;margin-bottom:24px}}.hero h1{{font-size:26px;margin-bottom:6px}}.hero .sub{{font-size:14px;color:#94a3b8}}.card{{background:#fff;border-radius:14px;padding:20px;margin-bottom:14px;display:flex;gap:14px}}.card-num{{width:28px;height:28px;border-radius:8px;flex-shrink:0;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:13px}}.card-body{{flex:1}}.card-title{{font-size:16px;font-weight:600;margin-bottom:8px}}.card-source{{font-size:12px;color:#999;margin-bottom:8px}}.card-summary{{font-size:13px;color:#555;margin-bottom:12px}}.card-insight-box{{background:#f8f9fa;border-radius:8px;padding:12px 14px}}.insight-label{{font-size:12px;font-weight:600;margin-bottom:4px;display:inline-block}}.card-insight-text{{font-size:13px;color:#666}}.footer{{text-align:center;padding:24px;font-size:12px;color:#94a3b8}}</style>
</head><body><div class="container">
<div class="hero"><h1>AI 行业日报</h1><div class="sub">{html_lib.escape(date_display)}</div></div>
<div style="display:grid;gap:14px">{cards_html}</div>
<div class="footer">数据来源：<a href="https://aihot.virxact.com">AI HOT</a></div>
</div></body></html>"""


if __name__ == "__main__":
    main()
