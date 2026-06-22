# Troubleshooting

## Setup Fails Before Cloud Calls

- Missing Tencent Cloud SDK dependencies: the script should automatically create an isolated runtime under the user cache and install them there.
- If isolated runtime setup fails, check network access to PyPI or set `TENCENT_COS_CDN_SKILL_CACHE` to a writable cache directory and rerun.
- YAML config fails to load: install `PyYAML` or use JSON.
- Missing credentials: export `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY`.

## COS

- `BucketAlreadyOwnedByYou`: treat as reuse and continue.
- `BucketAlreadyExists`: choose a globally unique bucket base name.
- `AccessDenied`: check that the credentials have COS bucket-management permission.
- CORS preflight fails: verify the bucket CORS rule includes the exact scheme, host, and non-default port.

## CAM

- `SubUserNameInUse`: the script will try to look up the existing user by name and use it as the target app sub-user. Check the report for any setting differences such as console login.
- `PolicyNameInUse`: the script will fetch the existing policy and reuse it only when the document exactly matches or is permission-equivalent to the planned least-privilege COS bucket policy. Broader or mismatched policies pause the flow; choose a new `cam.policy_name`, manually review/update the existing policy in CAM, or skip policy attachment until the user decides.
- Attach fails with user not found: the target sub-user could not be resolved. Choose an existing CAM user in the console or let the skill create a new one.
- Attach reports already done: the target user already has the planned policy attached, so no extra action is needed.

## CDN

- `CdnHostNoIcp`: use an eligible acceleration area or complete ICP filing.
- `CdnHostExists`: the script will read the existing domain config and reuse it only when origin/service settings match the plan. If it fails compatibility, the flow pauses; use a new CDN domain, manually review the existing domain, or skip CDN for now.
- `CdnConfigInvalidHost`: verify the domain is a valid public hostname.
- `域名部署中，请在域名部署完成后重试`: run `resume "$RUN_DIR/plan.json" --apply` after the CDN domain status becomes deployed/online.
- TypeA format error: ensure the key is 6-32 letters/digits and `FileExtensions`/`FilterType` are present.
- Private CDN returns 403 from COS: check COS bucket CDN service authorization / origin-pull authorization in the COS console.
- `CosPrivateAccess = off`: private COS origin access is not complete. Rerun resume; if still off, enable it in the COS/CDN console.

## DNSPod

- Domain not found: ensure the zone is hosted in DNSPod under the same Tencent Cloud account.
- Conflicting record: inspect the existing record before enabling replacement.
- Empty record query returns `ResourceNotFound.NoDataOfRecord`: treat it as no existing record and create the CNAME.
- `记录线路不正确`: use `record_line: "默认"` for Chinese DNSPod accounts.
- DNS has not propagated: wait for TTL and rerun `verify`.
