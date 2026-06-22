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
   - Environment mainly affects generated resource names, run directories, and safety prompts. It does not skip confirmation or change Tencent Cloud resource class by itself.
   - File access mode is one of three standard layouts: one public bucket, one private bucket, or one public bucket plus one private bucket. If the user needs multiple bucket sets, run the skill separately per module/environment or ask for a custom config.
   - DNSPod-managed domain means DNS records for the root domain are hosted in Tencent Cloud DNSPod and the current Tencent Cloud account can create CNAME records. It is not ICP filing and not "already pointed to CDN".
4. Infer the setup mode:
   - Public images/files only -> `public-only`
   - Private downloads only -> `private-only`
   - Both public and private files -> `public-private`
5. Read `references/config-schema.md` when creating or reviewing a config file.
6. Create an isolated run directory outside the user project before writing any generated files:

```bash
RUN_DIR="$(python3 scripts/tencent_cos_cdn.py run-dir --project my-app --env testing --create)"
```

7. Generate a plan before applying any real Tencent Cloud change. Write config, plan, state, secrets, and the combined report under the isolated run directory, not the user's project:

```bash
python3 scripts/tencent_cos_cdn.py plan "$RUN_DIR/config.json" --out "$RUN_DIR/plan.json" --report "$RUN_DIR/plan.report.md"
```

8. Summarize the plan in plain language for the user. Mention what will be created and what will remain manual.
9. After the plan is generated, explicitly offer two paths:
   - AI applies the plan after user confirmation.
   - User applies it manually from the report's "Manual Operator Guide".
10. Ask for explicit confirmation before applying real changes. For real cloud changes, export Tencent Cloud credentials and run:

```bash
export TENCENTCLOUD_SECRET_ID="..."
export TENCENTCLOUD_SECRET_KEY="..."
python3 scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json" --apply --stop-on-failure
```

Without `--apply`, `apply` is a dry run.

If an apply run fails after some actions succeed, resume with:

```bash
python3 scripts/tencent_cos_cdn.py resume "$RUN_DIR/plan.json" --apply
```

11. Verify DNS/CDN behavior:

```bash
python3 scripts/tencent_cos_cdn.py verify "$RUN_DIR/plan.json" --report "$RUN_DIR/plan.report.md"
```

After apply or verify, summarize the integration values the project needs, point to the single combined report in the run directory (`$RUN_DIR/plan.report.md` by default), and summarize the top incomplete manual items. Do not end with only raw command output.

## Existing Resource Reuse Policy

Default behavior is safe reuse, not silent mutation.

- COS bucket: reuse only when Tencent Cloud says the bucket is already owned by the account, then continue setting the planned ACL and CORS.
- CAM user: if the planned user name already exists, look it up and use that existing sub-user. Do not change existing login or access-key settings silently; surface differences in the result/report.
- CAM policy: if the planned policy name already exists, fetch and parse the current policy document. Reuse only when it is an exact match or permission-equivalent to the planned least-privilege COS bucket policy and has no conflicting deny. Broader or mismatched policies are not automatically attached; pause and ask the user to choose a new policy name, manually review/update the existing policy, or skip that step.
- CAM policy attachment: if the policy is already attached to the target user, treat it as already done.
- CDN domain: if the planned domain already exists, fetch the current config. Reuse only when origin/service settings match the plan; if it differs, pause and ask the user to choose a new domain, manually review the existing domain, or skip CDN for now.
- DNSPod record: matching CNAME is reused. Conflicting records pause the flow unless replacement is explicitly enabled by the user.

When a resource is incompatible or mismatched, pause the flow and ask the user to choose the next action, such as use a different resource name, manually review/update the existing resource, or skip that step. Continue only after the user answers. Do not automatically broaden an existing CAM policy that may be shared by other users/apps.

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

## Project File Rule

Treat this skill as a one-time Tencent Cloud configuration assistant. Do not create `config.json`, `plan.json`, `report.md`, state files, secrets files, or verification artifacts inside the user's project repository by default.

Use an isolated run directory under the skill cache for all generated working files. Only write into the user's project if the user explicitly asks for a project config file or code change. The final answer should give the user the configuration values they need to copy into their own app config, plus the run-directory report path for audit/acceptance.

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

If the user later returns to add CDN/DNS after COS/CAM was already configured:

- Ask for the previous `plan.report.md` path or run directory first.
- If the previous report is unavailable, ask for the previous project name, environment, Tencent Cloud APPID, region, and bucket names.
- Build a new plan that reuses matching COS/CAM resources and adds CDN/DNS. Do not ask the user to start from scratch.
- Still generate a plan first and ask for explicit confirmation before apply.

If the user only wants a test run, recommend a non-production environment name and test-only resource names.

For the first message after invocation, ask only:

1. Is this for testing or production? Explain that this mainly affects generated names and safety prompts.
2. Does the app need public files, private files, or both? Explain the three standard layouts.
3. Do you already have a domain hosted in DNSPod? Explain that this means DNS records are managed in DNSPod, not ICP filing.

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
RUN_DIR="$(python3 scripts/tencent_cos_cdn.py run-dir --project my-app --env testing --create)"
python3 scripts/tencent_cos_cdn.py init-config --mode public-private --out "$RUN_DIR/config.json"
```

Render only the CAM policy:

```bash
python3 scripts/tencent_cos_cdn.py render-policy "$RUN_DIR/config.json"
```

Show planned actions without contacting Tencent Cloud:

```bash
python3 scripts/tencent_cos_cdn.py plan "$RUN_DIR/config.json" --out "$RUN_DIR/plan.json" --report "$RUN_DIR/plan.report.md"
python3 scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json"
```

Apply real changes:

```bash
python3 scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json" --apply --stop-on-failure
```

Verify after DNS propagation:

```bash
python3 scripts/tencent_cos_cdn.py verify "$RUN_DIR/plan.json" --report "$RUN_DIR/plan.report.md"
```
