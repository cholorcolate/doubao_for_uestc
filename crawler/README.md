# 清水河畔论坛爬虫

这是一个用于爬取电子科技大学清水河畔论坛（https://bbs.uestc.edu.cn）的Python爬虫。

## 功能

- 登录论坛（支持需要登录才能访问的内容）
- 爬取所有板块信息
- 爬取板块下的帖子列表
- 爬取帖子的完整内容（包括回复）
- 数据保存为JSON格式

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. 基本使用

```bash
pythonuestc_bbs_crawler.py
```

程序会提示输入密码，然后选择爬取模式。

### 2. 爬取模式

- **模式1**: 爬取所有板块和帖子（耗时较长）
- **模式2**: 爬取指定板块（需要提供板块ID）
- **模式3**: 爬取指定帖子（需要提供帖子ID）
- **模式4**: 只爬取板块列表

### 3. 数据结构

爬取的数据保存在 `data` 目录下：

```
data/
├── boards/              # 板块信息
│   ├── board_45.json
│   ├── board_61.json
│   └── ...
├── threads/             # 帖子列表
│   ├── threads_45.json
│   └── ...
├── posts/               # 帖子内容
│   ├── thread_123456.json
│   └── ...
└── boards_list.json     # 所有板块列表
```

### 4. JSON格式示例

#### 板块信息 (board_45.json)
```json
{
  "fid": "45",
  "name": "情感专区",
  "url": "https://bbs.uestc.edu.cn/forum.php?mod=forumdisplay&fid=45"
}
```

#### 帖子列表 (threads_45.json)
```json
[
  {
    "tid": "123456",
    "title": "帖子标题",
    "url": "https://bbs.uestc.edu.cn/forum.php?mod=viewthread&tid=123456",
    "author": "用户名",
    "replies": 10,
    "views": 100,
    "fid": "45"
  }
]
```

#### 帖子内容 (thread_123456.json)
```json
{
  "tid": "123456",
  "title": "帖子标题",
  "posts": [
    {
      "post_id": "789",
      "author": "用户名",
      "time": "2024-1-1 12:00",
      "content": "帖子内容...",
      "floor": "楼主"
    }
  ],
  "total_posts": 1
}
```

## 注意事项

1. 请合理使用爬虫，避免对服务器造成过大压力
2. 爬取间隔建议设置为0.5-1秒
3. 遵守论坛的robots.txt规则
4. 请勿爬取敏感或私密信息
5. 建议在本地网络环境下使用

## 常见问题

### Q: 登录失败怎么办？
A: 请检查用户名和密码是否正确。如果论坛启用了验证码，可能需要手动处理。

### Q: 爬取速度太慢？
A: 可以减少 `time.sleep()` 的值，但建议不要低于0.3秒，以免给服务器造成压力。

### Q: 如何爬取特定板块？
A: 使用模式2，输入板块ID。可以在论坛页面的URL中找到板块ID（fid参数）。

### Q: 数据保存在哪里？
A: 默认保存在程序运行目录下的 `data` 文件夹中。

## 免责声明

本爬虫仅供学习和研究使用，请遵守相关法律法规和网站使用条款。使用本爬虫造成的一切后果由用户自行承担。
