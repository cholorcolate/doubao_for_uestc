"""
知识库检索测试脚本

功能：对 Chroma 向量库做语义检索，验证"AI 能懂"的效果

使用方法：
    python search.py --query "保研需要什么条件" --top-k 5
"""

import argparse
import os
import sys

# 输出容错：遇到控制台无法编码的字符时替换而不是崩溃
sys.stdout.reconfigure(errors="replace")
sys.stderr.reconfigure(errors="replace")

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import chromadb
from sentence_transformers import SentenceTransformer

# bge 中文检索官方建议的 query 前缀
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


def main():
    parser = argparse.ArgumentParser(description="知识库检索测试")
    parser.add_argument("--query", required=True, help="查询问题")
    parser.add_argument("--top-k", type=int, default=5, help="返回条数")
    parser.add_argument("--db", default="./chroma_db", help="Chroma 目录")
    parser.add_argument("--collection", default="uestc_bbs", help="集合名")
    parser.add_argument("--model", default="BAAI/bge-small-zh-v1.5", help="Embedding 模型")
    args = parser.parse_args()

    print(f"加载模型与向量库...")
    model = SentenceTransformer(args.model)
    client = chromadb.PersistentClient(path=args.db)
    collection = client.get_collection(args.collection)
    print(f"库中共 {collection.count()} 条\n")

    queryText = QUERY_PREFIX + args.query
    queryEmbedding = model.encode([queryText], normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=queryEmbedding,
        n_results=args.top_k,
        include=["documents", "metadatas", "distances"],
    )

    print(f"查询: {args.query}")
    print("=" * 60)
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        similarity = 1 - dist  # cosine 距离 -> 相似度
        print(f"\n[{i + 1}] 相似度 {similarity:.4f} | 板块: {meta.get('board_name', '')}")
        print(f"    标题: {meta.get('title', '')}")
        print(f"    链接: {meta.get('source', '')}")
        snippet = doc.replace("\n", " ")
        print(f"    内容: {snippet[:200]}{'...' if len(snippet) > 200 else ''}")


if __name__ == "__main__":
    main()
