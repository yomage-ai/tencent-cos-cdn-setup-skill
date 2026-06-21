# Beginner Flow

Use this reference when the user is not familiar with Tencent Cloud setup.

## Conversation Style

- Show one step at a time.
- Ask at most three questions.
- Hide command output unless the user asks to see it.
- Explain Tencent Cloud terms only when needed for the current step.
- Prefer "keep default" / "choose this option" instructions over conceptual explanations.
- Do not show `export TENCENTCLOUD_SECRET_ID=...` to beginners. Say "I will use the credentials locally after you provide them."

## First Three Questions

Ask only these first:

1. Is this for testing or production?
2. Do you need public files, private files, or both?
3. Do you already have a domain in DNSPod?

If the user does not know:

- Environment: use `testing`.
- File type: use `both` for a full smoke test.
- Domain: if they are unsure, skip CDN/DNS first and plan only COS + CAM.

Infer project name from the folder. Use a lowercase, hyphenated name.

## Credential Step

The skill needs a temporary "installer credential" to call Tencent Cloud APIs. This is separate from the final least-privilege user created for the app.

For a beginner smoke test, guide the user through this:

1. Open Tencent Cloud Console.
2. Go to **Access Management (CAM)**.
3. Open **Users > User List**.
4. Click **Create User** / **New User**.
5. Choose **Custom creation**.
6. User type: choose the normal sub-user type that can access resources and receive messages.
7. User name: use something like `cos-skill-installer-test`.
8. Access method:
   - Enable **Programming access**, **API access**, or **Access key**.
   - Do not enable console login unless the page requires it.
   - Keep password/login-related options default if console login is disabled.
9. User permissions:
   - For this skill smoke test, attach **AdministratorAccess**.
   - Explain that this is required for the simplest full test because the skill creates COS, CDN, DNSPod, and CAM resources.
   - Tell the user to disable or delete this key after the test.
   - For formal company use, ask an admin to provide a temporary key with COS, CDN, DNSPod, and CAM management permissions.
10. Tags: keep default or skip.
11. Review: confirm and create.
12. Open the created user details.
13. Open **API Key** / **Access Key**.
14. Create a key if one was not created automatically.
15. Copy `SecretId` and `SecretKey`.

Important: Tencent Cloud only shows `SecretKey` when the key is created. Tell the user to copy it immediately and store it safely.

After the user provides credentials, do not echo them back.

## Domain Step

If the user has no domain:

- Say: "We can still test COS buckets and permissions first. CDN/DNS can be added later."
- Set `cdn.enabled=false` and `dns.enabled=false` in the generated config.

If the user has a domain:

Ask for:

- Root domain, for example `example.com`.
- Public file domain, or let the skill suggest `public.<root-domain>`.
- Private file domain, or let the skill suggest `private.<root-domain>`.

If the user is in Mainland China and the domain may not have ICP filing, recommend `overseas` CDN area for the smoke test.

## Private CDN Key

If private CDN TypeA is needed:

- Generate a random key locally.
- Do not ask the user to invent one.
- Do not print the full key in chat.
- Save it only in a local generated notes file if needed, and remind the user not to commit it.

## Plan Summary For Beginners

After generating a plan, summarize like this:

```text
I prepared a plan. It will create:
- 2 COS buckets: one public, one private
- Browser access rules for your frontend domain
- One temporary app access policy
- CDN domains only if you provided a DNSPod domain
- DNSPod CNAME records only if DNSPod is enabled

Nothing has been changed in Tencent Cloud yet.
```

Avoid listing raw action IDs such as `cos.create_bucket` unless the user asks.

## Apply Confirmation

Before real changes, ask:

```text
I can now apply this plan to Tencent Cloud. This will create cloud resources and may incur cost. Should I continue?
```

Only run apply after explicit confirmation.

## After Apply

Show only:

- What succeeded.
- What needs manual confirmation.
- The next single action.

For private CDN, tell the user to check:

```text
COS bucket > Domain and Transmission > Custom CDN acceleration domain
```

If the console shows a CDN service authorization prompt, click the authorization button.
