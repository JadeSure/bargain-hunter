# 黑五 2026 — 来源补充清单（`BF2026_DATA_PRD.md` 的附录）

- 状态：**已开工并交货**。2026-11-02 第二次更新。
  `data/bf2026/` 现在是 **14,561 行 points ＋ 1,861 条 promos**，过 `data/bf2026/check.py`，
  覆盖 OzBargain（6 个活动页 ＋ 3 个标签页）、Wayback（补 2021–23 黑五）、Dealmoon、
  BuyWisely、ShopBack、**Chemist Warehouse**（见 §2d）、**小红书**（见第 3 节）。
  抓取脚本都在 `scripts/bf2026/`，**没有接进 GitHub Actions**。
- 本轮两处结构性改善：
  **①** `promos` 从 84 条到 1,861 条，`礼品卡折扣` 1→487、`积分加倍` 0→798（见 §2c）；
  **②** `was_suspect` 从**恒为 false** 变成有 469 条 true，第一次有行承认自己的原价是
  厂商建议零售价而非此前售价（见 §2d）。`was_price` 覆盖率 16%→19%。
- 主文档：[`BF2026_DATA_PRD.md`](BF2026_DATA_PRD.md)。本文**不重复**它第 4 节的来源，只做三件事：
  **①** 修正它里面几条实测对不上的说法；**②** 补它没列的平台；**③** 说清楚哪些平台在它自己的规矩下根本交不了货。
- 全部端点 2026-10-31 从墨尔本 IP、用仓库自己的 UA（`strategy_hunter.sources.base.USER_AGENT`）实测。
  **没有伪装任何 UA，没有绕任何验证**（PRD §5.3）。只能靠绕过才进得去的，一律记成"进不去"，不重试。

---

## 1. 对 PRD 第 4 节的修正

### C1 — OzBargain 往年入口不用自己找，活动页本身能翻到 2024

PRD P0 #1 写的是"往年的入口自己找：往年活动页、`web.archive.org` 快照，或者按 node 编号区间逐页读"。
实测 `/event/black-friday?page=N` 直接就是跨年归档：

```
page=0    HTTP=200  95,850B  50 nodes   2026
page=5    HTTP=200  55,575B  20 nodes
page=20   HTTP=200  57,347B  20 nodes
page=50   HTTP=200  56,361B  20 nodes   2025-11 ~ 2025-12
page=100  HTTP=200           20 nodes   2025
page=160  HTTP=200           20 nodes   2024 + 2025
page=220  HTTP=200            0 nodes   ← 到底了
```

> ### ⚠️ 修正（2026-10-31，当天）
>
> 上面写的"后边界在 page 160 和 220 之间"**结论对、原因错**，而原因才是有用的那部分。
>
> 实测：`?page=199` 仍然是满的 20 条，`?page=200` 直接 **HTTP 404**。
> 黑五和节礼日**两个活动页都一样**。所以这是一个**固定的 200 页列表上限
> （200 × 20 = 4000 条）**，不是"数据到此为止"。
>
> ```
> black-friday page=199  HTTP=200  20 nodes  2024
> black-friday page=200  HTTP=404   0 nodes
> boxing-day   page=199  HTTP=200  20 nodes  2017
> boxing-day   page=200  HTTP=404   0 nodes
> ```
>
> 差别在**每年发帖密度**：黑五帖子多，4000 条只回溯到 2024-11；节礼日帖子少，
> 同样 4000 条一路回到 **2017**。
>
> 这推翻了下面 C3 的前提：**黑五 2021–2023 不是站上没有，是被翻页上限挡住了。**
> 下面那句"按 node 编号区间逐页爬可以不做了"**只对 2024 年以后成立**；
> 要拿黑五 2021–2023，node 区间爬（或别的入口）恰恰是需要的。robots 允许 `/node/`。

后边界是**翻页上限 page 199**，黑五因此只覆盖到 **2024-11**，节礼日覆盖到 **2017**。
**2024 年以后不用按 node 编号爬** —— 一个 URL 翻页就够，请求量差两个数量级。

### C2 — `points` 要的字段全在列表页上，不用逐个开 `/node/<id>`

列表页每张卡的结构（实测 page=100 的 HTML）：

