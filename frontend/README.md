# 成电智答 · 前端

电子科技大学校园问答智能体「成电智答」的 Web 前端。纯静态、无构建步骤、无第三方运行时依赖，
clone 下来用任意静态服务器就能跑。

前端与后端**完全解耦**：不引用任何后端源码，只通过 6 个 HTTP 接口通信，接口契约见下文。

---

## 快速开始

```bash
# 任意静态服务器都行，不要直接双击 index.html（file:// 下 fetch 会被 CORS 拦）
python -m http.server 5500
# 或 npx serve .
```

打开 <http://127.0.0.1:5500>。

此时页面会去连 `http://127.0.0.1:8000` 的后端。没起后端也能打开页面，但数据区会显示连接失败——
这是预期行为，前端不内置假数据。

---

## 目录结构

```
frontend/
├── index.html          # 结构（154 行，无内联样式/脚本）
├── config.js           # 运行时配置：后端地址
└── assets/
    ├── style.css       # 全部样式，CSS 变量集中在 :root
    └── app.js          # 全部交互逻辑，单个 IIFE，无依赖
```

刻意不引入打包工具：这个前端的体积和复杂度不值得为它配一套 node_modules，
改完直接刷新就能看到效果，也方便别人 fork 后立刻上手。

---

## 后端地址配置

三层优先级，**从高到低**：

| 优先级 | 方式 | 用途 |
|---|---|---|
| 1 | URL 参数 `?api=http://host:port` | 临时切换，会写入 localStorage |
| 2 | 页面「我的 → 后端连接」 | 图形化修改，同样写入 localStorage |
| 3 | `config.js` 里的 `apiBase` | 部署时的默认值 |

```js
// config.js
window.ZD_CONFIG = {
  apiBase: "http://127.0.0.1:8000"
};
```

**关于混合内容**：页面若以 https 部署（GitHub Pages），浏览器只允许直连 http 的
`localhost` / `127.0.0.1`。指向其他 http 主机会被当作混合内容拦截，需要给后端套
https 隧道（cloudflared / ngrok / frp）。这是浏览器行为，前端无法绕过。

---

## 接口契约

所有接口都在同一个 `API_BASE` 下，路径以 `/api` 开头，请求与响应均为 UTF-8 编码的 JSON。

- 后端已开启 `CORS: allow_origins=["*"]`，跨域请求无需额外配置。
- 前端只判断 HTTP 状态码 2xx，**不解析后端的错误响应体**（后端出错时统一返回降级数据而非 4xx）。
- 字段命名不统一：问答来源用 `board_name` / `create_time`（snake_case），
  信息流与工具条目用 `board` / `time`（短名），问答来源的排序分又是 `rerankScore`（camelCase）。
  这是历史原因，前端按各接口的实际字段名取值，**改动前务必对照本文档**。

---

### 1. 健康检查

```
GET /api/health
```

用于「我的 → 后端连接」面板的状态显示。页面加载时会自动调用一次。

