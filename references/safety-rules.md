# Safety Rules

## Default To Dry Run

Always run `plan` first. Run `apply` without `--apply` to inspect the exact actions. Only use `--apply` after the user confirms the plan.

## Secrets

- Read Tencent Cloud credentials from `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY`.
- Read CDN TypeA auth keys from the environment variable named by `cdn.private_auth.key_env`.
- Do not print SecretKey, TypeA keys, certificate private keys, or access-key secrets.
- If CAM user creation returns a `SecretKey`, show only that a key was created; never include the secret in generated reports.

## DNS

- If no record exists, creating a CNAME is safe.
- If an identical CNAME exists, skip it.
- If a different CNAME exists, stop unless replacement is explicitly enabled.
- If A/AAAA/TXT/MX or another record type exists for the same host, stop unless the user explicitly accepts the risk and replacement is supported.

## CAM

- Prefer a dedicated CAM sub-user per application/environment.
- Keep `create_access_key` false unless the user explicitly asks for a long-lived key.
- Use generated least-privilege policies for selected buckets. Do not attach administrator policies.

## CDN

- Public CDN domains should not enable URL authentication by default.
- Private CDN domains should enable TypeA authentication by default.
- Private CDN TTL must match the application's download URL TTL.
- Existing complex CDN configs should be queried and reviewed before partial updates. Tencent Cloud CDN `UpdateDomainConfig` can reset omitted nested fields for complex config objects.

## No Destructive Actions

This skill must not delete buckets, objects, CDN domains, CAM users, policies, or DNS records.