```
div.node.node-ozbdeal.node-teaser[.expired]     ← 每条一个
  div.n-vote.n-deal                             ← 正/负票数（如 "408  0"）
  a[href="/node/<id>"]                          ← 标题，价格就嵌在标题里（实测一页 143 个 $ 匹配）
  "on 31/10/2025 - 00:03"                       ← 发布时间
  <商家域名>  /  "1 Dec 2025 11:59pm"            ← 商家、过期时间
  <点击数>  <评论数>
```

所以一次列表请求 = 20 条完整的 `points` 行（`item` / `price` / `votes` / `date` / `retailer` / `source`）。
按 2 秒间隔，**215 页约 8 分钟**，一次 `/node/` 都不用开。
PRD §6 要的"≥300 条带票数的往年黑五价"，**约 15 页就够了**；跑满是为了品类配额。

注意：`price` 要从标题里正则解析，`was_price` 多数标题没有 —— 这意味着
**"往年折扣幅度"（需要 `was_price` + `was_suspect=false`）仍然得靠价格追踪站和 Wayback**，
列表页解决的是"有票数的黑五成交价"，不是折扣率。这两个指标别混。

### C3 — 黑五 2021–2023 被翻页上限挡住（原因已按 C1 的修正更新）

**不是站上没有，是 `?page=N` 够不着**（见 C1 的修正：200 页硬上限）。
节礼日同样的上限却能回到 2017，因为它每年帖子少得多 —— 实测节礼日已拿到
2017–2025 共 9 个赛季、2547 条。

所以黑五 2021–2023 有三条路，都还没试：
① Wayback 快照（下面的 CDX 结果）；② 按 node 编号区间爬（robots 允许 `/node/`，
本文件原先说"可以不做了"，那句只对 2024 年以后成立）；③ 找按年份分的入口
—— subagent 查过 page-0 的 HTML 里没有往年入口链接。

Wayback 这条路**必须带 `www.`**：

```
www.ozbargain.com.au/event/black-friday   19 snapshots   2021 2022 2023 2024 2025  ✓
www.ozbargain.com.au/pages/black-friday   16 snapshots   2021 2022 2023 2024 2025  ✓
   ozbargain.com.au/tag/black-friday       0 snapshots   （少了 www，会读成"没存档"）
```

PRD §6 要求 2021–2025 每年 ≥40 条，所以 **2021/2022/2023 这三年完全押在这 19 个快照上** ——
这是整个 P0 里最脆的一环，建议先取一个 2021 快照数一数实际能拿到多少条，再决定要不要把
"每年 ≥40 条"往下调。先验证，别最后交不出来。

### C4 — robots.txt 与 PRD 所述一致（已核对）

```
User-Agent: *
Disallow: /api/  /comment/  /goto/  /ozbapi/  /privatemsg/  /search/  /user/login
```

`/event/`、`/pages/`、`/node/` 都没被禁。另有 AhrefsBot / dotbot / Superfeedr 全站禁止，与我们无关。

### C5 — 官方黑五 hub 页活着，就是 `calendar.json` 的来源

`https://www.ozbargain.com.au/pages/black-friday` → HTTP=200, 59,450B。P0 #5 直接用它。

---

## 2. PRD 没列、但该加的平台

### 2a. OzBargain 的其他活动页 —— 回答"黑五是不是全年最便宜"最便宜的办法

PRD §3.3 要"同一个 `key` 的黑五点 vs 非黑五点"，而 `event` 枚举里已经有
`Click Frenzy` `Prime Day` `双11` `节礼日`。这些 OzBargain 各自都有活动页，
和黑五**同一套 HTML、同一套 `?page=N`**，实测全部可用：

```
event-cyber-monday      200  19,597B  10 items   最新 2025-12-03
event-click-frenzy      200  17,497B  10 items
event-singles-day       200  17,399B  10 items
event-boxing-day        200  19,129B  10 items   最新 2026-01-13
event-amazon-prime-day  200  17,726B  10 items
```

已用标题比对（不是比字节）确认是真的按活动分流：`black-friday ∩ boxing-day = 0 条重复`。
`/tag/<x>/feed` 会 302 到 `/event/<x>/feed`，仓库里 `ozbargain_tags.py:48` 已经带了
`follow_redirects=True`，写法照抄即可。

**同一个爬虫改个活动名就能跑**，等于白拿 Q2 的对照组。

### 2b. Dealmoon AU 澳洲省钱快报 —— 唯一真正新增的高价值平台

