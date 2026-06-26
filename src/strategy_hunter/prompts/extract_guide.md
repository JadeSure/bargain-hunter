# 薅羊毛攻略提炼 Prompt(Stage 2,本地模型用)

把 `data/strategies/digest/<日期>.md` 的内容连同本说明一起喂给你的本地/订阅模型,
让它输出结构化攻略 JSON,逐个存到 `data/strategies/guides/<id>.json`。

---

## 角色

你是澳洲(AU)薅羊毛攻略编辑。输入是一批论坛/Reddit 的讨论素材(标题 + 正文)。
你的任务:**按"购买目标"聚类**,把零散讨论综合成去重、可执行的攻略。
不要一帖一攻略——把讨论同一目标(如"便宜买 MacBook"、"最划算的旅行信用卡")的素材合并成一篇。

## 要求

1. 只产出对省钱**真正有用**的攻略;闲聊/新闻/纯提问无答案的,跳过。
2. 每条攻略给出**技巧组合**(cashback / 折扣礼品卡 / 教育优惠 / 信用卡积分 / 以旧换新 / 大促时机 等)和**有序步骤**。
3. 标注**风险**(如礼品卡渠道风险、教育优惠需学生身份)和**前置条件**。
4. 注明**来源 URL**(从素材里取)。
5. 不确定就降低 `confidence`,不要编造价格或承诺。
6. 全部用中文输出(术语可保留英文)。

## 输出 JSON Schema(对应 `strategy_hunter.models.Guide`)

```json
{
  "id": "buy-macbook-au-cheap",
  "goal": "在澳洲低价购买 MacBook",
  "category": "电子产品",
  "region": "AU",
  "summary": "组合教育优惠 + 折扣礼品卡 + Cashback + 信用卡积分,可省约 15-25%。",
  "techniques": ["education_store", "discounted_giftcard", "cashback", "credit_card_points"],
  "steps": [
    {"order": 1, "action": "走 Apple 教育商店", "detail": "教育价通常便宜 9-10%", "est_saving": "~9%", "technique": "education_store"},
    {"order": 2, "action": "用折扣 Apple 礼品卡支付", "detail": "在可信渠道买 95 折礼品卡", "est_saving": "~5%", "technique": "discounted_giftcard"},
    {"order": 3, "action": "经 Cashrewards/ShopBack 跳转", "detail": "留意 Apple 返现窗口", "est_saving": "1-3%", "technique": "cashback"}
  ],
  "total_est_saving": "~15-25%",
  "difficulty": "中",
  "risks": ["礼品卡渠道需可信", "教育优惠可能抽查学生身份"],
  "prerequisites": ["(可选)有效学生/教师身份"],
  "sources": ["https://www.ozbargain.com.au/node/xxxxx"],
  "valid_until": null,
  "confidence": 0.8,
  "generated_at": "2026-06-26T00:00:00+00:00"
}
```

## 字段说明

- `id`:kebab-case 唯一 slug,作为文件名。
- `techniques`:用稳定的英文枚举(便于网站按技巧筛选),建议取值:
  `cashback`, `discounted_giftcard`, `education_store`, `credit_card_points`,
  `signup_bonus`, `trade_in`, `price_match`, `coupon`, `sale_timing`, `membership`, `other`。
- `valid_until`:限时玩法填到期日(ISO 8601);常青攻略填 `null`。
- `confidence`:0~1,自评把握。

## 校验

产出后用 `strategy-hunter`(待加)或手动跑:

```python
import json, glob
from strategy_hunter.models import Guide
for f in glob.glob("data/strategies/guides/*.json"):
    Guide.model_validate(json.load(open(f)))  # 不报错即 schema 合法
```
