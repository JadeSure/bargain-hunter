# Cloudflare vs AWS 服务对比

以 AWS 为基准对照 Cloudflare 的完整服务列表，重点标注免费额度差异。

---

## Serverless 计算

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 边缘 Serverless | **Workers** — 永久免费：100,000 请求/天，10ms CPU/请求，运行于 300+ PoP 全球边缘，JS/TS/WASM（V8 隔离） | **Lambda** — 永久免费：1,000,000 请求/月，400,000 GB-秒，单 Region，支持更多语言运行时 | 各有所长（CF 更快/边缘，AWS 语言更多） |
| CDN 边缘函数 | **Workers** — 永久免费，本身就运行在边缘，无额外计费 | **Lambda@Edge**（无免费额度）/ **CloudFront Functions**（2M 次/月免费）— Lambda@Edge 按调用 + 时长额外计费 | **CF 胜出** |

---

## 对象存储

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 对象存储 | **R2** — 永久免费：10 GB 存储，100 万次 A 类操作（PUT/DELETE），1000 万次 B 类操作（GET），**出流量完全免费 ✓**，兼容 S3 API | **S3** — 12 个月免费：5 GB 存储，20,000 次 GET，2,000 次 PUT，**出流量 $0.09/GB ✗**，期满后全面收费 | **CF 显著胜出（出流量免费是核心差距）** |

---

## 数据库 & KV 存储

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 键值存储 | **Workers KV** — 永久免费：100,000 次读取/天，1,000 次写入/天，1 GB 存储，全球边缘读取（最终一致） | **DynamoDB** — 永久免费：25 GB 存储，25 WCU + 25 RCU/秒，约 200 万次写/月，强一致可选 | **AWS 胜出（DynamoDB 写入额度更高）** |
| 关系型数据库 | **D1** — 永久免费：5 GB 存储，2500 万行读取/天，10 万行写入/天，基于 SQLite（无法替代生产级 PG） | **RDS** — 12 个月免费：t3.micro 750 小时/月，20 GB 存储，MySQL/PostgreSQL/MariaDB，期满后约 $15–30/月 | **CF 胜出（D1 永久免费，但仅 SQLite）** |
| 有状态边缘对象 | **Durable Objects** — 永久免费（有限）：400,000 GB-秒/月，100 万次请求/月，适合实时协作/聊天/游戏 | 无直接对标（类似 DynamoDB + Lambda 组合，但非边缘） | **CF 独有** |
| 数据库连接池 | **Hyperdrive** — 永久免费，让 Workers 高效连接外部 PostgreSQL，连接池 + 全局查询缓存 | **RDS Proxy** — 无免费额度，约 $0.015/vCPU-小时 | **CF 胜出** |

---

## CDN & 网络

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 内容分发网络 | **CDN** — 永久免费：**带宽无限制 ✓**，自动 HTTPS，HTTP/3 + QUIC，Brotli 压缩 | **CloudFront** — 永久免费（限量）：1 TB 流量/月 + 1000 万次请求，超出后 $0.0085–0.02/GB | **CF 显著胜出（无限带宽差距悬殊）** |

---

## 静态站点 & 前端托管

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 静态站点托管 | **Pages** — 永久免费：无限站点，500 次构建/月，**带宽无限制 ✓**，支持 Next.js / Astro / SvelteKit 等 | **Amplify Hosting** — 12 个月免费：15 GB 流量/月，1,000 构建分钟/月，5 GB 存储，期满后按量计费 | **CF 胜出** |

---

## DNS

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 托管 DNS | **DNS** — 永久免费：无限域名，无限 DNS 查询，全球任播网络（极低延迟），DNSSEC 支持 | **Route 53** — **无免费额度**：$0.50/托管区域/月，$0.40/百万 DNS 查询，健康检查 $0.50/月起 | **CF 显著胜出（Route 53 完全不免费）** |

---

## 安全

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| Web 应用防火墙 | **WAF** — 永久免费（基础规则）：基础规则集 + 速率限制免费，托管规则集需付费计划 | **AWS WAF** — **无免费额度**：$5/月/WebACL，$1/百万次请求，托管规则集额外收费 | **CF 显著胜出** |
| DDoS 防护 | **DDoS Protection** — 永久免费：**无限流量防护 ✓**，L3/L4/L7 全覆盖，默认开启 | **Shield Standard**（免费，仅基础 L3/L4）/ **Shield Advanced**（$3,000/月起，L7 还需额外配 WAF） | **CF 显著胜出** |
| CAPTCHA / Bot 防护 | **Turnstile** — 永久免费：100 万次验证/月，无摩擦体验，替代 Google reCAPTCHA | 无直接对标（WAF Bot Control 需付费，通常集成第三方） | **CF 独有** |
| SSL/TLS 证书 | **Universal SSL** — 永久免费：自动签发和续期，通配符证书需付费计划 | **ACM** — 永久免费：配合 CloudFront/ALB 完全免费，EC2 直接挂载需付费 | 基本持平 |

