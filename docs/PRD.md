# Bargain Hunter 产品需求文档 (PRD)

- 状态:草稿 v0.1,待审批
- 日期:2026-06-18
- 作者:Shawn Wang
- 决策基线:Python · 邮件(v1) + Telegram(后期) · deal 历史存 repo / 用户与已发送存 Notion · 来源 OzBargain + CamelCamelCamel(可降级)

---

## 1. 背景与目标

在澳洲薅羊毛主要靠刷 OzBargain,但真正好的 deal 往往涨势极快,几分钟内被抢光或下架,人工刷跟不上,错过即损失。

**目标:** 定时、自动地发现"真正值得出手"的 deal,并按每个人的关注精准推送,让用户第一时间收到提醒。

**衡量标准(v1):**
- 系统能稳定定时运行,从 OzBargain 正确解析带票数的 deal。
- 能算出涨势(velocity)并按阈值挑出"爆款";能按个人关注清单做针对性匹配。
- 通知去重、合并摘要,通过邮件送达(v1);Telegram 作为后期通道。
- 公开仓库不泄露任何订阅者隐私。

**非目标(v1 明确不做):**
- 不做自动下单 / 自动抢购。
- 不做完整的商品价格历史数据库。
- 不做 Web 前端或管理后台(用 Notion 当后台)。
- 不追求覆盖所有平台,不上机器学习评分。

---

## 2. 用户与角色

- **订阅者(约 10 人量级):** 在 Notion 里登记邮箱 / Telegram,设置关注清单与偏好,被动接收推送。
- **维护者(你):** 管理 Notion 数据、密钥、评分阈值与运行。

---

## 3. 核心设计:两条独立赛道

把"点赞速度"和"价格折扣"当成两条独立赛道,而不是一个算法里的两个变量,因为它们的**时效性与精确度正好相反**:

| 赛道 | 信号 | 性质 | 面向 | 频率/门槛 |
|---|---|---|---|---|
| **爆款 (Hot)** | 投票涨速 velocity + 绝对票数 + 发布时长 | 滞后但准,误报低 | 所有开启该项的订阅者 | 低频、高门槛,宁缺毋滥 |
| **盯货 (Watch)** | 关键词命中个人清单 + 折扣/低价 | 提前但吵,容忍噪音 | 仅关注该商品的用户 | 较高频、低门槛,主动盯 |

**为什么两条都要:** velocity 是事后指标,等涨势确认时最猛的 deal 可能已经快没了,但它几乎能覆盖所有"客观上的好 deal";价格/折扣是 deal 一出现就能算的提前指标,够快但噪音大。两者确有重叠(好价格通常很快被投票顶起来),但正因时效性相反,各管一摊最合理:爆款赛道负责"广撒网抓客观好货",盯货赛道负责"早一步抓你点名要的东西"。

**重叠处理:** 一个 deal 若同时上了热度榜又命中某人的关注清单,该用户**只收一条**(合并,文案标注"你在盯 + 全站正火")。

---

## 4. 数据来源

来源层做成可插拔 adapter 接口,统一输出标准 `Deal` 模型,未来可加 Catch / Amazon / 社媒等。

### 4.1 OzBargain(主来源,已实测确认)
- Feed:`https://www.ozbargain.com.au/deals/feed`
- 每条 item 带 `<ozb:meta>`,含 `votes-pos`、`votes-neg`、`comment-count`、`click-count`、商家直链 `url`、`image`、`expiry`(部分带 `starting`)。
- 同时支撑两条赛道:主 feed 跑 velocity;按关键词的 search/tag feed(如 `.../cat/<分类>/deals/feed`)支撑盯货。
- **velocity 只靠 RSS 即可,无需抓 HTML。**

### 4.2 CamelCamelCamel AU(第二来源,服务价格/盯货赛道,可降级)
- 提供逐商品价格历史 RSS 与 `https://au.camelcamelcamel.com/top_drops` 跌幅页。
- 价值:给"这个价到底算不算低"提供真实价格历史依据,补 OzBargain 没有价格史的短板。
- ⚠️ 限制:top_drops 无官方 feed、需抓 HTML,受 ToS 与页面结构变动影响,较脆弱;关键词到 ASIN 有映射成本。
- **降级策略:** 做成可随时关闭/替换的 adapter。盯货赛道先用 OzBargain 关键词 search feed 跑通,CCC 作为价格佐证增量接入;CCC 不可用时系统照常运行。

