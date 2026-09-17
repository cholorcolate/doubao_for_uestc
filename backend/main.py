from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio, random

app = FastAPI(title="成电智答 Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

QA = {
    "保研成绩怎么算？": (
        "保研综合成绩一般由学业成绩与综合素质测评构成，不同学院权重可能不同，具体以教务处当年通知为准。",
        "教务处官网（示例）",
    ),
    "这学期校历安排": (
        "校历页签提供教学周、考试周与假期安排，具体日期以学校官方发布为准。",
        "学校官网 · 校历（示例）",
    ),
    "清水河到沙河班车时刻": (
        "工作日开行通勤班车，发车时间与站点以后勤保障部最新通知为准。",
        "后勤保障部（示例）",
    ),
    "选课退课规则": (
        "选课一般分预选、正选、补退选三个阶段，各阶段时间与规则以教务系统通知为准。",
        "教务处（示例）",
    ),
}
FALLBACK = ("这个问题知识库暂未收录，建议去对应部门官网核实。", "知识库未收录")


class ChatReq(BaseModel):
    question: str


@app.post("/api/chat")
async def chat(req: ChatReq):
    await asyncio.sleep(0.8 + random.random() * 0.5)
    q = req.question.strip()
    answer, source = QA.get(q, FALLBACK)
    return {"answer": answer, "source": source}


app.mount("/", StaticFiles(directory="web", html=True), name="web")
