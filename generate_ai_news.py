#!/usr/bin/env python3
"""
AI News Daily Generator
- Fetches AI news from AI HOT API (aihot.virxact.com)
- Synthesizes top 5 with DeepSeek LLM
- Saves as markdown file
"""

import os
import sys
import json
import re
import html as html_lib
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============ Configuration ============
AI_HOT_API = "https://aihot.virxact.com/api/public/items"
DEEPSEEK_API = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
MAX_NEWS_ITEMS = 40  # Max items to feed to LLM


def fetch_ai_hot_news():
    """Fetch curated AI news from AI HOT API (past 24h)."""
    now_utc = datetime.now(timezone.utc)
    since = (now_utc - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"User-Agent": USER_AGENT}

    # Primary: selected mode
    try:
        resp = requests.get(
            AI_HOT_API,
            headers=headers,
            params={"mode": "selected", "since": since, "take": 50},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        print(f"[AI HOT] selected: {len(items)} items")
    except Exception as e:
        print(f"[AI HOT] selected fetch failed: {e}")
        items = []

    # Fallback: if too few, also fetch mode=all
    if len(items) < 8:
        try:
            resp2 = requests.get(
                AI_HOT_API,
                headers=headers,
                params={"mode": "all", "since": since, "take": 50},
                timeout=30,
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


def format_news_items(items):
    """Format news items as text for the LLM prompt."""
    lines = []
    for i, item in enumerate(items, 1):
        title = item.get("title", "N/A")
        source = item.get("source", "N/A")
        summary = item.get("summary", "N/A")
        category = item.get("category", "N/A")
        score = item.get("score", 0)
        url = item.get("url", "")
        lines.append(
            f"[{i}] 标题: {title}\n"
            f"来源: {source}\n"
            f"分类: {category} | 热度: {score}\n"
            f"摘要: {summary}\n"
            f"链接: {url}\n"
        )
    return "\n".join(lines)


def synthesize_with_deepseek(news_text, date_display, item_count):
    """Call DeepSeek API to pick top 5 and write the report."""
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
        "> 精选5条今日最有价值的AI资讯\n\n"
        "---\n\n"
        "## 1. [标题]\n\n"
        "**来源：** [来源]\n\n"
        "[摘要2-3句]\n\n"
        "**启示：** [2-4句具体启示]\n\n"
        "---\n\n"
        "## 2. [标题]\n...\n\n"
        "---\n\n"
        "> **今日关键词：** [3-5个关键词用×分隔]\n\n"
        "> 数据来源：AI HOT (aihot.virxact.com) 等"
    )

    user_prompt = (
        f"以下是今天（{date_display}）从AI HOT平台获取的{item_count}条AI行业新闻。"
        "请挑选5条最有价值的，按指定格式输出：\n\n"
        f"{news_text}"
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 4096,
        "temperature": 0.7,
        "stream": False,
    }

    try:
        print("[DeepSeek] Calling API...")
        resp = requests.post(DEEPSEEK_API, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        print(
            f"[DeepSeek] OK. tokens: prompt={usage.get('prompt_tokens', '?')}, "
            f"completion={usage.get('completion_tokens', '?')}"
        )
        return content
    except Exception as e:
        print(f"[ERROR] DeepSeek API failed: {e}")
        try:
            print(f"[ERROR] Response: {resp.text[:500]}")
        except Exception:
            pass
        return None


def markdown_to_html(md_text, date_display):
    """Convert the AI news markdown report into a styled HTML page."""
    lines = md_text.strip().split("\n")
    cards = []
    current_card = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if current_card:
                cards.append(current_card)
            title = stripped[3:].strip()
            current_card = {"title": title, "source": "", "summary": "", "insight": ""}
        elif current_card is not None:
            if stripped.startswith("**来源") or stripped.startswith("**来源"):
                current_card["source"] = stripped.replace("**", "").replace("来源：", "").replace("来源:", "").strip()
            elif stripped.startswith("**启示") or stripped.startswith("**启示"):
                current_card["insight"] = stripped.replace("**", "").replace("启示：", "").replace("启示:", "").strip()
            elif stripped and not stripped.startswith("---") and not stripped.startswith(">") and not stripped.startswith("#"):
                if not current_card["summary"]:
                    current_card["summary"] = stripped
                elif current_card["insight"] and not stripped.startswith("**"):
                    current_card["insight"] += " " + stripped
                elif not current_card["insight"]:
                    current_card["summary"] += " " + stripped

    if current_card:
        cards.append(current_card)

    # Extract keywords
    keywords = ""
    for line in lines:
        if "今日关键词" in line:
            keywords = line.replace(">", "").replace("**", "").replace("今日关键词：", "").strip()
            break

    # Build cards HTML
    card_colors = ["#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#e67e22"]
    cards_html = ""
    for i, card in enumerate(cards):
        color = card_colors[i % len(card_colors)]
        num = i + 1
        cards_html += f"""
        <div class="card" style="border-left: 4px solid {color};">
            <div class="card-header">
                <span class="card-num" style="background:{color};">{num}</span>
                <h2 class="card-title">{html_lib.escape(card['title'])}</h2>
            </div>
            <div class="card-source">来源：{html_lib.escape(card['source'])}</div>
            <div class="card-summary">{html_lib.escape(card['summary'])}</div>
            <div class="card-insight">
                <span class="insight-label">启示</span>
                <p>{html_lib.escape(card['insight'])}</p>
            </div>
        </div>"""

    keywords_html = ""
    if keywords:
        kw_items = "".join(f'<span class="keyword">{html_lib.escape(k.strip())}</span>' for k in keywords.split("×"))
        keywords_html = f'<div class="keywords">{kw_items}</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 行业日报 — {html_lib.escape(date_display)}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            background: #f0f2f5;
            color: #333;
            line-height: 1.8;
            padding: 20px;
        }}
        .container {{ max-width: 720px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            padding: 36px 28px;
            border-radius: 16px 16px 0 0;
            text-align: center;
        }}
        .header h1 {{ font-size: 26px; margin-bottom: 8px; font-weight: 700; }}
        .header .subtitle {{ font-size: 14px; opacity: 0.85; }}
        .card {{
            background: #fff;
            margin: 0;
            padding: 24px 28px;
            border-bottom: 1px solid #f0f0f0;
        }}
        .card:last-of-type {{ border-bottom: none; }}
        .card-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
        .card-num {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 28px; height: 28px; border-radius: 50%;
            color: #fff; font-size: 14px; font-weight: 700; flex-shrink: 0;
        }}
        .card-title {{ font-size: 17px; font-weight: 600; color: #1a1a1a; line-height: 1.5; }}
        .card-source {{ font-size: 12px; color: #999; margin-bottom: 10px; }}
        .card-summary {{ font-size: 14px; color: #555; margin-bottom: 14px; }}
        .card-insight {{
            background: #f8f9fa; border-radius: 8px; padding: 14px 16px;
        }}
        .insight-label {{
            display: inline-block; font-size: 12px; font-weight: 600;
            color: #667eea; margin-bottom: 6px;
        }}
        .card-insight p {{ font-size: 13px; color: #666; }}
        .keywords {{ padding: 20px 28px; background: #fff; text-align: center; }}
        .keyword {{
            display: inline-block; margin: 4px; padding: 4px 14px;
            background: #f0f2f5; border-radius: 20px; font-size: 13px; color: #666;
        }}
        .footer {{
            background: #fff; border-radius: 0 0 16px 16px;
            padding: 16px 28px; text-align: center;
            font-size: 12px; color: #bbb;
        }}
        .footer a {{ color: #667eea; text-decoration: none; }}
        @media (max-width: 600px) {{
            body {{ padding: 10px; }}
            .header h1 {{ font-size: 22px; }}
            .card {{ padding: 18px 20px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AI 行业日报</h1>
            <div class="subtitle">{html_lib.escape(date_display)} · 精选5条今日最有价值的AI资讯</div>
        </div>
        {cards_html}
        {keywords_html}
        <div class="footer">
            数据来源：<a href="https://aihot.virxact.com">AI HOT</a> · 由 DeepSeek AI 自动生成
        </div>
    </div>
</body>
</html>"""


def parse_news_cards(md_text):
    """Parse markdown report into structured news cards."""
    lines = md_text.strip().split("\n")
    cards = []
    current = None
    keywords = ""
    title = ""

    for line in lines:
        s = line.strip()
        if s.startswith("# AI") or s.startswith("# AI 行业日报"):
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


def send_webhook(content, webhook_url, html_url=None):
    """Send full report to WeChat Work (企业微信) in multiple messages.

    企微单条 markdown 上限 2048 字节，自动拆分为多条连续发送，
    每条包含完整的新闻内容（标题+来源+摘要+启示），并使用企微 font 标签美化。
    """
    import time

    title, cards, keywords = parse_news_cards(content)

    # Colors for each card number (企微只支持 info/comment/warning 三色)
    num_colors = ["warning", "info", "info", "warning", "info"]

    def _send(md_text):
        payload = {"msgtype": "markdown", "markdown": {"content": md_text}}
        resp = requests.post(webhook_url, json=payload, timeout=15)
        print(f"[Webhook] Status: {resp.status_code}, Resp: {resp.text[:200]}")
        return resp

    # Message 1: Header + first 2 cards
    msg1 = f"# {title}\n"
    msg1 += "> 精选5条今日最有价值的AI资讯\n\n"

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
        msg3 += f"> 📄 完整报告：[点击查看]({html_url})"

    _send(msg3)


def main():
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    date_str = now.strftime("%Y-%m-%d")
    date_display = now.strftime("%Y年%m月%d日")

    print(f"=== AI News Daily Generator ===")
    print(f"Date: {date_display} (UTC+8)\n")

    # Step 1: Fetch
    print("[1/3] Fetching AI news...")
    items = fetch_ai_hot_news()
    if not items:
        print("[ERROR] No news fetched. Exiting.")
        sys.exit(1)
    print(f"  -> {len(items)} items\n")

    # Step 2: Synthesize
    print("[2/3] Synthesizing with DeepSeek...")
    news_text = format_news_items(items)
    report = synthesize_with_deepseek(news_text, date_display, len(items))
    if not report:
        print("[ERROR] Synthesis failed. Exiting.")
        sys.exit(1)

    # Step 3: Save
    print("[3/4] Saving report...")
    output_dir = os.environ.get("OUTPUT_DIR", ".")
    filepath = Path(output_dir) / f"ai_news_{date_str}.md"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(report, encoding="utf-8")
    print(f"  -> {filepath}")

    # Step 4: Generate HTML
    print("[4/4] Generating HTML...")
    html_content = markdown_to_html(report, date_display)
    html_filepath = Path(output_dir) / f"ai_news_{date_str}.html"
    html_filepath.write_text(html_content, encoding="utf-8")
    print(f"  -> {html_filepath}\n")

    # Build HTML URL (GitHub Pages)
    html_url = os.environ.get("HTML_BASE_URL", "")
    if html_url:
        html_url = html_url.rstrip("/") + f"/ai_news_{date_str}.html"

    # Optional webhook
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    if webhook_url:
        send_webhook(report, webhook_url, html_url)

    print("=== Done! ===\n")
    print("=" * 60)
    print(report)
    print("=" * 60)


if __name__ == "__main__":
    main()
