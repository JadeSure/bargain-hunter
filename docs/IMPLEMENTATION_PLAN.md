# Bargain Hunter 实施计划

- 状态：**v1.1 上线**（2026-06-24）
- 配套文档：`docs/PRD.md`

---

## 1. 技术栈

| 领域 | 选择 | 备注 |
|---|---|---|
| 语言 | Python 3.13 | venv at `.venv/` |
| 调度 | GitHub Actions cron `*/5` + cron-job.org 外部触发 | GH cron 不可靠，外部触发保底 |
| RSS 解析 | `defusedxml` | 防 XXE，支持 `ozb:meta` 命名空间 |
| HTTP | `httpx` | 同步，用于 Notion API 直调 |
| 数据模型 | `pydantic` v2，`extra="forbid"` | 严格模式 |
| Notion | `notion-client` + 直接 `httpx` | notion-client 不含 `databases.query()`，需直调；API 版本锁定 `2022-06-28` |
| 邮件 | SMTP（Gmail app password） | 邮件层可插拔，日后可切 Resend |
| 模板 | `Jinja2` | 响应式 HTML email |
| 测试/质量 | `pytest` + `ruff`（lint + format） | 36 个测试，全部通过 |
| 反馈 Worker | Cloudflare Workers（JS） | HMAC 签名，写 Notion Feedback DB |
| 基础设施 | Terraform + Cloudflare R2 state | push 到 main 自动 apply |
| Telegram | 后期通道，v1 未实现 | |

---

## 2. 仓库结构

```
bargain-hunter/
  README.md
  docs/
    PRD.md
    IMPLEMENTATION_PLAN.md
  pyproject.toml
  .env.example
  .github/workflows/
    hunt.yml                   # 主抓取 + 通知 workflow
    terraform-feedback.yml     # Cloudflare Worker 自动部署
  config/
    settings.yaml              # 阈值等可调参数（含 alerting、sources）
  data/
    deals_state.json           # 票数滚动快照（热状态走 Actions Cache，每日落盘）
    alert_state.json           # 维护者报警节流状态（gitignored）
  feedback-worker/
    src/index.js               # Cloudflare Worker：接收 👍/👎，HMAC 验证，写 Notion
  terraform/
    main.tf                    # Worker + subdomain 资源
    variables.tf               # 含 feedback_hmac_secret（sensitive）
    backend.hcl                # R2 state backend（gitignored，CI 动态写入）
    terraform.tfvars           # 非敏感变量（gitignored）
  scripts/
    setup_notion.py            # 自动建 Subscribers / Sent Log / Feedback 三库
  src/bargain_hunter/
    __init__.py
    __main__.py
    main.py                    # 编排入口
    models.py                  # Deal / Subscriber / Notification (pydantic)
    config.py                  # settings.yaml + env 加载，load_dotenv()
    state.py                   # 票数快照读写 + 冷启动判定
    alert_throttle.py          # 维护者报警节流（data/alert_state.json）
    matching.py                # 盯货关键词匹配（含到期时间解析）
    observations.py            # 观测记录（可选）
    sources/
      base.py
      ozbargain.py             # RSS + ozb:meta 解析，HTML 清理
      camelcamelcamel.py       # CCC AU top_drops RSS 解析
    scoring.py                 # velocity + hot score + 折扣解析
    subscribers.py             # 从 Notion 读订阅者
    dedup.py                   # 已发记录（Notion 读写）
    notify/
      email.py                 # SMTP 发送
      render.py                # Jinja2 渲染 + HMAC 签名 feedback URL
    templates/
      email.html.j2
  tests/
    test_ozbargain.py
    test_scoring.py
    test_matching.py
    test_observations.py
    test_state.py
```

---

## 3. 实施阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 0 | 脚手架：repo、pyproject.toml、ruff、目录骨架 | ✅ |
| Phase 1 | 数据模型 + 配置：Deal/Subscriber/Notification；settings.yaml | ✅ |
| Phase 2 | OzBargain adapter：RSS 拉取、ozb:meta 解析、HTML 清理、时区标准化 | ✅ |
| Phase 3 | 状态快照 + 冷启动：deals_state.json，Actions Cache，每日落盘 | ✅ |
| Phase 4 | 评分 + 折扣解析：velocity、hot score、标题价格正则 | ✅ |
| Phase 5 | 盯货匹配：关键词/目标价/到期时间（`@HH:MM` / `@YYYY-MM-DDTHH:MM`） | ✅ |
| Phase 6 | Notion 集成：setup_notion.py 建库；读 Subscribers；写 Sent Log | ✅ |
| Phase 7 | 通知：Jinja2 HTML email，SMTP，摘要合并，频率上限 | ✅ |
| Phase 8 | 编排 main.py：全流程串联，幂等，dry-run，maintainer alert | ✅ |
| Phase 9 | GitHub Actions：cron，concurrency 锁，cache，secrets 注入 | ✅ |
| Phase 10 | 上线：Notion + SMTP 接真实环境，cron-job.org 外部触发，订阅者入库 | ✅ |
| Phase 11 | v1.1：CCC 来源、Watch 简化、报警节流、HMAC feedback、Cloudflare Worker + Terraform CI | ✅ |

