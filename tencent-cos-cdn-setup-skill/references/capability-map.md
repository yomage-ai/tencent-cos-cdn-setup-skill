# Capability Map

This skill is a semi-automated setup assistant for standard Tencent Cloud COS delivery stacks.

## Automated

- Generate an end-to-end plan for `public-only`, `private-only`, or `public-private` modes.
- Generate least-privilege CAM policy JSON for object read/write/delete access to selected buckets.
- Create or reuse standard COS buckets.
- Set COS bucket ACLs.
- Configure COS CORS rules.
- Create a CAM sub-user when requested.
- Create a CAM custom policy and attach it to a newly created or provided sub-user UIN.
- Add CDN acceleration domains using COS default bucket domains as origins.
- Configure private CDN TypeA authentication when a private CDN domain is used.
- Enable CDN COS private origin access for private COS origins when supported by the CDN API.
- Create or update DNSPod CNAME records with conflict protection.
- Verify DNS resolution and HTTPS/HTTP response headers.
- Auto-prepare isolated Python SDK dependencies before real apply.
- Persist apply state and resume after failed runs.
- Generate plan/apply/verify reports with console links, search keywords, check fields, current status, completion state, incomplete reason, and manual action paths.

## Manual Or Confirmed Before Apply

- Buying resource packs or enabling paid services.
- ICP filing and domain ownership compliance.
- HTTPS certificate upload/deployment, unless added in a future version.
- COS private bucket CDN service authorization if Tencent Cloud still requires console confirmation for the target account. The script tries to enable `CosPrivateAccess`, but the report still surfaces the COS console check as mandatory for private CDN.
- Destructive cleanup such as deleting buckets, CDN domains, policies, users, or DNS records.

## Tencent Cloud API Surfaces

- COS XML SDK: create bucket, put bucket ACL, put bucket CORS.
- CAM API 2019-01-16: `AddUser`, `CreatePolicy`, `AttachUserPolicy`.
- CDN API 2018-06-06: `AddCdnDomain`, `UpdateDomainConfig`.
- DNSPod API 2021-03-23: `DescribeRecordList`, `CreateRecord`, `ModifyRecord`.

## Related But Out Of Scope

- Object upload/download workflows and Data Intelligence/CI image processing.
- R2/S3 historical object migration.
- Client ZIP parsing or JSZip download debugging.
- EdgeOne site onboarding.
