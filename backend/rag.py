"""
RAG 核心模块：混合检索（向量 + BM25）+ Rerank + 大模型生成

功能：
1. 懒加载本地 bge 向量模型、Chroma 向量库与 SQLite FTS5 关键词索引
2. 双路召回：向量语义检索 + BM25 关键词检索，RRF 融合（论坛专名如
   「东二院」「保七条」纯向量易漏，BM25 可补召回）
3. 融合候选交给硅基流动 Rerank 精排，取最相关片段生成带出处的回答
4. 支持板块 / 时间范围过滤（向量侧 metadata + FTS5 侧 WHERE 同时生效）
5. 任一环节不可用逐级降级：无 Rerank -> RRF 序；无 FTS -> 纯向量；
   无 API Key / 生成失败 -> 检索原文摘要

配置（环境变量，或写在项目根目录 .env，不会入库）：
    SILICONFLOW_API_KEY        硅基流动密钥
    SILICONFLOW_MODEL          生成模型，默认 Qwen/Qwen3-8B
    SILICONFLOW_RERANK_MODEL   重排模型，默认 BAAI/bge-reranker-v2-m3
    KB_DIR                     知识库目录，默认 项目根/knowledge_base
"""

import os
import re
import sqlite3
from pathlib import Path

# 项目根目录（backend 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent


def loadEnvFile():
    """加载项目根目录 .env，不覆盖已有环境变量"""
    envPath = BASE_DIR / ".env"
    if not envPath.exists():
        return
    for line in envPath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


loadEnvFile()

# 知识库路径
KB_DIR = Path(os.environ.get("KB_DIR", str(BASE_DIR / "knowledge_base")))
CHROMA_PATH = str(KB_DIR / "chroma_db")
COLLECTION_NAME = "uestc_bbs"
FTS_DB_PATH = KB_DIR / "fts_index.db"

# 本地向量模型（与建库时保持一致）
EMBED_MODEL = "BAAI/bge-small-zh-v1.5"
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："

