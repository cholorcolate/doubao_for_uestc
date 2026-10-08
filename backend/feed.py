"""
信息聚合模块：按分类从论坛知识库提取通知公告、讲座、竞赛、招聘

数据来源：知识库 FTS 索引（knowledge_base/fts_index.db 的 docs 表），
按「板块白名单 + 标题关键词」归类（任一命中即归入），同一帖子（tid）
只取首个分块作摘要，按发帖时间倒序分页返回。
"""

import sqlite3

from rag import FTS_DB_PATH

# 分类定义：boards=板块白名单，keywords=标题关键词，OR 关系
CATEGORIES = {
    "notice": {
        "name": "通知公告",
        "boards": ["站务公告", "部门直通车"],
        "keywords": ["通知", "公告", "公示"],
    },
    "lecture": {
        "name": "讲座",
        "boards": [],
        "keywords": ["讲座", "报告会", "学术报告", "沙龙"],
    },
    "contest": {
        "name": "竞赛",
        "boards": [],
        "keywords": ["竞赛", "大赛", "挑战杯", "建模"],
    },
    "job": {
        "name": "招聘",
        "boards": ["就业创业", "公考选调"],
        "keywords": ["招聘", "宣讲会", "实习", "春招", "秋招", "选调"],
    },
}

SNIPPET_CHARS = 150  # 列表摘要最大字数


def buildWhere(category=None, board=None):
    """拼接 WHERE 条件，返回 (sql 片段, 参数列表)"""
    clauses = []
    params = []
    if category:
        spec = CATEGORIES[category]
        parts = []
        if spec["boards"]:
            marks = ",".join("?" * len(spec["boards"]))
            parts.append(f"board_name IN ({marks})")
            params.extend(spec["boards"])
        for kw in spec["keywords"]:
            parts.append("title LIKE ?")
            params.append(f"%{kw}%")
        clauses.append("(" + " OR ".join(parts) + ")")
    if board:
        clauses.append("board_name = ?")
        params.append(board)
    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


def queryFeed(category=None, board=None, page=1, size=20):
    """分页查询信息流；分类未知或索引缺失时返回空列表"""
    try:
        page = max(1, int(page))
        size = min(max(1, int(size)), 50)
    except (TypeError, ValueError):
        page, size = 1, 20

    if category and category not in CATEGORIES:
        return {"items": [], "total": 0, "page": page, "size": size,
                "error": "未知分类"}
    if not FTS_DB_PATH.exists():
        return {"items": [], "total": 0, "page": page, "size": size}

    where, params = buildWhere(category, board)
    conn = sqlite3.connect(str(FTS_DB_PATH), timeout=5)
    try:
        total = conn.execute(
            f"SELECT COUNT(DISTINCT tid) FROM docs WHERE {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT d.tid, d.title, d.board_name, d.source, d.create_time, d.text"
            " FROM docs d"
            f" JOIN (SELECT MIN(id) AS mid FROM docs WHERE {where} GROUP BY tid) t"
            " ON d.id = t.mid"
            " ORDER BY d.create_time DESC LIMIT ? OFFSET ?",
            params + [size, (page - 1) * size],
        ).fetchall()
    finally:
        conn.close()

    items = []
    for tid, title, boardName, source, createTime, text in rows:
        items.append({
            "tid": str(tid),
            "title": title or "",
            "board": boardName or "",
            "url": source or "",
            "time": (createTime or "")[:10],
            "snippet": (text or "").replace("\n", " ")[:SNIPPET_CHARS],
        })
    return {"items": items, "total": total, "page": page, "size": size}
