# 澳洲黑五 + 节礼日 2026 数据补抓 PRD（给数据采集 AI）

- 状态：草稿 v0.2，2026-10-31（v0.2 加入节礼日 Boxing Day）
- 仓库：`JadeSure/bargain-hunter`（**公开仓库**，别提交任何账号、cookie、个人信息）
- 读者：负责抓数据的 AI。你只交数据文件和一份覆盖报告，不改网页代码。

---

## 1. 背景

我们在 bargain-hunter 网站上有一个不公开的黑五分析页（不在导航和 sitemap 里），回答五个问题：

1. 往年黑五哪些东西真值得买、平均便宜多少？
2. 黑五是不是全年最便宜？
3. **节礼日（12/26 起）会不会比黑五更便宜？哪些东西该等节礼日？**
4. 今年（2026）每样东西大概什么价，到多少钱该下手？
5. 送礼（国内亲友、伴侣家人、同事 Secret Santa）买什么、什么时候买？

现在的数据只够做个样子：

| 问题 | 现状 |
|---|---|
| 样本量 | 43 条往年黑五价，其中 2025 年 26 条、2024 年 15 条、2023 年 2 条，2021–2022 年为 0 |
| 品类 | 家电厨房 18 条，数码 10 条，户外运动只有 2 条 |
| 来源 | 主要是媒体的“黑五好价”盘点，带选择偏差；Amazon 占 11 条 |
| 社区验证 | 没有票数，分不出“真好价”和“凑数价” |
| 价格历史 | 只有 15 个商品有非黑五价可比，没有连续的价格走势 |
| 2026 现价 | 25 个关注商品里只有 8 个有今年的价格 |
| 节礼日 | **0 条**，只有几句没出处的说法（Sonos、Lululemon、旧款 Dyson 吸尘器 12 月更低） |

你的任务：**从多个独立来源补数据**，让上面每个问题都有足够的样本和出处。

---

## 2. 交付物

全部放在 `data/bf2026/` 下面（这个目录和校验脚本由我们先建好，你在它合并到 main 之后开工）：

```
data/bf2026/
  points/<来源>.json     # 你写：价格点，每个来源一个文件，例如 ozbargain.json、wayback.json
  promos/<来源>.json     # 你写：全场活动 / 返现加码 / 礼品卡折扣
  calendar.json          # 可改：把“按往年推测”的行改成“已确认”，必须附官方来源
  rules.json             # 可改：把“未核实”的寄回国规则补上官方出处
  watch.json             # 不要改（编辑判断由人做），建议写进覆盖报告
  check.py               # 不要改；交付前必须跑通
```

每个来源一个文件，几个 AI 可以同时干活，不会冲突。

另外在 PR 描述里写**覆盖报告**（见第 7 节）。

---

## 3. 数据格式

### 3.1 价格点 `points/<来源>.json`

一个 JSON 数组，每一行是“某天、某个商家、某个商品、某个价格”的一次观测。

| 字段 | 类型 | 规则 |
|---|---|---|
| `id` | string | 全局唯一，前缀是来源：`ozb-980008`、`wb-dyson-supersonic-20241129`、`ccc-B0CXXXX-20251128` |
| `key` | string | 商品键，小写 kebab，`品牌-型号`。已有的键优先复用（见 `watch.json` 和 `points/curated.json`）。只是颜色不同用同一个键；不同代、不同套装用不同的键 |
| `item` | string | 给人看的商品名 |
| `model` | string \| null | 型号或 SKU，有就填 |
| `category` | enum | `数码电子` `家电厨房` `美妆个护` `户外运动` `保健食品` `礼品` `其他` |
| `retailer` | string | 商家名，和已有写法保持一致（`Amazon AU`、`JB Hi-Fi`、`Chemist Warehouse`…） |
| `date` | string | 价格生效日期 `YYYY-MM-DD`；只能确定月份时写 `YYYY-MM` |
| `event` | enum | `黑五季` `Click Frenzy` `Prime Day` `EOFY` `双11` `节礼日` `平日` `其他促销` |
| `price` | number | 澳元含 GST，普通人结账就能拿到的价。公开优惠码算进去；**返现、礼品卡叠加不算** |
| `was_price` | number \| null | 商家标的原价 / RRP |
| `was_suspect` | boolean | 原价可疑：只在黑五前两周出现、预购价、套装价、明显高于平时售价 |
| `conditions` | string | 没限制填 `""`；否则写清楚：`仅会员`、`仅学生`、`需优惠码`、`套装`、`水货`、`海外直邮` |
| `votes` | integer \| null | OzBargain 净票数（赞减踩），其他来源填 null |
| `history_low` | boolean | 价格追踪网站显示这是截至当天的历史最低价 |
| `source` | string | **能直接看到这个价格**的网页 URL；原页面已经变了就用 `web.archive.org` 快照链接 |
| `evidence` | string | 原网页上含价格的原句，不超过 200 字符 |
| `retrieved_at` | string | 你抓取的日期 `YYYY-MM-DD` |
| `note` | string | 可空 |

