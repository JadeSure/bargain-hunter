# Bargain Hunter Web 前端计划

- 状态: 规划中
- 日期: 2026-06-26
- 配套文档: `docs/PRD.md`, `docs/IMPLEMENTATION_PLAN.md`

---

## 技术栈

| 层 | 技术 | 部署(现在) | 部署(迁移 AWS) |
|---|---|---|---|
| 前端 | Next.js 15 + TypeScript + Tailwind | Cloudflare Pages | OpenNext + CloudFront + S3 |
| API | Hono (TypeScript) | Cloudflare Worker | AWS Lambda (换 adapter) |
| Auth | Magic Link + Google OAuth | - | - |
| Session / Token | Cloudflare KV | - | DynamoDB / ElastiCache |
| 数据 | Notion (现有 Subscriber DB) | - | 可换 DynamoDB |
| 邮件(Magic Link) | Resend API | - | AWS SES |
| UI 设计 | Claude Design | - | - |

**Python 抓取引擎不动,继续跑 GitHub Actions cron。**

---

## 仓库结构(新增部分)

```
bargain-hunter/
  frontend/                    ← Next.js 项目
    app/
      page.tsx                 ← Landing page (公开)
      login/
        page.tsx               ← 登录页 (Magic Link + Google)
      portal/
        page.tsx               ← 个人设置主页
        keywords/page.tsx      ← 盯货 / 屏蔽关键词管理
        settings/page.tsx      ← 通知设置
      auth/
        callback/page.tsx      ← OAuth / magic link 回调处理
    components/
    lib/
      api.ts                   ← 前端调 portal-worker 的封装
    middleware.ts              ← 保护 /portal/* 路由
    next.config.ts
    package.json
    wrangler.toml              ← Cloudflare Pages 配置

  portal-worker/               ← Hono API Worker
    src/
      index.ts                 ← 入口,路由注册
      middleware/
        auth.ts                ← session 校验 middleware
      routes/
        auth/
          magic-link.ts        ← POST /auth/magic-link, GET /auth/verify
          google.ts            ← GET /auth/google, GET /auth/google/callback
          logout.ts            ← POST /auth/logout
        subscriber.ts          ← GET/PUT /api/me
      lib/
        notion.ts              ← 读写 Notion Subscriber DB
        kv.ts                  ← session / token 操作封装
        email.ts               ← Resend 发 magic link 邮件
    wrangler.jsonc
    package.json

  terraform/                   ← 扩展现有配置
    main.tf                    ← 新增: KV namespace, portal-worker, Pages project
    variables.tf               ← 新增: google_client_id/secret, resend_api_key
```

---

## 实施阶段

### Phase 1 — UI 设计 (Claude Design)

- [ ] Landing page 设计稿
  - Hero: 一句话说清楚产品是什么
  - 功能亮点: 爆款推送 / 关键词盯货 / 精准过滤
  - CTA: 申请加入 / 登录
- [ ] 登录页设计稿
  - Magic Link 输入框
  - Google 登录按钮
- [ ] Portal 设计稿
  - 关键词管理(盯货 / 屏蔽)
  - 通知设置(开关、每日上限、最低折扣、分类)
  - 账号信息

### Phase 2 — 基础设施

- [ ] Terraform: 新增 Cloudflare KV namespace(session + magic link token)
- [ ] Terraform: 新增 portal-worker 资源
- [ ] Terraform: 新增 Cloudflare Pages 项目
- [ ] Terraform: 新增变量(Google OAuth, Resend API key)
- [ ] GitHub Actions: `portal-worker` 部署 workflow
- [ ] GitHub Actions: `frontend` 部署 workflow(Pages)

### Phase 3 — Hono API Worker