```
www.dealmoon.com.au/              200  852,843B  18,057 个中文字  服务端渲染，无 __NEXT_DATA__
www.dealmoon.com.au/cn            200  888,523B  18,645 个中文字
www.dealmoon.com.au/guide         200  129,387B   3,058 个中文字   ← 攻略文章
www.dealmoon.com.au/robots.txt    200
    Content-Signal: search=yes, ai-input=yes, ai-train=no
    Disallow: /cn/top/ /en/top/ /top/ /v2/ /Log/ /h5/api/ /exec/ /bg/ ...
```

- **首页今天就有 20 个「黑五」**，英文 "Black Friday" 0 个 —— 它的黑五内容本来就是中文的。
- 链接形状：`/guide/<id>`（攻略）、`/product/<id>`（单品）、`/stores/<商家>`、品类页。
- 政策上干净：`ai-input=yes` 明确允许作为生成式回答的输入，比 repo 之前因
  `use=reference` 而拒掉的 linux.do 宽松；`ai-train=no` 我们本来就不训练模型（PRD §5.5 同款表述）。
  Disallow 没覆盖 `/guide` 和列表页。
- **避开 `/exec/`** —— 首页 138 个 `go.dealmoon.com.au/exec/j?...` 是联盟跳转链接，在 Disallow 里；
  落地到 `/product/<id>` 再取 `source`。
- 没有 RSS：`/feed` `/rss` `/sitemap.xml` 全 404，只能解析 HTML。
- **主机名陷阱**：`au.dealmoon.com` 是 **NXDOMAIN**，正确的是 `www.dealmoon.com.au`。

对得上 PRD 的三块：P0 #4（2026 现价，中文商家视角）、P1 #6（返现加码 / 礼品卡 → `promos/`）、
P1 #8（Swisse / Blackmores / A2 / UGG 这类送礼品，它就是主战场）。

---

### 2c. OzBargain 的标签页 —— 把 `礼品卡折扣` 和 `积分加倍` 从几乎为零做起来

`promos/` 原来只有 84 条，而且 check.py 允许的六个 `kind` 里，
**`礼品卡折扣` 只有 1 条、`积分加倍` 0 条**。也就是说澳洲华人实际最常叠的那两级
——先折价买礼品卡，再在礼品卡上吃积分倍数——库里整个是空的。

OzBargain 自己给这两件事各有一个标签，robots.txt 只封 `/api/ /search/ /goto/ /comment/`，
标签页允许抓：

| 标签 | 用途 |
|---|---|
| `/tag/gift-card` | 礼品卡折扣的主入口 |
| `/tag/reward-points` | 积分加倍（`/tag/flybuys`、`/tag/everyday-rewards`、`/tag/points` 都 302 到这里） |
| `/tag/sitewide`、`/tag/storewide` | 全场折扣（`/tag/clearance` 不存在，404 跳过） |

脚本 `scripts/bf2026/fetch_ozbargain_promos.py`，复用同目录 `fetch_ozbargain.py` 的
`parse_cards` / `split_title` / UA / 2 秒节流，不重写解析。281 次请求 → **1,777 条 promos**，
**回溯到 2023-11**，覆盖三个黑五。

| kind | 之前 | 现在 |
|---|---|---|
| 积分加倍 | **0** | **798** |
| 礼品卡折扣 | **1** | **487** |
| 返现加码 | 27 | 431 |
| 品类折扣 | 36 | 115 |
| 全场折扣 | 15 | 25 |

**`evidence` 就是帖子标题本身** —— 折扣写在标题里，`source` 是对应的 `/node/<id>`，
打开就能看到同一句话，满足 §5.1。标题里的括号注解自动转成 `conditions`
（`EDR Required` → 需 Everyday Rewards 会员，`In-Store Only` → 仅限门店，
`Activation Required` → 需先激活）。

**主动丢掉的：** 63 条抽奖/赠品类（`$100 Gift Cards for 1st 50 Customers`
是送不是折），911 条标题里根本没写折扣幅度的。

**这批数据直接推翻了 `prep.json` 第 5 步**，详见
[`BF2026_TIMING.md`](BF2026_TIMING.md)：71% 的黑五礼品卡折扣在 D-10 之后才出现，
而且黑五季和平日的中位折扣**都是 10%**，所以礼品卡根本不该等黑五。

**写的时候被自己坑了两次，都钉成测试了**（`--self-check`，11 条标题）：
`10,000 Flybuys Points` 被千分位逗号截成 `000 Flybuys Points`；
`Cashback: 2% Upsized` 这种倒装被降级成光秃秃的 `Cashback`。

