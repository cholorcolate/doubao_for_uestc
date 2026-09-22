# 清水河畔论坛知识库

> 基于爬取的论坛数据，构建供AI调用的知识库

## 项目结构

```
knowledge_base/
├── preprocess.py          # 数据预处理脚本
├── README.md              # 本文档
├── raw/                   # 原始数据（需手动放入）
└── processed/             # 处理后的数据
    ├── knowledge_units.json   # 知识单元数据
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

## 后续步骤

数据预处理完成后，可以进行：

1. **向量化**：使用豆包 doubao-embedding 将文本转为向量
2. **存储**：存入 Chroma/Milvus/VikingDB 向量数据库
3. **检索**：实现混合检索（向量+关键词+元数据）
4. **生成**：接入LLM（豆包/DeepSeek-V4）生成回答

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