# 硅基流动 API
API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
BASE_URL = os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL = os.environ.get("SILICONFLOW_MODEL", "Qwen/Qwen3-8B")
RERANK_MODEL = os.environ.get("SILICONFLOW_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

# 检索与生成参数
VECTOR_TOP_K = 30      # 向量召回条数
BM25_TOP_K = 30        # BM25 召回条数
RRF_K = 60             # RRF 融合常数
FUSION_TOP_K = 10      # 融合后进入 Rerank 的候选数
TOP_K = 5              # 最终交给生成的片段数
RERANK_ALPHA = 0.7     # Rerank 与 RRF 分数的融合权重（评测调优：0.7*Rerank+0.3*RRF）
MIN_SIMILARITY = 0.35  # 向量路低于该相似度视为不相关
MAX_SNIPPET_CHARS = 600  # 单条资料喂给模型的最大字数
TEMPERATURE = 0.3
MAX_TOKENS = 900
LLM_TIMEOUT = 60
RERANK_TIMEOUT = 20

# 查询侧停用词（索引期保留全部 token，仅查询期过滤，保证召回）
QUERY_STOPWORDS = {
    "什么", "怎么", "怎样", "如何", "为什么", "是不是", "有没有", "能不能",
    "吗", "呢", "啊", "吧", "呀", "哦", "么", "什么的",
    "的", "了", "是", "在", "有", "和", "与", "或", "及", "就", "都",
    "也", "还", "很", "非常", "太", "更", "最", "把", "被", "给", "让",
    "从", "到", "为", "之", "其", "而", "但", "并", "且", "再", "又",
    "我", "你", "他", "她", "它", "我们", "你们", "他们", "大家",
    "这个", "那个", "这些", "那些", "一个", "一种", "一下", "一点",
    "请问", "想问", "问下", "问问", "求助", "咨询", "知道", "看看",
    "可以", "需要", "应该", "会", "能", "要", "会", "得", "着",
    "哪个", "哪些", "哪里", "哪儿", "多少", "几个", "何时", "多会儿",
    "怎么样", "咋", "嘛", "呗", "啦", "哟",
}

# 时间范围映射（天数），用于 create_time >= cutoff 的字符串比较
TIME_RANGES = {
    "30d": "30",
    "90d": "90",
    "180d": "180",
    "1y": "365",
    "3y": "1095",
}

SYSTEM_PROMPT = (
    "你是电子科技大学校园问答助手「成电智答」，基于清水河畔论坛知识库回答问题。\n"
    "规则：\n"
    "1. 只依据提供的【参考资料】回答，不要编造资料中没有的信息；\n"
    "2. 资料不足以回答时，明确说明「根据现有资料未找到」，可提示用户去对应部门官网核实；\n"
    "3. 使用简体中文，回答简洁、分点组织，关键结论后标注来源编号如 [1]；\n"
    "4. 涉及具体时间、金额、政策时提醒以学校最新通知为准。"
)


def buildTimeCutoff(timeRange: str):
    """把 30d/1y 等时间范围转为 ISO 截止日期（字符串可直接比较），
    返回 None 表示不过滤"""
    if not timeRange or timeRange == "all":
        return None
    days = TIME_RANGES.get(timeRange)
    if not days:
        return None
    from datetime import date, timedelta
    return (date.today() - timedelta(days=int(days))).isoformat()


def buildFtsQuery(question: str) -> str:
    """查询侧分词：jieba 切词 -> 去停用词/单字 -> FTS5 OR 表达式"""
    import jieba
    tokens = []
    for tok in jieba.lcut(question):
        tok = tok.strip()
        if not tok or tok in QUERY_STOPWORDS:
            continue
        if len(tok) < 2 and not tok.isdigit():
            continue
        if re.search(r"[一-鿿A-Za-z0-9]", tok) and tok not in tokens:
            tokens.append(tok)
    if not tokens:
        # 全被过滤时退回原始分词（含单字），避免空查询
        tokens = [t.strip() for t in jieba.lcut(question) if t.strip()]
    # FTS5 OR 语义：任一 token 命中即召回，BM25 分数排序
    return " OR ".join(f'"{t}"' for t in tokens)


class RagEngine:
    """RAG 引擎：混合检索 + Rerank + 生成（单例，模型只加载一次）"""

    _instance = None

    @classmethod
    def instance(cls) -> "RagEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._embedder = None
        self._collection = None
        self._ftsOk = None  # None=未检查, False=索引不存在

    @property
    def embedder(self):
        """懒加载本地向量模型"""
        if self._embedder is None:
            # 离线模式：模型已在本地缓存，跳过对 huggingface.co 的联网检查
            # （联网会因 SSL 证书问题反复重试，导致预热卡住数分钟）
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            from sentence_transformers import SentenceTransformer

            print("加载向量模型...")
            self._embedder = SentenceTransformer(EMBED_MODEL)
            print("向量模型加载完成")
        return self._embedder

    @property
    def collection(self):
        """懒加载向量库"""
        if self._collection is None:
            import chromadb

            client = chromadb.PersistentClient(path=CHROMA_PATH)
            self._collection = client.get_collection(COLLECTION_NAME)
            print(f"向量库加载完成，共 {self._collection.count()} 条")
        return self._collection

    @property
    def ftsOk(self) -> bool:
        """FTS5 关键词索引是否存在（首次检查后缓存结果）"""
        if self._ftsOk is None:
            self._ftsOk = FTS_DB_PATH.exists()
            if not self._ftsOk:
                print(f"FTS 索引不存在（{FTS_DB_PATH}），关键词检索不可用")
        return self._ftsOk

    def warmup(self):
        """预热：提前加载模型与各索引，避免首个请求卡住"""
        _ = self.embedder
        _ = self.collection
        _ = self.ftsOk

    @staticmethod
    def _buildWhere(board):
        """构造 Chroma metadata 过滤条件（仅板块）。
        注意：Chroma 的 $gte 只支持数值，不支持日期字符串，
        因此时间过滤在 Python 侧二次筛选（见 _vectorSearch）。"""
        if not board:
            return None
        return {"board_name": {"$eq": board}}

    def _vectorSearch(self, question: str, board=None, cutoff=None, topK=VECTOR_TOP_K):
        """向量语义检索，返回相似度降序的片段列表（含时间过滤）"""
        queryText = QUERY_PREFIX + question
        embedding = self.embedder.encode([queryText], normalize_embeddings=True).tolist()
        # 带时间过滤时多召回一些，避免二次筛选后不足
        fetchK = min(topK * 3, 100) if cutoff else topK
        results = self.collection.query(
            query_embeddings=embedding,
            n_results=fetchK,
            where=self._buildWhere(board),
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            similarity = 1 - dist  # cosine 距离 -> 相似度
            if similarity < MIN_SIMILARITY:
                continue
            createTime = meta.get("create_time", "") or ""
            # 时间过滤：ISO 日期字符串可直接比较（少量相对时间格式会被排除）
            if cutoff and createTime < cutoff:
                continue
            # Chroma 未存 chunk_id，用 tid+chunk_index 重建（与 chunks.jsonl 一致）
            chunkId = "{}_{}".format(
                meta.get("tid", ""), meta.get("chunk_index", 0)
            )
            hits.append({
                "chunk_id": chunkId,
                "tid": str(meta.get("tid", "")),
                "title": meta.get("title", ""),
                "board_name": meta.get("board_name", ""),
                "source": meta.get("source", ""),
                "create_time": createTime,
                "similarity": round(similarity, 4),
                "text": doc[:MAX_SNIPPET_CHARS],
                "vectorRank": len(hits) + 1,
                "bm25Rank": None,
            })
            if len(hits) >= topK:
                break
        return hits

    def _bm25Search(self, question: str, board=None, cutoff=None, topK=BM25_TOP_K):
        """BM25 关键词检索（SQLite FTS5），失败返回空列表"""
        if not self.ftsOk:
            return []
        try:
            expr = buildFtsQuery(question)
            sql = (
                "SELECT d.chunk_id, d.tid, d.title, d.board_name, d.source,"
                " d.create_time, d.text,"
                " bm25(docs_fts, 10.0, 1.0) AS score"
                " FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid"
                " WHERE docs_fts MATCH ?"
            )
            params = [expr]
            if board:
                sql += " AND d.board_name = ?"
                params.append(board)
            if cutoff:
                sql += " AND d.create_time >= ?"
                params.append(cutoff)
            sql += " ORDER BY score LIMIT ?"
            params.append(topK)

            # 每次查询用独立短连接（WAL 模式下并发读安全）
            conn = sqlite3.connect(str(FTS_DB_PATH), timeout=5)
            try:
                rows = conn.execute(sql, params).fetchall()
            finally:
                conn.close()
        except Exception as e:
            print(f"BM25 检索失败，仅用向量检索：{e}")
            return []

        hits = []
        for rank, row in enumerate(rows, 1):
            chunkId, tid, title, boardName, source, createTime, text, _score = row
            hits.append({
                "chunk_id": chunkId,
                "tid": str(tid),
                "title": title,
                "board_name": boardName,
                "source": source,
                "create_time": createTime,
                "similarity": None,
                "text": (text or "")[:MAX_SNIPPET_CHARS],
                "vectorRank": None,
                "bm25Rank": rank,
            })
        return hits

    @staticmethod
    def _rrfFuse(vectorHits: list, bm25Hits: list) -> list:
        """RRF 融合双路召回结果（按 chunk_id 聚合，各路内部已按质量排序）"""
        scores = {}
        merged = {}
        for hits in (vectorHits, bm25Hits):
            for rank, hit in enumerate(hits, 1):
                cid = hit["chunk_id"]
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
                if cid not in merged:
                    merged[cid] = hit
                else:
                    # 两路都命中时合并信息（保留向量相似度）
                    exist = merged[cid]
                    if exist.get("similarity") is None and hit.get("similarity") is not None:
                        exist["similarity"] = hit["similarity"]
                    if exist.get("vectorRank") is None and hit.get("vectorRank") is not None:
                        exist["vectorRank"] = hit["vectorRank"]
                    if exist.get("bm25Rank") is None and hit.get("bm25Rank") is not None:
                        exist["bm25Rank"] = hit["bm25Rank"]
        fused = []
        for cid, hit in sorted(merged.items(), key=lambda kv: -scores[kv[0]]):
            hit["rrfScore"] = round(scores[cid], 6)
            fused.append(hit)
        return fused

    @staticmethod
    def _dedup(hits: list) -> list:
        """同一帖子可能被切成多个分块，按标题+链接去重，只保留排序最靠前的一条"""
        seen = set()
        deduped = []
        for hit in hits:
            key = (hit["title"], hit["source"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(hit)
        return deduped

    def _rerank(self, question: str, hits: list) -> list:
        """调用硅基流动 Rerank 精排；失败返回 None（由调用方降级为 RRF 序）"""
        if not API_KEY or not hits:
            return None
        try:
            import requests

            documents = [
                f"{h['title']}\n{h['board_name']}\n{h['text']}" for h in hits
            ]
            resp = requests.post(
                f"{BASE_URL}/rerank",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={
                    "model": RERANK_MODEL,
                    "query": question,
                    "documents": documents,
                    "top_n": min(TOP_K, len(hits)),
                    "return_documents": False,
                },
                timeout=RERANK_TIMEOUT,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return None
            reranked = []
            for item in results:
                hit = dict(hits[item["index"]])
                hit["rerankScore"] = round(item["relevance_score"], 4)
                reranked.append(hit)
            return reranked
        except Exception as e:
            print(f"Rerank 失败，降级为融合排序：{e}")
            return None

    def retrieve(
        self,
        question: str,
        topK: int = TOP_K,
        board=None,
        timeRange=None,
        useRerank: bool = True,
    ):
        """混合检索：向量 + BM25 -> RRF 融合 -> Rerank 加权重排

        纯 Rerank 重排在评测集上会损失 hit@5，因此采用加权融合：
        final = RERANK_ALPHA * rerankScore + (1-RERANK_ALPHA) * 归一化(rrfScore)
        兼顾语义精排与词面召回（评测 hit@1 55.3%->61.7%，MRR 0.660->0.667）
        """
        cutoff = buildTimeCutoff(timeRange)
        vectorHits = self._vectorSearch(question, board=board, cutoff=cutoff)
        bm25Hits = self._bm25Search(question, board=board, cutoff=cutoff)

        fused = self._dedup(self._rrfFuse(vectorHits, bm25Hits))
        if not fused:
            return []

        candidates = fused[:FUSION_TOP_K]
        if useRerank:
            reranked = self._rerank(question, candidates)
            if reranked:
                return self._blendScores(reranked, candidates)[:topK]
        return candidates[:topK]

    def keywordSearch(self, question: str, topK: int = 8) -> list:
        """纯 BM25 关键词检索 + 去重（校园工具页等轻量场景，
        不走向量模型与 Rerank，毫秒级返回）"""
        hits = self._bm25Search(question, topK=topK * 3)
        return self._dedup(hits)[:topK]

    @staticmethod
    def _blendScores(reranked: list, candidates: list) -> list:
        """Rerank 分数与归一化 RRF 分数加权融合后重排。

        Rerank 接口只返回 top_n 条，未返回的候选项按 rerankScore=0 参与融合，
        保证 RRF 高分候选不会因精排截断而丢失。"""
        rrfScores = {h["chunk_id"]: h["rrfScore"] for h in candidates}
        mn = min(rrfScores.values())
        mx = max(rrfScores.values())

        def rrfNorm(cid):
            s = rrfScores.get(cid, mn)
            return (s - mn) / (mx - mn) if mx > mn else 1.0

        merged = {h["chunk_id"]: h for h in reranked}
        for h in candidates:
            merged.setdefault(h["chunk_id"], h)

        blended = []
        for h in merged.values():
            score = RERANK_ALPHA * h.get("rerankScore", 0) + (1 - RERANK_ALPHA) * rrfNorm(h["chunk_id"])
            blended.append((score, h))
        blended.sort(key=lambda x: -x[0])
        return [h for _, h in blended]

    def _generate(self, question: str, hits: list):
        """调用硅基流动生成回答，失败返回 None（由调用方降级）"""
        if not API_KEY:
            print("未配置 SILICONFLOW_API_KEY，跳过生成")
            return None
        try:
            from openai import OpenAI

            blocks = []
            for i, hit in enumerate(hits, 1):
                timeStr = (hit["create_time"] or "")[:10]
                blocks.append(
                    f"[{i}]（板块：{hit['board_name']}｜标题：{hit['title']}｜时间：{timeStr}）\n"
                    f"链接：{hit['source']}\n"
                    f"内容：{hit['text']}"
                )
            userPrompt = "【参考资料】\n" + "\n\n".join(blocks) + f"\n\n【问题】\n{question}"

            client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=LLM_TIMEOUT)
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": userPrompt},
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            content = (resp.choices[0].message.content or "").strip()
            return content or None
        except Exception as e:
            print(f"大模型生成失败，降级为检索原文：{e}")
            return None

    def answer(self, question: str, board=None, timeRange=None) -> dict:
        """完整 RAG 流程：混合检索 -> Rerank -> 生成 -> 结果（兼容前端字段）"""
        question = (question or "").strip()
        if not question:
            return {"answer": "请输入问题。", "source": "知识库未收录", "sources": []}

        try:
            hits = self.retrieve(question, board=board, timeRange=timeRange)
        except Exception as e:
            print(f"检索失败：{e}")
            return {"answer": "知识库检索失败，请稍后重试。", "source": "知识库未收录", "sources": []}

        if not hits:
            scopeHint = ""
            if board:
                scopeHint += f"（板块限定：{board}）"
            if timeRange and timeRange != "all":
                scopeHint += f"（时间范围：{timeRange}）"
            return {
                "answer": f"根据现有资料未找到相关内容{scopeHint}，建议放宽筛选条件或去对应部门官网核实。",
                "source": "知识库未收录",
                "sources": [],
            }

        generated = self._generate(question, hits)
        if generated:
            answerText = generated
        else:
            # 降级：直接展示检索原文
            parts = [f"【{h['board_name']}】{h['title']}\n{h['text']}" for h in hits[:2]]
            answerText = "未配置大模型，以下是检索到的原文：\n\n" + "\n\n".join(parts)

        primary = hits[0]
        return {
            "answer": answerText,
            "source": f"{primary['board_name']} · {primary['title']}",
            "sources": [
                {
                    key: hit.get(key)
                    for key in (
                        "title", "board_name", "source", "create_time",
                        "similarity", "rerankScore",
                    )
                }
                for hit in hits
            ],
        }


if __name__ == "__main__":
    # 快速自测：python rag.py "保研需要什么条件" [板块] [时间范围]
    import json
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "保研需要什么条件"
    boardArg = sys.argv[2] if len(sys.argv) > 2 else None
    timeArg = sys.argv[3] if len(sys.argv) > 3 else None
    result = RagEngine.instance().answer(query, board=boardArg, timeRange=timeArg)
    print(json.dumps(result, ensure_ascii=False, indent=2))
