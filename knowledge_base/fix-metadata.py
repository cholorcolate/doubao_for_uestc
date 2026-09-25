"""
板块元数据修复脚本

功能：
读取重新生成的 chunks.jsonl，把正确的板块名/板块 ID
更新到已有的 Chroma 向量库（不重新向量化，只更新 metadata）

使用方法：
    python fix-metadata.py --chunks ./processed/chunks.jsonl --db ./chroma_db
"""

import argparse
import json
import time

import chromadb


def main():
    parser = argparse.ArgumentParser(description="修复向量库板块元数据")
    parser.add_argument("--chunks", default="./processed/chunks.jsonl", help="新生成的分块文件")
    parser.add_argument("--db", default="./chroma_db", help="Chroma 目录")
    parser.add_argument("--collection", default="uestc_bbs", help="集合名")
    parser.add_argument("--batch", type=int, default=2000, help="每批更新条数")
    args = parser.parse_args()

    # 读取新分块的板块信息
    print("读取新分块...")
    boardInfo = {}
    with open(args.chunks, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            boardInfo[record["chunk_id"]] = (record["board_name"], record.get("board_id", ""))
    print(f"共 {len(boardInfo)} 个块的板块信息")

    client = chromadb.PersistentClient(path=args.db)
    collection = client.get_collection(args.collection)
    print(f"向量库现有 {collection.count()} 条")

    # 分批取出并更新
    startTime = time.time()
    offset = 0
    updated = 0
    while offset < collection.count():
        batch = collection.get(
            include=["metadatas"],
            limit=args.batch,
            offset=offset,
        )
        ids = batch["ids"]
        metadatas = []
        for cid, meta in zip(ids, batch["metadatas"]):
            newBoard = boardInfo.get(cid)
            if newBoard:
                meta = dict(meta)
                meta["board_name"] = newBoard[0]
                meta["board_id"] = newBoard[1]
            metadatas.append(meta)
        collection.update(ids=ids, metadatas=metadatas)
        updated += len(ids)
        offset += len(ids)
        elapsed = time.time() - startTime
        print(f"进度: {updated}/{collection.count()} 耗时 {elapsed / 60:.1f} 分钟")

    print(f"完成！共更新 {updated} 条")


if __name__ == "__main__":
    main()
