# Bargain Hunter

定时在 GitHub Actions 上抓取折扣信息(先做 OzBargain),用"涨势(velocity)"和"个人盯货清单"两条赛道判断哪些 deal 真正值得出手,再通过邮件(v1;Telegram 后期)推送给 Notion 里登记的订阅者。

完整设计见 [`docs/PRD.md`](docs/PRD.md) 与 [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)。

## 两条赛道

- **爆款 (Hot):** 投票涨速 + 票数 + 发布时长,过阈值才推给所有人。高精度、低频。
- **盯货 (Watch):** 命中你在 Notion 里登记的关键词且有折扣,只推给关注该商品的人。

## 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
```

## 配置

- 复制 `.env.example` 为 `.env` 填入密钥(Notion / SMTP;Telegram 后期可选)。`.env` 不入库。
- 可调参数(阈值、窗口、来源开关)都在 `config/settings.yaml`,改完即生效。

## 状态与隐私

- `data/deals_state.json` 存 deal 票数滚动快照(非个人数据,用于算 velocity)。热状态走 best-effort GitHub Actions Cache,每天向 repo 落盘一次作调参与灾备种子,避免高频提交刷脏历史(见 PRD §10.1)。
- 订阅者、关注清单、已发送记录只存私有 Notion;公开仓库不含任何个人数据。

## 运行(开发中)

完整 CLI 入口与 GitHub Actions 工作流将在后续阶段加入(见实施计划 Phase 8-9)。当前已可直接验证抓取与解析:

```bash
python -c "from bargain_hunter.sources.ozbargain import OzBargainSource as S; print(len(S().fetch()), 'deals fetched')"
```

## 当前进度

OzBargain 抓取与解析已完成并有测试覆盖。后续:状态/velocity、评分、盯货匹配、Notion、通知、编排、Actions。
