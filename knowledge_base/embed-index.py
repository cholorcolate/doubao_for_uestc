"""
向量化并导入 Chroma 向量数据库

功能：
1. 读取 chunks.jsonl
2. 用本地中文 Embedding 模型（默认 bge-small-zh-v1.5）批量向量化
3. 写入 Chroma 持久化向量库（支持断点续传：重复执行会 upsert）

使用方法：
    python embed-index.py --input ./processed/chunks.jsonl --db ./chroma_db

说明：
- 零成本：模型完全本地运行，无需 API Key
- 国内网络自动使用 hf-mirror.com 镜像下载模型
"""

import argparse
import json
import os
import time

# 国内 HuggingFace 镜像（若用户已自行设置则尊重用户配置）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import chromadb
from sentence_transformers import SentenceTransformer


def main():
    parser = argparse.ArgumentParser(description="向量化并导入 Chroma")
    parser.add_argument("--input", default="./processed/chunks.jsonl", help="分块数据 jsonl")
    parser.add_argument("--db", default="./chroma_db", help="Chroma 持久化目录")
    parser.add_argument("--model", default="BAAI/bge-small-zh-v1.5", help="Embedding 模型")
    parser.add_argument("--collection", default="uestc_bbs", help="集合名")
    parser.add_argument("--batch", type=int, default=64, help="模型推理批量大小")
    parser.add_argument("--upsert-batch", type=int, default=500, help="入库批量大小")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 条（0=全部）")
    args = parser.parse_args()

    # 读取分块
    print(f"读取分块: {args.input}")
    records = []
    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
            if args.limit and len(records) >= args.limit:
                break
    print(f"共 {len(records)} 个块待向量化")

    # 加载模型（首次会自动下载约 100MB）
    print(f"加载模型: {args.model}")
    model = SentenceTransformer(args.model)
    print("模型加载完成")

    # 打开向量库
    client = chromadb.PersistentClient(path=args.db)
    try:
        collection = client.get_collection(
            name=args.collection,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"已存在集合，当前 {collection.count()} 条，将增量 upsert")
    except Exception:
        collection = client.create_collection(
            name=args.collection,
            metadata={"hnsw:space": "cosine"},
        )
        print("创建新集合")

    # 分批向量化 + 入库
    total = len(records)
    done = 0
    startTime = time.time()
    batchBuf = []

    def flush(buf):
        if not buf:
            return
        texts = [r["text"] for r in buf]
        embeddings = model.encode(
            texts,
            batch_size=args.batch,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        collection.upsert(
            ids=[r["chunk_id"] for r in buf],
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=[
                {
                    "tid": r["tid"],
                    "title": r["title"][:500],
                    "board_name": r["board_name"],
                    "source": r["source"],
                    "create_time": r["create_time"] or "",
                    "chunk_index": r["chunk_index"],
                }
                for r in buf
            ],
        )

    for record in records:
        batchBuf.append(record)
        if len(batchBuf) >= args.upsert_batch:
            flush(batchBuf)
            done += len(batchBuf)
            batchBuf = []
            elapsed = time.time() - startTime
            speed = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / speed if speed > 0 else 0
            print(f"进度: {done}/{total} ({done * 100 // total}%) "
                  f"速度 {speed:.0f} 条/秒 预计剩余 {eta / 60:.1f} 分钟")

    flush(batchBuf)
    done += len(batchBuf)

    elapsed = time.time() - startTime
    print(f"完成！共入库 {done} 条，耗时 {elapsed / 60:.1f} 分钟")
    print(f"向量库: {args.db}，集合: {args.collection}，总数: {collection.count()}")


if __name__ == "__main__":
    main()
