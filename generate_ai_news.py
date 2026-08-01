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


def send_webhook(content, webhook_url):
    """Optionally send report to a webhook (Server酱/PushPlus/custom)."""
    try:
        resp = requests.post(
            webhook_url,
            json={"text": content, "desp": content, "title": "AI行业日报"},
            timeout=15,
        )
        print(f"[Webhook] Sent. Status: {resp.status_code}")
    except Exception as e:
        print(f"[Webhook] Failed: {e}")


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
    print("[3/3] Saving report...")
    output_dir = os.environ.get("OUTPUT_DIR", ".")
    filepath = Path(output_dir) / f"ai_news_{date_str}.md"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(report, encoding="utf-8")
    print(f"  -> {filepath}\n")

    # Optional webhook
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    if webhook_url:
        send_webhook(report, webhook_url)

    print("=== Done! ===\n")
    print("=" * 60)
    print(report)
    print("=" * 60)


if __name__ == "__main__":
    main()
