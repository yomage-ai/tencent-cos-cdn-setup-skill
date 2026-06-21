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

接下来你只需要按 Codex 的问题回答。第一轮通常只会问这三个：

- 这是测试环境还是生产环境？
- 你的项目需要公开文件、私有文件，还是两种都要？
- 有没有已经放在 DNSPod 管理的域名？

如果你不知道，就直接回答：

```text
不知道，你帮我推荐一个默认值。
```

后面只有到了需要真实配置腾讯云时，Codex 才会让你准备腾讯云访问密钥。

### 如果 Codex 让你创建腾讯云子用户

这是为了让 Codex 可以调用腾讯云 API 自动创建测试资源。小白测试时按下面选：

1. 打开腾讯云控制台。
2. 进入 **访问管理 CAM**。
3. 进入 **用户 > 用户列表**。
4. 点击 **新建用户**。
5. 创建方式选 **自定义创建**。
6. 用户类型选普通的 **可访问资源并接收消息** 子用户。
7. 用户名填：`cos-skill-installer-test`。
8. 访问方式：
   - 勾选 **编程访问 / API 访问 / 访问密钥**。
   - 不要勾选控制台登录，除非页面强制要求。
   - 登录密码、重置密码、MFA 等登录相关配置保持默认。
9. 用户权限：
   - 只做本 skill 的测试验收时，直接临时绑定 **AdministratorAccess**。
   - 这个权限很大，只适合临时测试；测试完成后删除这个子用户或禁用密钥。
   - 正式公司环境不要长期使用这个权限，应让管理员提供临时安装密钥。
10. 用户标签：跳过或保持默认。
11. 审阅后点击完成。
12. 进入这个子用户详情，打开 **API 密钥 / 访问密钥**。
13. 创建密钥，复制 `SecretId` 和 `SecretKey`。

注意：`SecretKey` 通常只在创建时显示一次。复制后不要发到群里、截图里，也不要提交到代码仓库。

### 你需要准备什么

最少准备这些：

- 一个腾讯云账号。
- 到真实执行时，再准备一个临时测试用 SecretId / SecretKey。
- 如果要测试 CDN 域名，最好有一个已经放在 DNSPod 里的域名。

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

真实执行前请先安装依赖：

```bash
python3 -m pip install tencentcloud-sdk-python cos-python-sdk-v5
```

真实执行建议这样跑，失败时会停下来，修好后可以继续：

```bash
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply plan.json --apply --stop-on-failure
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py resume plan.json --apply
```

执行后会生成：

- `plan.state.json`：记录已经成功的动作，避免重复创建。
- `plan.secrets.json`：如果自动生成了 private CDN TypeA key，会保存在这里。不要提交这个文件，要把 key 保存到你的后端密钥系统。

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

- Is this for dev, staging, or production?
- Does your app need public files, private files, or both?
- Do you already have a DNSPod-hosted domain?

If you do not know an answer, say:

```text
I don't know. Please recommend a default.
```

Codex should ask for Tencent Cloud credentials only when it is time to apply real cloud changes.

### If Codex Asks You To Create A Tencent Cloud Sub-user

This lets Codex call Tencent Cloud APIs to create test resources. For a beginner smoke test:

1. Open Tencent Cloud Console.
2. Go to **Access Management (CAM)**.
3. Open **Users > User List**.
4. Click **Create User** / **New User**.
5. Choose **Custom creation**.
6. User type: choose the normal sub-user type that can access resources and receive messages.
7. User name: `cos-skill-installer-test`.
8. Access method:
   - Enable **Programming access**, **API access**, or **Access key**.
   - Do not enable console login unless the page requires it.
   - Keep login password, password reset, and MFA settings at their defaults if console login is disabled.
9. User permissions:
   - For this skill smoke test, temporarily attach **AdministratorAccess**.
   - This is broad permission and should only be used for temporary testing.
   - Delete this sub-user or disable the key after testing.
   - For company production use, ask an administrator for a temporary installer key instead.
10. Tags: skip or keep defaults.
11. Review and finish.
12. Open the new sub-user details, then open **API Key** / **Access Key**.
13. Create a key and copy `SecretId` and `SecretKey`.

Important: `SecretKey` is usually shown only once when the key is created. Do not post it in chat, screenshots, or code repositories.

### What You Need

At minimum:

- A Tencent Cloud account.
- A temporary test SecretId / SecretKey when you are ready to apply real changes.
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

Install dependencies before real apply:

```bash
python3 -m pip install tencentcloud-sdk-python cos-python-sdk-v5
```

Recommended real apply flow:

```bash
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply plan.json --apply --stop-on-failure
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py resume plan.json --apply
```

Generated local files:

- `plan.state.json`: completed action state, used for resume.
- `plan.secrets.json`: generated private CDN TypeA keys, if any. Do not commit it; store the key in your backend secret manager.
