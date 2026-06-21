# Tencent COS/CDN Setup Skill

## 中文

这是一个给 Codex 用的 skill，用来帮你把项目接入腾讯云标准 COS、CDN、DNSPod 和 CAM 权限。

你不需要先懂 COS、CDN、DNSPod、CAM 都是什么。正确用法是：

1. 先安装这个 skill。
2. 新建一个空文件夹作为你的配置工作区。
3. 在 Codex 里说一句启动语。
4. 后面 Codex 会问你问题；你知道就回答，不知道就说“不知道”。
5. Codex 先生成计划，不会直接改腾讯云。
6. 你确认后，再让 Codex 执行真实配置。

### 安装

在 Codex 里说：

```text
$skill-installer install https://github.com/yomage-ai/tencent-cos-cdn-setup-skill/tree/main/tencent-cos-cdn-setup-skill
```

安装完成后，重启 Codex，让新 skill 生效。

### 小白使用方式

创建一个新的空文件夹，例如：

```text
我的项目-cos配置测试
```

然后在这个文件夹里打开 Codex，说：

```text
Use $tencent-cos-cdn-setup-skill to plan Tencent COS + CDN + DNSPod setup for my app.
```

接下来你只需要按 Codex 的问题回答。你大概率会被问到这些：

- 项目叫什么名字？
- 这是测试环境还是生产环境？
- 你的腾讯云 APPID 是多少？
- 你有没有自己的域名？
- 域名是不是在 DNSPod 管理？
- 你的项目需要公开文件、私有文件，还是两种都要？
- 前端访问地址是什么？
- 你是否允许我先生成计划？
- 你是否确认执行真实腾讯云配置？

如果你不知道，就直接回答：

```text
不知道，你帮我推荐一个默认值。
```

### 你需要准备什么

最少准备这些：

- 一个腾讯云账号。
- 一个可以操作腾讯云资源的 SecretId / SecretKey。
- 如果要配置 CDN 域名，最好有一个已经放在 DNSPod 里的域名。

如果你没有域名，也可以先让 Codex 只规划 COS bucket 和权限，不配置 CDN/DNS。

### 你不需要一开始就懂什么

你不需要提前知道：

- bucket 应该叫什么。
- CORS 应该怎么写。
- CAM 权限策略怎么写。
- CDN TypeA 鉴权是什么。
- DNSPod CNAME 怎么配。

这些都应该由 Codex 根据你的回答生成方案。

### 安全原则

Codex 第一步只会生成计划，不应该直接修改腾讯云。

真正修改腾讯云前，它应该明确问你确认。你看到类似“是否执行 apply / 是否真实配置腾讯云资源”的问题时，再决定是否继续。

不要把 SecretKey、CDN 鉴权 key、证书私钥发到公开仓库、截图或聊天群里。

### 这个 skill 会产出什么

通常会产出：

- 一份配置计划。
- 一份腾讯云资源清单。
- 一份待执行动作清单。
- 一份验证结果。
- 必要时，一份你项目里可以参考的对象存储配置片段。

### 给懂命令行的人

这个 skill 也带了 CLI：

```bash
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py init-config --mode public-private --out config.json
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py plan config.json --out plan.json --report report.md
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply plan.json
```

不带 `--apply` 时，`apply` 只是 dry-run，不会改腾讯云。

## English

This is a Codex skill for setting up Tencent Cloud standard COS, CDN, DNSPod, and CAM permissions for an application.

You do not need to understand COS, CDN, DNSPod, or CAM before using it. The intended flow is:

1. Install the skill.
2. Create a fresh empty folder as your setup workspace.
3. Ask Codex to use the skill.
4. Codex asks questions; answer what you know and say "I don't know" when unsure.
5. Codex generates a plan first.
6. Only after you confirm should Codex apply real Tencent Cloud changes.

### Install

Ask Codex:

```text
$skill-installer install https://github.com/yomage-ai/tencent-cos-cdn-setup-skill/tree/main/tencent-cos-cdn-setup-skill
```

Restart Codex after installation.

### Beginner Flow

Create a fresh folder, then open Codex in that folder and say:

```text
Use $tencent-cos-cdn-setup-skill to plan Tencent COS + CDN + DNSPod setup for my app.
```

Codex should then guide you with questions such as:

- What is the project name?
- Is this for dev, staging, or production?
- What is your Tencent Cloud APPID?
- Do you have a domain name?
- Is the domain hosted in DNSPod?
- Does your app need public files, private files, or both?
- What frontend origins should access these files?
- Should I generate a plan now?
- Do you confirm applying real Tencent Cloud changes?

If you do not know an answer, say:

```text
I don't know. Please recommend a default.
```

### What You Need

At minimum:

- A Tencent Cloud account.
- A SecretId / SecretKey with enough permission to manage test resources.
- A DNSPod-hosted domain if you want CDN domain setup.

If you do not have a domain yet, Codex can plan COS buckets and permissions first, then leave CDN/DNS for later.

### What The Skill Handles

You should not need to design these manually at the start:

- COS bucket names.
- CORS rules.
- CAM least-privilege policies.
- CDN TypeA authentication.
- DNSPod CNAME records.

Codex should propose them based on your answers.

### Safety

The first step should be a plan, not a real cloud change.

Before applying changes, Codex should ask for explicit confirmation.

Never commit or publicly share SecretKey values, CDN auth keys, or certificate private keys.

### CLI For Advanced Users

The skill also includes a CLI:

```bash
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py init-config --mode public-private --out config.json
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py plan config.json --out plan.json --report report.md
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply plan.json
```

Without `--apply`, `apply` is only a dry run and will not change Tencent Cloud.
