---
name: tencent-cos-cdn-setup-skill
description: Plan, configure, and verify Tencent Cloud standard COS + CDN + DNSPod delivery setups. Use when the user asks in English or Chinese to configure Tencent Cloud object storage, 腾讯云对象存储, 腾讯云 COS, COS/CDN, CDN 加速域名, DNSPod 解析, 腾讯云后台配置, 对象存储相关配置, 对象存储相关的配置, 帮我配置腾讯云对象存储, 帮我配置腾讯云的对象存储相关配置, file upload/download storage, public/private buckets, CORS, CAM permissions, CDN TypeA authentication, or end-to-end dry-run/apply/verification for public-only, private-only, or public-private object storage delivery.
---

# Tencent COS/CDN Setup

Use this skill to build or audit a Tencent Cloud standard COS delivery stack. Prefer guided questions for users who are not familiar with cloud storage terms, and prefer the bundled script for deterministic planning, cloud changes, and validation.

## Workflow

1. Start in guided mode unless the user already provides a config file. Ask one to three simple questions at a time. Do not dump the full schema on the user.
2. If the user does not know an answer, propose a safe default and explain the tradeoff in one short sentence.
3. Collect the minimum project parameters: project name, environment, Tencent Cloud APPID, region, whether a domain exists, whether DNSPod manages that domain, and whether the app needs public files, private files, or both.
4. Infer the setup mode:
   - Public images/files only -> `public-only`
   - Private downloads only -> `private-only`
   - Both public and private files -> `public-private`
5. Read `references/config-schema.md` when creating or reviewing a config file.
6. Generate a plan before applying any real Tencent Cloud change:

```bash
python3 scripts/tencent_cos_cdn.py plan config.json --out plan.json --report report.md
```

7. Summarize the plan in plain language for the user. Mention what will be created and what will remain manual.
8. Ask for explicit confirmation before applying real changes. For real cloud changes, export Tencent Cloud credentials and run:

```bash
export TENCENTCLOUD_SECRET_ID="..."
export TENCENTCLOUD_SECRET_KEY="..."
python3 scripts/tencent_cos_cdn.py apply plan.json --apply --stop-on-failure
```

Without `--apply`, `apply` is a dry run.

If an apply run fails after some actions succeed, resume with:

```bash
python3 scripts/tencent_cos_cdn.py resume plan.json --apply
```

9. Verify DNS/CDN behavior:

```bash
python3 scripts/tencent_cos_cdn.py verify plan.json --report verify.md
```

After apply or verify, always point the user to the generated apply/verify report and summarize the top incomplete manual items. Do not end with only raw command output.

## Beginner Guidance

Read `references/beginner-flow.md` before guiding a beginner, a smoke test, or a user who says they do not know Tencent Cloud configuration.

Follow these rules:

- Tell the user only the current next action. Do not show the full technical plan unless they ask.
- Do not show raw `export ...` commands, SDK names, JSON schema, or long command output to beginners.
- Treat `SecretId`, `SecretKey`, and CDN TypeA keys as credentials. Explain where to copy them from, but avoid displaying their values.
- If Tencent Cloud credentials are missing, guide the user through creating a temporary installer sub-user first.
- Use temporary broad permissions only for smoke testing, and tell the user to delete or disable the temporary key after testing.
- After collecting answers, say what will be created in plain language, then ask whether to generate the plan.
- Do not ask beginners to install Python SDK dependencies. The bundled script auto-creates an isolated runtime in the user cache when SDKs are missing.
- For private CDN, highlight that COS private origin authorization is mandatory and must be checked in the COS console even when the script tries to enable `CosPrivateAccess`.

## User Operation Link Rule

When the user must open Tencent Cloud or copy information from a console page, provide all of this in the same response:

- Direct console URL.
- Click path from the opened page.
- Search keyword, such as the bucket, CDN domain, DNS zone, policy, or CAM user name.
- Fields to check.
- The exact action to take.
- Whether the step is required or optional.

Never say only "open Tencent Cloud Console", "go to CAM", or "check CDN". Use links such as:

- CAM users: `https://console.cloud.tencent.com/cam/user`
- CAM policies: `https://console.cloud.tencent.com/cam/policy`
- COS buckets: `https://console.cloud.tencent.com/cos/bucket`
- CDN domains: `https://console.cloud.tencent.com/cdn/domains`
- DNSPod / DNS: `https://console.cloud.tencent.com/cns`
- SSL certificates: `https://console.cloud.tencent.com/ssl`

For beginner-facing replies, avoid exposing SDK names, pip commands, virtualenv details, JSON schema, or long command output unless the user asks.

## Guided Questions

Use questions like these for beginners:

- What is the project name? If unsure, use a short lowercase name based on the folder name.
- Is this for development, testing, staging, or production?
- What is the Tencent Cloud APPID? If unknown, tell the user where to find it in Tencent Cloud account info.
- Does the app need public files, private files, or both?
- Do you already have a domain name for file access?
- Is that domain managed in DNSPod?
- What website/app origins should access files in the browser?
- Do you want me to generate a plan now?
- Do you confirm applying real Tencent Cloud changes?

If the user has no domain, plan COS and CAM first and leave CDN/DNS disabled or marked for later.

If the user only wants a test run, recommend a non-production environment name and test-only resource names.

For the first message after invocation, ask only:

1. Is this a test or production setup?
2. Does the app need public files, private files, or both?
3. Do you already have a domain managed in DNSPod?

Infer the project name from the folder if the user does not care.

## Safety Rules

- Treat Tencent Cloud Console state as production state. Generate and review a plan before changing anything.
- Do not log, commit, or write SecretKey values, CDN TypeA auth keys, or certificate private keys.
- Read private CDN auth keys from environment variables, not from config files.
- Create access keys only when the user explicitly asks for them; otherwise create CAM policies and users without long-lived keys.
- Do not overwrite existing DNSPod records unless the user explicitly enables replacement.
- Use standard COS buckets. Do not route users to Lighthouse/LightCOS for this workflow.

Read `references/safety-rules.md` before applying changes to a real Tencent Cloud account.

## Bundled Resources

- `scripts/tencent_cos_cdn.py`: the semi-automated planner, applier, verifier, and config template generator.
- `references/config-schema.md`: config file schema and examples.
- `references/capability-map.md`: what the script automates, what remains manual, and which Tencent Cloud APIs are involved.
- `references/beginner-flow.md`: minimal beginner-facing flow and Tencent Cloud console steps.
- `references/safety-rules.md`: credential, dry-run, DNS, CAM, and CDN safety guidance.
- `references/troubleshooting.md`: operational failure modes for COS/CDN/DNSPod setup.

## Common Commands

Create a starter config:

```bash
python3 scripts/tencent_cos_cdn.py init-config --mode public-private --out cos-cdn-config.json
```

Render only the CAM policy:

```bash
python3 scripts/tencent_cos_cdn.py render-policy config.json
```

Show planned actions without contacting Tencent Cloud:

```bash
python3 scripts/tencent_cos_cdn.py plan config.json --out plan.json
python3 scripts/tencent_cos_cdn.py apply plan.json
```

Apply real changes:

```bash
python3 scripts/tencent_cos_cdn.py apply plan.json --apply --stop-on-failure
```

Verify after DNS propagation:

```bash
python3 scripts/tencent_cos_cdn.py verify plan.json
```
