"""
知识单元分块脚本

功能：
1. 读取预处理后的 knowledge_units.json
2. 将长文本按楼层与句子边界切成检索友好的块（chunk）
3. 每个块附带元数据（标题、板块、来源链接、时间等）
4. 输出 chunks.jsonl（每行一个 JSON 块）

使用方法：
    python chunk-data.py --input ./processed/knowledge_units.json --output ./processed/chunks.jsonl
"""

import argparse
import json
import os
import re
from typing import Dict, List

# 句子切分边界（中文与常见英文标点）
SENTENCE_SPLIT = re.compile(r'(?<=[。！？；!?;\n])')


def loadBoardMap(boardsPath: str) -> Dict[str, str]:
    """加载板块列表，建立 fid -> 板块名称 映射"""
    boardMap = {}
    if boardsPath and os.path.exists(boardsPath):
        with open(boardsPath, "r", encoding="utf-8") as f:
            boards = json.load(f)
        for board in boards:
            boardMap[str(board.get("fid", ""))] = board.get("name", "")
    return boardMap


def loadTidToFid(threadsDir: str) -> Dict[str, str]:
    """加载板块索引文件，建立 tid -> fid 映射"""
    tidToFid = {}
    if threadsDir and os.path.isdir(threadsDir):
        for filename in os.listdir(threadsDir):
            if not (filename.startswith("threads_") and filename.endswith(".json")):
                continue
            try:
                with open(os.path.join(threadsDir, filename), "r", encoding="utf-8") as f:
                    items = json.load(f)
                for item in items:
                    tid = str(item.get("tid", ""))
                    fid = str(item.get("fid", ""))
                    if tid and fid:
                        tidToFid[tid] = fid
            except Exception as e:
                print(f"读取索引失败 {filename}: {e}")
    return tidToFid


def splitLongText(text: str, maxChars: int, overlap: int) -> List[str]:
    """超长文本按句子边界切分，带重叠窗口"""
    if len(text) <= maxChars:
        return [text]

    pieces = []
    buffer = ""
    for sentence in SENTENCE_SPLIT.split(text):
        if not sentence:
            continue
        # 单句就超长：硬切
        if len(sentence) > maxChars:
            if buffer:
                pieces.append(buffer)
                buffer = ""
            start = 0
            while start < len(sentence):
                pieces.append(sentence[start:start + maxChars])
                start += maxChars - overlap
            continue
        if len(buffer) + len(sentence) > maxChars:
            pieces.append(buffer)
            tail = buffer[-overlap:] if overlap > 0 else ""
            buffer = tail + sentence
        else:
            buffer += sentence
    if buffer.strip():
        pieces.append(buffer)
    return [p.strip() for p in pieces if p.strip()]


def buildChunks(unit: Dict, maxChars: int, overlap: int, minChars: int) -> List[Dict]:
    """把一个知识单元切成若干块"""
    tid = unit.get("id", "")
    title = unit.get("title", "").strip()
    boardName = unit.get("board_name", "") or ""
    source = unit.get("source", "")
    createTime = unit.get("create_time") or ""

    # 组装段落：主楼与各楼层正文
    paragraphs = []
    for post in unit.get("posts", []):
        content = (post.get("content") or "").strip()
        if content:
            paragraphs.append(content)

    fullBody = "\n\n".join(paragraphs)
    if len(fullBody) < minChars and len(title) < minChars:
        return []

    # 正文按楼层累积成块
    rawChunks = []
    buffer = ""
    for para in paragraphs:
        candidate = (buffer + "\n\n" + para).strip() if buffer else para
        if len(candidate) <= maxChars:
            buffer = candidate
        else:
            if buffer:
                rawChunks.append(buffer)
            # 单个超长楼层再按句子切
            if len(para) > maxChars:
                for piece in splitLongText(para, maxChars, overlap):
                    rawChunks.append(piece)
                buffer = ""
            else:
                buffer = para
    if buffer.strip():
        rawChunks.append(buffer)

    # embedding 文本统一带标题前缀，增强语义
    chunks = []
    for idx, body in enumerate(rawChunks):
        embedText = f"{title}\n\n{body}" if title else body
        chunks.append({
            "chunk_id": f"{tid}_{idx}",
            "tid": tid,
            "chunk_index": idx,
            "title": title,
            "board_name": boardName,
            "board_id": unit.get("board_id", ""),
            "source": source,
            "create_time": createTime,
            "reply_count": unit.get("reply_count", 0),
            "text": embedText,
        })
    return chunks


def main():
    parser = argparse.ArgumentParser(description="知识单元分块")
    parser.add_argument("--input", required=True, help="knowledge_units.json 路径")
    parser.add_argument("--output", default="./processed/chunks.jsonl", help="输出 jsonl 路径")
    parser.add_argument("--boards", default="", help="boards_list.json 路径（可选，用于补板块名）")
    parser.add_argument("--threads", default="", help="threads 索引目录（可选，用于 tid -> fid 映射）")
    parser.add_argument("--max-chars", type=int, default=600, help="单块最大字符数")
    parser.add_argument("--overlap", type=int, default=60, help="切分重叠字符数")
    parser.add_argument("--min-chars", type=int, default=20, help="低于该长度的知识单元跳过")
    args = parser.parse_args()

    print(f"读取知识单元: {args.input}")
    with open(args.input, "r", encoding="utf-8") as f:
        units = json.load(f)
    print(f"共 {len(units)} 个知识单元")

    boardMap = loadBoardMap(args.boards)
    tidToFid = loadTidToFid(args.threads)
    print(f"板块映射 {len(boardMap)} 个，线程索引 {len(tidToFid)} 条")

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    totalChunks = 0
    skipped = 0
    with open(args.output, "w", encoding="utf-8") as out:
        for i, unit in enumerate(units, 1):
            # 补全板块信息：优先线程索引的 tid -> fid 映射
            fid = tidToFid.get(str(unit.get("id", "")), "") or str(unit.get("board_id", ""))
            boardName = unit.get("board_name", "") or ""
            if fid and (not boardName or boardName.startswith("板块_")):
                unit["board_name"] = boardMap.get(fid, f"板块_{fid}")
                unit["board_id"] = fid
            elif not fid and boardName and boardName.startswith("板块_"):
                unit["board_name"] = ""

            chunks = buildChunks(unit, args.max_chars, args.overlap, args.min_chars)
            if not chunks:
                skipped += 1
                continue
            for chunk in chunks:
                out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                totalChunks += 1

            if i % 20000 == 0:
                print(f"进度: {i}/{len(units)}，已生成 {totalChunks} 块")

    print(f"完成！共生成 {totalChunks} 个块，跳过 {skipped} 个单元")
    print(f"输出: {args.output}")


if __name__ == "__main__":
    main()