- [ ] 项目脚手架: `portal-worker/`,Hono + TypeScript + wrangler
- [ ] KV 封装: session CRUD, magic link token CRUD
- [ ] Notion 封装: 按邮件读 Subscriber, 更新 Subscriber 字段
- [ ] `POST /auth/magic-link`: 生成 token 存 KV,发 Resend 邮件
- [ ] `GET /auth/verify?token=xxx`: 校验 token, 创建 session, 重定向到 portal
- [ ] `GET /auth/google`: 重定向到 Google OAuth
- [ ] `GET /auth/google/callback`: 处理回调, 创建 session
- [ ] `POST /auth/logout`: 清除 session
- [ ] Auth middleware: 校验 session cookie, 注入 user context
- [ ] `GET /api/me`: 返回当前用户 Subscriber 数据
- [ ] `PUT /api/me`: 更新关键词 / 设置, 写回 Notion

### Phase 4 — Next.js 前端

- [ ] 项目脚手架: `frontend/`,Next.js 15 + Tailwind + TypeScript
- [ ] `middleware.ts`: 未登录访问 `/portal/*` 重定向到 `/login`
- [ ] Landing page (`/`): 按设计稿实现
- [ ] 登录页 (`/login`): Magic Link 表单 + Google 登录按钮
- [ ] Auth 回调页 (`/auth/callback`): 处理 magic link / OAuth 跳转
- [ ] Portal 主页 (`/portal`): 概览, 跳转各子页
- [ ] 关键词管理 (`/portal/keywords`): 盯货关键词增删, 屏蔽关键词增删
- [ ] 通知设置 (`/portal/settings`):
  - 开关: 订阅爆款 (`subscribe_hot`)
  - 每日最多推送 (`max_alerts_per_day`, `max_watch_alerts_per_day`)
  - 最低折扣 (`min_discount_percent`)
  - 通知渠道 (`channels`: Email / Telegram)
  - 分类偏好 (`categories`)

### Phase 5 — 收尾

- [ ] 错误处理: API 错误提示, token 过期友好提示
- [ ] 移动端适配
- [ ] 基本 SEO: `<title>`, `<meta description>`, Open Graph
- [ ] 确认临时域名可访问(`*.pages.dev` + `*.workers.dev`)

---

## Portal 管理的字段

对应现有 `Subscriber` 模型,全部可在 portal 里编辑:

| 字段 | 类型 | 说明 |
|---|---|---|
| `watch_keywords` | list[str] | 盯货关键词,每行一个 |
| `block_keywords` | list[str] | 屏蔽关键词,每行一个 |
| `subscribe_hot` | bool | 是否订阅爆款推送 |
| `min_discount_percent` | float | 最低折扣门槛 |
| `max_alerts_per_day` | int | 爆款每日上限 |
| `max_watch_alerts_per_day` | int | 盯货每日上限 |
| `channels` | list[str] | Email / Telegram |
| `categories` | list[str] | 分类偏好 |

`name`, `email`, `telegram_chat_id` 只读展示(不在 portal 里改,避免绕过维护者审核)。

---

## Auth 流程

### Magic Link
```
用户输入邮件 → portal-worker 生成 token(15分钟过期)存 KV
→ Resend 发邮件(含链接) → 用户点链接
→ portal-worker 校验 token → 创建 session cookie → 重定向 /portal
```

### Google OAuth
```
用户点「Google 登录」→ portal-worker 重定向 Google
→ 用户授权 → Google 回调 portal-worker
→ 校验 email 在 Notion Subscriber DB 中存在
→ 创建 session cookie → 重定向 /portal
```

**两种方式都要求邮件在 Notion 订阅者库中存在。** 不接受自助注册,维护者手动添加订阅者。

---

## 迁移到 AWS(备忘)

| 现在 | AWS 替换 |
|---|---|
| Cloudflare Pages | CloudFront + S3(via OpenNext) |
| Cloudflare Worker (Hono) | AWS Lambda(换 `hono/aws-lambda` adapter) |
| Cloudflare KV | DynamoDB 或 ElastiCache |
| Resend | AWS SES |

Hono 业务逻辑代码不需要改动,只换入口 adapter。