---

## 5. 功能需求 (Functional Requirements)

- **FR1 抓取:** 定时拉取各来源,标准化成统一 `Deal` 模型。
- **FR2 状态快照:** 每次记录每个 deal 的 `(votes_pos, votes_neg, comment_count, timestamp)`,用于算 velocity;持久化方式见 §10.1。
- **FR3 热度评分:** 按第 6 节算法计算 hot score,过阈值才进爆款赛道。
- **FR4 盯货匹配:** 关键词 + 目标价 + 最小折扣匹配个人清单。
- **FR5 去重(允许"变更再提醒"):** 同一 deal 对同一人默认只发一次;**但若该 deal 实质性变好(价格再降 ≥ 配置幅度,或票数/热度跨上一个台阶),可再推一次,每个 deal 对每人最多再推 `max_realerts_per_deal` 次(默认 1)**,避免无脑刷。已发送记录存 Notion(Sent Log),并记录上次触发状态以支撑再提醒;访问模式与幂等见 §10.2。
- **FR6 通知:** v1 只实现邮件;通知层仍按"订阅者拥有的通道"建模,Telegram 作为后期通道(见 §14 决策 4)。同一次运行多个 deal 合并成一封摘要;每人每天频率上限;可选安静时段(频率上限与安静时段均按 AET 计,见 §14 决策 7)。每日上限按"deal × 人 × 天"计,不按邮件封数计;同一 deal 同时命中 Hot/Watch 仍只占一次。
- **FR7 订阅者与偏好:** 从 Notion 读取(schema 见第 7 节)。
- **FR8 冷启动:** 首次运行只记录基线、不发通知;之后只考虑"系统首次见到时间"之后出现的新 deal,不回灌历史。
- **FR9 过期/失效过滤:** `expiry` 已过、标记 expired / out of stock 的不推。
- **FR10 可观测与失败告警:** 每次运行输出运行摘要(聚合计数,不含订阅者标识);**失败必须自我告警**——跑挂、关键调用报错、或解析到 0 条 deal(几乎必是 feed 格式坏了而非当天没货)时,主动发邮件通知维护者;另设心跳,超过 N 小时没成功跑完则提醒。静默不响是告警系统最坏的失败模式。

---

## 6. "好 deal" 评分算法(全部参数可配)

### 6.1 Velocity 定义
- 短窗涨速:用当前快照与 `window_minutes` 前最近的一次快照计算 `Δvotes / Δt`(票/小时);若历史不足,退回最近两次快照,但不把冷启动第一轮用于通知。
- 全程均速:自发布以来 `votes_pos / age_hours`。

### 6.2 爆款赛道(Hot)
满足**任一**条件即为候选:
1. 最近一个窗口内净增票 ≥ `V1`(默认示例:1 小时 +15 票)。
2. 早期爆发:`age < H` 小时且 `votes_pos ≥ V2`(默认示例:2 小时内 ≥ 25 票)。
3. velocity 处于当前活跃 deal 的前 `P%`。

候选再算加权 hot score,过 `HOT_THRESHOLD` 才推:
- 正向:vote velocity、绝对票数、comment velocity。
- 惩罚:年龄(越老越降权)、`votes_neg` 占比高(争议/差评)降权。
- 初始公式(可调,上线后校准):
  `hot_score = age_factor * (vote_velocity / V1 + log1p(votes_pos) / log1p(V2) + 0.25 * comment_velocity) - neg_vote_penalty_weight * neg_ratio`
  - `age_factor = 0.5 ** (age_hours / age_penalty_half_life_hours)`
  - `neg_ratio = votes_neg / max(votes_pos + votes_neg, 1)`
  - percentile 候选只在活跃、未过期、且达到 `min_votes_for_percentile` 的 deal 中计算,避免低样本噪声。

### 6.3 盯货赛道(Watch)
- 关键词匹配 deal 标题/描述(忽略大小写,可选模糊),命中用户清单。
- 触发条件:命中关键词 **且**(折扣 ≥ 用户 `MIN_DISCOUNT` **或** 价格 ≤ 用户目标价 **或** CCC 判定为近期低点)。
- 折扣解析(尽力猜,不保守拒绝):从标题正则**尽力**提取价格与 `was/RRP/% off`(如 `$X (was $Y)`、`30% off`),抠到就用。真抠不出价格/折扣时,不直接全量放行,而走噪声保护:关键词必须是精确短语命中,或 deal 已达到 `watch.unpriced_min_votes` 的最低热度,或用户显式配置该关键词为"任意命中即提醒"。这样避免 `SSD`、`laptop`、`iPhone` 这类宽词刷屏。

