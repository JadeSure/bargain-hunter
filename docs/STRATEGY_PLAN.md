# 薅羊毛攻略聚合 (Strategy Hunter)

- 状态: Stage 1 (采集) 已实现;Stage 2/3 规划中
- 日期: 2026-06-26
- 配套: `docs/PRD.md`, `docs/WEB_PLAN.md`

把散落在论坛 / OzBargain 的「组合薅羊毛攻略」聚合 + AI 提炼成结构化攻略,发布到网站,
让用户不用到处搜。与 `bargain_hunter`(单个 deal 推送)是**两条独立管线**。

---

## 内容分两类

| 类型 | 例子 | 特点 |
|---|---|---|
| 常青攻略 (playbook) | "在澳洲低价买 MacBook" | 相对稳定,SEO 价值高 |
| 限时组合 (live stack) | "现在 X 礼品卡 95 折 + Cashrewards 3%" | 几天过期,可复用 deal pipeline |

---

## 三阶段管线

### Stage 1 — 采集 (GitHub Actions, 每天全自动) ✅

`src/strategy_hunter/`,沿用 `bargain_hunter` 的 `sources/` 适配器模式。

- **源**(`config/settings.yaml` 的 `strategy:` 段可配):
  - OzBargain 论坛:`/forum/1341` Find Me A Bargain、`/forum/38183` Financial(HTML 抓板块 + 主题 OP)
  - Reddit:r/AusFinance、r/AusFrugal、r/fiaustralia(Atom RSS,需 browser UA)
  - Whirlpool:`/forum/153` Shopping、`/forum/150` Finance、`/forum/149` Travel(HTML)
- **相关度过滤**:`relevance.py` 统计省钱信号词命中数,低于 `min_relevance` 丢弃,
  避免把无关新闻/闲聊喂给模型。
- **去重落盘**:每帖一个 JSON,`data/strategies/raw/<source>/<id>.json`;
  仅当 `content_hash` 变化才重写(编辑过的帖子才更新)。
- **digest**:当天新素材按板块分组、按相关度排序,渲染成
  `data/strategies/digest/<AET-date>.md`,供模型一次读完。
- 工作流 `.github/workflows/collect-strategies.yml`,`[skip ci]` 提交语料。

### Stage 2 — 提纯 (本地 / 订阅模型) 🔜

人用 Claude / ChatGPT 等读 digest,按 `src/strategy_hunter/prompts/extract_guide.md`
的 schema,**按购买目标聚类**产出结构化攻略 `data/strategies/guides/<id>.json`
(对应 `strategy_hunter.models.Guide`)。模型后端可插拔(本地 Ollama 亦可)。

产出后用 `python -m strategy_hunter validate-guides` 校验(schema + 语义:
kebab-case id、id 唯一、步骤/来源非空、confidence ∈ 0..1)。

### Stage 3 — 发布 (网站) ✅ 已接入

`frontend/`(Next.js 16 App Router)新增公开攻略区:
- `app/guides/page.tsx` — 列表,按技巧筛选(`?technique=`,服务端渲染)。
- `app/guides/[slug]/page.tsx` — 详情,`generateStaticParams` 在 build 时静态生成(SEO 优先)。
- `lib/guides.ts` — build 时读取 `data/strategies/guides/*.json`,映射 `Guide` 模型;
  语料为空时优雅显示空状态。
- 落地页导航加「薅羊毛攻略」入口;样式复用 `globals.css` 设计 token。

---

## 数据模型

- `CapturedPost`:采集单元(论坛主题 / Reddit 帖),含 source/title/body/board/relevance。
- `Guide`:结构化攻略 = 目标 + 技巧组合 + 有序步骤 + 风险 + 来源 + 有效期 + confidence。
  技巧用稳定英文枚举(cashback / discounted_giftcard / education_store / ...)便于筛选。

---

## 已验证的源结构 (2026-06-26)

- Reddit:`/r/<sub>/<listing>.rss`(JSON 端点 403,RSS 可用,需 browser UA)。
  注意:Reddit 对**数据中心 IP**(如 GitHub Actions)的公共 RSS 反复返回 `429`。
  本地住宅 IP 一般没问题。要在 CI 稳定采集 Reddit,配置 **OAuth(app-only)**:
  在 reddit.com/prefs/apps 建一个 *script* 应用,把 `client_id` / `secret` 存为
  仓库 secrets `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`,workflow 已自动透传。
  没配凭据时该源会在限流时**优雅跳过**(WARNING,不报错、不误触发告警)。
- OzBargain:板块 `/forum/<id>` 列 `/node/<id>` 主题;主题页首个 `div.content` = OP 正文
- Whirlpool:板块 `/forum/<id>` 列 `a.title[href^=/thread/]`;主题页首个 `div.replytext` = OP

---

## 后续 (Roadmap)

- 本地提纯命令 + guide schema 校验 + MDX 渲染
- embeddings 聚类后再综合(同目标多帖合并,质量更高)
- 有效期衰减:来源 deal 过期 → 标记"可能过时"
- PR 审核闸门:模型产出开 PR,维护者合并后才上线
- 二期源:贴吧 / 小红书(反爬,建议本地半手动)
- 与 deal pipeline 交叉喂养(常青攻略 ↔ 限时组合)
