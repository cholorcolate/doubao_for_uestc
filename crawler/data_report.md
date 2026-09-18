# 清水河畔论坛爬取数据报告

> 爬取时间：2026-09-18 04:21:59
> 数据目录：`C:\soft\opencode_download\uestc-public-20260918`

## 一、数据概览

| 指标 | 数量 |
|------|------|
| 板块数 | 29 |
| 索引文件 | 24 个（每个板块一个） |
| 主题总数 | 13,947 |
| 成功抓取 | 13,943 |
| 失败 | 4 |
| 数据大小 | 52.64 MB |

## 二、失败主题

以下4个主题抓取失败（已删除或需登录）：

| 主题ID | 原因 |
|--------|------|
| 2489471 | 主题不存在/已删除/审核中 |
| 2490488 | 主题不存在/已删除/审核中 |
| 2490492 | 主题不存在/已删除/审核中 |
| 2490479 | 主题不存在/已删除/审核中 |

## 三、数据结构

```
uestc-public-20260918/
├── boards/                    # 板块信息（本次为空，沿用旧数据）
├── threads/                   # 主题索引（24个文件）
│   ├── threads_17.json        # 同城同乡
│   ├── threads_20.json        # 学术交流
│   ├── threads_25.json        # 水手之家
│   ├── threads_45.json        # 情感专区
│   ├── threads_61.json        # 二手专区
│   ├── threads_66.json        # 电子数码
│   ├── threads_70.json        # 程序员之家
│   ├── threads_95.json        # 科技学术
│   ├── threads_111.json       # 店铺专区
│   ├── threads_121.json       # IC电设
│   ├── threads_174.json       # 就业创业
│   ├── threads_199.json       # 保研考研
│   ├── threads_201.json       # 生活信息
│   ├── threads_225.json       # 交通出行
│   ├── threads_236.json       # 校园热点
│   ├── threads_237.json       # 毕业感言
│   ├── threads_255.json       # 房屋租赁
│   ├── threads_305.json       # 失物招领
│   ├── threads_309.json       # 成电锐评
│   ├── threads_316.json       # 自然科学
│   ├── threads_326.json       # 新生专区
│   ├── threads_370.json       # 吃喝玩乐
│   ├── threads_382.json       # 考试专区
│   └── threads_391.json       # 拼车同行
├── posts/                     # 主题正文（13,943个文件）
│   ├── thread_*.json          # 每个主题一个JSON文件
│   └── _run_report.json       # 运行报告
└── users/                     # 用户信息（未爬取）
```

## 四、JSON格式示例

### 主题索引（threads_*.json）
```json
[
  {
    "tid": "2481677",
    "title": "请问博士三组团如何连接移动宽带呢",
    "url": "https://bbs.uestc.edu.cn/forum.php?mod=viewthread&tid=2481677",
    "author": "用户名",
    "replies": 3,
    "views": 370,
    "fid": "403"
  }
]
```

### 主题正文（thread_*.json）
```json
{
  "tid": "2481677",
  "title": "请问博士三组团如何连接移动宽带呢",
  "posts": [
    {
      "post_id": "41904496",
      "author": "xxzzcc",
      "time": "发表于 2026-8-27 14:41:35",
      "content": "帖子内容...",
      "floor": ""
    }
  ],
  "total_posts": 4,
  "complete": true,
  "pages_fetched": 1,
  "crawled_at": "2026-09-17T23:23:34"
}
```

## 五、未爬取内容

| 类型 | 说明 |
|------|------|
| 板块后续页面 | 每板块只抓前5页索引，大量历史主题未索引 |
| 用户资料 | users目录为空 |
| 附件/图片 | 只抓文字，未下载附件 |
| 登录后内容 | 仅匿名可访问的内容 |
| 水滴付费内容 | 未发现需要水滴才能访问的帖子 |

## 六、使用说明

1. 数据仅供学习研究使用
2. 遵守论坛robots.txt规则
3. 控制抓取频率，避免对服务器造成压力
4. 请勿爬取敏感或私密信息

## 七、运行命令

```bash
# 安装依赖
pip install -r requirements.txt

# 匿名抓取
python uestc_bbs_crawler.py --no-login

# 登录抓取
export BBS_USER="用户名"
export BBS_PASS="密码"
export BBS_MODE="6"  # 重抓全部主题
python uestc_bbs_crawler.py --data-dir ./data --interval 1.0
```
