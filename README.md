# douyin-hot-search-archive：抖音热搜每日存档

抖音热搜榜只显示“现在”，过了就没了。这个仓库每天自动抓一次抖音热搜，按天存成 CSV，攒成一份**可以回看、可以统计的热搜历史**。
也能顺手存微博热搜、B站热门、小红书热点。

- 一个 Python 文件，只用标准库；
- 用 GitHub Actions 定时跑，不用自己开服务器；
- 不用抖音账号、不用 Cookie、不跑浏览器；
- 每抓一次 $0.002，一天一次一年不到 $1。

## 存下来的样子

```
data/douyin/
├── latest.md                 # 最近一次的榜单，Markdown 表格，带链接
└── 2026/11/2026-11-12.csv    # 按北京时间分天；一天跑多次就往同一个文件追加
```

CSV 的列：`fetched_at`（抓取时间，UTC）、`rank`、`name`（话题）、`heat`（热度）、`url`。

## 三步跑起来（GitHub Actions）

1. 点右上角 **Fork**（或 Use this template）复制到自己账号下。
2. 在 [okdata](https://okdata.online/zh/signup/?src=gh-douyin-hot-search-archive) 注册拿一个 key，
   到你仓库的 **Settings → Secrets and variables → Actions → New repository secret**，名字填 `OKDATA_API_KEY`。
3. 到 **Actions** 页面启用工作流，点 **archive → Run workflow** 先手动跑一次。之后每天北京时间 9:07 自动跑。

想多存几个榜：在 **Settings → Secrets and variables → Actions → Variables** 新建 `BOARDS`，值写
`douyin weibo bilibili`（空格分隔）。想一天多抓几次：改 `.github/workflows/archive.yml` 里的 `cron`。

没有设置 `OKDATA_API_KEY` 时，工作流会直接跳过，不会报错。

## 在本地跑

```bash
git clone https://github.com/okdataapi/douyin-hot-search-archive
cd douyin-hot-search-archive
export OKDATA_API_KEY=okd_...      # 不要写进代码或提交到仓库
python3 archive.py                 # 抖音
python3 archive.py --board weibo   # 微博热搜；还有 bilibili、xiaohongshu
```

## 花多少钱

| 榜单 | 接口 | 每次 |
|---|---|---|
| 抖音热搜 | [`douyin.trends.list`](https://okdata.online/zh/apis/douyin/trends/list/) | $0.002 |
| 微博热搜 | [`weibo.trends.list`](https://okdata.online/zh/apis/weibo/trends/list/) | $0.002 |
| B站热门 | [`bilibili.trends.list`](https://okdata.online/zh/apis/bilibili/trends/list/) | $0.002 |
| 小红书热点 | [`xiaohongshu.trends.list`](https://okdata.online/zh/apis/xiaohongshu/trends/list/) | $0.02 |

每天抓一次抖音：一个月约 $0.06。每小时抓一次：一个月约 $1.44。失败不扣钱。价格以
[prices.json](https://github.com/okdataapi/okdata/blob/main/docs/prices.json) 为准。

## 说明

- 这是 [okdata](https://okdata.online/zh/) 的示例项目，不是抖音或字节跳动的官方项目。脚本只调用 okdata 的接口，本身没有爬虫。
- 只看一眼现在的热搜，不想存档：[okdata.online/zh/tools/hot-search](https://okdata.online/zh/tools/hot-search/)。
- 在 AI 里直接问热搜（Claude Code、Cursor 等）：接 okdata 的远程 MCP `https://api.okdata.online/mcp`，或装
  [okdataapi/skills](https://github.com/okdataapi/skills) 里的 `okdata-trends`。
- 测试：`python3 -m unittest discover -s tests`（本地模拟服务器，不联网、不花钱）。
- 问题和建议请提 issue。MIT 许可证。

---

## English

Archive the Douyin hot search board every day into CSV files (one per Beijing-time day), with a GitHub Action, so
you build your own searchable history. Also works for the Weibo hot search, the Bilibili popular board and
Xiaohongshu hot topics. One Python 3.9+ file, standard library only, no Douyin account or cookies. Each snapshot
costs $0.002 (Xiaohongshu $0.02); failed calls are free.

Fork the repo, add an `OKDATA_API_KEY` secret ([sign up](https://okdata.online/signup/?src=gh-douyin-hot-search-archive)),
enable Actions. Unofficial. MIT licence.