### 2d. Chemist Warehouse —— 补两个最薄的类，顺便给 `was_suspect` 开张

`保健食品`（184 行）和 `礼品`（149 行）是全库最薄的两个类目，
而且**全库 `was_price` 只有 16%**，折扣深度根本算不准。

CW 的商品页**服务端就渲染了价格**，连参考价一起：

```html
<h2 class="display-l ...">$22.49</h2>
<p ...>$69.50 Off RRP</p><p ...>Don't Pay RRP $91.99</p>
```

robots.txt 禁 `/search`、`/native-search` 和 `?category=` `?brand=` 这类筛选 URL，
但它自己公布了 sitemap，所以**只走 sitemap**：
`https://static.chemistwarehouse.com.au/AMS/sitemap/cwh_sitemap.xml` → 26,370 个商品页，
按品牌/品类关键词筛出保健品 1,800、礼品 486，均匀抽 800 个抓。

结果：**708 行，466 行带 RRP，0 解析失败**，92 个 sitemap 里已下架的 404 跳过。

| 类目 | 之前 | 现在 |
|---|---|---|
| 保健食品 | 184 | **583** |
| 礼品 | 149 | **458** |

#### ⚠️ 这批的 `was_price` 是 RRP，必须打折看

**RRP 是厂商建议零售价，不是 Chemist Warehouse 此前卖过的价。**
它正是"虚高原价"这个问题本身，所以这 466 行**全部 `was_suspect = true`**
——这是全库第一次有行把 `was_suspect` 置 true（之前恒为 false，是文档里记了很久的洞）。

**用法**：这些行是用来给黑五价**当对照基线**的，不是"CW 平时就五折"的证据。
看到 `$10.49 / RRP $20.99` 要读成"黑五价得明显低于 $10.49 才算好价"，
不能读成"这件商品打了五折"。

另外两点照直说：
- `date` 是抓取当天、`event` 是当天所属的档期。这批跑在 11-02，所以全是 `平日` 基线。
  在 11-10..12-02 之间再跑一次，同一批商品就会产出 `黑五季` 的行，两边可以直接比。
  脚本用的是**悉尼时间**（和 `fetch_ozbargain.py` 一致），不是 UTC —— 第一版用了 UTC，
  整批日期差了一天，已修正。
- `key` 用的是商品页 slug，**不会和 OzBargain 的 key 聚合到一起**。
  这批是独立基线，不参与跨源按 `key` 比价。

---

## 3. 交不了货的平台 —— 以及为什么

### 小红书：交货了 —— `points/xhs.json` 162 行 ＋ `promos/xhs.json` 15 行

> 这一节在 2026-11-02 整个重写过。之前写的是"交不了货"，那个判断**已经被实测推翻**，
> 旧结论和推翻它的过程都保留在本节末尾，别只看结论不看是怎么翻的。

**怎么抓的**（业主账号已登录，走浏览器，没有伪造签名）：

1. 搜索页用正常导航翻 10 个关键词（`澳洲黑五`、`澳洲 boxing day`、`chemist warehouse 黑五`、
   `澳洲黑五 礼品卡` 等），从 DOM 收笔记卡片 —— 得到 **166 篇**，每篇带 `xsec_token`。
2. 笔记正文用同源 `fetch` 取服务端渲染的 HTML，两次请求间隔 2.1 秒。
   **103 篇拿到正文**，0 失败。
3. 价格基本不在正文里，在图里。把高价值笔记的图按仓库自己的 UA 下载下来逐张读。

**三个实测发现，都和"小红书能给什么"直接相关：**

**① 发帖地点就在 `date` 字段里，这是现成的澳洲过滤器。**
`class="date"` 的内容是「5天前 澳大利亚」「10-12 浙江」这种，定位跟在日期后面。
166 篇里只有 **43 篇是澳大利亚发的**，123 篇来自辽宁、安徽、浙江、江西、江苏、
中国香港、加拿大、河北、广东 —— 这些讲"澳洲黑五"的内容绝大多数是代购引流。
`BF2026_XHS_FINDINGS.md` 里记的那条非澳洲污染，这回量化了：**约 74% 的搜索结果不是本地人发的**。
（注意：没有定位后缀的老笔记不能一概排除，Costco 目录那篇 492 赞的就没有定位。）

**② 真正值钱的不是网友的文字，是网友转发的零售商目录原图。**
产出的 162 行里，**130 行来自两篇笔记转发的官方目录扫图**：

