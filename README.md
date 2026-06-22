# Tencent COS/CDN Setup Skill

## 中文

这是一个给 Codex 用的 skill，用来帮你把项目接入腾讯云标准 COS、CDN、DNSPod 和 CAM 权限。

你不需要先懂 COS、CDN、DNSPod、CAM 都是什么。正确用法是：

1. 先安装这个 skill。
2. 新建一个空文件夹作为你的配置工作区。
3. 在 Codex 里说一句启动语。
4. 后面 Codex 会问你问题；你知道就回答，不知道就说“不知道”。
5. Codex 先生成计划，不会直接改腾讯云。
6. 你可以选择让 Codex 执行真实配置，也可以自己按报告里的手动操作指南去腾讯云后台配置。

默认情况下，过程文件会放在用户缓存目录里的独立运行目录，不会写进你的项目仓库。完成后你只需要拿走项目配置需要的值。

### 安装

先打开 [Releases](https://github.com/yomage-ai/tencent-cos-cdn-setup-skill/releases)，复制标记为 latest / 最新的版本号，例如 `v0.2.3`。

然后在终端执行，把命令里的 `vX.Y.Z` 替换成刚复制的最新版本号：

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#vX.Y.Z
```

安装完成后，重启 Codex，让新 skill 生效。

如果已经安装过旧版本，想强制覆盖：

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#vX.Y.Z --force
```

### 小白使用方式

创建一个新的空文件夹，例如：

```text
我的项目-cos配置测试
```

然后在这个文件夹里打开 Codex，直接说类似这样的话就可以：

```text
帮我配置腾讯云的对象存储相关配置
```

也可以说：

```text
帮我的项目接入腾讯云 COS 和 CDN
```

```text
帮我配置腾讯云 COS、CDN、DNSPod
```

接下来你只需要按 Codex 的问题回答。第一轮通常只会问这三个：

- 这是测试环境还是生产环境？
  这个答案主要用来生成资源名字和提示强度，例如 bucket、CAM 用户、策略、报告目录里会带 `testing` / `prod` 之类的环境标识。它不会自动让腾讯云资源“变高级”，也不会跳过确认；只是避免把测试资源和生产资源混在一起。
- 你的项目需要公开文件、私有文件，还是两种都要？
  当前标准方案只支持三种：一个公开 bucket、一个私有 bucket、或一个公开 bucket + 一个私有 bucket。多个业务目录可以先放在同一个 bucket 里按路径区分；如果你确实需要多套公开/私有 bucket，就按模块或环境分多次运行。
- 有没有已经放在 DNSPod 管理的域名？
  意思是：你的域名 DNS 解析是否已经托管在腾讯云 DNSPod 控制台，并且当前腾讯云账号有权限新增 CNAME 记录。这不是“域名有没有备案”，也不是“域名是否已经解析到 CDN”。备案是另一件事，只影响中国大陆 CDN 能不能正常接入。

如果你不知道，就直接回答：

```text
不知道，你帮我推荐一个默认值。
```

后面只有到了需要真实配置腾讯云时，Codex 才会让你准备腾讯云访问密钥。

生成计划后通常有两种方式：

- 让 Codex 在你确认后执行真实配置。
- 不让 Codex 执行，自己打开报告里的 **Manual Operator Guide / 手动操作指南**，按每一步的控制台链接、点击路径、搜索关键词、检查字段和填写值操作。

### 如果 Codex 让你创建腾讯云子用户

这是为了让 Codex 可以调用腾讯云 API 自动创建测试资源。小白测试时按下面选：

1. 打开 [CAM 用户列表](https://console.cloud.tencent.com/cam/user)。
2. 如果页面没有直接进入用户列表，点击 **用户 > 用户列表**。
3. 点击 **新建用户**。
4. 创建方式选 **自定义创建**。
5. 用户类型选普通的 **可访问资源并接收消息** 子用户。
6. 用户名填：`cos-skill-installer-test`。
7. 访问方式：
   - 勾选 **编程访问 / API 访问 / 访问密钥**。
   - 不要勾选控制台登录，除非页面强制要求。
   - 登录密码、重置密码、MFA 等登录相关配置保持默认。
8. 用户权限：
   - 只做本 skill 的测试验收时，直接临时绑定 **AdministratorAccess**。
   - 这个权限很大，只适合临时测试；测试完成后删除这个子用户或禁用密钥。
   - 正式公司环境不要长期使用这个权限，应让管理员提供临时安装密钥。
9. 用户标签：跳过或保持默认。
10. 审阅后点击完成。
11. 进入这个子用户详情，打开 **API 密钥 / 访问密钥**。
12. 创建密钥，复制 `SecretId` 和 `SecretKey`。

注意：`SecretKey` 通常只在创建时显示一次。复制后不要发到群里、截图里，也不要提交到代码仓库。

### 你需要准备什么

最少准备这些：

- 一个腾讯云账号。
- 到真实执行时，再准备一个临时测试用 SecretId / SecretKey。
- 如果要测试 CDN 域名，最好有一个已经放在 DNSPod 里的域名。

如果你没有域名，或者域名不在 DNSPod，也可以先让 Codex 只规划 COS bucket 和权限，不配置 CDN/DNS。

后面有域名后，可以继续用这个 skill 补 CDN/DNS。最省事的说法是：

```text
继续给上次这个项目补 CDN/DNS。之前已经完成 COS bucket 和 CAM 权限配置，报告在 <上次的 plan.report.md 路径>。现在域名已经放在 DNSPod 管理，域名是 example.com。
```

如果找不到上次报告，也可以重新说启动语，但尽量告诉 Codex 上次的项目名、环境、APPID、region 和已经创建好的 bucket 名。Codex 会先生成新的计划，复用已存在且匹配的 COS/CAM 资源，只补 CDN/DNS；不会直接修改腾讯云。

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

请先在测试环境验证，再用于生产环境。这个项目按开源工具方式提供，真实云资源变更需要由操作者自行确认和承担结果。

同名资源的处理原则是安全复用，不静默改旧资源：

- 同名 CAM 用户存在时，会使用这个已有子用户继续配置，但不偷偷修改它已有的登录方式或密钥设置。
- 同名 CAM 策略存在时，只有在策略内容完全一致或权限等价时才复用；更宽或不匹配的策略不会自动绑定。
- 同名 CDN 域名存在时，只有源站和服务配置匹配才复用；不匹配时流程会暂停，等待你选择换域名、人工检查，或暂时跳过 CDN。

如果遇到不兼容或不匹配，流程会暂停并给出下一步选择，例如换一个资源名、手动检查后继续，或放弃这一步。用户回复选择后，Codex 再继续；不会在用户没表态时偷偷覆盖旧资源。

### 这个 skill 会产出什么

通常会产出：

- 一份配置计划。
- 一份腾讯云资源清单。
- 一份待执行动作清单。
- 一份手动操作指南，包含控制台链接、点击路径、搜索关键词、应检查字段、要做什么、是否必做。
- 一份执行/验证后的用户验收清单，包含控制台链接、搜索关键词、检查字段、当前状态、是否完成和未完成原因。
- 一组你项目需要使用的配置数据，例如 region、bucket、CDN 域名、CORS 来源、private CDN TypeA key 的保存位置。

### 给懂命令行的人

这个 skill 也带了 CLI：

```bash
RUN_DIR="$(python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py run-dir --project my-app --env testing --create)"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py init-config --mode public-private --out "$RUN_DIR/config.json"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py plan "$RUN_DIR/config.json" --out "$RUN_DIR/plan.json" --report "$RUN_DIR/plan.report.md"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json"
```

不带 `--apply` 时，`apply` 只是 dry-run，不会改腾讯云。

真实执行时，如果缺少腾讯云 Python SDK，脚本会自动在用户缓存目录创建隔离运行环境并安装依赖，不会污染你的项目 Python 环境。

真实执行建议这样跑，失败时会停下来，修好后可以继续：

```bash
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json" --apply --stop-on-failure
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py resume "$RUN_DIR/plan.json" --apply
```

执行后会生成：

- `$RUN_DIR/plan.state.json`：记录已经成功的动作，避免重复创建。
- `$RUN_DIR/plan.secrets.json`：如果自动生成了 private CDN TypeA key，会保存在这里。不要提交这个文件，要把 key 保存到你的后端密钥系统。
- `$RUN_DIR/plan.report.md`：plan、apply、verify 共用的本地合并报告，包含手动操作指南、执行结果、验证结果、用户验收清单、必须手动完成事项、项目需要使用的配置数据。

### 备用安装方式

如果你的环境不能使用 `npx`，也可以在 Codex 里使用系统自带的 `$skill-installer`：

```text
$skill-installer install https://github.com/yomage-ai/tencent-cos-cdn-setup-skill/tree/vX.Y.Z/tencent-cos-cdn-setup-skill
```

## English

This is a Codex skill for setting up Tencent Cloud standard COS, CDN, DNSPod, and CAM permissions for an application.

You do not need to understand COS, CDN, DNSPod, or CAM before using it. The intended flow is:

1. Install the skill.
2. Create a fresh empty folder as your setup workspace.
3. Ask Codex to use the skill.
4. Codex asks questions; answer what you know and say "I don't know" when unsure.
5. Codex generates a plan first.
6. You can either let Codex apply real Tencent Cloud changes after confirmation, or follow the report's Manual Operator Guide yourself.

By default, generated working files are kept in an isolated run directory under the user cache, not in your project repository. After setup, copy only the needed integration values into your app config.

### Install

Open [Releases](https://github.com/yomage-ai/tencent-cos-cdn-setup-skill/releases), copy the latest release tag, for example `v0.2.3`.

Then run this command, replacing `vX.Y.Z` with that latest tag:

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#vX.Y.Z
```

Restart Codex after installation.

To replace an old installation:

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#vX.Y.Z --force
```

### Beginner Flow

Create a fresh folder, then open Codex in that folder and say something natural:

```text
Help me configure Tencent Cloud object storage for my app.
```

Other examples:

```text
Help my project use Tencent COS and CDN.
```

```text
帮我配置腾讯云的对象存储相关配置
```

Codex should then guide you with questions such as:

- Is this for testing or production?
  This mostly affects generated names and safety prompts, such as bucket names, CAM users, policies, and report folders. It does not skip confirmation or automatically change the class of Tencent Cloud resources.
- Does your app need public files, private files, or both?
  The standard setup supports three choices: one public bucket, one private bucket, or one public bucket plus one private bucket. Multiple business folders can share the same bucket by path. If you need multiple public/private bucket sets, run the skill separately per module or environment.
- Do you already have a domain hosted in DNSPod?
  This means the domain's DNS records are managed in Tencent Cloud DNSPod and the current Tencent Cloud account can create CNAME records. It does not mean ICP filing, and it does not mean the domain already points to CDN. ICP filing is a separate requirement for Mainland China CDN.

If you do not know an answer, say:

```text
I don't know. Please recommend a default.
```

Codex should ask for Tencent Cloud credentials only when it is time to apply real cloud changes.

After a plan is generated, there are two normal paths:

- Let Codex apply the plan after you explicitly confirm.
- Do not let Codex apply it; open the report's **Manual Operator Guide** and follow the console URL, click path, search keyword, fields to check, and values for each step.

### If Codex Asks You To Create A Tencent Cloud Sub-user

This lets Codex call Tencent Cloud APIs to create test resources. For a beginner smoke test:

1. Open [CAM Users](https://console.cloud.tencent.com/cam/user).
2. If needed, click **Users > User List**.
3. Click **Create User** / **New User**.
4. Choose **Custom creation**.
5. User type: choose the normal sub-user type that can access resources and receive messages.
6. User name: `cos-skill-installer-test`.
7. Access method:
   - Enable **Programming access**, **API access**, or **Access key**.
   - Do not enable console login unless the page requires it.
   - Keep login password, password reset, and MFA settings at their defaults if console login is disabled.
8. User permissions:
   - For this skill smoke test, temporarily attach **AdministratorAccess**.
   - This is broad permission and should only be used for temporary testing.
   - Delete this sub-user or disable the key after testing.
   - For company production use, ask an administrator for a temporary installer key instead.
9. Tags: skip or keep defaults.
10. Review and finish.
11. Open the new sub-user details, then open **API Key** / **Access Key**.
12. Create a key and copy `SecretId` and `SecretKey`.

Important: `SecretKey` is usually shown only once when the key is created. Do not post it in chat, screenshots, or code repositories.

### What You Need

At minimum:

- A Tencent Cloud account.
- A temporary test SecretId / SecretKey when you are ready to apply real changes.
- A domain hosted in DNSPod if you want the skill to set up CDN/DNS automatically.

If you do not have a domain yet, or the domain is not hosted in DNSPod, Codex can plan COS buckets and permissions first, then leave CDN/DNS for later.

You can use the same skill later to add CDN/DNS. The simplest prompt is:

```text
Continue the previous project and add CDN/DNS. COS buckets and CAM permissions are already configured. The previous report is at <path to plan.report.md>. My domain is now hosted in DNSPod: example.com.
```

If you cannot find the previous report, start the skill again and provide the previous project name, environment, APPID, region, and bucket names. Codex will generate a new plan, reuse matching COS/CAM resources, and only add CDN/DNS. It will not change Tencent Cloud without confirmation.

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

Test in a non-production environment first. This project is provided as an open-source tool; the operator is responsible for reviewing and accepting real cloud-resource changes.

Existing resources are handled by safe reuse, not silent mutation:

- If a CAM user with the planned name exists, the script uses that existing sub-user but does not silently change existing login/key settings.
- If a CAM policy with the planned name exists, the script reuses it only when its document exactly matches or is permission-equivalent to the planned least-privilege policy; broader or mismatched policies pause the flow for user choice.
- If a CDN domain with the planned name exists, the script reuses it only when origin and service settings match; otherwise the flow pauses for user choice.

When a conflict or mismatch is found, the flow pauses and shows choices such as using a different resource name, manually reviewing the existing resource, or skipping that step. Codex continues only after the user chooses the next action.

### CLI For Advanced Users

The skill also includes a CLI:

```bash
RUN_DIR="$(python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py run-dir --project my-app --env testing --create)"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py init-config --mode public-private --out "$RUN_DIR/config.json"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py plan "$RUN_DIR/config.json" --out "$RUN_DIR/plan.json" --report "$RUN_DIR/plan.report.md"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json"
```

Without `--apply`, `apply` is only a dry run and will not change Tencent Cloud.

During real apply, the script auto-prepares an isolated Python runtime for Tencent Cloud SDK dependencies if needed. It does not install packages into your project Python environment.

Recommended real apply flow:

```bash
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json" --apply --stop-on-failure
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py resume "$RUN_DIR/plan.json" --apply
```

Generated local files:

- `$RUN_DIR/plan.state.json`: completed action state, used for resume.
- `$RUN_DIR/plan.secrets.json`: generated private CDN TypeA keys, if any. Do not commit it; store the key in your backend secret manager.
- `$RUN_DIR/plan.report.md`: combined local report shared by plan, apply, and verify, including the manual operator guide, apply results, verification results, acceptance checklist, required manual actions, and project integration values.

### Alternative Install

If `npx` is not available, use Codex's built-in `$skill-installer`:

```text
$skill-installer install https://github.com/yomage-ai/tencent-cos-cdn-setup-skill/tree/vX.Y.Z/tencent-cos-cdn-setup-skill
```
