#!/usr/bin/env python3
"""抓取最新军事新闻
数据源: 中国军网 (81.cn) RSS
用法: python3 military_news.py [--max N] [--json] [--save FILE]
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from html import unescape
RSS_URL = "http://www.81.cn/rss.xml"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/xml, text/xml, */*",
}
TIMEOUT = 30
RETRIES = 2

ITEM_RE = re.compile(
    r"<item>\s*"
    r"<title>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</title>\s*"
    r"<link>\s*(.*?)\s*</link>\s*"
    r"<description>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</description>",
    re.DOTALL,
)
PUBDATE_RE = re.compile(r"<pubDate>\s*(.*?)\s*</pubDate>")
TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(text: str) -> str:
    text = TAG_RE.sub("", text)
    return unescape(text).strip()


def fetch(url: str) -> str | None:
    for attempt in range(RETRIES + 1):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, OSError) as e:
            if attempt == RETRIES:
                print(f"✗ 请求失败: {url} — {e}", file=sys.stderr)
                return None
            time.sleep(1.5)
    return None


def parse_items(html: str) -> list[dict]:
    articles: list[dict] = []
    for m in ITEM_RE.finditer(html):
        title = strip_tags(m.group(1))
        link = m.group(2).strip()
        desc = strip_tags(m.group(3))
        if desc:
            desc = desc[:120] + "…" if len(desc) > 120 else desc

        pub_date = ""
        end = m.end()
        tail = html[end : end + 300]
        pm = PUBDATE_RE.search(tail)
        if pm:
            pub_date = pm.group(1).strip()

        if title and link:
            articles.append({
                "title": title,
                "link": link,
                "source": "中国军网",
                "summary": desc,
                "pub_date": pub_date,
                "fetched_at": datetime.now().isoformat(),
            })
    return articles


def format_output(articles: list[dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"{'=' * 60}",
        f"  军事新闻速览  —  {now}  —  中国军网",
        f"{'=' * 60}",
        "",
    ]
    for i, a in enumerate(articles, 1):
        lines.append(f"{i:3d}. {a['title']}")
        lines.append(f"     {a['link']}")
        if a["summary"]:
            lines.append(f"     {a['summary']}")
        if a["pub_date"]:
            lines.append(f"     📅 {a['pub_date']}")
        lines.append("")
    lines.extend([
        f"{'=' * 60}",
        f"  共 {len(articles)} 条新闻",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="抓取最新军事新闻")
    parser.add_argument("--max", type=int, default=20, help="最多显示条数 (默认 20)")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--save", type=str, default=None, metavar="FILE",
                        help="保存到指定文件 (如 military_news.txt)")
    args = parser.parse_args()

    print(f"正在从 中国军网 获取新闻…", file=sys.stderr)
    xml_text = fetch(RSS_URL)
    if xml_text is None:
        print("抓取失败，请检查网络连接。", file=sys.stderr)
        sys.exit(1)

    articles = parse_items(xml_text)

    # 去重
    seen: set[str] = set()
    unique: list[dict] = []
    for a in articles:
        if a["link"] not in seen:
            seen.add(a["link"])
            unique.append(a)
    articles = unique[: args.max]

    if args.json:
        output = json.dumps(articles, ensure_ascii=False, indent=2)
        if args.save:
            with open(args.save, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"已保存 JSON 到 {args.save}", file=sys.stderr)
            print(f"共 {len(articles)} 条新闻")
        else:
            print(output)
        return

    if not articles:
        print("未找到新闻条目。")
        return

    output = format_output(articles)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ 已保存到 {args.save}", file=sys.stderr)
        print(f"   共 {len(articles)} 条新闻")

    print(output)


if __name__ == "__main__":
    main()