| 笔记 | 内容 | 产出 |
|---|---|---|
| Costco Early Black Friday 目录 | 7 页，每件都印 item number、现价和 After $X off | 47 行 |
| JB Hi-Fi 黑五专场目录 | 8 页，每件都印 TICKET（票价）和现价 | 69 行 |

Costco 那份目录自己印着 *Only valid in Costco warehouses located in Australia*
和 *Savings are valid 17/11/25 – 1/12/25*，澳洲属性和档期都是图里写死的，不靠推断。

这直接补上了全库最大的一个洞：**`was_price` 覆盖率**。
`points/xhs.json` 有 **109/162 行带原价（67%）**，而全库原来只有约 16%
（OzBargain 标题大多不写原价）。目录上的 "After $X off" / "TICKET $Y" 是印在图上的，
不是推算的。

**③ 华人圈的省钱打法，OzBargain 上基本看不到。**
`iPhone 18 Pro` 这种在正文里被拆成一条完整的叠加链：
Costco 报价 → 拿去 Officeworks 做 price beat 再减 5% → 叠九折礼品卡 → OnePass 积分 → TRS 退税。
四篇不同的笔记独立记下同一套打法，落价从 $2399.99 一路到 $1692。
这条链里的每一步都单独落了行，`conditions` 写明前提（"需拿 Costco 价格做 price beat"）。

**抓到哪里停的：遇到验证码，停了。**
抓到第 103 篇之后，同源 `fetch` 开始对**所有**笔记（包括之前成功过的那几篇）返回
一个固定 10,395 字节的空壳，没有 `__INITIAL_STATE__`。
等了半小时再试，一样。改用正常导航打开笔记页，被跳到
`/website-login/captcha`（`error_code=300031`，Security Verification）。

**剩下 63 篇没有抓。** PRD §5.3 的「不破验证码」没有被取消，所以到这里就停了，
没有换 UA、没有换 IP、没有解验证码。被挡住的这 63 篇恰好偏向
**礼品卡折扣**和 **Boxing Day 攻略**两类。

> #### 2026-11-02 续：验证码过了，但这 63 篇还是没补上，原因变了
>
> 业主过了验证码，笔记页确实恢复了 —— 同源 `fetch` 一篇笔记回 110,124 字节，
> `__INITIAL_STATE__`、`class="desc"` 都在，风控那一关算过去了。
>
> **但搜索页要登录，而会话没了。** 搜索页现在返回「登录后查看搜索结果」，
> 页面里 `"isLogin":false`。笔记页不要求登录（所以 `fetch` 照样通），搜索页要求。
>
> 更麻烦的是**那 63 篇的 note id 和 xsec_token 丢了**。它们只存在浏览器标签页的
> `sessionStorage['bf_cards']` 里，标签页关掉就没了；当时只打印过条数和前几条样本，
> 没有把完整清单落盘，会话记录里也只剩 26 组（就是已经入库的那些）。
> 笔记页的 SSR 在未登录时只渲染当前这一篇，不带推荐流，所以也没法从已有的 26 篇爬出新 id。
>
> **结论：这 63 篇不是「接着抓」，是要重新搜一遍。** 前提是浏览器里有登录态 ——
> 扫码登录是业主自己的账号和手机，我不代填手机号和验证码。
>
> **教训（已改）**：浏览器里攒出来的工作清单要立刻落盘到 scratchpad，
> 不能只留在 `sessionStorage` 里。
>
> 另外，这两块空白后来**换了来源补上**，没有等小红书：
> 见 §2c，OzBargain 的 `/tag/gift-card` 和 `/tag/reward-points` 直接把
> `礼品卡折扣` 从 1 条做到了三位数，`积分加倍` 从 0 条开张。