`event` 怎么定：

- 来源明说是黑五 / 网一促销价，或日期在当年 **11/10 – 12/02** 之间**且是促销价** → `黑五季`
- 同一时期的日常价（没打折）写 `平日`：比如黑五前一周的正常价，这正是抓“先涨后降”的证据
- 来源明说是 Boxing Day / 节礼日 / 年末清仓促销价，或日期在 **12/24 – 次年 1/15** 之间**且是促销价** → `节礼日`。1 月的价算上一年的节礼日（网页会这样归年份）
- 其他大促照实写；其他时间的日常价写 `平日`（这类点对“黑五是不是最便宜”最有用）

示例：

```json
{
  "id": "ozb-912345",
  "key": "dyson-supersonic",
  "item": "Dyson Supersonic 吹风机",
  "model": "HD08",
  "category": "美妆个护",
  "retailer": "Dyson eBay 店",
  "date": "2025-11-12",
  "event": "黑五季",
  "price": 299,
  "was_price": 699,
  "was_suspect": false,
  "conditions": "",
  "votes": 412,
  "history_low": false,
  "source": "https://www.ozbargain.com.au/node/912345",
  "evidence": "Dyson Supersonic Hair Dryer $299 Delivered @ Dyson eBay",
  "retrieved_at": "2026-11-02",
  "note": ""
}
```

### 3.2 全场活动 `promos/<来源>.json`

| 字段 | 类型 | 规则 |
|---|---|---|
| `id` | string | 全局唯一，前缀是来源 |
| `year` | integer | 年份 |
| `retailer` | string | 商家；礼品卡活动写卖卡的商家（`Coles`、`Woolworths`） |
| `kind` | enum | `全场折扣` `品类折扣` `返现加码` `礼品卡折扣` `积分加倍` `会员价` |
| `value` | string | `20%`、`10x 积分`、`$20 off $100` |
| `start` / `end` | string \| null | `YYYY-MM-DD` |
| `scope` | string | 适用范围，例如 `Myer 全场（不含电器）`、`JB Hi-Fi 礼品卡` |
| `conditions` | string | 同上 |
| `votes` | integer \| null | 同上 |
| `source` / `evidence` / `retrieved_at` / `note` | | 同上 |

### 3.3 网页怎么用这些数据（让你知道哪些字段最重要）

- **往年折扣**：`event=黑五季`、有 `was_price`、`was_suspect=false` 的点，算 `1 - price / was_price`，按品类取中位数
- **黑五是不是最便宜**：同一个 `key` 既有黑五点、又有非黑五点（或 `history_low=true`）时，比两边最低价
- **今年提醒价**：`min(往年黑五最低价, 2026 年已出现的最低价)`，两边都**只算 `conditions` 为空的价**（学生价、会员价、水货、套装、箱损都不算进提醒价，只在“今年已见”里标出来）
- **黑五 vs 节礼日**：同一个 `key` 两边都有价时比两边最低价；按品类比两边的中位折扣（都要有 `was_price`）
- **往年高票**：OzBargain 黑五季每个品类票数最高的商品

