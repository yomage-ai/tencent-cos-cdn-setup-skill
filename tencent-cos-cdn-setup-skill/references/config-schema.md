# Config Schema

Use JSON for the most portable path. YAML is also accepted when `PyYAML` is installed.

## Minimal Example

```json
{
  "project": "demo-app",
  "env": "prod",
  "region": "ap-shanghai",
  "appid": "1250000000",
  "mode": "public-private",
  "buckets": {
    "public": {
      "base_name": "demo-public-prod",
      "acl": "public-read"
    },
    "private": {
      "base_name": "demo-private-prod",
      "acl": "private"
    }
  },
  "cors": {
    "origins": ["https://app.example.com", "http://localhost:5173"],
    "methods": ["GET", "PUT", "HEAD", "OPTIONS"],
    "allowed_headers": ["*"],
    "expose_headers": ["ETag", "Content-Length", "Content-Type"],
    "max_age_seconds": 600
  },
  "cam": {
    "enabled": true,
    "user_name": "demo-cos-prod",
    "create_user": true,
    "create_access_key": false,
    "policy_name": "demo-cos-prod-policy"
  },
  "cdn": {
    "enabled": true,
    "area": "mainland",
    "service_type": "web",
    "public_domain": "public.example.com",
    "private_domain": "private.example.com",
    "private_auth": {
      "type": "tencent_type_a",
      "key_env": "TENCENT_CDN_AUTH_KEY",
      "sign_param": "sign",
      "ttl_seconds": 3600
    }
  },
  "dns": {
    "enabled": true,
    "zone": "example.com",
    "ttl": 600,
    "replace_existing": false
  }
}
```

## Required Fields

- `project`: short project identifier used in generated names and reports.
- `env`: environment label such as `dev`, `staging`, or `prod`.
- `region`: COS region, for example `ap-shanghai`.
- `appid`: Tencent Cloud APPID. If omitted, every bucket `name` must already include the `-APPID` suffix.
- `mode`: one of `public-only`, `private-only`, `public-private`.

## Buckets

Each enabled bucket accepts:

- `name`: full bucket name such as `demo-public-prod-1250000000`.
- `base_name`: bucket prefix without APPID. The script appends `-<appid>`.
- `acl`: `private`, `public-read`, or `public-read-private-write`. The last value is normalized to COS canned ACL `public-read`.

`public-only` requires `buckets.public`. `private-only` requires `buckets.private`. `public-private` requires both.

## CDN

When `cdn.enabled` is true:

- Public domains are generated for the public bucket only.
- Private domains are generated for the private bucket only.
- `cdn.private_auth.key_env` names an environment variable. Store the real TypeA auth key there.
- `cdn.private_auth.ttl_seconds` should match the application download URL TTL.

The script uses COS default bucket domains as CDN origins:

```text
<bucket>.cos.<region>.myqcloud.com
```

## DNSPod

When `dns.enabled` is true:

- `dns.zone` is the DNSPod root zone such as `example.com`.
- The script creates CNAME records for CDN domains.
- By default, CNAME targets are generated as `<domain>.cdn.dnsv1.com`. Override with `cdn.public_cname_target` or `cdn.private_cname_target` if Tencent Cloud returns a different target.
- Existing conflicting records stop the run unless `dns.replace_existing` is true or `--replace-dns` is passed.

## Credentials

Use environment variables:

```bash
export TENCENTCLOUD_SECRET_ID="..."
export TENCENTCLOUD_SECRET_KEY="..."
```

Do not put SecretKey or CDN auth keys in config files.