> #### 2026-11-02 再续：业主扫码登录了，搜索恢复，但笔记页立刻又是验证码
>
> 业主扫码后 `isLogin:true`，**搜索页完全正常**。重搜了三个关键词
> （`澳洲黑五` / `澳洲礼品卡打折` / `澳洲boxing day`），拿到 **81 张卡片**，
> 其中有 4 篇零售商目录转发（Costco 三份、JB Hi-Fi 一份）和 7 篇礼品卡专帖
> —— 正是上一轮缺的那两类。
>
> **这一次卡片清单第一时间落盘了**：
> `scratchpad/xhs-cards/01-aozhou-heiwu.json`、`02-giftcard-boxingday.json`，
> 带 note id ＋ xsec_token ＋ 标题。上一轮丢清单的失败模式不会重演。
>
> **但笔记正文还是没拿到。** 同源 `fetch` 连开 16 篇，**16 篇全部返回那个
> 固定 10,395 字节的空壳**（上一轮是抓到第 103 篇才开始，这次是第 1 篇就开始）。
> 改用正常导航打开笔记页 → 又被跳到 `/website-login/captcha`
> （`verifyType=124`，Security Verification）。
>
> **§5.3「不破验证码」没有被取消，所以又停了。** 没换 UA、没换 IP、没解验证码。
>
> **不从标题凑数。** 搜索卡片的标题里是有价格的
> （`$1468 69折拿下18pro`、`iPhone18 Pro（$855）`、`162🔪拿下勃肯`），
> 但 §5.1 要的是"打开 `source` 能看到同一个价格"，我自己都没能打开笔记页核对，
> 而且标题里没有零售商和型号，`key` 和 `retailer` 组不出来。**所以一行都没收。**
>
> **下次再试的节流参考**：这次 16 篇连抓（间隔 2.4 秒）就触发了，
> 上一轮是约 100 篇。说明触发阈值跟着会话历史走，不是固定篇数。
> 真要补这 81 篇，得把间隔拉到分钟级、分多次会话慢慢来。

**数据成色，照直说：**

- `source` 是带 `xsec_token` 的笔记链接。token 会过期，过期后没有登录态的人打不开 —— 这是
  全部来源里唯一一个 `source` 可能验不了的。
- 目录扫图那 130 行，价格印在**零售商自己的目录**上，`retailer` 记的是 Costco / JB Hi-Fi，
  小红书只是搬运。这部分证据强度其实高于普通的 OzBargain 标题。
- 正文转述那 32 行里，有 19 行来自一篇转述第三方比价站 WhatsCheap 的笔记，**没有零售商**，
  `retailer` 记成"未注明"，`conditions` 写清楚了。看到这些行要知道它们只能当量级参考。
- 每一行的 `note` 都写明来自第几页图或哪句正文。

**主动排除掉的，比收进来的更值得看一眼：**

| 排除的 | 为什么 |
|---|---|
| 一篇攻略里的 `$200/$160/$149` | 正文自己写着「💰举个**假设**例子」，是编的 |
| 新西兰 Chemist Warehouse 黑五价 | PRD §9：不抓澳洲以外的价格 |
| lululemon「去年低至 $74」那一串 | 出现在一篇写明「仅为预测参考」的笔记里，没有可打开的价格页 |
| amaysim 年卡 88/133 刀 | 正文是「需要的私信」，转卖不是零售价 |
| 新秀丽 $187.5 | 商家以标错价砍单了；收的是补券后真正成交的 $234.37 |
| 「仅仅 294🔪 拿下戴森」 | 没有型号、没有零售商，组不出 `key` |
| 一堆「$4 off」「$7 off」的 Costco 食品 | 目录上只印了减多少，没印现价，`price` 无从填 |

---

<details>
<summary>以下是 2026-10-31 写的旧结论，已被上面的实测推翻，保留备查</summary>

当时写的是：

```
www.xiaohongshu.com/search_result?keyword=澳洲黑五
    HTTP=200   59,939B   noteCard × 0   __INITIAL_STATE__ × 1   登录 × 2
```

200，但服务端一条笔记都没渲染，而且有登录墙。真正的数据接口
（`/api/sns/web/v1/search/notes`）要签名过的 `x-s` / `x-t` 加会话 cookie。

当时的结论是「小红书不该进 `points/`，它真正的用处是选品而不是价格证据」，
理由有两条，后来一条被业主取消、一条被实测推翻：

1. **PRD §6 的交叉抽查过不了** —— 业主已于 2026-10-31 取消 §6 的交叉复核，这条自动失效。
2. **「服务端一条笔记都没渲染」** —— 这是**当时没登录**造成的。登录之后，
   搜索页正常导航就能拿到卡片，笔记页的同源 `fetch` 直接返回服务端渲染好的完整 HTML，
   连 `__INITIAL_STATE__` 都带。不需要碰 `/api/sns/web/v1/search/notes`，
   也就不需要签名。我当时把"要签名的接口"当成了唯一入口，这个判断是错的。

