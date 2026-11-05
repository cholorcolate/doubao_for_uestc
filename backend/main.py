"""
成电智答后端：FastAPI + RAG 问答

启动方式（项目根或 backend 目录均可）：
    cd backend
    uvicorn main:app --host 127.0.0.1 --port 8000
"""

import asyncio
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from feed import CATEGORIES as FEED_CATEGORIES, queryFeed, warmFeed
from rag import API_KEY, FTS_DB_PATH, RagEngine
from tools import listTools, searchTool

# 项目根目录下的前端目录（与启动时的工作目录无关）
WEB_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动阶段（单线程、接流量前）预导入重依赖：
    # 避免预热线程与请求线程并发首次 import numpy 触发循环导入竞态
    import jieba  # noqa: F401
    import numpy  # noqa: F401
    import chromadb  # noqa: F401
    import sentence_transformers  # noqa: F401

    # 启动时后台预热模型/向量库、信息流首页与板块列表，避免首个请求等待
    def _warmup():
        RagEngine.instance().warmup()
        warmFeed()
        try:
            _boardsCache["data"] = _queryBoards()
            _boardsCache["at"] = time.monotonic()
        except Exception as e:
            print(f"板块列表预热失败：{e}")

    asyncio.create_task(asyncio.to_thread(_warmup))
    yield


app = FastAPI(title="成电智答", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatReq(BaseModel):
    question: str
    # 可选筛选：板块名（如「保研考研」）、时间范围（30d/90d/180d/1y/3y/all）
    board: str | None = None
    time_range: str | None = None


@app.post("/api/chat")
async def chat(req: ChatReq):
    # 检索与生成是阻塞调用，放到线程池避免卡住事件循环
    result = await asyncio.to_thread(
        RagEngine.instance().answer,
        req.question,
        req.board,
        req.time_range,
    )
    return result


_boardsCache = {"at": 0.0, "data": None}
BOARDS_CACHE_TTL = 300  # 板块分布变化很慢，缓存 5 分钟


def _queryBoards():
    """板块列表（供前端筛选下拉框），来自 FTS 索引"""
    if not FTS_DB_PATH.exists():
        return {"boards": []}
    conn = sqlite3.connect(str(FTS_DB_PATH), timeout=5)
    try:
        rows = conn.execute(
            "SELECT board_name, COUNT(*) AS c FROM docs"
            " GROUP BY board_name ORDER BY c DESC"
        ).fetchall()
    finally:
        conn.close()
    return {"boards": [{"name": b, "count": c} for b, c in rows if b]}


@app.get("/api/boards")
async def boards():
    cached = _boardsCache["data"]
    if cached is not None and time.monotonic() - _boardsCache["at"] < BOARDS_CACHE_TTL:
        return cached
    # 同步 SQLite 查询放到线程池，避免阻塞事件循环
    data = await asyncio.to_thread(_queryBoards)
    _boardsCache["at"] = time.monotonic()
    _boardsCache["data"] = data
    return data


@app.get("/api/feed/categories")
async def feedCategories():
    """信息聚合分类列表（前端 tab）"""
    return {
        "categories": [{"id": cid, "name": spec["name"]}
                       for cid, spec in FEED_CATEGORIES.items()]
    }


@app.get("/api/feed")
async def feedList(category: str | None = None, board: str | None = None,
                   page: int = 1, size: int = 20):
    """信息聚合分页列表（通知公告/讲座/竞赛/招聘，可按板块过滤）"""
    return await asyncio.to_thread(queryFeed, category, board, page, size)


@app.get("/api/tools")
async def toolsList():
    """校园工具列表"""
    return {"tools": listTools()}


@app.get("/api/tools/{toolId}")
async def toolSearch(toolId: str, q: str | None = None, topK: int = 8):
    """校园工具知识库检索（BM25，q 覆盖预置检索词）"""
    return await asyncio.to_thread(searchTool, toolId, q, topK)


_kbCount = None  # 知识库条目数；数据更新需重启服务，故进程内缓存即可


def _countKnowledge():
    return RagEngine.instance().collection.count()


@app.get("/api/health")
async def health():
    global _kbCount
    if _kbCount is None:
        _kbCount = await asyncio.to_thread(_countKnowledge)
    return {
        "status": "ok",
        "llm": bool(API_KEY),
        "llm_error": RagEngine.instance().lastLlmError,
        "count": _kbCount,
        "fts": RagEngine.instance().ftsOk,
    }


@app.get("/health", include_in_schema=False)
async def healthAlias():
    """兼容常见的 /health 探活路径，避免反复 404"""
    return await health()


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="frontend")
