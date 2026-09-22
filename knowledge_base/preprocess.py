"""
清水河畔论坛数据预处理脚本

功能：
1. 加载原始爬取数据
2. 清洗文本（去除HTML实体、表情符号、无意义内容）
3. 构建知识单元（主题+回复）
4. 去重与过滤
5. 输出处理后的JSON数据

使用方法：
    python preprocess.py --input ../uestc-public-full/posts --output ./processed
"""

import os
import re
import json
import html
import argparse
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict


# ============ 文本清洗 ============

def clean_html_entities(text: str) -> str:
    """清理HTML实体"""
    if not text:
        return ""
    # 解码HTML实体
    text = html.unescape(text)
    # 清理残留的HTML标签
    text = re.sub(r'<[^>]+>', '', text)
    return text


def clean_emoji(text: str) -> str:
    """清理表情符号和特殊标记"""
    if not text:
        return ""
    # 移除Discuz表情标记 [xxx] 格式
    text = re.sub(r'\[.*?\]', '', text)
    # 移除自定义表情标记
    text = re.sub(r'\(s\)|\(w\)|\(h\)|\(g\)|\(k\)', '', text)
    # 移除图片附件标记
    text = re.sub(r'\d+\.(jpg|png|gif|jpeg)\(.*?\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'下载附件保存到相册.*?上传', '', text)
    return text


def clean_whitespace(text: str) -> str:
    """清理空白字符"""
    if not text:
        return ""
    # 合并多个空格
    text = re.sub(r'\s+', ' ', text)
    # 去除首尾空白
    text = text.strip()
    return text


def clean_time_prefix(text: str) -> str:
    """清理时间前缀（如"发表于昨天 00:01"）"""
    if not text:
        return ""
    text = re.sub(r'^发表于\s*.*?\s+', '', text)
    return text


def clean_quote(text: str) -> str:
    """清理引用内容"""
    if not text:
        return ""
    # 移除引用块
    text = re.sub(r'引用\s*.*?发表于.*?\n.*?\n', '', text, flags=re.DOTALL)
    # 移除简单的引用标记
    text = re.sub(r'^>.*$', '', text, flags=re.MULTILINE)
    return text


def clean_text(text: str) -> str:
    """综合文本清洗"""
    if not text:
        return ""
    text = clean_html_entities(text)
    text = clean_emoji(text)
    text = clean_quote(text)
    text = clean_time_prefix(text)
    text = clean_whitespace(text)
    return text


# ============ 内容过滤 ============

# 无意义内容的关键词
MEANINGLESS_PATTERNS = [
    r'^我是来.*水滴',
    r'^获取水滴',
    r'^水滴.*',
    r'^顶$',
    r'^沙发$',
    r'^板凳$',
    r'^马克$',
    r'^mark$',
    r'^帮顶$',
    r'^学习了$',
    r'^感谢分享$',
    r'^谢谢$',
    r'^thank',
    r'^gg$',
    r'^mm$',
]


def is_meaningful(text: str) -> bool:
    """判断内容是否有意义"""
    if not text or len(text.strip()) < 5:
        return False
    text_lower = text.strip().lower()
    for pattern in MEANINGLESS_PATTERNS:
        if re.match(pattern, text_lower):
            return False
    return True


def should_skip_thread(thread_data: dict) -> bool:
    """判断是否应该跳过该主题"""
    title = thread_data.get("title", "")
    posts = thread_data.get("posts", [])

    # 跳过空主题
    if not posts:
        return True

    # 跳过标题包含特定关键词的主题
    skip_keywords = ["水滴", "签到", "每日打卡"]
    for keyword in skip_keywords:
        if keyword in title and len(posts) <= 2:
            return True

    return False


# ============ 时间解析 ============

def parse_time(time_str: str) -> Optional[str]:
    """解析各种时间格式，统一输出为ISO格式"""
    if not time_str:
        return None

    # 清理时间字符串
    time_str = time_str.strip()
    time_str = re.sub(r'^发表于\s*', '', time_str)

    # 处理相对时间
    if "昨天" in time_str:
        return "yesterday"
    if "今天" in time_str:
        return "today"
    if "天前" in time_str:
        match = re.search(r'(\d+)\s*天前', time_str)
        if match:
            return f"{match.group(1)}_days_ago"

    # 尝试解析标准格式
    patterns = [
        r'(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})',
        r'(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})',
        r'(\d{4})-(\d{1,2})-(\d{1,2})',
    ]

    for pattern in patterns:
        match = re.search(pattern, time_str)
        if match:
            groups = match.groups()
            if len(groups) == 6:
                return f"{groups[0]}-{groups[1].zfill(2)}-{groups[2].zfill(2)}T{groups[3].zfill(2)}:{groups[4].zfill(2)}:{groups[5].zfill(2)}"
            elif len(groups) == 5:
                return f"{groups[0]}-{groups[1].zfill(2)}-{groups[2].zfill(2)}T{groups[3].zfill(2)}:{groups[4].zfill(2)}:00"
            elif len(groups) == 3:
                return f"{groups[0]}-{groups[1].zfill(2)}-{groups[2].zfill(2)}T00:00:00"

    return time_str


# ============ 知识单元构建 ============

def build_knowledge_unit(thread_data: dict, board_info: dict = None) -> dict:
    """
    将一个主题构建成知识单元

    输入：原始thread_*.json数据
    输出：标准化的知识单元
    """
    tid = thread_data.get("tid", "")
    title = thread_data.get("title", "")
    posts = thread_data.get("posts", [])

    if not posts:
        return None

    # 清洗标题
    title = clean_text(title)

    # 处理所有回复
    cleaned_posts = []
    for post in posts:
        content = clean_text(post.get("content", ""))
        if not content or not is_meaningful(content):
            continue

        cleaned_post = {
            "post_id": post.get("post_id", ""),
            "author": post.get("author", "匿名"),
            "time": parse_time(post.get("time", "")),
            "content": content,
        }
        cleaned_posts.append(cleaned_post)

    # 过滤后没有有效内容
    if not cleaned_posts:
        return None

    # 构建完整文本（用于向量化）
    full_text = f"标题：{title}\n\n"
    full_text += "\n\n".join([p["content"] for p in cleaned_posts])

    # 构建知识单元
    knowledge_unit = {
        "id": tid,
        "title": title,
        "source": f"https://bbs.uestc.edu.cn/forum.php?mod=viewthread&tid={tid}",
        "board_id": board_info.get("fid", "") if board_info else "",
        "board_name": board_info.get("name", "") if board_info else "",
        "author": posts[0].get("author", "匿名") if posts else "匿名",
        "create_time": parse_time(posts[0].get("time", "")) if posts else None,
        "last_reply_time": parse_time(posts[-1].get("time", "")) if len(posts) > 1 else None,
        "reply_count": len(cleaned_posts) - 1,
        "view_count": thread_data.get("views", 0),
        "posts": cleaned_posts,
        "full_text": full_text,
        "processed_at": datetime.now().isoformat(timespec="seconds"),
    }

    return knowledge_unit


# ============ 主处理流程 ============

def load_board_list(threads_dir: str) -> Dict[str, dict]:
    """加载板块信息，建立fid到板块信息的映射"""
    board_map = {}

    # 尝试从threads文件名推断板块
    for filename in os.listdir(threads_dir):
        if filename.startswith("threads_") and filename.endswith(".json"):
            fid = filename.replace("threads_", "").replace(".json", "")
            board_map[fid] = {"fid": fid, "name": f"板块_{fid}"}

    return board_map


def process_thread_file(filepath: str, board_map: Dict[str, dict]) -> List[dict]:
    """处理单个主题文件"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            thread_data = json.load(f)

        # 获取板块信息
        fid = ""
        if "fid" in thread_data:
            fid = str(thread_data["fid"])
        elif "posts" in thread_data and thread_data["posts"]:
            # 从文件名推断
            filename = os.path.basename(filepath)
            if filename.startswith("thread_"):
                tid = filename.replace("thread_", "").replace(".json", "")
                # 需要从索引文件获取fid

        board_info = board_map.get(fid, {"fid": fid, "name": f"板块_{fid}"})

        # 构建知识单元
        knowledge_unit = build_knowledge_unit(thread_data, board_info)
        return [knowledge_unit] if knowledge_unit else []

    except Exception as e:
        print(f"处理文件失败 {filepath}: {e}")
        return []


def process_all(input_dir: str, output_dir: str, max_files: int = 0):
    """处理所有数据"""
    print(f"开始处理数据...")
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 加载板块信息
    board_map = load_board_list(input_dir)
    print(f"发现 {len(board_map)} 个板块")

    # 获取所有主题文件
    thread_files = [f for f in os.listdir(input_dir) if f.startswith("thread_") and f.endswith(".json")]
    total_files = len(thread_files)
    print(f"发现 {total_files} 个主题文件")

    if max_files > 0:
        thread_files = thread_files[:max_files]
        print(f"限制处理前 {max_files} 个文件")

    # 处理所有文件
    all_knowledge_units = []
    skipped = 0
    processed = 0

    for i, filename in enumerate(thread_files, 1):
        filepath = os.path.join(input_dir, filename)

        if i % 1000 == 0:
            print(f"进度: {i}/{len(thread_files)} ({i*100/len(thread_files):.1f}%)")

        try:
            knowledge_units = process_thread_file(filepath, board_map)
            if knowledge_units:
                all_knowledge_units.extend(knowledge_units)
                processed += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"处理失败 {filename}: {e}")
            skipped += 1

    print(f"\n处理完成!")
    print(f"成功处理: {processed} 个主题")
    print(f"跳过: {skipped} 个主题")
    print(f"生成知识单元: {len(all_knowledge_units)} 个")

    # 保存结果
    output_file = os.path.join(output_dir, "knowledge_units.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_knowledge_units, f, ensure_ascii=False, indent=2)
    print(f"保存到: {output_file}")

    # 生成统计信息
    stats = {
        "total_threads": total_files,
        "processed_threads": processed,
        "skipped_threads": skipped,
        "knowledge_units": len(all_knowledge_units),
        "boards": len(board_map),
        "processed_at": datetime.now().isoformat(timespec="seconds"),
    }
    stats_file = os.path.join(output_dir, "stats.json")
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"统计信息: {stats_file}")

    return all_knowledge_units


# ============ 命令行入口 ============

def main():
    parser = argparse.ArgumentParser(description="清水河畔论坛数据预处理")
    parser.add_argument("--input", required=True, help="原始数据目录（包含thread_*.json）")
    parser.add_argument("--output", default="./processed", help="输出目录")
    parser.add_argument("--max-files", type=int, default=0, help="最大处理文件数（0=全部）")
    args = parser.parse_args()

    process_all(args.input, args.output, args.max_files)


if __name__ == "__main__":
    main()
