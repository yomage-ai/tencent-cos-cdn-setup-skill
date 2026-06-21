# Safety Rules

## Default To Dry Run

Always run `plan` first. Run `apply` without `--apply` to inspect the exact actions. Only use `--apply` after the user confirms the plan.

For real apply, prefer:

```bash
python3 scripts/tencent_cos_cdn.py apply "$RUN_DIR/plan.json" --apply --stop-on-failure
python3 scripts/tencent_cos_cdn.py resume "$RUN_DIR/plan.json" --apply
```

Use a run directory outside the user's project repository. The state file in that run directory prevents successful actions from being repeated during resume.

## Secrets

- Read Tencent Cloud credentials from `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY`.
- Read CDN TypeA auth keys from the environment variable named by `cdn.private_auth.key_env`.
- Do not print SecretKey, TypeA keys, certificate private keys, or access-key secrets.
- If CAM user creation returns a `SecretKey`, show only that a key was created; never include the secret in generated reports.
- If the script generates a CDN TypeA key, save it from the local secrets file into the backend secret store and do not commit the secrets file.

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
- TypeA keys must be 6-32 letters/digits. Do not use URL-safe keys with `-` or `_`.
- Wait for CDN domains to finish deployment before updating TypeA authentication.
- Private COS origins require COS private origin access / CDN service authorization. Treat the COS console check as mandatory.
- Existing complex CDN configs should be queried and reviewed before partial updates. Tencent Cloud CDN `UpdateDomainConfig` can reset omitted nested fields for complex config objects.

## No Destructive Actions

This skill must not delete buckets, objects, CDN domains, CAM users, policies, or DNS records.
