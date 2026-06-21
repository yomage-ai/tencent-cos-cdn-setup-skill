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

- `SubUserNameInUse`: reuse the existing user and provide its UIN in config as `cam.user_uin`, or choose a new name.
- `PolicyNameInUse`: reuse the existing policy ID if known or choose a new policy name.
- Attach fails with user not found: `AttachUserPolicy` requires the sub-account UIN, not only the username.

## CDN

- `CdnHostNoIcp`: use an eligible acceleration area or complete ICP filing.
- `CdnHostExists`: reuse the domain and review existing config before updating.
- `CdnConfigInvalidHost`: verify the domain is a valid public hostname.
- `域名部署中，请在域名部署完成后重试`: run `resume plan.json --apply` after the CDN domain status becomes deployed/online.
- TypeA format error: ensure the key is 6-32 letters/digits and `FileExtensions`/`FilterType` are present.
- Private CDN returns 403 from COS: check COS bucket CDN service authorization / origin-pull authorization in the COS console.
- `CosPrivateAccess = off`: private COS origin access is not complete. Rerun resume; if still off, enable it in the COS/CDN console.

## DNSPod

- Domain not found: ensure the zone is hosted in DNSPod under the same Tencent Cloud account.
- Conflicting record: inspect the existing record before enabling replacement.
- Empty record query returns `ResourceNotFound.NoDataOfRecord`: treat it as no existing record and create the CNAME.
- `记录线路不正确`: use `record_line: "默认"` for Chinese DNSPod accounts.
- DNS has not propagated: wait for TTL and rerun `verify`.
