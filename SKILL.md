---
name: tencent-cos-cdn-setup-skill
description: Plan, configure, and verify Tencent Cloud standard COS + CDN + DNSPod delivery setups. Use when Codex needs to create or reuse Tencent COS buckets, configure CORS, generate and attach least-privilege CAM policies, add CDN acceleration domains, configure private CDN TypeA authentication, create DNSPod CNAME records, or produce dry-run/apply/verification reports for public-only, private-only, or public-private object storage delivery.
---

# Tencent COS/CDN Setup

Use this skill to build or audit a Tencent Cloud standard COS delivery stack. Prefer the bundled script for deterministic planning, cloud changes, and validation.

## Workflow

1. Collect the project parameters: project name, environment, region, APPID, mode (`public-only`, `private-only`, or `public-private`), bucket names, domains, DNSPod zone, CORS origins, and private CDN TTL.
2. Read `references/config-schema.md` when creating or reviewing a config file.
3. Run:

```bash
python scripts/tencent_cos_cdn.py plan config.json --out plan.json --report report.md
```

4. Review the generated plan. Check CAM resources, CDN domains, DNS records, and warnings before applying.
5. For real cloud changes, export Tencent Cloud credentials and run:

```bash
export TENCENTCLOUD_SECRET_ID="..."
export TENCENTCLOUD_SECRET_KEY="..."
python scripts/tencent_cos_cdn.py apply plan.json --apply
```

Without `--apply`, `apply` is a dry run.

6. Verify DNS/CDN behavior:

```bash
python scripts/tencent_cos_cdn.py verify plan.json --report verify.md
```

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
- `references/safety-rules.md`: credential, dry-run, DNS, CAM, and CDN safety guidance.
- `references/troubleshooting.md`: operational failure modes for COS/CDN/DNSPod setup.

## Common Commands

Create a starter config:

```bash
python scripts/tencent_cos_cdn.py init-config --mode public-private --out cos-cdn-config.json
```

Render only the CAM policy:

```bash
python scripts/tencent_cos_cdn.py render-policy config.json
```

Show planned actions without contacting Tencent Cloud:

```bash
python scripts/tencent_cos_cdn.py plan config.json --out plan.json
python scripts/tencent_cos_cdn.py apply plan.json
```

Apply real changes:

```bash
python scripts/tencent_cos_cdn.py apply plan.json --apply
```

Verify after DNS propagation:

```bash
python scripts/tencent_cos_cdn.py verify plan.json
```
