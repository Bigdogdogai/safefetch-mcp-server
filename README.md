# SafeFetch MCP Server

A secure web fetching service for local AI agents.  
一个面向本地 AI Agent 的安全网页抓取服务。  
It is designed for real usage, with strong defaults on **security boundaries, resource limits, and observable outputs**.  
它不是“能跑就行”的脚本，而是强调**安全边界、资源控制、可观测输出**的可落地节点。

## Why SafeFetch

这是一个帮 AI 安全上网的“数字保安”。

它主要帮你搞定三件事：

- **防止 AI 进错屋**：普通工具很憨，AI 让它查建材，它可能顺手就把你家卧室的保险柜（内网服务器、路由器后台）给测绘了。这个工具会给 AI 划红线：公网可以查，内网不准进。
- **防止电脑被撑爆**：有些网页像超大的垃圾包，AI 一抓，机器可能直接卡死。这个工具是严格的仓管：只要体积异常，立刻切断，优先保住机器稳定。
- **把乱码变成标准报表**：网页原始内容常常很乱，AI 容易误读。这个工具会自动做清洗和结构化，输出稳定 JSON/Markdown，AI 看得更清楚，任务更容易做准。

## What This Project Does | 这个项目是干什么的？

Think of it as a secure web helper for AI agents (not a visual browser).  
你可以把它理解成一个“给 AI 用的安全浏览器助手”（但它不是可视化浏览器）。  
When your agent needs content from a webpage, this server fetches and normalizes it with safety controls:  
当你的 Agent 需要“去网页上拿内容”时，它负责把内容抓回来，并且尽量做到：

- **No unexpected intranet access** (SSRF defenses)
- **No memory blow-ups from oversized pages** (raw/decompressed limits)
- **Clear failure reasons** (stable JSON output for retries/stops)
- **不乱进内网**（防 SSRF）
- **不被超大页面拖垮**（体积和解压限制）
- **失败时说清楚原因**（标准 JSON 返回，方便自动重试或停止）

In one line: make web fetching for AI safer, more stable, and easier to debug.  
一句话：**让 AI 抓网页这件事，更安全、更稳定、更容易排错。**

## Key Benefits | 它的优点

- **Beginner-friendly**: one-click install scripts
- **Engineering-friendly**: stable output contract for agent orchestration
- **Production-friendly**: strong security defaults, not a bare script
- **Maintenance-friendly**: clear errors for faster troubleshooting
- **对小白友好**：有一键安装脚本，跑起来不折腾
- **对工程友好**：输出格式固定，接入 OpenClaw 这类 Agent 更稳
- **对上线友好**：默认防护比较全，不是裸奔脚本
- **对维护友好**：出错信息清晰，后续排查省时间

> **License model（双许可）**：AGPL v3.0 + Commercial License  
> 闭源集成、SaaS 商用或希望免除 AGPL 义务，请查看 `COMMERCIAL.md`。

---

## 项目定位

`SafeFetch MCP Server` 主要解决三件事：

1. **抓得稳**：支持静态 HTTP/HTTPS 抓取，处理重定向、编码、正文提取和截断。  
2. **拦得住**：默认启用 SSRF 防护、内网/IP 拦截、解压体积限制。  
3. **好接入**：输出固定 JSON 契约，适合 Agent 自动判断和排障。

这非常适合作为 OpenClaw 或其他本地 Agent 的“基础信息采集层”。

---

## 为什么做这个项目

很多抓取工具在 Demo 阶段很好用，但一到真实环境就会遇到问题：

- 输出不稳定，Agent 很难自动处理失败
- 安全边界薄弱，容易被 SSRF 或重定向绕过
- 大响应或压缩炸弹导致内存/进程异常

这个项目的目标就是把“基础抓取能力”打磨成一个可长期使用的底座。

---

## 核心能力

### 1) 安全防护（默认开启）

- URL 协议白名单（仅 `http` / `https`）
- 用户信息字段拦截（`userinfo_not_allowed`）
- DNS 解析与 IP 分类校验（含本地网段/保留地址拦截）
- 重定向逐跳复检（防跳转穿透）
- HTTPS 降级拦截
- 本地 IPv4 / IPv6（含 link-local）防护

### 2) 资源保护

- 原始响应体积上限（`MAX_RAW_BYTES`）
- 解压后体积上限（`MAX_DECOMPRESSED_BYTES`）
- MIME allowlist
- 内容编码校验（含不支持编码阻断）

### 3) Agent 友好输出

