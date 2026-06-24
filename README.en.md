# Tencent COS/CDN Setup Skill

[中文](README.md) | [English](README.en.md)

This is an Agent Skill for Codex, Claude Code, and other LLM agents that support the Agent Skills directory structure. It connects an app to a standard Tencent Cloud COS, CDN, DNSPod, and CAM permission setup. It generates a plan first and does not modify Tencent Cloud immediately. After you review the plan, you can let your AI agent apply the changes or follow the generated Manual Operator Guide in the Tencent Cloud console.

By default, generated working files are placed in an isolated run directory under the user cache, not in your project repository. After completion, you only need to copy the integration values into your app config.

## Install

Recommended interactive installer:

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.1 install
```

The wizard lets you choose where to install the skill:

- Codex: installs to `~/.codex/skills/tencent-cos-cdn-setup-skill`
- Claude Code: installs to `~/.claude/skills/tencent-cos-cdn-setup-skill`
- Custom directory: for other LLM agents compatible with the `SKILL.md` directory structure

Non-interactive installs:

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.1 install --client codex
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.1 install --client claude-code
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.1 install --all
```

Overwrite an older install:

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.1 install --all --force
```

Install into a custom skills directory:

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.1 install --dest /path/to/skills
```

The old command still works and defaults to Codex:

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.1
```

Restart the target AI agent after installation. Claude Code usually detects changes under an existing skills directory live, but if the directory was created for the first time, restart Claude Code. When a new stable release is published, the maintainer updates the tag in the commands above, so users can copy the command directly.

If `npx` is not available, use Codex's built-in `$skill-installer`:

```text
$skill-installer install https://github.com/yomage-ai/tencent-cos-cdn-setup-skill/tree/v0.2.1/tencent-cos-cdn-setup-skill
```

## What It Saves

A complete "public files + private files + CDN + DNSPod" setup usually involves 10-12 operations or checks across about 5 Tencent Cloud pages: COS buckets, CAM users, CAM policies, CDN domains, and DNSPod. HTTPS certificates may also need to be handled as needed.

If this is your first time figuring out the full COS + CDN + private-bucket flow, it still takes some time to study, and it is easy to miss CORS, private COS origin access, TypeA authentication, CNAME records, or least-privilege CAM policies. With this skill, the common flow becomes: 3-10 minutes to generate the plan and operation guide, then 5-20 minutes to apply or confirm the steps by following the guide. The remaining time is mostly CDN/DNS propagation. Actual savings depend on account state, domain/ICP status, certificates, and permission approvals.

The implementation uses Tencent Cloud's official SDKs and APIs: COS uses `cos-python-sdk-v5`; CAM, CDN, and DNSPod use `tencentcloud-sdk-python`. Cloud changes are made through official Tencent Cloud APIs using your Tencent Cloud credentials, and the manual guide links to Tencent Cloud's official console pages.

## Usage

If you only want to try it, create an empty setup folder. If you already have an app project, you can open an AI agent where this skill is installed directly in that project directory. By default, this skill writes plans, reports, state files, and temporary secret files to an isolated run directory, not into your project repository. After completion, copy the config values from the report back into your app.

Open the AI agent and say:

```text
Help me configure Tencent Cloud object storage for my app.
```

The AI agent usually asks only three questions in the first round:

- Is this for testing or production?
  This is used to generate resource names and report directories, such as `testing` / `prod`, so test and production resources do not get mixed. It does not skip confirmation.
- Do you need public files, private files, or both?
  The standard setup supports three choices: one public bucket, one private bucket, or one public bucket plus one private bucket. Multiple business folders can usually share the same bucket by path. If you truly need multiple public/private bucket sets, run the skill separately by module or environment.
- Do you already have a domain managed in DNSPod?
  This means the domain's DNS is hosted in Tencent Cloud DNSPod and the current Tencent Cloud account can add CNAME records.

If you are not sure, answer:

```text
I am not sure. Please recommend a safe default.
```

## No Domain Yet

If you do not have a domain yet, or the domain is not managed in DNSPod, you can configure only COS buckets and CAM permissions first, without CDN/DNS.

Later, when the domain is ready, you can use the same skill to add CDN/DNS:

```text
Continue adding CDN/DNS for this previous project. COS buckets and CAM permissions are already configured. The previous report is at <path to the previous plan.report.md>. The domain is now managed in DNSPod, and the domain is example.com.
```

If you cannot find the previous report, you can start again with the normal prompt, but try to provide the previous project name, environment, APPID, region, and bucket names. The AI agent will generate a new plan, reuse matching COS/CAM resources, and only add CDN/DNS. It still will not modify Tencent Cloud directly without confirmation.

## Temporary Credentials

The AI agent only asks for temporary `SecretId` / `SecretKey` when real Tencent Cloud changes are about to be applied. For beginner testing, create a temporary CAM sub-user, then delete that user or disable its access key after testing. Do not share `SecretKey`, CDN authentication keys, or certificate private keys in public repositories, screenshots, or chat groups.

## Safety Boundaries

- The first step only generates a plan; it does not modify Tencent Cloud.
- Real changes require your confirmation.
- The current script does not provide a cleanup/delete flow and does not proactively plan deletion of buckets, objects, CDN domains, CAM users, policies, or DNS records.
- Test in a non-production environment first. The operator is responsible for reviewing and accepting real cloud resource changes.

Same-name resources are reused safely and are not silently overwritten:

- If a same-name CAM user exists, the skill uses that existing sub-user but does not change its existing login or access-key settings.
- If a same-name CAM policy exists, it is reused only when the policy document is identical or permission-equivalent. Broader or mismatched policies are not attached automatically.
- If a same-name CDN domain exists, it is reused only when the origin and service configuration match. If it does not match, the flow pauses and waits for you to choose a new domain, review manually, or skip CDN for now.

## Outputs

The skill usually generates:

- A setup plan and Tencent Cloud resource inventory.
- A Manual Operator Guide with console links, click paths, search keywords, fields to check, exact actions, and required/optional status.
- A user acceptance checklist after apply/verify, including console links, search keywords, fields to check, current status, completion status, and unfinished reasons.
- App integration values such as region, bucket names, CDN domains, CORS origins, and where to store the private CDN TypeA key.

## CLI Usage

```bash
RUN_DIR="$(python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py run-dir --project my-app --env testing --create)"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py init-config --mode public-private --out "$RUN_DIR/config.json"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py plan "$RUN_DIR/config.json" --out "$RUN_DIR/plan.json" --report "$RUN_DIR/plan.report.md"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json"
```

Without `--apply`, `apply` is a dry run and does not modify Tencent Cloud. Recommended real apply commands:

```bash
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json" --apply --stop-on-failure
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py resume "$RUN_DIR/plan.json" --apply
```

Generated files:

- `$RUN_DIR/plan.state.json`: records successful actions for resume.
- `$RUN_DIR/plan.secrets.json`: generated private CDN TypeA key, if any. Do not commit it.
- `$RUN_DIR/plan.report.md`: combined report with the Manual Operator Guide, execution results, verification results, acceptance checklist, and app config values.
