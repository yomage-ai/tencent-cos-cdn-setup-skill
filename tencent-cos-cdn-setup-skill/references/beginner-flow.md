# Beginner Flow

Use this reference when the user is not familiar with Tencent Cloud setup.

## Conversation Style

- Show one step at a time.
- Ask at most three questions.
- Hide command output unless the user asks to see it.
- Explain Tencent Cloud terms only when needed for the current step.
- Prefer "keep default" / "choose this option" instructions over conceptual explanations.
- Do not show `export TENCENTCLOUD_SECRET_ID=...` to beginners. Say "I will use the credentials locally after you provide them."
- Do not ask beginners to install Python packages or SDKs. Let the script prepare its isolated runtime automatically.
- Whenever the user must operate in Tencent Cloud, include the direct URL, click path, search keyword, fields to check, and exact action in the same response.
- Also say whether the console step is required or optional.
- Do not write generated working files into the user's project folder. Use the script's isolated run directory for config, plan, state, secrets, and reports.

## First Three Questions

Ask only these first:

1. Is this for testing or production? Say this mainly affects generated resource names and safety prompts; it does not skip confirmation.
2. Do you need public files, private files, or both? Say the standard setup supports one public bucket, one private bucket, or one of each.
3. Do you already have a domain hosted in DNSPod? Say this means DNS records are managed in Tencent Cloud DNSPod and the account can add CNAME records; it is not ICP filing.

If the user does not know:

- Environment: use `testing`.
- File type: use `both` for a full smoke test.
- Domain: if they are unsure, skip CDN/DNS first and plan only COS + CAM.

Infer project name from the folder. Use a lowercase, hyphenated name.

## Credential Step

The skill needs a temporary "installer credential" to call Tencent Cloud APIs. This is separate from the final least-privilege user created for the app.

For a beginner smoke test, guide the user through this:

1. Open [CAM Users](https://console.cloud.tencent.com/cam/user).
2. Click **Users > User List** if the page does not open there directly.
3. Click **Create User** / **New User**.
4. Choose **Custom creation**.
5. User type: choose the normal sub-user type that can access resources and receive messages.
6. User name: use something like `cos-skill-installer-test`.
7. Access method:
   - Enable **Programming access**, **API access**, or **Access key**.
   - Do not enable console login unless the page requires it.
   - Keep password/login-related options default if console login is disabled.
8. User permissions:
   - For this skill smoke test, attach **AdministratorAccess**.
   - Explain that this is required for the simplest full test because the skill creates COS, CDN, DNSPod, and CAM resources.
   - Tell the user to disable or delete this key after the test.
   - For formal company use, ask an admin to provide a temporary key with COS, CDN, DNSPod, and CAM management permissions.
9. Tags: keep default or skip.
10. Review: confirm and create.
11. Open the created user details.
12. Open **API Key** / **Access Key**.
13. Create a key if one was not created automatically.
14. Copy `SecretId` and `SecretKey`.

Important: Tencent Cloud only shows `SecretKey` when the key is created. Tell the user to copy it immediately and store it safely.

After the user provides credentials, do not echo them back.

When asking the user for APPID, give the direct entry and what to copy:

- Open [Tencent Cloud Account Info](https://console.cloud.tencent.com/developer).
- Search/check field: **APPID**.
- Action: copy only the numeric APPID, not SecretId, SecretKey, or any other account ID.

## Domain Step

If the user has no domain:

- Say: "We can still test COS buckets and permissions first. CDN/DNS can be added later with this same skill."
- Set `cdn.enabled=false` and `dns.enabled=false` in the generated config.

If the user has a domain but it is not hosted in DNSPod:

- Say: "We can still plan COS and CAM now. I will leave DNS automation off, and the report can show what CNAME values to configure later."
- Set `dns.enabled=false`. Enable CDN only if the user can manually create the required DNS record outside DNSPod.

If the user has a domain:

Ask for:

- Root domain, for example `example.com`.
- Public file domain, or let the skill suggest `public.<root-domain>`.
- Private file domain, or let the skill suggest `private.<root-domain>`.

If the user is in Mainland China and the domain may not have ICP filing, recommend `overseas` CDN area for the smoke test.

## Later Add CDN/DNS

When the user comes back later with a domain, do not make them restart conceptually from zero.

Ask for the previous report first:

```text
Do you still have the previous plan.report.md path? If yes, send it to me and I will reuse the existing COS/CAM values.
```

If they do not have the report, ask only for the missing basics: project name, environment, APPID, region, and existing bucket names. Then generate a new plan that reuses matching COS/CAM resources and adds CDN/DNS. Still ask for confirmation before applying real changes.

## Existing Resource Conflicts

If apply reports an incompatible existing CAM policy, CDN domain, or DNS record, do not call it a normal failure and do not overwrite it. Tell the user the flow is paused and give simple choices:

- Use a new resource name and regenerate the plan.
- Open the Tencent Cloud console to review/update the existing resource manually.
- Skip that feature for now, such as leaving CDN/DNS for later.

Continue only after the user chooses. Every console review action must include the direct URL, click path, search keyword, fields to check, exact action, and whether it is required.

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
I kept the working files in an isolated run directory, not in your project folder.
The report also has a Manual Operator Guide if you want to do the Tencent Cloud steps yourself.
```

Avoid listing raw action IDs such as `cos.create_bucket` unless the user asks.

After the plan summary, ask the user to choose one path:

- AI applies the plan after explicit confirmation.
- User follows the generated Manual Operator Guide.

If the user chooses manual operation, give only the next one or two console actions in chat. Each action must include direct console URL, click path, search keyword, fields to check, exact action, and whether it is required.

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
Open https://console.cloud.tencent.com/cos/bucket -> search bucket -> click bucket -> Domain and Transmission -> Custom CDN acceleration domain
```

If the console shows a CDN service authorization prompt, click the authorization button.

## Final Response Shape

After apply or verify, always give the user:

- The project integration values they need to copy into their own app config.
- Link to the generated report file in the isolated run directory.
- A short "Done / Not done yet" summary.
- The top required manual actions with Tencent Cloud links and click paths.
- For each top required manual action, include direct console URL, click path, search keyword, fields to check, exact action, and whether it is required.
- If the user chose manual operation, point to the report's "Manual Operator Guide" and continue with only the next one or two actions at a time.

Do not finish with only "generated report.md" or raw command output.
