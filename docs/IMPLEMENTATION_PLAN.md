# Bargain Hunter 实施计划

- 状态：**完成 v1.0**（2026-06-19）
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
  .github/workflows/hunt.yml
  config/
    settings.yaml             # 阈值等可调参数
  data/
    deals_state.json          # 票数滚动快照（热状态走 Actions Cache，每日落盘）
  scripts/
    setup_notion.py           # 自动建 Subscribers + Sent Log 两库
  src/bargain_hunter/
    __init__.py
    __main__.py
    main.py                   # 编排入口
    models.py                 # Deal / Subscriber / Notification (pydantic)
    config.py                 # settings.yaml + env 加载，load_dotenv()
    state.py                  # 票数快照读写 + 冷启动判定
    sources/
      ozbargain.py            # RSS + ozb:meta 解析，HTML 清理
    scoring.py                # velocity + hot score + 折扣解析
    matching.py               # 盯货关键词匹配（含到期时间解析）
    subscribers.py            # 从 Notion 读订阅者
    dedup.py                  # 已发记录（Notion 读写）
    notify/
      email.py                # SMTP 发送
      render.py               # Jinja2 渲染 + 摘要合并
    templates/
      email.html.j2
  tests/
    test_ozbargain.py
    test_scoring.py
    test_matching.py
```

---

## 3. 实施阶段（全部完成）

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 0 | 脚手架：repo、pyproject.toml、ruff、目录骨架 | ✅ |
| Phase 1 | 数据模型 + 配置：Deal/Subscriber/Notification；settings.yaml | ✅ |
| Phase 2 | OzBargain adapter：RSS 拉取、ozb:meta 解析、HTML 清理、时区标准化 | ✅ |
| Phase 3 | 状态快照 + 冷启动：deals_state.json，Actions Cache，每日落盘 | ✅ |
| Phase 4 | 评分 + 折扣解析：velocity、hot score、标题价格正则 | ✅ |
| Phase 5 | 盯货匹配：关键词/目标价/折扣/到期时间（`@HH:MM` / `@YYYY-MM-DDTHH:MM`） | ✅ |
| Phase 6 | Notion 集成：setup_notion.py 建库；读 Subscribers；写 Sent Log | ✅ |
| Phase 7 | 通知：Jinja2 HTML email，SMTP，摘要合并，频率上限 | ✅ |
| Phase 8 | 编排 main.py：全流程串联，幂等，dry-run，maintainer alert | ✅ |
| Phase 9 | GitHub Actions：cron，concurrency 锁，cache，secrets 注入 | ✅ |
| Phase 10 | 上线：Notion + SMTP 接真实环境，cron-job.org 外部触发，订阅者入库 | ✅ |

---

## 4. 关键实现决策记录

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

---

## 5. 测试覆盖

| 文件 | 测试数 | 覆盖点 |
|---|---|---|
| `test_ozbargain.py` | 5 | RSS 解析、时区、HTML 清理 |
| `test_scoring.py` | 13 | 折扣解析、velocity、hot score 边界 |
| `test_matching.py` | 18 | 关键词匹配、目标价、噪音守门、关键词到期 |
| **合计** | **36** | 全部通过 |