### 6.4 默认阈值
> ⚠️ **当前 `config/settings.yaml` 里的阈值是一组未经真实数据验证的保守起始猜测,不是有依据的最优值。** 上线后必须按实际数据校准:先只发给自己、跑 1 到 2 天,对着"该推没推 / 不该推却推了"纠偏(见实施计划 Phase 10)。

所有阈值(`V1/V2/H/P/HOT_THRESHOLD/MIN_DISCOUNT/窗口长度`)均可在 `settings.yaml` 改,存盘即生效,无需改代码。

---

## 7. Notion 数据模型

### DB: Subscribers(订阅者)
| 字段 | 类型 | 说明 |
|---|---|---|
| Name | Title | 姓名 |
| Email | Email | 邮箱 |
| Telegram Chat ID | Text | Telegram 推送用 |
| Active | Checkbox | 是否启用 |
| Channels | Multi-select | Email / Telegram |
| Subscribe Hot Deals | Checkbox | 是否接收爆款赛道 |
| Watch Keywords | Text(多行) | 每行一个关键词,可带目标价,如 `iPhone 17 Pro <=1800` |
| Min Discount % | Number | 盯货最小折扣 |
| Categories | Multi-select | 可选分类过滤 |
| Max Alerts/Day | Number | 每日上限,默认 10 |
| Quiet Hours | Text | 可选安静时段(按澳洲东部时间 AET 解释;v1 不按人存时区) |

### DB: Sent Log(已发送记录,私有,用于去重)
| 字段 | 类型 | 说明 |
|---|---|---|
| Deal ID | Title | deal 唯一标识 |
| Subscriber | Relation/Email | 收件人 |
| Channel | Select | Email / Telegram |
| Track | Select | Hot / Watch |
| Sent At | Date | 发送时间 |
| Price | Number | 发送时识别到的价格(可空) |
| Discount % | Number | 发送时识别到的折扣(可空) |
| Votes Pos | Number | 发送时正票数 |
| Heat Band | Select | 发送时热度档位,用于判断是否跨档 |
| Re-alert Count | Number | 该 deal 对该订阅者已再提醒次数 |
| Trigger Signature | Text | 规则版本 + 触发原因摘要,便于调试与幂等 |

> 这些个人数据**只在 Notion(私有)**,绝不进公开 repo。

### (可选) DB: Deals 观测库
记录被判为 hot 的 deal 与其评分,便于回看与调参。v1 可选。

---

## 8. 通知内容 (UX)

- **邮件(HTML 模板):** 标题、价格/折扣、票数与涨势(如"过去 1 小时 +28 票")、为什么推(命中规则)、直达链接(OzBargain 帖 + 商家 url)、过期时间。一次多个 deal → 一封摘要列表。底部说明如何去 Notion 管理订阅。
- **Telegram:** 精简文本卡片 + 链接,适合即时阅读。
- 文案克制、信息密度高,不堆形容词。

---

## 9. 隐私 / 安全 / 合规

- **公开 repo 只 commit 非个人数据**(每日一次的 deal 票数历史快照,见 §10.1),不含任何订阅者信息。
- 密钥(`NOTION_TOKEN`、邮件 API key、`TELEGRAM_BOT_TOKEN` 等)走 GitHub Actions Secrets,绝不入库;提供 `.env.example`。
- 个人数据(邮箱、关注、已发送)只存 Notion(私有)。
- 尊重来源 ToS(礼貌抓取):优先 RSS、合理频率;设真实可联系的 User-Agent;带条件请求缓存(`If-Modified-Since`/`ETag`,命中 304 不重复下载);遇 `429`/限速则指数退避;通知里链回 OzBargain 帖子页(`Deal.url`)而非商家直链,让来源拿到流量;不激进抓取;CCC 抓取保守、可随时关闭。
- 不接受、不存储凭证;公开 repo 与日志不存 PII。私有 Notion 只存最小必要 PII(邮箱、Telegram chat id、关注偏好、已发送记录)。
- **公开仓库的 Actions 运行日志对所有人可见:** 日志中绝不打印任何订阅者标识(邮箱、Telegram chat_id、姓名),只输出聚合计数或无意义的 Notion 内部 ID。这是比"密钥不入库"更隐蔽的 PII 泄露面。
- **公开仓库 + Secrets 的攻击面:** 抓取 workflow 只允许 `schedule` 与 `workflow_dispatch` 触发,不使用 `pull_request_target`、不在任何 PR 触发路径中暴露 secrets;`GITHUB_TOKEN` 按最小权限配置(仅"每日落盘 state"需 `contents: write`);第三方 action 用完整 commit SHA 钉版本,防供应链劫持。

