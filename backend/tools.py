"""
校园工具模块：校历、班车、课表、场馆等工具的信息检索

数据来源：知识库 FTS 关键词检索（纯 BM25，快速且不依赖向量模型），
每个工具预置检索词，前端也可传入自定义问题覆盖；
检索结果附「去问答深挖」预设问题，跳转问答页由 RAG 生成完整回答。
"""

from rag import RagEngine

# 工具定义：query=默认检索词，ask=跳转问答页的预设问题
TOOLS = [
    {
        "id": "calendar",
        "name": "校历",
        "desc": "教学周、考试周与假期安排",
        "query": "校历 教学周 考试周 假期",
        "ask": "这学期校历是怎么安排的？",
    },
    {
        "id": "shuttle",
        "name": "班车时刻",
        "desc": "清水河 ↔ 沙河校区通勤班车",
        "query": "班车 时刻 沙河 清水河 校车",
        "ask": "清水河到沙河的班车时刻是什么？",
    },
    {
        "id": "courses",
        "name": "课表考试",
        "desc": "选课、课表查询与考试安排",
        "query": "课表 选课 考试安排",
        "ask": "怎么查询课表和考试安排？",
    },
    {
        "id": "venues",
        "name": "场馆预约",
        "desc": "体育馆、游泳馆等场馆预约",
        "query": "体育馆 游泳馆 场馆 预约",
        "ask": "体育馆怎么预约？",
    },
    {
        "id": "library",
        "name": "图书馆教室",
        "desc": "开放时间、自习与教室信息",
        "query": "图书馆 开放时间 自习 教室",
        "ask": "图书馆的开放时间是什么？",
    },
]

SNIPPET_CHARS = 150  # 列表摘要最大字数


def listTools():
    """工具列表（不含预置检索词，供前端卡片展示）"""
    return [
        {"id": t["id"], "name": t["name"], "desc": t["desc"]}
        for t in TOOLS
    ]


def searchTool(toolId, query=None, topK=8):
    """检索工具相关帖子；未知工具或索引缺失时返回空结果"""
    tool = next((t for t in TOOLS if t["id"] == toolId), None)
    if not tool:
        return {"error": f"未知工具: {toolId}", "items": []}

    q = (query or "").strip() or tool["query"]
    hits = RagEngine.instance().keywordSearch(q, topK=topK)
    items = [
        {
            "title": h["title"],
            "board": h["board_name"],
            "url": h["source"],
            "time": (h["create_time"] or "")[:10],
            "snippet": (h["text"] or "").replace("\n", " ")[:SNIPPET_CHARS],
        }
        for h in hits
    ]
    return {
        "tool": tool["id"],
        "name": tool["name"],
        "query": q,
        "ask": tool["ask"],
        "items": items,
    }
