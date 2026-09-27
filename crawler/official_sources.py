"""
官方信息源抓取骨架（教务处 / 研究生院 / 学工部 / 后勤等）

现状说明：
- 清水河畔论坛（bbs.uestc.edu.cn）已由 uestc_bbs_crawler.py 全量覆盖
- 本文件为官方站点抓取提供统一骨架：每个源只需在 SOURCES 中配置
  列表页 URL 与解析函数，即可复用「列表页 -> 文章页 -> 统一 JSON」流程
- 输出格式与论坛 thread_*.json 对齐（tid/title/posts），
  便于直接进入 preprocess.py -> chunk-data.py 既有流水线
- 教务处（jwc）已接入：列表用 li[newsid] 属性拼 /info/{newsid}，
  文章页标题取 .detail_header h2、正文取 .NewText

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

# 各官方源配置：url=列表页，parser=列表解析器，article_parser=文章解析器
# 抓取前请人工访问列表页确认 DOM 结构是否变化
SOURCES = {
    "jwc": {
        "name": "教务处",
        "url": "https://www.jwc.uestc.edu.cn/",
        "parser": "jwc_list",
        "article_parser": "jwc",
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


def jwc_list(html: str, baseUrl: str) -> list[dict]:
    """教务处列表解析：文章标识在 <li newsid="..."> 属性上，a[href] 是 JS 占位。

    拼接规则：文章页 URL = /info/{newsid}（由页面内 /info/xxx 链接确认）。
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()
    for li in soup.find_all("li", attrs={"newsid": True}):
        newsid = li["newsid"].strip()
        a = li.find("a", href=True)
        title = ""
        if a:
            title = (a.get("title") or "").strip() or a.get_text(strip=True)
        if not newsid or not title or newsid in seen:
            continue
        seen.add(newsid)
        url = requests.compat.urljoin(baseUrl, f"/info/{newsid}")
        items.append({"id": newsid, "title": title, "url": url})
    return items


def jwc_article(html: str) -> dict | None:
    """教务处文章页解析：标题在 .detail_header h2，正文在 .NewText（不含上一篇/下一篇）。"""
    soup = BeautifulSoup(html, "html.parser")
    h2 = soup.select_one(".detail_header h2") or soup.find("h2")
    if not h2:
        return None
    title = h2.get_text(strip=True)

    body = soup.find("div", class_="NewText") or soup.find("div", class_="contentNewText")
    if not body:
        return None
    text = body.get_text("\n", strip=True)
    if len(text) < 50:
        return None

    pubTime = ""
    itemTag = soup.select_one(".detail_header .item")
    m = re.search(r"发布时间[:：]\s*(20\d{2}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2})?)",
                  itemTag.get_text(" ", strip=True) if itemTag else "")
    if m:
        pubTime = m.group(1).replace("/", "-")

    return {"title": title, "text": text, "publish_time": pubTime}


# 解析器注册表：SOURCES 中按名称引用，新站点接入时在此挂载
LIST_PARSERS = {
    "generic_list": generic_list,
    "jwc_list": jwc_list,
}
ARTICLE_PARSERS = {
    "generic": parse_article,
    "jwc": jwc_article,
}


def saveArticle(dataDir: str, sourceKey: str, artId, article: dict):
    """保存为与论坛帖子对齐的 thread_*.json 格式，直接进入既有流水线"""
    # 优先用站点文章 id（如教务处 newsid）保证增量抓取时 tid 稳定，
    # 无站点 id 的源退回调用序号
    tid = f"official_{sourceKey}_{artId}"
    record = {
        "tid": tid,
        "title": article["title"],
        "posts": [{
            "post_id": str(artId),
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def crawlSource(sourceKey: str, dataDir: str, maxPages: int = 3):
    """抓取单个源：列表页 -> 文章页 -> 落盘"""
    conf = SOURCES[sourceKey]
    print(f"\n抓取 {conf['name']} ({conf['url']})")
    session = requests.Session()
    parser = LIST_PARSERS[conf.get("parser", "generic_list")]
    articleParser = ARTICLE_PARSERS[conf.get("article_parser", "generic")]

    count = 0
    seenUrls = set()
    for page in range(1, maxPages + 1):
        # 多数官方站点列表页带 page 参数，不支持时会返回同页（跨页按 URL 去重兜底）
        listUrl = conf["url"] if page == 1 else f"{conf['url']}index_{page}.html"
        html = fetch(listUrl, session)
        if not html:
            break
        items = parser(html, conf["url"])
        if not items:
            break
        for item in items:
            if item["url"] in seenUrls:
                continue
            seenUrls.add(item["url"])
            artHtml = fetch(item["url"], session)
            if not artHtml:
                continue
            article = articleParser(artHtml)
            if article:
                saveArticle(dataDir, sourceKey, item.get("id", count), article)
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