---

## 10. 非功能需求

- **时效:** GitHub Actions 定时最快 5 分钟一跑(`*/5`),且高峰常被推迟 5 到 15 分钟。v1 接受该延迟(频率与状态方案见 §10.1);v2 评估迁移到 AWS Lambda + EventBridge 或更准时的外部调度做更紧轮询。
- **成本:** 全部免费层可覆盖(公共仓库 Actions 标准 runner 不限分钟、SMTP/Gmail、Telegram、Notion 免费、CCC 免费)。
- **可靠性:** 用 concurrency 锁防止上次没跑完又触发;关键调用重试;全流程幂等。
- **可维护:** 参数化配置(严格区块用 pydantic `extra="forbid"`——`settings.yaml` 键名拼错即报错、不静默忽略,防"我明明改了怎么没生效";`SourceConfig` 保留 `extra="allow"` 以容纳 `feed_url` 等来源自定义键);来源 adapter 可插拔;日志清晰。

### 10.1 运行频率与状态持久化(2026-06-18 定)

**运行频率:** cron `*/5 * * * *`,全天均匀,不分昼夜。5 分钟是 GitHub Actions 允许的最快间隔;受排队延迟影响,实际触发约 5 到 15 分钟一次。均匀间隔让 velocity 的快照成为规整的等间距时间序列,便于计算 `Δvotes/Δt` 且无夜间断档。用 `concurrency` 锁防止延迟导致的重叠重跑。

**两类"历史"分开存,各自保持干净:**

1. **热状态(velocity 滚动快照)→ GitHub Actions Cache,不进 git,但只作为 best-effort 热缓存。**
   - 文件 `deals_state.json` 结构:`{ deal_key: [ {ts, votes_pos, votes_neg, comment_count}, ... ] }`,只保留最近一个保留窗口(默认 24 小时)的快照,超出即裁剪,文件大小有界。
   - 每轮流程:从 cache 恢复 → 追加本轮快照 → 裁剪过期 → 存回 cache。**全程不产生任何 git commit。**
   - cache key 用 `deals-state-<run_id>` + `restore-keys: deals-state-` 取最近一份。注意 GitHub Actions Cache 是 immutable 且有容量/淘汰策略,因此不能把它当强一致数据库;cache 丢失时从每日落盘历史种子恢复,并把该轮按冷启动/低置信处理。

2. **持久历史(调参回看 + 灾备种子)→ 每天 commit 一次。**
   - 每天(以 AET 计)首次运行时,把整理过的快照落盘到 `data/`(约 1 commit/天)。
   - 双重用途:(a) 给阈值调参留长期数据;(b) cache 丢失时(被清理 / 首次运行)作为恢复种子,velocity 不必从冷启动重来。

**为什么这么设计:** 若每轮都 commit,5 分钟一次 → 公开 repo 一天约 288 个提交,git 历史被刷脏。把"记快照"(高频、走 best-effort cache)与"提交历史"(低频、进 git)解耦后,大多数运行可保持 5 分钟分辨率,而 repo 历史每天只长 1 个提交。隐私边界不变:cache 与 commit 的都是非个人的 deal 票数数据。若后续发现 cache 淘汰影响 hot 判断,优先迁移热状态到可更新的外部 state store(如 Notion 私有表、Gist、S3/R2)。

### 10.2 去重与幂等(2026-06-18 定)

**去重存哪:** 已发送记录(Sent Log)仍在 Notion(属个人数据,必须留在私有库)。

**访问模式(防限流):** 每轮**一次性查询最近去重窗口(默认 7 天)的 Sent Log**,载入内存做本地比对,**不对每个 (deal, 人) 逐条点查**——Notion API 约 3 请求/秒,逐条点查会触发限流且随 Sent Log 增长越来越慢。窗口取 7 天足以覆盖一个 deal 的存活期;超窗记录定期归档/删除,Sent Log 不无限膨胀。

