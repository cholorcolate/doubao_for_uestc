"""
官方信息源抓取骨架（教务处 / 研究生院 / 学工部 / 后勤等）

现状说明：
- 清水河畔论坛（bbs.uestc.edu.cn）已由 uestc_bbs_crawler.py 全量覆盖
- 本文件为官方站点抓取提供统一骨架：每个源只需在 SOURCES 中配置
  列表页 URL 与解析函数，即可复用「列表页 -> 文章页 -> 统一 JSON」流程
- 输出格式与论坛 thread_*.json 对齐（tid/title/posts），
  便于直接进入 preprocess.py -> chunk-data.py 既有流水线

使用方法（需先安装依赖：pip install requests beautifulsoup4）:
    python official_sources.py --list                # 列出已配置的源
    python official_sources.py --source jwc          # 抓取单个源
    python official_sources.py --all                 # 抓取全部已配置源
"""

import argparse
import json
import os
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# 各官方源配置：url=列表页，parser 对应下方 parse_* 函数
# 抓取前请人工访问列表页确认 DOM 结构是否变化
SOURCES = {
    "jwc": {
        "name": "教务处",
        "url": "https://jwc.uestc.edu.cn/",
        "parser": "generic_list",
    },
    "yjsy": {
        "name": "研究生院",
        "url": "https://yz.uestc.edu.cn/",
        "parser": "generic_list",
    },
    # TODO: 学工部、后勤、校医院、图书馆等按同样格式补充
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
REQUEST_INTERVAL = 1.0  # 礼貌性延迟（秒）


def fetch(url: str, session: requests.Session) -> str | None:
    """抓取单页，失败返回 None"""
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        resp.encoding = resp.apparent_encoding or "utf-8"
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}: {url}")
            return None
        return resp.text
    except requests.RequestException as e:
        print(f"  请求失败: {url} -> {e}")
        return None


def generic_list(html: str, baseUrl: str) -> list[dict]:
    """通用列表页解析：提取页内所有指向同域文章页的链接。

    官方站点 DOM 各不相同，首次接入时需按实际结构调整选择器；
    这里用保守策略——同域且 URL 形如 xxx/20xx/ 或带数字 id 的链接。
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)
        if not title or len(title) < 6:
            continue
        # 过滤导航/菜单等非文章链接
        if not re.search(r"/\d{4}(/|\.p|_)", href) and not re.search(r"id=\d+", href):
            continue
        url = requests.compat.urljoin(baseUrl, href)
        if url in seen or not url.startswith("http"):
            continue
        seen.add(url)
        items.append({"title": title, "url": url})
    return items


def parse_article(html: str) -> dict | None:
    """通用文章页解析：提取标题、正文、发布时间。

    各站点发布时间位置不同，识别失败时 crawled_at 兜底；
    需要精确时间的源可在此函数按站点加分支。
    """
    soup = BeautifulSoup(html, "html.parser")
    titleTag = soup.find("h1") or soup.find("title")
    if not titleTag:
        return None
    title = titleTag.get_text(strip=True)

    body = soup.find("div", class_=re.compile(r"content|article|v_news_content", re.I))
    if not body:
        body = soup.find("article") or soup.body
    text = body.get_text("\n", strip=True) if body else ""
    if len(text) < 50:
        return None

    pubTime = ""
    timeTag = soup.find(string=re.compile(r"20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}"))
    if timeTag:
        m = re.search(r"20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}", timeTag)
        pubTime = m.group(0).replace("年", "-").replace("月", "-").replace("/", "-")

    return {"title": title, "text": text, "publish_time": pubTime}


def saveArticle(dataDir: str, sourceKey: str, index: int, article: dict):
    """保存为与论坛帖子对齐的 thread_*.json 格式，直接进入既有流水线"""
    # 官方文章无论坛 tid，用源前缀+序号生成稳定 id（增量时可对比跳过）
    tid = f"official_{sourceKey}_{index:04d}"
    record = {
        "tid": tid,
        "title": article["title"],
        "posts": [{
            "post_id": str(index),
            "author": SOURCES[sourceKey]["name"],
            "time": article.get("publish_time") or "",
            "content": article["text"],
            "floor": "",
        }],
        "total_posts": 1,
        "complete": True,
        "pages_fetched": 1,
        "source": "official",
        "crawled_at": datetime.now().isoformat(timespec="seconds"),
    }
    path = os.path.join(dataDir, "posts", f"thread_{tid}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def crawlSource(sourceKey: str, dataDir: str, maxPages: int = 3):
    """抓取单个源：列表页 -> 文章页 -> 落盘"""
    conf = SOURCES[sourceKey]
    print(f"\n抓取 {conf['name']} ({conf['url']})")
    session = requests.Session()
    parser = generic_list  # 当前只有通用解析，站点专用解析在此扩展

    count = 0
    for page in range(1, maxPages + 1):
        # 多数官方站点列表页带 page 参数，不支持时会返回同页（去重兜底）
        listUrl = conf["url"] if page == 1 else f"{conf['url']}index_{page}.html"
        html = fetch(listUrl, session)
        if not html:
            break
        items = parser(html, conf["url"])
        if not items:
            break
        for item in items:
            artHtml = fetch(item["url"], session)
            if not artHtml:
                continue
            article = parse_article(artHtml)
            if article:
                saveArticle(dataDir, sourceKey, count, article)
                count += 1
            time.sleep(REQUEST_INTERVAL)
    print(f"  {conf['name']} 完成，共保存 {count} 篇")


def main():
    parser = argparse.ArgumentParser(description="官方信息源抓取骨架")
    parser.add_argument("--list", action="store_true", help="列出已配置的源")
    parser.add_argument("--source", default="", help="抓取指定源（key，如 jwc）")
    parser.add_argument("--all", action="store_true", help="抓取全部源")
    parser.add_argument("--data-dir", default=r"C:\soft\opencode_download\uestc-public-full",
                        help="输出目录（与论坛爬虫共用，posts/ 下统一入库）")
    parser.add_argument("--max-pages", type=int, default=3, help="每个源最多抓列表页数")
    args = parser.parse_args()

    os.makedirs(os.path.join(args.data_dir, "posts"), exist_ok=True)

    if args.list:
        for key, conf in SOURCES.items():
            print(f"{key:<8} {conf['name']:<10} {conf['url']}")
        return
    if args.source:
        if args.source not in SOURCES:
            print(f"未知源: {args.source}，可用: {', '.join(SOURCES)}")
            return
        crawlSource(args.source, args.data_dir, args.max_pages)
        return
    if args.all:
        for key in SOURCES:
            crawlSource(key, args.data_dir, args.max_pages)
        return
    parser.print_help()


if __name__ == "__main__":
    main()
