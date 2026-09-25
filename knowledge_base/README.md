# 清水河畔论坛知识库

> 基于爬取的论坛数据，构建供AI调用的知识库

## 项目结构

```
knowledge_base/
├── preprocess.py          # 数据预处理脚本
├── chunk-data.py          # 分块脚本（知识单元 -> 检索块）
├── embed-index.py         # 向量化并导入 Chroma
├── fix-metadata.py        # 修复向量库板块元数据
├── search.py              # 检索测试脚本
├── README.md              # 本文档
├── chroma_db/             # Chroma 向量库（558,379 条）
├── raw/                   # 原始数据（需手动放入）
└── processed/             # 处理后的数据
    ├── knowledge_units.json   # 知识单元数据
    ├── chunks.jsonl           # 检索块（每行一个 JSON）
    └── stats.json             # 统计信息
```

## 快速开始

### 1. 数据准备

将爬取的原始数据放到 `raw/` 目录，或者直接指定爬取数据的路径：

```bash
# 数据已下载到 C:\soft\opencode_download\uestc-public-full\posts
```

### 2. 运行预处理

```bash
# 处理全部数据（约20万个主题，需要较长时间）
python preprocess.py --input C:\soft\opencode_download\uestc-public-full\posts --output ./processed

# 只处理前1000个主题（用于测试）
python preprocess.py --input C:\soft\opencode_download\uestc-public-full\posts --output ./processed --max-files 1000
```

### 3. 查看结果

```bash
# 查看统计信息
cat processed/stats.json

# 查看知识单元示例
python -c "import json; data=json.load(open('processed/knowledge_units.json')); print(json.dumps(data[0], ensure_ascii=False, indent=2))"
```

## 数据格式

### 输入格式（原始爬取数据）

每个主题一个JSON文件 `thread_{tid}.json`：

```json
{
  "tid": "123456",
  "title": "帖子标题",
  "posts": [
    {
      "post_id": "789",
      "author": "用户名",
      "time": "发表于 2026-1-1 12:00:00",
      "content": "帖子内容...",
      "floor": ""
    }
  ],
  "total_posts": 10,
  "complete": true,
  "pages_fetched": 2
}
```

### 输出格式（知识单元）

处理后的知识单元 `knowledge_units.json`：

```json
{
  "id": "123456",
  "title": "帖子标题",
  "source": "https://bbs.uestc.edu.cn/forum.php?mod=viewthread&tid=123456",
  "board_id": "45",
  "board_name": "情感专区",
  "author": "用户名",
  "create_time": "2026-01-01T12:00:00",
  "last_reply_time": "2026-01-02T15:30:00",
  "reply_count": 9,
  "view_count": 100,
  "posts": [
    {
      "post_id": "789",
      "author": "用户名",
      "time": "2026-01-01T12:00:00",
      "content": "清洗后的内容..."
    }
  ],
  "full_text": "标题：帖子标题\n\n清洗后的内容1\n\n清洗后的内容2...",
  "processed_at": "2026-09-22T18:21:42"
}
```

## 预处理步骤

### 1. 文本清洗

- **HTML实体清理**：`&amp;` → `&`，`&lt;` → `<` 等
- **表情符号清理**：移除 `[xxx]` 格式的Discuz表情
- **引用内容清理**：移除引用块，保留原创内容
- **空白字符清理**：合并多个空格，去除首尾空白
- **时间前缀清理**：移除"发表于..."前缀

### 2. 内容过滤

**跳过的主题：**
- 空主题（无回复）
- 纯水帖（如"我是来获取水滴的"）
- 签到帖、打卡帖

**跳过的回复：**
- 内容长度 < 5字符
- 纯表情回复
- 无意义回复（如"顶"、"沙发"、"mark"）

### 3. 知识单元构建

- 合并同一主题的所有回复
- 保留元数据（作者、时间、板块等）
- 生成完整文本（用于向量化）
- 统一时间格式为ISO 8601

## 统计信息示例

```json
{
  "total_threads": 205439,
  "processed_threads": 198000,
  "skipped_threads": 7439,
  "knowledge_units": 198000,
  "boards": 29,
  "processed_at": "2026-09-22T18:21:42"
}
```

## 向量化与检索（已完成，2026-09-25）

全流程零成本：Embedding 使用本地模型 `BAAI/bge-small-zh-v1.5`，无需 API Key，向量库使用本地 Chroma。

### 完整流程

```bash
# 1. 预处理（25.5 万个知识单元）
python preprocess.py --input C:\soft\opencode_download\uestc-public-full\posts --output ./processed

# 2. 分块（558,379 个块，通过线程索引补全板块名）
#    boards_list_full.json = boards_list.json（29 个公开板块）
#                          + crawler/crawl_missing_boards.py 中的 15 个登录可见板块映射，共 44 个
python chunk-data.py --input ./processed/knowledge_units.json --output ./processed/chunks.jsonl --boards C:\soft\opencode_download\uestc-public-full\boards_list_full.json --threads C:\soft\opencode_download\uestc-public-full\threads

# 3. 向量化并入库（首次自动下载模型约 100MB，支持断点续传）
python embed-index.py --input ./processed/chunks.jsonl --db ./chroma_db

# 4. 仅修改了板块名等元数据时，用此脚本增量刷新向量库（不重新向量化）
python fix-metadata.py --chunks ./processed/chunks.jsonl --db ./chroma_db

# 5. 检索测试
python search.py --query "保研需要什么条件" --top-k 5
```

### 实际结果

- 知识单元：255,370 个（原始 257,345 主题）
- 检索块：558,379 个（单块最多 600 字，重叠 60 字）
- 向量库：Chroma 55.8 万条，磁盘约 5.4 GB
- 板块：39 个板块全部为真实名称，占位符 `板块_编号` 已清零（含 15 个需登录可见的板块）
- 每个块携带元数据：标题、板块名、来源链接、发帖时间，可做过滤检索
- 检索效果示例：查询"保研需要什么条件"命中《想问下保研都需要哪些条件》（相似度 0.72，板块：保研考研）

### 后续步骤

1. **生成**：接入 LLM（豆包/DeepSeek-V4）基于检索结果生成回答（RAG）
2. **混合检索**：叠加关键词检索（BM25）与元数据过滤提升准确率
3. **重排**：接入 Rerank 模型（如硅基流动 Qwen3-Reranker）精排

## 注意事项

1. **磁盘空间**：原始数据约800MB，处理后约500MB
2. **处理时间**：全部数据预处理约需30-60分钟
3. **内存需求**：建议至少4GB可用内存
4. **编码**：统一使用UTF-8编码

## 自定义配置

如需修改过滤规则或清洗逻辑，可编辑 `preprocess.py` 中的：

- `MEANINGLESS_PATTERNS`：无意义内容的正则模式
- `clean_text()`：文本清洗函数
- `is_meaningful()`：内容判断函数
- `should_skip_thread()`：主题跳过判断函数

## 免责声明

本知识库仅供学习和研究使用，数据来源于公开论坛。使用时请遵守相关法律法规和论坛规定。