**幂等(防中途崩溃重发):** 每个通道**每成功发出一条就立即写一条 Sent Log**(而非攒到运行末尾批量写),并对写 log 做重试。若 SMTP 已成功但 Notion 写 log 最终失败,下次仍可能重复发送,因此必须记录错误并告警维护者;v1 目标是 at-least-once 发送 + 尽量避免重复,不承诺严格 exactly-once。配合 §10.1 的 `concurrency` 锁防止延迟导致的并发重叠。

**变更再提醒(对应 FR5):** 去重不是"永不再发"。记录上次发送时的关键状态(价格 / 折扣 / 票数档位);新一轮若实质性变好(降价达配置阈值、或票数跨档),且该 deal 对该人的再提醒次数未超 `max_realerts_per_deal`(默认 1),则再推一条并计数。

**每日上限计数:** 复用这份近窗 Sent Log,按 **AET 当天**已发 deal 数判断是否超过 `max_alerts_per_day`(时区见 §14 决策 7)。Quiet hours 内默认不发送非紧急通知;安静时段结束后的下一轮重新评估仍有效且未超过上限的 deal,过期或已失效的 deal 不补发。

---

## 11. 风险与对策

| 风险 | 对策 |
|---|---|
| velocity 滞后,最猛的 deal 已被抢 | 盯货赛道(提前信号)+ 早期爆发规则补偿 |
| Actions 定时延迟 | v1 接受;v2 迁移到更紧的调度 |
| 误报/漏报 | 阈值可调 + 观测库回看迭代 |
| CCC 脆弱 / ToS | adapter 可降级;OzBargain search feed 兜底 |
| 邮件进垃圾箱 | v1 先用 Gmail app password 做低成本验证;后续可加 Telegram 并行或切到信誉更好的发件域 |
| 关键词到 ASIN 摩擦 | v1 让用户贴 Amazon 链接,或用 OzBargain 关键词 feed |

---

## 12. v1 验收标准

- 定时运行;能从 OzBargain 正确解析含票数的 deal。
- 能算 velocity 并按阈值挑出 hot;能按 Notion 关注清单做针对性匹配。
- 能去重并通过邮件发出合并通知;Telegram 设计保留但不纳入 v1 验收。
- 首次运行不回灌历史。
- 密钥不入库,公开 repo 无隐私泄露。

---

## 13. 路线图

- **v1 (MVP,本次):** 上表功能。
- **v1.1:** 调参 + 观测库 + Amazon/CCC 增强。
- **v2:** 更紧的调度(Lambda)、更多来源、更聪明的评分。

---

## 14. 已确认决策(2026-06-18)

1. **第二来源:** CamelCamelCamel AU(可降级,默认先关,增量接入)。
2. **阈值:** 先用本文件第 6 节的默认值跑,据实际数据再调。
3. **Notion:** 由脚本自动建 Subscribers / Sent Log 两个库(需要带建库权限的 integration token)。
4. **通知通道(2026-06-18 修订):** 通道按订阅者实际拥有的来发——有邮箱发邮箱、有 Telegram 发 Telegram、两个都有就都发,**不强制两者都填**。**v1 先只实现邮箱(SMTP,默认 Gmail app password,$0、无需自有域名)**;Telegram 留作后期通道(其 onboarding 较麻烦:用户须先 /start bot,且需把 chat id 对应到 Notion 里的人)。邮件层做成可插拔,日后有自有域名可切 Resend 提升送达率。〔本条取代原"Telegram 为主力"的表述。〕
5. **命名:** 项目 / 包 / 公开 repo 统一用 `bargain-hunter`(本地文件夹改名放到最后,以免打断当前会话的项目关联)。
6. **运行频率与状态存储:** cron 固定 `*/5`(全天均匀);velocity 滚动快照优先从 best-effort GitHub Actions Cache 恢复(不进 git),每天向 repo 落盘一次作调参数据与 cache 灾备种子。详见 §10.1。
7. **时区:** v1 假设订阅者均在澳洲,全系统统一用澳洲东部时间(`Australia/Sydney`,墨尔本与悉尼同一时区,`zoneinfo` 自动含夏令时)计算每日上限重置、安静时段与每日落盘边界;不做按订阅者时区的处理(`Subscriber` 的 Timezone 字段取消,统一时区写在 `config/settings.yaml` 的 `run.timezone`)。
