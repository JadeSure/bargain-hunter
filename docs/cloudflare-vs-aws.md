# Cloudflare vs AWS Service Comparison

A full Cloudflare service list benchmarked against AWS equivalents, with particular attention to free tier differences.

---

## Serverless Compute

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Edge Serverless | **Workers** — always free: 100,000 requests/day, 10ms CPU/request, runs at 300+ PoPs worldwide, JS/TS/WASM (V8 isolates) | **Lambda** — always free: 1,000,000 requests/month, 400,000 GB-seconds, single region, more language runtimes | Each has its strengths (CF faster/edge, AWS more languages) |
| CDN edge functions | **Workers** — always free, runs on the edge by design, no extra charges | **Lambda@Edge** (no free tier) / **CloudFront Functions** (2M invocations/month free) — Lambda@Edge billed extra per invocation + duration | **CF wins** |

---

## Object Storage

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Object storage | **R2** — always free: 10 GB storage, 1M Class A operations (PUT/DELETE), 10M Class B operations (GET), **egress completely free ✓**, S3-compatible API | **S3** — 12-month free tier: 5 GB storage, 20,000 GET requests, 2,000 PUT requests, **egress $0.09/GB ✗**, then full price | **CF wins decisively (free egress is the core difference)** |

---

## Database & KV Storage

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Key-value store | **Workers KV** — always free: 100,000 reads/day, 1,000 writes/day, 1 GB storage, globally distributed reads (eventually consistent) | **DynamoDB** — always free: 25 GB storage, 25 WCU + 25 RCU/second, ~2M writes/month, optional strong consistency | **AWS wins (DynamoDB write quota is higher)** |
| Relational database | **D1** — always free: 5 GB storage, 25M row reads/day, 100K row writes/day, SQLite-based (no replacement for production-grade PG) | **RDS** — 12-month free tier: t3.micro 750 hours/month, 20 GB storage, MySQL/PostgreSQL/MariaDB, then ~$15–30/month | **CF wins (D1 always free, but SQLite only)** |
| Stateful edge objects | **Durable Objects** — always free (limited): 400,000 GB-seconds/month, 1M requests/month, suited for real-time collaboration/chat/gaming | No direct equivalent (closest is DynamoDB + Lambda, but not edge-native) | **CF exclusive** |
| Database connection pooling | **Hyperdrive** — always free, lets Workers efficiently connect to external PostgreSQL, connection pooling + global query caching | **RDS Proxy** — no free tier, ~$0.015/vCPU-hour | **CF wins** |

---

## CDN & Networking

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Content delivery network | **CDN** — always free: **unlimited bandwidth ✓**, automatic HTTPS, HTTP/3 + QUIC, Brotli compression | **CloudFront** — always free (capped): 1 TB traffic/month + 10M requests, then $0.0085–0.02/GB | **CF wins decisively (unlimited bandwidth is a massive gap)** |

---

## Static Sites & Frontend Hosting

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Static site hosting | **Pages** — always free: unlimited sites, 500 builds/month, **unlimited bandwidth ✓**, supports Next.js / Astro / SvelteKit etc. | **Amplify Hosting** — 12-month free tier: 15 GB traffic/month, 1,000 build minutes/month, 5 GB storage, then pay-per-use | **CF wins** |

---

## DNS

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Managed DNS | **DNS** — always free: unlimited domains, unlimited DNS queries, global anycast network (very low latency), DNSSEC support | **Route 53** — **no free tier**: $0.50/hosted zone/month, $0.40/million DNS queries, health checks from $0.50/month | **CF wins decisively (Route 53 has zero free tier)** |

---

## Security

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Web Application Firewall | **WAF** — always free (basic rules): basic ruleset + rate limiting free, managed rulesets require a paid plan | **AWS WAF** — **no free tier**: $5/month/WebACL, $1/million requests, managed rulesets billed separately | **CF wins decisively** |
| DDoS protection | **DDoS Protection** — always free: **unlimited traffic mitigation ✓**, L3/L4/L7 coverage, enabled by default | **Shield Standard** (free, basic L3/L4 only) / **Shield Advanced** ($3,000/month+, L7 requires separate WAF configuration) | **CF wins decisively** |
| CAPTCHA / Bot protection | **Turnstile** — always free: 1M validations/month, friction-free experience, replaces Google reCAPTCHA | No direct equivalent (WAF Bot Control requires payment; typically integrates third-party solutions) | **CF exclusive** |
| SSL/TLS certificates | **Universal SSL** — always free: automatic issuance and renewal, wildcard certificates require a paid plan | **ACM** — always free: completely free when used with CloudFront/ALB; attaching directly to EC2 requires payment | Roughly equivalent |