没有变的：**伪造 `x-s`/`x-t` 签名、刻意按人类节奏躲风控、解验证码，都不做。**
最后那 63 篇就是因为第三条停下来的。

</details>

### 其他

| 平台 | 实测 | 结论 |
|---|---|---|
| 微博 | `m.weibo.cn/api/container/getIndex?…q=黑五` → **302**（无会话） | 登录墙，同小红书 |
| 微信公众号 | 搜狗微信入口是验证码 | 破验证码，PRD §5.3 禁止 |
| 今日悉尼 sydneytoday | 仓库 UA → **403**（Cloudflare） | 记成"这个 UA 被挡"，**不是**"站点有墙"（`HIGH_VALUE_SOURCES_PLAN.md` C2 的教训）。换个合规路径可以再试一次 |
| yeeyi 澳洲同城 | 200，41,057B，但只有 **663 个中文字、0 个 href** | 客户端渲染空壳。你自己有 `yeeyi-jobs` 仓库，复用那边能跑通的取数路径，别重新摸 |
| 抖音 / B站 / YouTube | — | 价格在语音里，拿不到"打开链接就能看到同一个价格"的证据，过不了 §5.1 |
| CamelCamelCamel | robots 封 ClaudeBot / GPTBot 等 | PRD P0 #2 已经写明：UA 在名单里就别用，**不准改 UA 绕过** |

---

## 4. 开工前有两个硬阻塞

1. **PRD §8.1 说"`main` 上已经有 `data/bf2026/` 和 `check.py` 之后再开工"，但现在它们只在
   `feat/bf2026-hidden-page` 上，而且没提交**：
   `?? data/bf2026/`、`?? docs/BF2026_DATA_PRD.md`、`?? frontend/app/p/`、`?? frontend/lib/bf2026.ts`，
   另有 `M .github/workflows/deploy-frontend.yml`。按它自己的流程，这些得先合进 `main`。
2. ~~`check.py` 还没跑过~~ —— 已跑：`python3 data/bf2026/check.py` → `ok: 67 points, 0 promos`，exit 0。
   种子数据是 `points/curated.json`（67 条）和空的 `promos/curated.json`；`watch.json` 25 个关注品齐全。
   校验器可用，格式按它的报错对齐即可。

## 5. 建议的第一批（按性价比）

| # | 做什么 | 产出 | 量级 |
|---|---|---|---|
| 1 | ~~跑 `check.py`~~ 已跑通（`ok: 67 points, 0 promos`） | — | 完成 |
| 2 | `/event/black-friday?page=0..215` 解析列表页 | `points/ozbargain.json` ≈3,000–4,000 条（2024–2026，带票数） | 约 8 分钟请求 |
| 3 | 取 1 个 2021 的 Wayback 快照，数实际条数 | 决定 2021–2023 的配额是否可达 | 10 分钟 |
| 4 | 另外 5 个活动页同一套解析 | `points/ozbargain-events.json`，Q2 的对照组 | 复用 #2 |
| 5 | Dealmoon `/guide` + 首页黑五条目 | `points/dealmoon.json` + `promos/dealmoon.json` | 新写解析 |
| 6 | 商家官网 25 个关注品的 2026 现价 | 补 P0 #4 | 逐站 |

脚本放 `scripts/bf2026/`，**不接 GitHub Actions**，不给主项目加依赖（PRD §5.6）。
每站两次请求间隔 ≥2 秒，遇 403/429 就停（§5.2）。

---

## 6. 2026-11-02 对着 PRD §6 验收标准逐条过了一遍

动机：前面几轮一直在加来源，没人回头核对验收标准。过完发现**没做的不是来源，是验收本身的两条**。

### 6a. 抽查复核（PRD §6 最后一条）—— 做了，可验证的 33/33 全对

脚本在 `scripts/bf2026/spotcheck.py`，按来源文件分层抽样（每个文件 3 行，共 36 行），
逐条打开 `source` 看页面上还能不能找到同一个价格。请求间隔沿用 2.2 秒。

裸 HTTP 的结果是 30/36 = 83.3%，但 6 行 MISS 全部落在两个来源，而且原因都不是数据错：

| 来源 | 为什么裸 HTTP 看不到 | 处理 |
|---|---|---|
| `dealmoon.json`（605 行） | 对非浏览器请求返回 **0 字节**，整页客户端渲染 | 抽到的 3 行在浏览器里逐条看过：`$399.00` / `$35.00` / `$159.42`，和数据里**精确一致** |
| `xhs.json`（162 行） | 搜索页和笔记页现在都要登录，返回登录墙 | 核不了，见 §3 |

