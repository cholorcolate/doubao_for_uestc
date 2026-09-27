"""
构建 SQLite FTS5 关键词索引（BM25 检索用，混合检索的关键词一路）

功能：
1. 流式读取 chunks.jsonl，jieba 预分词
2. 原文元数据存 docs 表，分词文本存 docs_fts（FTS5，标题列权重更高）
3. 磁盘持久化，查询期零大内存占用（BM25 只在查询时按需加载）

使用方法：
    python build-fts.py --input ./processed/chunks.jsonl --db ./fts_index.db

说明：
- 索引期保留全部实义 token（含单字、疑问词），停用词过滤只在查询侧做，
  保证查询 token 一定能在索引中命中
- create_time 保留原始字符串（ISO 为主，少量相对时间如「前天 23:40」），
  时间过滤时按字符串比较，对 ISO 时间语义正确
"""

import argparse
import json
import sqlite3
import time
import unicodedata
from pathlib import Path

import jieba


def safeTid(value) -> int:
    """tid 转数值；官方源等非数字 tid（如 official_jwc_0001）视为极大值，
    使其在增量模式下始终进入候选（实际是否插入由 chunk_id 去重兜底）"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10 ** 12


def keepToken(token: str) -> bool:
    """只保留含字母/数字/汉字的 token，丢弃纯标点符号"""
    return any(unicodedata.category(ch)[0] in ("L", "N") for ch in token)


def segment(text: str) -> str:
    """jieba 分词并过滤纯标点 token，返回空格分隔的词串"""
    if not text:
        return ""
    return " ".join(t for t in jieba.lcut(text) if keepToken(t))


def main():
    parser = argparse.ArgumentParser(description="构建 FTS5 关键词索引")
    parser.add_argument("--input", default="./processed/chunks.jsonl", help="分块数据 jsonl")
    parser.add_argument("--db", default="./fts_index.db", help="SQLite 数据库路径")
    parser.add_argument("--batch", type=int, default=5000, help="提交批大小")
    parser.add_argument("--min-tid", type=int, default=0,
                        help="增量模式：只索引 tid 大于该值的新分块（0=全量重建）")
    args = parser.parse_args()

    dbPath = Path(args.db)
    incremental = args.min_tid > 0 and dbPath.exists()

    if incremental:
        # 增量追加：复用现有库，rowid 从当前最大值续接
        conn = sqlite3.connect(str(dbPath))
        startRowid = conn.execute("SELECT COALESCE(MAX(id), 0) FROM docs").fetchone()[0]
        existing = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        # 幂等兜底：已入库的 chunk_id 直接跳过（重复执行不会产生重复行）
        doneIds = {row[0] for row in conn.execute("SELECT chunk_id FROM docs")}
        print(f"增量模式：已有 {existing} 条，rowid 从 {startRowid + 1} 起，"
              f"只索引 tid > {args.min_tid} 的新分块")
    else:
        # 重建索引：删除旧库（含 WAL/SHM 残留）
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(dbPath) + suffix)
            if p.exists():
                p.unlink()
        startRowid = 0
        doneIds = set()

        conn = sqlite3.connect(str(dbPath))
        conn.execute(
            """
            CREATE TABLE docs (
                id INTEGER PRIMARY KEY,
                chunk_id TEXT,
                tid TEXT,
                chunk_index INTEGER,
                title TEXT,
                board_name TEXT,
                source TEXT,
                create_time TEXT,
                text TEXT
            )
            """
        )
        conn.execute("CREATE INDEX idx_docs_board ON docs(board_name)")
        conn.execute("CREATE INDEX idx_docs_time ON docs(create_time)")
        conn.execute(
            """
            CREATE VIRTUAL TABLE docs_fts USING fts5(
                title_seg, text_seg, tokenize='unicode61'
            )
            """
        )

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB 页缓存，批量写入提速

    print(f"读取分块: {args.input}")
    startTime = time.time()
    total = startRowid
    inserted = 0
    skipped = 0
    buf = []

    def flush():
        if not buf:
            return
        # 显式指定 docs.id，保证与 docs_fts.rowid 一一对齐
        conn.executemany(
            "INSERT INTO docs(id, chunk_id, tid, chunk_index, title, board_name,"
            " source, create_time, text) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (r["_rowid"], r["chunk_id"], r["tid"], r["chunk_index"], r["title"],
                 r["board_name"], r["source"], r["create_time"], r["text"])
                for r in buf
            ],
        )
        conn.executemany(
            "INSERT INTO docs_fts(rowid, title_seg, text_seg) VALUES (?,?,?)",
            [
                (r["_rowid"], r["_title_seg"], r["_text_seg"]) for r in buf
            ],
        )
        conn.commit()
        buf.clear()

    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if args.min_tid and safeTid(rec.get("tid")) <= args.min_tid:
                continue
            if rec.get("chunk_id") in doneIds:
                skipped += 1
                continue
            titleSeg = segment(rec.get("title", ""))
            textSeg = segment(rec.get("text", ""))
            total += 1
            inserted += 1
            buf.append({
                "chunk_id": rec["chunk_id"],
                "tid": str(rec["tid"]),
                "chunk_index": rec["chunk_index"],
                "title": rec.get("title", ""),
                "board_name": rec.get("board_name", ""),
                "source": rec.get("source", ""),
                "create_time": rec.get("create_time", "") or "",
                "text": rec.get("text", ""),
                "_rowid": total,  # 从 startRowid 起递增，docs.id 与 docs_fts.rowid 对齐
                "_title_seg": titleSeg,
                "_text_seg": textSeg,
            })
            if len(buf) >= args.batch:
                flush()
                elapsed = time.time() - startTime
                speed = inserted / elapsed if elapsed > 0 else 0
                remain = (558379 - total) / speed / 60 if speed > 0 else 0
                print(
                    f"进度: {total} 条（新增 {inserted}），速度 {speed:.0f} 条/秒, "
                    f"已用 {elapsed / 60:.1f} 分钟, 预计剩余 {remain:.1f} 分钟",
                    flush=True,
                )

    if buf:
        flush()

    print("优化索引中...", flush=True)
    conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('optimize')")
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()

    elapsed = time.time() - startTime
    count = sqlite3.connect(str(dbPath)).execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    sizeMb = dbPath.stat().st_size / 1024 / 1024
    print(
        f"完成！入库 {count} 条（跳过 {skipped}），耗时 {elapsed / 60:.1f} 分钟，"
        f"库大小 {sizeMb:.0f} MB -> {dbPath}",
        flush=True,
    )


if __name__ == "__main__":
    main()