---

## Identity & Zero Trust Access

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Zero Trust access control | **Access / ZTNA** — always free: 50 users free, SSO integration (Google/GitHub/Okta), suited for zero-trust control of non-AWS resources | **IAM Identity Center** — always free (primarily for AWS-internal resources) / **Cognito** 50,000 MAU free | Different use cases (CF suited for non-AWS resources) |
| Private network tunnelling | **Tunnel** — always free: encrypted tunnel to Cloudflare edge, like ngrok but more stable, no bandwidth limits | **Site-to-Site VPN** — **no free tier**: $0.05/hour/connection, ~$36/month, complex configuration | **CF wins decisively** |

---

## Message Queuing

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Message queue | **Queues** — always free: 1M message operations/month, deep Workers integration, automatic retry | **SQS** — always free: 1M requests/month, standard + FIFO queues, mature and ecosystem-rich | Roughly equivalent |

---

## AI Inference

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Managed AI inference | **Workers AI** — always free (limited): daily free neuron quota, LLaMA/Whisper/Stable Diffusion etc., edge-run with low latency | **Bedrock** — **no free tier**: pay per token, Claude/Llama/Titan etc., broader model selection | **CF has a free quota** |

---

## Media Processing

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Video storage & streaming | **Stream** — always free (limited): 1,000 minutes storage + 1,000 minutes delivery/month, then $5/1,000 minutes | **S3 + MediaConvert** — MediaConvert has no free tier: from $0.0075/minute, requires multiple services, more powerful but complex to configure | **CF has a free quota** |
| Image optimisation | **Images** — always free (limited): 5,000 original images stored, 100K image deliveries/month, automatic WebP/AVIF conversion | No managed image optimisation service (requires self-built Lambda + Sharp, or a third-party image CDN) | **CF exclusive** |

---

## Email

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Email routing / receiving | **Email Routing** — always free: unlimited routing rules, forwards @yourdomain.com to any mailbox. ⚠️ Routing only — cannot send outbound email | **SES** — always free (limited): 62,000 emails/month free when sent from EC2, otherwise $0.10/1,000 emails, can receive and send | Different use cases (CF routes, AWS sends and receives) |

---

## Analytics & Monitoring

| Category | Cloudflare | AWS | Free tier winner |
|------|-----------|-----|---------|
| Traffic analytics | **Analytics** — always free: unsampled complete traffic data, no cookies (GDPR-compliant), Workers Analytics Engine supports custom metrics | **CloudWatch** — always free (limited): 10 custom metrics, 5 GB log ingestion/month, primarily for infrastructure monitoring | Different use cases (CF for traffic, AWS for infrastructure) |

---

## Services AWS Has That Cloudflare Doesn't

| AWS Service | Notes |
|---------|------|
| EC2 / ECS / EKS | General-purpose VMs, container runtimes. CF has no VMs; Workers are V8 isolates with significant constraints. |
| RDS (PostgreSQL/MySQL) | Production-grade managed relational database. CF D1 is SQLite and cannot replace it. |
| SageMaker / Bedrock | Full ML training platform and broad model selection. CF Workers AI handles lightweight inference only. |
| Kinesis / MSK | Real-time data stream processing. CF Queues is a simple message queue, not a streaming compute engine. |
| ELB / ALB | Internal application load balancers for VPC-internal service routing. |
| X-Ray / CloudWatch APM | Distributed tracing, full infrastructure monitoring. |
| VPC / PrivateLink | Private networks, subnet isolation, secure internal service interconnect. CF has no VPC concept. |
| Step Functions | Complex workflow orchestration, multi-step state machines. CF has no equivalent. |

---

## Summary

Cloudflare is not a replacement for AWS — it's a strong **edge-layer complement**. A common combination is Cloudflare for CDN + DNS + WAF + DDoS (zero additional cost) with AWS for backend compute + database + containers.

Pure static sites or lightweight APIs can run entirely on Cloudflare at near-zero cost. The most notable cost savings:

- **R2 egress free:** versus S3's $0.09/GB the difference is significant
- **CDN unlimited bandwidth:** CloudFront starts billing after 1 TB
- **WAF + DDoS free:** AWS equivalents are fully paid services
- **DNS free:** Route 53 has no free tier
