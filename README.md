# Tencent COS/CDN Setup Skill

中文说明见下方：[中文](#中文)。

## English

This repository contains a Codex skill for semi-automated Tencent Cloud standard COS + CDN + DNSPod setup.

It helps an agent or operator:

- Plan public-only, private-only, or public-private COS bucket setups.
- Generate least-privilege CAM policy JSON.
- Configure COS buckets, ACLs, and CORS.
- Add CDN acceleration domains.
- Configure private CDN TypeA authentication.
- Create DNSPod CNAME records with conflict protection.
- Verify DNS and HTTP/CDN behavior.

The skill defaults to safe dry-run behavior. Real Tencent Cloud changes only happen when `--apply` is explicitly passed.

### Repository Layout

```text
.
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── capability-map.md
│   ├── config-schema.md
│   ├── example-public-private.json
│   ├── safety-rules.md
│   └── troubleshooting.md
└── scripts/tencent_cos_cdn.py
```

### Use As A Codex Skill

Install or copy this repository as a skill folder, then ask Codex:

```text
Use $tencent-cos-cdn-setup-skill to plan Tencent COS + CDN + DNSPod setup for my app.
```

The agent should read `SKILL.md`, collect your project parameters, generate a plan, and guide you through dry-run, apply, and verification.

### Use The CLI Directly

Create a starter config:

```bash
python3 scripts/tencent_cos_cdn.py init-config --mode public-private --out cos-cdn-config.json
```

Edit `cos-cdn-config.json`, then generate a plan:

```bash
python3 scripts/tencent_cos_cdn.py plan cos-cdn-config.json --out plan.json --report report.md
```

Preview actions without changing Tencent Cloud:

```bash
python3 scripts/tencent_cos_cdn.py apply plan.json
```

Apply real changes:

```bash
export TENCENTCLOUD_SECRET_ID="..."
export TENCENTCLOUD_SECRET_KEY="..."
export TENCENT_CDN_AUTH_KEY="..." # required when private CDN TypeA is used

python3 scripts/tencent_cos_cdn.py apply plan.json --apply
```

Verify DNS/CDN after propagation:

```bash
python3 scripts/tencent_cos_cdn.py verify plan.json --report verify.md
```

### Supported Modes

- `public-only`: one public COS bucket, optional public CDN domain, DNSPod CNAME.
- `private-only`: one private COS bucket, private CDN TypeA authentication, DNSPod CNAME.
- `public-private`: public and private buckets with separate CDN domains.

### Python Dependencies

Planning works with the Python standard library for JSON configs.

Real Tencent Cloud changes require official SDKs:

```bash
python3 -m pip install tencentcloud-sdk-python cos-python-sdk-v5
```

YAML config support is optional:

```bash
python3 -m pip install PyYAML
```

### Safety Notes

- Run `plan` first and review `report.md`.
- `apply` is a dry run unless `--apply` is passed.
- Do not store Tencent SecretKey, CDN TypeA keys, or certificate private keys in config files.
- DNSPod conflicts are not overwritten by default.
- The tool does not delete buckets, objects, CDN domains, CAM users, policies, or DNS records.
- COS private bucket CDN service authorization may still require console confirmation depending on account/API availability.

For details, read:

- `references/config-schema.md`
- `references/capability-map.md`
- `references/safety-rules.md`
- `references/troubleshooting.md`

## 中文

这个仓库存放的是一个 Codex skill，用于半自动配置腾讯云标准 COS + CDN + DNSPod。

它可以帮助 agent 或运维人员完成：

- 规划单 public 桶、单 private 桶、public/private 双桶三种部署模式。
- 生成 CAM 最小权限策略 JSON。
- 配置 COS bucket、ACL 和 CORS。
- 添加 CDN 加速域名。
- 配置 private CDN 的 TypeA 鉴权。
- 自动创建 DNSPod CNAME，并对冲突记录做保护。
- 验证 DNS 和 HTTP/CDN 访问状态。

这个 skill 默认是安全的 dry-run 模式。只有显式传入 `--apply` 时，才会真正修改腾讯云资源。

### 仓库结构

```text
.
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── capability-map.md
│   ├── config-schema.md
│   ├── example-public-private.json
│   ├── safety-rules.md
│   └── troubleshooting.md
└── scripts/tencent_cos_cdn.py
```

### 作为 Codex Skill 使用

把这个仓库安装或复制为 skill 目录后，对 Codex 说：

```text
Use $tencent-cos-cdn-setup-skill to plan Tencent COS + CDN + DNSPod setup for my app.
```

Codex 会读取 `SKILL.md`，收集你的项目参数，生成配置计划，并引导你完成 dry-run、apply 和验证。

### 直接使用 CLI

生成初始配置：

```bash
python3 scripts/tencent_cos_cdn.py init-config --mode public-private --out cos-cdn-config.json
```

编辑 `cos-cdn-config.json` 后生成 plan：

```bash
python3 scripts/tencent_cos_cdn.py plan cos-cdn-config.json --out plan.json --report report.md
```

预览将要执行的动作，不修改腾讯云：

```bash
python3 scripts/tencent_cos_cdn.py apply plan.json
```

执行真实变更：

```bash
export TENCENTCLOUD_SECRET_ID="..."
export TENCENTCLOUD_SECRET_KEY="..."
export TENCENT_CDN_AUTH_KEY="..." # 使用 private CDN TypeA 时需要

python3 scripts/tencent_cos_cdn.py apply plan.json --apply
```

DNS 生效后验证：

```bash
python3 scripts/tencent_cos_cdn.py verify plan.json --report verify.md
```

### 支持模式

- `public-only`：一个 public COS 桶，可选 public CDN 域名和 DNSPod CNAME。
- `private-only`：一个 private COS 桶，private CDN TypeA 鉴权和 DNSPod CNAME。
- `public-private`：public/private 双桶，分别配置 CDN 域名。

### Python 依赖

如果使用 JSON 配置，只生成 plan 不需要第三方依赖。

真正调用腾讯云 API 需要官方 SDK：

```bash
python3 -m pip install tencentcloud-sdk-python cos-python-sdk-v5
```

如果要读取 YAML 配置，可选安装：

```bash
python3 -m pip install PyYAML
```

### 安全说明

- 先运行 `plan`，认真检查 `report.md`。
- `apply` 默认只是 dry-run，只有传 `--apply` 才会真实执行。
- 不要把 Tencent SecretKey、CDN TypeA 鉴权 key、证书私钥写入配置文件。
- DNSPod 已有冲突记录时默认不会覆盖。
- 工具不会删除 bucket、对象、CDN 域名、CAM 用户、策略或 DNS 记录。
- COS private 桶的 CDN 服务授权可能仍需在腾讯云控制台确认，取决于账号和 API 可用性。

详细说明请看：

- `references/config-schema.md`
- `references/capability-map.md`
- `references/safety-rules.md`
- `references/troubleshooting.md`
