"""
成电智答后端：FastAPI + RAG 问答

启动方式（项目根或 backend 目录均可）：
    cd backend
    uvicorn main:app --host 127.0.0.1 --port 8000
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rag import RagEngine

# 项目根目录下的前端目录（与启动时的工作目录无关）
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时后台预热模型与向量库，避免首个请求等待
    asyncio.create_task(asyncio.to_thread(RagEngine.instance().warmup))
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


@app.get("/api/boards")
async def boards():
    """板块列表（供前端筛选下拉框），来自 FTS 索引"""
    import sqlite3 as _sqlite3

    from rag import FTS_DB_PATH
    if not FTS_DB_PATH.exists():
        return {"boards": []}
    conn = _sqlite3.connect(str(FTS_DB_PATH), timeout=5)
    try:
        rows = conn.execute(
            "SELECT board_name, COUNT(*) AS c FROM docs"
            " GROUP BY board_name ORDER BY c DESC"
        ).fetchall()
    finally:
        conn.close()
    return {"boards": [{"name": b, "count": c} for b, c in rows if b]}


@app.get("/api/health")
async def health():
    engine = RagEngine.instance()
    return {
        "status": "ok",
        "llm": bool(__import__("rag").API_KEY),
        "count": engine.collection.count(),
        "fts": engine.ftsOk,
    }


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