所以最值钱的数据是：**同一个商品在全年不同时间的价格**，以及**带票数的往年黑五价**。

---

## 4. 数据源（按优先级）

动手前先看每个网站的 robots.txt。下面的结论是 2026-10-31 查的，以你查到的为准。

### P0 — 11/8 前交（11/9 起要用来定提醒价）

| # | 来源 | 抓什么 | 怎么抓 | 注意 |
|---|---|---|---|---|
| 1 | **OzBargain** | 2021–2025 每年黑五季的单品好价，带票数 | 今年的活动页是 `/event/black-friday`（`?page=N` 翻页），往年的入口自己找：往年活动页、`web.archive.org` 上的活动页快照，或者按 node 编号区间逐页读 `/node/<id>` | robots 不允许 `/search/`、`/goto/`、`/api/`、`/comment/`，别碰。**全场 X% off 这种不是单品价的帖子放进 promos，不要硬塞进 points**。仓库里 `src/strategy_hunter/sources/ozbargain_tags.py` 有请求间隔和 UA 写法可以照抄 |
| 1b | **OzBargain 节礼日** | 2021–2025 每年节礼日季（12/24 – 次年 1/15）的单品好价，带票数 | 活动页 `/event/boxing-day`（`?page=N` 翻页，2026-10-31 实测存在，首页是 2025-12-30 到 2026-01-13 的帖子），往前翻到没有为止；更早的年份同 #1 的办法 | 同 #1。**11/15 前交**：要赶在黑五前判断哪些东西该等节礼日 |
| 2 | **价格追踪站** | 关注清单（`watch.json`，25 个）每个商品近 18 个月的价格：最低、最高、各大促的价、平日价 | BuyWisely（robots 允许，`/api/product/` 显式允许）、PriceHipster、CamelCamelCamel AU（只有 Amazon） | CamelCamelCamel 的 robots 封了 ClaudeBot、GPTBot 等 AI 爬虫：如果你的抓取 UA 在名单里就**不要用**，改用快照或其他站；**不准改 UA 绕过**。图表读不出具体数就只记页面上明写的最低价 / 最高价及日期 |
| 3 | **Wayback Machine** | 关注商品在各大商家产品页的历史快照价（黑五前两周、黑五当天、节礼日 12/26–1/5、6 月） | CDX 接口 `http://web.archive.org/cdx/search/cdx?url=<产品页>&from=2023&to=2026&output=json` 列快照，再读具体快照 | 这是验证“先涨后降”（`was_suspect`）最硬的证据 |
| 4 | **2026 现价** | 25 个关注商品今天的价格，至少 2 家商家 | 商家官网产品页、BuyWisely | `event=平日`（或当前活动），`date` 写抓取当天 |
| 5 | **2026 日历** | 各大商家今年黑五起止日期 | 商家公告、新闻稿、OzBargain 今年活动页 | 改 `calendar.json`，状态改 `已确认` 并换成官方来源 |

### P1 — 11/15 前交

| # | 来源 | 抓什么 |
|---|---|---|
| 6 | OzBargain / 商家公告 | 2024–2025 黑五季的返现加码（ShopBack、TopCashback）、Coles / Woolworths 礼品卡折扣、Myer / David Jones 全场活动 → `promos/` |
| 7 | 海关总署、国家邮政局官网 | 蜂蜜、奶粉、保健品能不能寄、按什么税率 → 更新 `rules.json` 里“未核实”的行，只认 `.gov.cn` 官方原文 |
| 8 | Chemist Warehouse、Priceline、Amazon | 送国内亲友常买的东西（Swisse、Blackmores、Comvita、Bio Island、A2 奶粉、UGG、Aesop、Lanolin 面霜）近 12 个月价格，看半价活动多久轮一次 |
| 9 | 媒体盘点 | Canstar、Finder、Choice、Gizmodo AU、Man of Many 的 2021–2025 黑五**和节礼日**盘点，补户外运动和数码的往年价（只记文章写明的价，`source` 用文章 URL） |

### P2 — 有空再做

