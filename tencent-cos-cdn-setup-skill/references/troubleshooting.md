# Troubleshooting

## Setup Fails Before Cloud Calls

- Missing `tencentcloud-sdk-python`: install it with `python -m pip install tencentcloud-sdk-python`.
- Missing COS SDK: install it with `python -m pip install cos-python-sdk-v5`.
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
- Private CDN returns 403 from COS: check COS bucket CDN service authorization / origin-pull authorization in the COS console.

## DNSPod

- Domain not found: ensure the zone is hosted in DNSPod under the same Tencent Cloud account.
- Conflicting record: inspect the existing record before enabling replacement.
- DNS has not propagated: wait for TTL and rerun `verify`.