---

## 身份与零信任访问

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| Zero Trust 访问控制 | **Access / ZTNA** — 永久免费：50 用户免费，SSO 集成（Google/GitHub/Okta），适合非 AWS 资源的零信任管控 | **IAM Identity Center** — 永久免费（主要面向 AWS 内部资源）/ **Cognito** 50,000 MAU 免费 | 场景不同（CF 适合非 AWS 资源） |
| 内网穿透隧道 | **Tunnel** — 永久免费：加密隧道到 Cloudflare 边缘，类似 ngrok 但更稳定，无带宽限制 | **Site-to-Site VPN** — **无免费额度**：$0.05/小时/连接，约 $36/月，配置复杂 | **CF 显著胜出** |

---

## 消息队列

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 消息队列 | **Queues** — 永久免费：100 万次消息操作/月，与 Workers 深度集成，自动重试 | **SQS** — 永久免费：100 万次请求/月，标准队列 + FIFO，成熟稳定，生态丰富 | 基本持平 |

---

## AI 推理

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 托管 AI 推理 | **Workers AI** — 永久免费（有限）：每日免费神经元额度，LLaMA/Whisper/Stable Diffusion 等，边缘运行低延迟 | **Bedrock** — **无免费额度**：按 Token 付费，Claude/Llama/Titan 等，模型选择更丰富 | **CF 有免费额度** |

---

## 媒体处理

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 视频存储 & 流媒体 | **Stream** — 永久免费（有限）：1,000 分钟存储 + 1,000 分钟传输/月，超出 $5/1000 分钟 | **S3 + MediaConvert** — MediaConvert 无免费额度：$0.0075/分钟起，需多服务组合，功能更强但配置复杂 | **CF 有免费额度** |
| 图片优化 | **Images** — 永久免费（有限）：5,000 张原始图存储，10 万次图片分发/月，自动 WebP/AVIF 转换 | 无托管图片优化服务（需自行搭建 Lambda + Sharp，或使用第三方图片 CDN） | **CF 独有** |

---

## 邮件

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 邮件路由 / 收发 | **Email Routing** — 永久免费：无限路由规则，将 @yourdomain.com 转发到任意邮箱。⚠️ 仅路由，不能主动发送邮件 | **SES** — 永久免费（有限）：从 EC2 发送 62,000 封/月免费，其他 $0.10/1000 封，可接收 + 发送 | 场景不同（CF 路由，AWS 收发） |

---

## 分析 & 监控

| 类别 | Cloudflare | AWS | 免费胜出 |
|------|-----------|-----|---------|
| 流量分析 | **Analytics** — 永久免费：无采样完整流量数据，无 Cookie（符合 GDPR），Workers Analytics Engine 支持自定义指标 | **CloudWatch** — 永久免费（有限）：10 个自定义指标，5 GB 日志摄取/月，主要面向基础设施监控 | 场景不同（CF 看流量，AWS 看基础设施） |

---

## Cloudflare 没有的服务（AWS 独有）

| AWS 服务 | 说明 |
|---------|------|
| EC2 / ECS / EKS | 通用虚拟机、容器运行时。CF 没有 VM，Workers 是 V8 隔离，限制较多。 |
| RDS (PostgreSQL/MySQL) | 生产级托管关系型数据库。CF D1 是 SQLite，无法替代。 |
| SageMaker / Bedrock | 完整的 ML 训练平台和丰富的模型选择。CF Workers AI 仅做轻量推理。 |
| Kinesis / MSK | 实时数据流处理。CF Queues 是简单消息队列，不是流式计算。 |
| ELB / ALB | 内部应用负载均衡器，面向 VPC 内服务路由。 |
| X-Ray / CloudWatch APM | 分布式链路追踪、完整基础设施监控体系。 |
| VPC / PrivateLink | 私有网络、子网隔离、内部服务安全互联。CF 没有 VPC 概念。 |
| Step Functions | 复杂工作流编排，多步骤状态机。CF 暂无等效服务。 |

---

## 总结

Cloudflare 不是 AWS 的替代品，而是很好的**边缘层补充**。常见组合是：Cloudflare 做 CDN + DNS + WAF + DDoS（零额外成本），AWS 做后端计算 + 数据库 + 容器。

纯静态站点或轻量 API 可以完全跑在 Cloudflare 上，成本接近零。最值得关注的成本节省点：

- **R2 出流量免费**：对比 S3 的 $0.09/GB 差距显著
- **CDN 带宽无限制**：CloudFront 超出 1TB 后开始计费
- **WAF + DDoS 免费**：AWS 对应服务完全收费
- **DNS 免费**：Route 53 没有免费层