- 稳定扁平 JSON 字段
- 错误语义清晰（`fetch_status` + `blocked_reason`）
- 可观测重试信息（`attempts` / `retried` / `retryable_error`）
- `content_markdown` 可直接给 LLM 下游消费

---

## 适合谁使用

- **OpenClaw 用户**：通过 Skill + `mcporter` 快速接入一个安全抓取工具
- **本地 Agent 开发者**：需要稳定 JSON 契约来做自动化编排
- **安全敏感团队**：希望默认就有 SSRF 和资源边界，不靠人为补丁
- **务实构建者**：先把静态抓取稳定跑通，再考虑重型渲染能力

---

## 目录结构

```text
safefetch-mcp-server/
  server.py
  requirements.txt
  bootstrap.sh
  start-mcp.sh
  README.md
  LICENSE
  COMMERCIAL.md
  SECURITY.md
  TERMS.md
  CONTRIBUTING.md
  examples/
    SKILL-sample.md
    SKILL.local.md
    openclaw.skills-entry.sample.json
```

---

## 快速开始（小白推荐）

> 提示：下文中的 `~/` 或 `<YOUR_PATH>` 都表示你的本地项目路径，请按实际 clone 位置替换。

### 一键安装

```bash
cd ~/safefetch-mcp-server
bash bootstrap.sh
```

如果只安装不跑自检：

```bash
bash bootstrap.sh --skip-test
```

### 一键启动

```bash
bash start-mcp.sh
```

---

## 手动安装（可选）

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
python server.py --self-test
```

---

## 本地调试

### 抓取单个 URL

```bash
source .venv/bin/activate
python server.py --url "https://httpbin.org/get" --max-tokens 1200
```

### 运行自检

```bash
source .venv/bin/activate
python server.py --self-test
```

如果你的网络会把公网 DNS 解析到受限网段，可临时加：

```bash
WEBFETCH_ALLOW_CIDRS=198.18.0.0/15 python server.py --self-test
```

---

## OpenClaw 接入（复制即用）

### 1) 合并配置到 `openclaw.json`

参考文件：

- `examples/openclaw.skills-entry.sample.json`

将其深度合并到 `~/.openclaw/openclaw.json` 的 `skills.entries` 下，避免覆盖现有配置。

### 2) 放置技能文件

参考文件：

- `examples/SKILL.local.md`（本机路径版本）
- `examples/SKILL-sample.md`（`<YOUR_PATH>` 占位符版本）

示例：

```bash
mkdir -p ~/.openclaw/skills/webfetch-mcp-v1
cp ~/safefetch-mcp-server/examples/SKILL.local.md ~/.openclaw/skills/webfetch-mcp-v1/SKILL.md
```

### 3) Hello World 测试

```bash
openclaw agent --local --message "请使用 webfetch-mcp-v1 抓取 https://httpbin.org/get ，只输出纯 JSON（不加代码块），字段固定为 ok, fetch_status, blocked_reason, final_url, attempts, retryable_error, security_blocked, title。"
```

---

## `mcporter` 直连调用示例

```bash
mcporter call --stdio "env WEBFETCH_ALLOW_CIDRS=${WEBFETCH_ALLOW_CIDRS:-} <YOUR_PATH>/safefetch-mcp-server/.venv/bin/python <YOUR_PATH>/safefetch-mcp-server/server.py" fetch_url url=https://example.com caller_id=openclaw-agent max_tokens=3000
```

---

## 环境变量

- `WEBFETCH_ALLOW_CIDRS`：可选，CIDR 白名单（逗号分隔）
  - 用于特殊网络环境下放行指定网段
  - 默认不设置时采用严格阻断策略

---

## JSON 响应契约

常用字段：

- `ok`
- `fetch_status`
- `blocked_reason`
- `final_url`
- `status_code`
- `content_type`
- `title`
- `content_markdown`
- `content_chars`
- `redirects`
- `raw_bytes`
- `decompressed_bytes`
- `attempts`
- `retried`
- `retryable_error`
- `last_error`
- `security_blocked`

---

## 安全声明

本项目面向防御性、本地 Agent 抓取场景。  
生产环境请勿关闭 SSRF 与资源限制相关防线。

如发现安全问题，请查看 `SECURITY.md`。

---

## 许可与商用

- 开源许可：`GNU AGPL v3.0`（见 `LICENSE`）
- 商业授权：见 `COMMERCIAL.md`
- 反馈建议：请通过 GitHub `Issues` 或 `Pull Requests`