把浏览器复核的 3 行算上、小红书的 3 行排除后：**33/33 = 100%**，过 95% 的线。
仍然核不动的只剩小红书那 162 行（占全量 1.1%）。

教训写在脚本 docstring 里：这两个来源以后别用裸 HTTP 复核，一定报假 MISS。

### 6b. `calendar.json` 还有 9/17 条是「按往年推测」—— P0 #5 没交

这是**最影响"什么时候该准备什么"的一条**，而且 PRD P0 #5 写明要换成官方来源、状态改 `已确认`。
现在推测的全是商家开场日期：早鸟闪购、Amazon AU、The Good Guys、Kogan/Catch、
JB Hi-Fi/Harvey Norman/Officeworks、Sephora/Adore Beauty、Myer/David Jones/The Iconic、
Apple 购物活动、节礼日。来源字段指向的是 ShopBack / Mozo / Tom's Guide 的往年盘点文章，不是商家公告。

### 6c. `watch.json` 25 个商品：19 个不达标，但大半是「那年还没上市」

PRD 允许「商品那年还没上市的除外，报告里写明」，所以得分开看：

| 缺口 | 个数 | 性质 |
|---|---|---|
| 无节礼日价 | 18 | 多数是 2025/2026 的型号（`switch-2`、`airpods-pro-3`、`sony-xm6`、`roborock-curv`、`dyson-gen5`、`garmin-fr265`），往年节礼日根本不存在 → 属 PRD 允许的例外 |
| 黑五年份 < 2 | 11 | 同上，新型号为主 |
| 真正的空洞 | 2 | `roborock-curv` 只有 1 行、`t2-tea-books` 0 行 —— 这两个得补 |
| 软货品牌拿不到 | 5 | `lululemon`、`comvita`、`swisse-blackmores`、`boody-socks`、`pandora-bracelet` 的节礼日价为 0，OzBargain 基本不发这类 → 要补得换来源（品牌官网 Wayback 快照） |

品牌层面其实有货（节礼日文件里 dyson 17 行、roborock 15 行、garmin 12 行、oral-b 12 行），
只是**型号对不上** `watch.json` 的 key。这不是 key 命名问题，是确实没有那个具体型号。

### 6d. 过了的条目

| 验收条件 | 要求 | 实际 |
|---|---|---|
| `check.py` | 通过 | ok: 14561 points / 1861 promos |
| 非 curated 的网站数 | ≥ 4 | **8**（OzBargain、Chemist Warehouse、Dealmoon、BuyWisely、小红书、Canstar、Choice、Wayback） |
| 2021–2025 黑五季带票单品价 | ≥ 300，每年 ≥ 40 | **4893**，最少的 2022 年 467 |
| ↑ 每个品类（`其他` 不算） | ≥ 20 | 全部过：数码电子 2151 · 家电厨房 557 · 户外运动 246 · 美妆个护 181 · 礼品 52 · 保健食品 30 |
| 2021–2025 节礼日带票单品价 | ≥ 150，每年 ≥ 25 | **1163**，最少的 2023 年 87 |
| `promos/` | ≥ 30 | **1861** |

### 6e. 还欠的，按该不该补排序

1. **`calendar.json` 的 9 条商家开场日期**（§6b）—— 今天距黑五 25 天，部分商家应该已经挂出 hub 页，可查。
2. **`roborock-curv` 和 `t2-tea-books`** 几乎没有数据（§6c）。
3. **媒体盘点（P1 #9）只有 11 行** —— Canstar 8 + Choice 2 + Tom's Guide 1，等于没做。
4. **BuyWisely 只有 168 行** —— 它是 P0 #2 的价格追踪站，18 个月历史价是判断 `was_suspect` 的主要依据，太薄。
5. **`rules.json` 剩 1 条未核实** —— 保健品/奶粉/蜂蜜数量限制，现在的 `source` 是人民日报，PRD 要求「只认 `.gov.cn` 官方原文」。
6. **覆盖报告（PRD §7）没写** —— 本节算是补上了 1、3、5 三块，第 2 块（25 个商品逐个）见 §6c，第 4 块（发现）见 `BF2026_TIMING.md`。
7. 小红书 81 张卡片正文、Reddit/Whirlpool（P2 #10）、`全场折扣` 只 25 条 —— 都是老问题。
