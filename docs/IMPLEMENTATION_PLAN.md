# Bargain Hunter 实施计划

- 状态:草稿 v0.1,待审批
- 日期:2026-06-18
- 配套文档:`docs/PRD.md`

---

## 1. 技术栈

- **语言:** Python 3.12
- **调度:** GitHub Actions(cron,公共仓库)
- **RSS/XML 解析:** `defusedxml`(直接解析,可读取 OzBargain 自定义的 `ozb:meta` 命名空间块,且防 XXE)
- **HTTP:** `httpx`
- **数据模型/校验:** `pydantic`
- **Notion:** `notion-client`
- **邮件:** SMTP(默认 Gmail app password,$0、无需自有域名);邮件层可插拔,日后有自有域名再切 Resend 等服务提升送达率
- **Telegram:** Telegram Bot API(经 `httpx`),**后期通道**(v1 先做邮件,见 PRD §14 决策 4)
- **模板:** `Jinja2`
- **测试/质量:** `pytest`、`ruff`(含 formatter,不再单列 black)

---

## 2. 仓库结构(建议)

```
bargain-hunter/
  README.md
  docs/
    PRD.md
    IMPLEMENTATION_PLAN.md
  pyproject.toml
  .env.example
  .github/workflows/hunt.yml
  config/
    settings.yaml             # 阈值等可调参数
  data/
    deals_state.json          # 状态:非个人 deal 票数滚动快照(热状态走 best-effort Actions Cache,每日落盘一次)
  src/bargain_hunter/
    __init__.py
    main.py                   # 入口:编排一次完整运行
    models.py                 # Deal / Subscriber / Notification (pydantic)
    config.py                 # 读 settings + env
    state.py                  # 读写 deal 快照历史 + 冷启动判定
    sources/
      base.py                 # Source adapter 接口
      ozbargain.py            # RSS + ozb:meta 解析
      camelcamelcamel.py      # 第二来源(可降级)
    scoring.py                # velocity + hot score + 折扣解析
    matching.py               # 盯货关键词匹配
    subscribers.py            # 从 Notion 读订阅者/偏好
    dedup.py                  # 已发送记录(Notion 读写)
    notify/
      email.py
      telegram.py
      render.py               # Jinja2 渲染 + 合并摘要
    templates/
      email.html.j2
      telegram.md.j2
  tests/
    fixtures/                 # 固定 RSS/HTML 样本
    test_ozbargain.py
    test_scoring.py
    test_matching.py
```

---

## 3. 实施阶段(逐步,带验收)

每个阶段做完即可运行/验证,不一次性堆完再测。

- **Phase 0 — 脚手架:** repo init、`pyproject.toml`、ruff(含 formatter)、CI lint、`.env.example`、README、目录骨架。(若同意)把 `bargin` 改为 `bargain`。
- **Phase 1 — 数据模型 + 配置:** `Deal / Subscriber / Notification` 模型;`settings.yaml` + env 加载。
- **Phase 2 — OzBargain adapter:** 拉 RSS、解析 `ozb:meta`、标准化为 `Deal`;用固定 RSS 样本写单测。
- **Phase 3 — 状态快照 + 冷启动:** 每轮把票数快照写入 `deals_state.json` 并经 best-effort GitHub Actions Cache 跨 run 恢复(每天向 repo 落盘一次作为调参数据与灾备种子);首跑或 cache 丢失时只记录/低置信处理,不回灌历史通知;velocity 计算就绪。状态持久化细节见 PRD §10.1。
- **Phase 4 — 评分 + 折扣解析:** hot score 算法 + 标题价格/折扣正则;阈值走配置;单测覆盖边界。
- **Phase 5 — 盯货匹配:** 关键词 / 目标价 / 最小折扣匹配;单测。
- **Phase 6 — Notion 集成:** **脚本自动建** Subscribers / Sent Log 两库;读 Subscribers;一次性读取近窗 Sent Log;写 Sent Log 时包含价格/折扣/票数档位/re-alert count/trigger signature,用于去重与变更再提醒。
- **Phase 7 — 通知:** Jinja2 模板;**v1 先做 SMTP 邮件**(默认 Gmail app password,邮件层可插拔,日后可切 Resend 等服务),Telegram 作为后期通道;多 deal 合并摘要;频率上限与 quiet hours。先 `--dry-run`(只打印)验证,再接真实发送。
- **Phase 8 — 编排 main.py:** 串起全流程;幂等;错误处理;运行摘要日志。
- **Phase 9 — GitHub Actions:** workflow cron `*/5`,concurrency 锁,cache 恢复/保存热状态 + 每日落盘 state,secrets 注入,`workflow_dispatch` 便于手动测试;先 dry-run 跑几轮看日志。
- **Phase 10 — 上线与调参:** 接真 Notion + 真发送,先只发给你自己,观察 1 到 2 天调阈值,再开放给 10 人。

---

## 4. 需要你 / 外部准备的东西(README 会写清步骤)

- **Notion:** 建 integration 拿 token(给它建库权限);**建库由脚本自动完成**,你只需把目标页面分享给该 integration 并提供页面 ID。
- **SMTP:** 准备 Gmail app password 或其他 SMTP 凭据;v1 不要求自有域名或 Resend。
- **Telegram(后期):** 用 BotFather 建 bot 拿 token;每个用户跟 bot 发一句话以获取各自 chat id(我提供获取 chat id 的小工具/说明)。
- **GitHub:** 建 public repo,配 v1 Secrets(`NOTION_TOKEN`、`SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`ALERT_FROM_EMAIL`、`MAINTAINER_EMAIL` 等);Telegram/Resend secrets 后期再加。

---

## 5. 测试策略

- 固定 RSS/HTML 样本做单测,离线可复现。
- `scoring` / `matching` 为纯函数,重点覆盖边界。
- Notion / 邮件用 mock + `--dry-run`;Telegram 到后期通道实现时再加 mock 覆盖。
- 提供一个端到端 `--dry-run` 模式:打印"将要发送的内容",不真正发出。

---

## 6. 第一步建议

经你审批后,从 **Phase 0 + Phase 1** 开始:把仓库骨架、依赖、配置、数据模型搭好并能 `ruff`/`pytest` 跑通空壳,再进入 OzBargain adapter。每个 Phase 完成我都会停下让你看。
