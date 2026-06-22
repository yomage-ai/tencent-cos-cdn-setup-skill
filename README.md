# Tencent COS/CDN Setup Skill

[中文](README.md) | [English](README.en.md)

这是一个给 Codex 用的 skill，用来把项目接入腾讯云标准 COS、CDN、DNSPod 和 CAM 权限。它会先生成计划，不会一上来就修改腾讯云；你确认后可以让 Codex 代执行，也可以自己按报告里的手动操作指南去腾讯云后台配置。

默认情况下，过程文件会放在用户缓存目录里的独立运行目录，不会写进你的项目仓库。完成后只需要拿走项目配置要用的值。

## 安装

当前稳定版：

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#v0.1.0
```

覆盖旧版本：

```bash
npx --yes github:yomage-ai/tencent-cos-cdn-setup-skill#v0.1.0 --force
```

安装完成后，重启 Codex。以后发布新版本时，维护者会把上面命令里的 tag 更新到最新稳定版，用户直接复制即可。

如果不能使用 `npx`，可以用 Codex 自带的 `$skill-installer`：

```text
$skill-installer install https://github.com/yomage-ai/tencent-cos-cdn-setup-skill/tree/v0.1.0/tencent-cos-cdn-setup-skill
```

## 能节省什么

一次“公开文件 + 私有文件 + CDN + DNSPod”的完整配置，通常会涉及 10-12 个操作/检查步骤，跨 5 个左右腾讯云页面：COS bucket、CAM 用户、CAM 策略、CDN 域名、DNSPod，按需再处理 HTTPS 证书。

如果已经知道要配哪些页面和值，手工执行通常也要 45-90 分钟；如果是第一次摸索 COS + CDN + 私有桶完整链路，常见会花半天到 1 天以上，并且容易漏掉 CORS、私有回源、TypeA 鉴权、CNAME 或最小权限策略。使用这个 skill 后，常见流程会变成：3-10 分钟生成计划和操作指南，5-20 分钟执行或照着指南确认，剩余时间主要等待 CDN/DNS 生效。实际节省取决于账号状态、域名备案/解析、证书和权限审批。

底层执行使用腾讯云官方 SDK 和 API：COS 使用 `cos-python-sdk-v5`，CAM/CDN/DNSPod 使用 `tencentcloud-sdk-python`。所有云资源变更都通过你的腾讯云账号凭据调用官方接口；手动指南里的链接也指向腾讯云官方控制台。

## 使用

新建一个空文件夹作为配置工作区，在里面打开 Codex，然后说：

```text
帮我配置腾讯云的对象存储相关配置
```

Codex 第一轮通常只问三个问题：

- 这是测试环境还是生产环境？
  用来生成资源名字和报告目录，例如带上 `testing` / `prod`，避免测试资源和生产资源混在一起；不会跳过确认。
- 需要公开文件、私有文件，还是两种都要？
  标准方案支持三种：一个公开 bucket、一个私有 bucket、或公开+私有各一个。多个业务目录可以先放在同一个 bucket 里按路径区分；如果你确实需要多套公开/私有 bucket，就按模块或环境分多次运行。
- 有没有已经放在 DNSPod 管理的域名？
  指域名 DNS 解析托管在腾讯云 DNSPod，并且当前腾讯云账号能新增 CNAME 记录。

不知道就回答：

```text
不知道，你帮我推荐一个默认值。
```

## 没有域名

如果现在没有域名，或域名不在 DNSPod，可以先只配置 COS bucket 和 CAM 权限，不配置 CDN/DNS。

后面有域名后，可以继续用这个 skill 补 CDN/DNS：

```text
继续给上次这个项目补 CDN/DNS。之前已经完成 COS bucket 和 CAM 权限配置，报告在 <上次的 plan.report.md 路径>。现在域名已经放在 DNSPod 管理，域名是 example.com。
```

如果找不到上次报告，也可以重新说启动语，但尽量告诉 Codex 上次的项目名、环境、APPID、region 和已经创建好的 bucket 名。Codex 会重新生成计划，复用匹配的 COS/CAM，只补 CDN/DNS；仍然不会直接修改腾讯云。

## 临时密钥

只有到了真实执行腾讯云变更时，Codex 才会让你准备临时安装用的 `SecretId` / `SecretKey`。小白测试时可以创建一个临时 CAM 子用户，测试完成后删除这个子用户或禁用密钥。不要把 `SecretKey`、CDN 鉴权 key、证书私钥发到公开仓库、截图或聊天群里。

## 安全边界

- 第一步只生成计划，不直接改腾讯云。
- 真实执行前必须由你确认。
- 当前脚本不提供删除流程，也不会在计划里主动安排删除 bucket、对象、CDN 域名、CAM 用户、策略或 DNS 记录。
- 请先在测试环境验证，再用于生产环境；真实云资源变更由操作者自行确认和承担结果。

同名资源会安全复用，不会静默覆盖：

- 同名 CAM 用户存在时，使用这个已有子用户，但不修改它已有的登录方式或密钥设置。
- 同名 CAM 策略存在时，只有策略内容完全一致或权限等价才复用；更宽或不匹配的策略不会自动绑定。
- 同名 CDN 域名存在时，只有源站和服务配置匹配才复用；不匹配时流程暂停，等待你选择换域名、人工检查或暂时跳过 CDN。

## 产出物

通常会生成：

- 配置计划和腾讯云资源清单。
- 手动操作指南：控制台链接、点击路径、搜索关键词、检查字段、要做什么、是否必做。
- 执行/验证后的用户验收清单：控制台链接、搜索关键词、检查字段、当前状态、是否完成和未完成原因。
- 你的项目需要使用的配置数据，例如 region、bucket、CDN 域名、CORS 来源、private CDN TypeA key 的保存位置。

## 命令行用法

```bash
RUN_DIR="$(python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py run-dir --project my-app --env testing --create)"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py init-config --mode public-private --out "$RUN_DIR/config.json"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py plan "$RUN_DIR/config.json" --out "$RUN_DIR/plan.json" --report "$RUN_DIR/plan.report.md"
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json"
```

不带 `--apply` 时，`apply` 只是 dry-run，不会改腾讯云。真实执行建议：

```bash
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json" --apply --stop-on-failure
python3 tencent-cos-cdn-setup-skill/scripts/tencent_cos_cdn.py resume "$RUN_DIR/plan.json" --apply
```

生成文件：

- `$RUN_DIR/plan.state.json`：记录已成功动作，用于恢复执行。
- `$RUN_DIR/plan.secrets.json`：生成的 private CDN TypeA key，如有。不要提交它。
- `$RUN_DIR/plan.report.md`：合并报告，包含手动操作指南、执行结果、验证结果、验收清单和项目配置值。