```json
{
  "status": "ok",
  "llm": true,
  "llm_error": null,
  "count": 562383,
  "fts": true
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | 固定 `"ok"` |
| `llm` | bool | 是否配置了生成模型用的 API Key |
| `llm_error` | string \| null | 最近一次生成失败的原因，`null` 表示本次进程内还没失败过 |
| `count` | int | 向量库条目数 |
| `fts` | bool | 全文索引是否可用 |

> 注意 `llm: true` 只代表配了 Key，**不代表 Key 有效**。真正的失败要等一次问答后
> `llm_error` 才会有值。

---

### 2. 智能问答

```
POST /api/chat
Content-Type: application/json
```

请求体：

```json
{
  "question": "保研成绩怎么算？",
  "board": "保研考研",
  "time_range": "1y"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `question` | string | 是 | 用户问题，后端会 `strip()`，空串返回提示语 |
| `board` | string \| null | 否 | 板块名，取值来自 `/api/boards`；`null` 表示全部板块 |
| `time_range` | string \| null | 否 | `1m` / `3m` / `1y` / `3y`，分别对应 30 / 90 / 365 / 1095 天；`null` 或 `all` 表示不限 |

响应：

```json
{
  "answer": "保研综合成绩一般由学业成绩与综合素质测评构成 [1]...",
  "source": "保研考研 · 关于2027届推免工作的说明",
  "sources": [
    {
      "title": "关于2027届推免工作的说明",
      "board_name": "保研考研",
      "source": "https://bbs.uestc.edu.cn/forum.php?mod=viewthread&tid=2500001",
      "create_time": "2026-10-20T09:12:33",
      "similarity": 0.8123,
      "rerankScore": 0.9312
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `answer` | 回答正文。是 **Markdown 格式的纯文本**（可能含 `##`、`**`、`-` 列表），当前前端按 `white-space: pre-wrap` 原样展示，**不做渲染** |
| `source` | 首要来源的「板块 · 标题」，仅用于显示一行来源 |
| `sources` | 全部引用来源，最多 5 条，供「全部来源」折叠面板与收藏使用 |
| `sources[].source` | 原文链接（论坛帖为 `bbs.uestc.edu.cn`） |
| `sources[].similarity` | 向量检索相似度，不是 Rerank 分，未启用精排时可能为 `null` |
| `sources[].rerankScore` | 精排分数，未启用精排时为 `null` |

**降级行为**（后端不报错，靠 `answer` 内容区分）：

- 检索无结果：`answer` 为「根据现有资料未找到相关内容…」，`source` 固定 `"知识库未收录"`，`sources: []`
- 大模型不可用：`answer` 为「大模型生成不可用（账户余额不足 / 未配置 API Key / 服务暂时不可用），
  以下是检索到的原文：」+ 前两条检索原文，`sources` 仍正常返回

单次请求后端可能耗时数秒到数十秒（检索 + 生成），前端没有设超时，浏览器默认超时较长，
测试时请耐心等待。

---

### 3. 板块列表

```
GET /api/boards
```

填充问答区的「全部板块」下拉框。

```json
{
  "boards": [
    { "name": "保研考研", "count": 18342 },
    { "name": "选课交流", "count": 9021 }
  ]
}
```

按帖子数降序，后端缓存 5 分钟。

---

### 4. 信息流分类

```
GET /api/feed/categories
```

```json
{
  "categories": [
    { "id": "notice",  "name": "通知公告" },
    { "id": "lecture", "name": "讲座" },
    { "id": "contest", "name": "竞赛" },
    { "id": "job",     "name": "招聘" }
  ]
}
```

分类固定为这四个，前端不硬编码，一律以本接口返回为准。

---

### 5. 信息流列表（分页）

```
GET /api/feed?category=notice&page=1&size=15
```

| 参数 | 类型 | 说明 |
|---|---|---|
| `category` | string | 分类 id，来自上一个接口；不传则返回全库 |
| `board` | string | 按板块名过滤，用于「订阅」页拉某板块的最新帖；与 `category` 可同时使用 |
| `page` | int | 从 1 开始，默认 1 |
| `size` | int | 每页条数，默认 20，上限 50 |

响应：

```json
{
  "items": [
    {
      "tid": "2500001",
      "title": "关于2026-2027-1学期体质健康测试相关安排的通知",
      "board": "部门直通车",
      "site": "清水河畔",
      "url": "https://bbs.uestc.edu.cn/forum.php?mod=viewthread&tid=2500001",
      "time": "2026-10-27",
      "snippet": "各学院：现将本学期体质健康测试安排通知如下……"
    }
  ],
  "total": 2022,
  "page": 1,
  "size": 15
}
```

| 字段 | 说明 |
|---|---|
| `tid` | 帖子 ID（字符串，避免大整数精度问题） |
| `board` | 板块名，可能为空串 |
| `site` | 来源站点名，用于跳转展示 |
| `time` | `YYYY-MM-DD`，已截断到日期 |
| `snippet` | 纯文本摘要，最多 150 字，换行已替换为空格 |

`total` 是该分类/板块下的**去重帖子总数**，前端用它算总页数。
分类未知时返回 `{"items": [], "total": 0, "page": 1, "size": 20, "error": "未知分类"}`。

---

### 6. 校园工具

```
GET /api/tools
```

```json
{
  "tools": [
    { "id": "calendar", "name": "校历",      "desc": "教学周、考试周与假期安排" },
    { "id": "shuttle",  "name": "班车时刻",   "desc": "清水河 ↔ 沙河校区通勤班车" },
    { "id": "courses",  "name": "课表考试",   "desc": "选课、课表查询与考试安排" },
    { "id": "venues",   "name": "场馆预约",   "desc": "体育馆、游泳馆等场馆预约" },
    { "id": "library",  "name": "图书馆教室", "desc": "开放时间、自习与教室信息" }
  ]
}
```

```
GET /api/tools/{toolId}?topK=8
```

| 参数 | 说明 |
|---|---|
| `toolId` | 工具 id |
| `q` | 可选，覆盖该工具预置的检索词 |
| `topK` | 返回条数，默认 8 |

```json
{
  "tool": "shuttle",
  "name": "班车时刻",
  "query": "清水河 沙河 班车 时刻表 发车",
  "ask": "清水河到沙河班车时刻",
  "items": [
    {
      "title": "班车时刻表（2026年秋季）",
      "board": "部门直通车",
      "url": "https://bbs.uestc.edu.cn/forum.php?mod=viewthread&tid=2499880",
      "time": "2026-09-01",
      "snippet": "工作日 7:00-21:00 每小时一班……"
    }
  ]
}
```

`ask` 是为「去问答深挖」按钮准备的推荐问句，点击后直接带进问答区。
未知工具返回 `{"error": "未知工具: xxx", "items": []}`，前端会把 `error` 原样显示。

---

## 页面与接口的对应关系

| 页面 | 调用的接口 | 触发时机 |
|---|---|---|
| 智能问答 | `GET /api/boards` | 页面加载一次，填板块下拉 |
| | `POST /api/chat` | 点击发送 / 回车 / 快捷问题 |
| 信息聚合 | `GET /api/feed/categories` → `GET /api/feed` | 首次切到该页 |
| 校园工具 | `GET /api/tools` → `GET /api/tools/{id}` | 首次切到该页 / 点击工具卡片 |
| 我的 | `GET /api/health` | 页面加载 + 点「保存并重连」 |
| | `GET /api/boards`、`GET /api/feed?board=` | 切到「订阅」页签 |

### 本地存储

前端不依赖登录，所有个人数据都在 `localStorage`：

| Key | 内容 |
|---|---|
| `zd_favorites` | 收藏列表，元素为 `{title, url, board, time, ts}` |
| `zd_subscriptions` | 订阅的板块名数组 |
| `zd_api_base` | 用户改过的后端地址 |

清空浏览器数据会丢失收藏与订阅，这是设计取舍（无需账户体系）。

---

## 前后端分离的边界

- 前端**不包含**任何知识库数据、爬虫脚本、模型调用逻辑，这些全在后端。
- 后端**不包含**任何页面模板，只返回 JSON。唯一例外是 `StaticFiles` 把 `frontend/`
  挂到 `/`，那是为了方便本地一体化调试；用 GitHub Pages 部署时完全不经过后端。
- 想换一个后端？改 `config.js` 一行即可，只要新后端满足上表契约。
- 想换一个前端？后端所有接口都是无状态的 REST，换框架重写不影响后端。

---

## 已知限制

以下是当前实现的真实短板，欢迎修：

1. **`answer` 不渲染 Markdown**。模型返回 `## 标题`、`**加粗**`，页面上就是字面的井号和星号。
   需要引入一个轻量渲染器（或自己写个够用的），并注意 XSS——`answer` 目前是整体 `escape` 后
   放进 `textContent` 的。
2. **后端不可用时伪装成「知识库未收录」**。`send()` 的 `catch` 会走 `localReply()`，
   返回硬编码的示例回答，用户无法区分是网络故障还是真的没资料。
3. **并发提问会乱序**。多个请求各自 `appendChild`，先返回的答案会插在上面；
   同时 `typingMsg` 这个 id 被重复分配，打字动画会错位到别的气泡。
4. **「下一页」没有上界**。`feedState.page++` 不检查 `total`，快速点击会翻到不存在的页码。
5. **信息流首次加载失败不会重试**。`feedLoaded` 在 fetch 之前就置为 `true`，
   失败后切走再切回不会重新拉取，只能刷新页面。

---

## 参与开发

- 不需要装依赖、不需要构建，改完刷新即可。
- 提交前请确认页面在 1280px 和 375px 两个宽度下都正常（有 `@media (max-width:768px)` 断点）。
- 样式集中在 `assets/style.css` 顶部 `:root` 的 CSS 变量里，改配色优先改变量，别散落硬编码色值。
- 交互逻辑都在 `assets/app.js` 的单个 IIFE 内，没有模块系统，新增功能请沿用现有风格
  （`$()` 取元素、`esc()` 转义、事件委托绑定）。

---

## 许可

与主仓库一致，仅供学习和研究使用。数据来源为电子科技大学清水河畔论坛及校内公开信息源，
使用时请遵守相关站点的服务条款。