| # | 来源 | 抓什么 |
|---|---|---|
| 10 | Reddit（r/AusFinance、r/bapcsalesaustralia、r/AusSkincare）、Whirlpool | 往年黑五帖子里“最值的一单”，只用官方 API 或公开页面，记价格和链接，**不记用户名** |
| 11 | ACCC、Choice | 虚假折扣的执法和调查结论 → 写进覆盖报告，人工决定要不要放进页面 |
| 12 | 2026 节礼日现场 | **12/24 – 2027-01-10** 再跑一次 #1b 和 #4，记录今年节礼日的实际价格，用来回头检验黑五买得值不值 |

**先不要**：PriceSpy（不覆盖澳洲）、任何要登录的页面、付费 API。

---

## 5. 规矩（违反就整批作废）

1. **每一行都要能在 `source` 打开后看到同一个价格**。看不到的不收，不准凭记忆或推算补数。
2. 遵守 robots.txt；同一个网站两次请求至少隔 2 秒；遇到 403 / 429 停下来换来源，不要硬重试。
3. 不登录、不绕付费墙、不破验证码、不伪装 UA。
4. 不收集个人信息（用户名、头像、评论全文）；`evidence` 只摘含价格的那一句。
5. 抓来的数据只用于这个页面的分析，不拿去训练模型（BuyWisely、CamelCamelCamel 都声明了 `ai-train=no`）。
6. 抓取脚本可以写，放 `scripts/bf2026/`，**不要接进 GitHub Actions**，不要加新依赖到主项目（需要就在脚本里说明）。

---

## 6. 验收标准

P0 交付时必须全部满足：

- [ ] `python3 data/bf2026/check.py` 通过（格式、枚举、ID 唯一、`price < was_price`、日期合法、`evidence` 非空）
- [ ] 除 `curated` 之外，至少 **4 个不同网站**的数据
- [ ] 2021–2025 黑五季带票数的单品价 **≥ 300 条**，每年 ≥ 40 条，每个品类 ≥ 20 条（`其他` 不算）
- [ ] 2021–2025 节礼日季带票数的单品价 **≥ 150 条**，每年 ≥ 25 条（11/15 前交）
- [ ] `watch.json` 里 25 个商品，每个都有：
  - 至少 2 个年份的黑五价（商品那年还没上市的除外，报告里写明）
  - 至少 1 个年份的节礼日价
  - 至少 3 个非黑五价，分布在近 18 个月
  - 至少 2 家商家的 2026 现价，抓取日期在交付前 7 天内
  - 做不到的，在报告里逐个写原因
- [ ] 另起一个 AI 随机抽 10%（至少 20 行）打开 `source` 复核，**价格和日期吻合 ≥ 95%**；不合格的整个来源文件重做

P1：`promos/` ≥ 30 条；`rules.json` 里没有“未核实”的行，或者写明官方没有说法。

---

## 7. 覆盖报告（写在 PR 描述里）

1. 每个来源文件：行数、年份分布、品类分布、抓取日期
2. 25 个关注商品逐个：黑五年份数、节礼日年份数、非黑五点数、2026 现价商家数、缺什么
3. 抽查结果：抽了几行、对上几行、对不上的列出来
4. 发现：有没有明显的“先涨后降”、哪些商品黑五反而贵、建议加进关注清单的商品（附理由和数据行 ID）
5. 没抓成的来源和原因（被封、要登录、数据不全）

---

## 8. 流程

1. `main` 上已经有 `data/bf2026/` 和 `check.py` 之后再开工
2. 从 `main` 开分支：`data/bf2026-<来源>`
3. 写 `points/<来源>.json`、`promos/<来源>.json`
4. 跑 `python3 data/bf2026/check.py`
5. 开 PR，描述里放覆盖报告；**不要自己合并**，等人审

## 9. 不做

- 不改网页代码、不改 `watch.json` 的判断
- 不做实时价格监控（那是主 pipeline 的事）
- 不抓澳洲以外的价格（`海外直邮` 的澳洲到手价可以，写进 `conditions`）