---

## 4. v1.1 新增功能（2026-06-24）

### CamelCamelCamel AU
- `sources/camelcamelcamel.py` 解析 `au.camelcamelcamel.com/top_drops/feed`
- 标题正则：`"Product Name - down 18.16% ($5.99) to $26.99 from $32.98"`
- votes=0（无社区投票），噪音守门改用 `discount_percent >= min_discount_percent`
- 商家 URL 指向 `amazon.com.au/dp/{ASIN}`

### Watch 匹配简化
- 去掉"必须有折扣"条件，只用票数做噪音守门（`min_votes=5`）
- CCC 来源 fallback：votes OR discount 任一通过即可（因为 CCC 没有票数）
- 可选价格上限（`<=PRICE`）仍然支持

### 维护者报警节流
- `alert_throttle.py`：状态持久化到 `data/alert_state.json`（随 Actions Cache 一起保留）
- 策略：连续失败 ≥3 次 **且** 距上次发送 ≥1 小时才触发
- 成功运行自动重置计数器

### HMAC 签名 feedback 链接
- `notify/render.py`：`HMAC-SHA256(secret, "{deal_key}|{verdict}|{email}")` → 32 char hex
- 邮件模板用预签名的 `item.feedback_up_url` / `item.feedback_down_url`
- Worker 端用 Web Crypto API 验证 `?t=` 参数；无效签名返回 403

### Cloudflare Worker + Terraform CI/CD
- `feedback-worker/src/index.js`：无依赖 ES module，直接 content_file 上传
- `terraform/main.tf`：`cloudflare_workers_script` + `cloudflare_workers_script_subdomain`
- R2 bucket 存 Terraform state（S3-compatible backend）
- `terraform-feedback.yml`：push 到 main（触及 `terraform/**` 或 `feedback-worker/src/**`）自动 `init → fmt → validate → plan → apply`；PR 只跑 plan

---

## 5. 关键实现决策记录

**Notion API 兼容性**
`notion-client` 所有版本均不含 `databases.query()`；`databases.update()` 会静默丢弃 `properties`。
解决方案：全部改用 `httpx` 直调，API 版本锁定 `2022-06-28`。

**GitHub Actions cron 不可靠**
`*/5` 在低活跃 public repo 上会被 GitHub 跳过或延迟 30-60 分钟。
解决方案：cron-job.org 每 5 分钟 POST 触发 `workflow_dispatch`，GH cron 作为保底。
所需权限：GitHub Fine-grained PAT，`Actions: Read and write`。

**关键词到期时间**
`@HH:MM` 解析为当天 AET 时间，`@YYYY-MM-DDTHH:MM` 解析为绝对时间（均转 UTC 存储）。
`now >= expiry` 时跳过该关键词（边界为过期）。

**时区**
所有内部时间为 UTC tz-aware。用户展示用 `Australia/Sydney`。

**`.env` 加载**
`load_dotenv()` 在 `config.py` 中实现，不覆盖已有环境变量，GitHub Secrets 始终优先。

**Terraform state 选 R2 不选 S3**
免费，无跨区出口费，与 Cloudflare 账号绑定。R2 endpoint 用 S3-compatible backend；`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` 实为 R2 API token，名称是 Terraform S3 backend 的固定约定。

**非敏感 Terraform 变量硬编码进 workflow**
`cloudflare_account_id`、`feedback_db_id`、R2 endpoint 均为非敏感固定值，直接写进 YAML；避免 GitHub Variables 查询偶发失败，也减少运维负担。

---

## 6. 测试覆盖

| 文件 | 测试数 | 覆盖点 |
|---|---|---|
| `test_ozbargain.py` | 5 | RSS 解析、时区、HTML 清理 |
| `test_scoring.py` | 13 | 折扣解析、velocity、hot score 边界 |
| `test_matching.py` | 18 | 关键词匹配、目标价、噪音守门、关键词到期 |
| `test_observations.py` | — | 观测记录 |
| `test_state.py` | — | 快照读写 |
| **合计** | **36+** | 全部通过 |

---

## 7. 待办（v1.2 方向）

| 优先级 | 项目 | 说明 |
|---|---|---|
| 高 | 阈值校准 | 跑 1–2 周后对着 Sent Log 标注"该推/不该推"，用数据调整 `hot_threshold`、`min_votes`、`early_burst_*` |
| 中 | Feedback 数据闭环 | 将 👍/👎 数据汇总，验证哪类 deal 订阅者真正感兴趣，反哺阈值调整 |
| 中 | 邮件扫描器误点监控 | Safe Links / Proofpoint 等安全代理可能预点 feedback 链接；HMAC 已防垃圾写入，但需监控 Notion Feedback DB 是否有异常早于用户的记录 |
| 低 | Telegram 通道 | 已留接口，用户需先 /start bot 获取 chat_id |
| 低 | 更可靠调度 | AWS Lambda + EventBridge（v2）；当前 GH cron 偶发延迟 |
| 低 | observations 缓存路径 | 确认 `data/observations/` 是否纳入 Actions Cache 路径（hunt.yml） |
