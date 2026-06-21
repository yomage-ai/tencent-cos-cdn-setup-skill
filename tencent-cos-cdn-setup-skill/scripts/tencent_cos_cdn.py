#!/usr/bin/env python3
"""Plan, apply, and verify Tencent COS + CDN + DNSPod setups.

The script is intentionally conservative:
- `plan` never contacts Tencent Cloud.
- `apply` is a dry run unless `--apply` is passed.
- secrets are read from environment variables and redacted from output.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


Json = Dict[str, Any]

VALID_MODES = {"public-only", "private-only", "public-private"}
DEFAULT_COS_ACTIONS = [
    "name/cos:PutObject",
    "name/cos:GetObject",
    "name/cos:HeadObject",
    "name/cos:DeleteObject",
]
SECRET_KEYS = {"secret_key", "secretkey", "auth_key", "key", "password"}


class SkillError(Exception):
    """Expected user-facing failure."""


@dataclass
class Credentials:
    secret_id: str
    secret_key: str


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-config", help="write a starter JSON config")
    init.add_argument("--mode", choices=sorted(VALID_MODES), default="public-private")
    init.add_argument("--out", required=True)

    plan = sub.add_parser("plan", help="generate a plan from config")
    plan.add_argument("config")
    plan.add_argument("--out", default="plan.json")
    plan.add_argument("--report")

    render = sub.add_parser("render-policy", help="render only the CAM policy JSON")
    render.add_argument("config")

    apply_p = sub.add_parser("apply", help="apply a plan, dry-run by default")
    apply_p.add_argument("plan")
    apply_p.add_argument("--apply", action="store_true", help="perform real cloud changes")
    apply_p.add_argument("--replace-dns", action="store_true", help="allow replacing conflicting DNSPod CNAME values")

    verify = sub.add_parser("verify", help="verify DNS and HTTP/CDN behavior")
    verify.add_argument("plan")
    verify.add_argument("--report")
    verify.add_argument("--timeout", type=int, default=10)

    args = parser.parse_args(argv)

    try:
        if args.command == "init-config":
            return cmd_init_config(args)
        if args.command == "plan":
            return cmd_plan(args)
        if args.command == "render-policy":
            return cmd_render_policy(args)
        if args.command == "apply":
            return cmd_apply(args)
        if args.command == "verify":
            return cmd_verify(args)
    except SkillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    return 0


def cmd_init_config(args: argparse.Namespace) -> int:
    cfg = starter_config(args.mode)
    write_json(Path(args.out), cfg)
    print(f"wrote {args.out}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))
    plan = build_plan(config)
    write_json(Path(args.out), plan)
    print(f"wrote {args.out}")
    if args.report:
        Path(args.report).write_text(render_report(plan), encoding="utf-8")
        print(f"wrote {args.report}")
    else:
        print(render_plan_summary(plan))
    return 0


def cmd_render_policy(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))
    plan = build_plan(config)
    print(json.dumps(plan["cam_policy"], indent=2, ensure_ascii=False))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    plan = load_config(Path(args.plan))
    actions = plan.get("actions", [])
    if not actions:
        print("No actions in plan.")
        return 0

    dry_run = not args.apply
    print(f"mode: {'dry-run' if dry_run else 'apply'}")
    print(render_plan_summary(plan))

    if dry_run:
        print("Dry run only. Re-run with --apply to perform these actions.")
        return 0

    creds = load_credentials()
    ctx = ApplyContext(plan=plan, creds=creds, replace_dns=args.replace_dns)
    results: List[Json] = []
    for index, action in enumerate(actions, start=1):
        print(f"[{index}/{len(actions)}] {action['id']}")
        result = apply_action(ctx, action)
        results.append(result)
        status = result.get("status", "unknown")
        detail = result.get("detail", "")
        print(f"  {status}{': ' + detail if detail else ''}")

    print(json.dumps({"results": redact(results)}, indent=2, ensure_ascii=False))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    plan = load_config(Path(args.plan))
    results = verify_plan(plan, timeout=args.timeout)
    output = render_verify_report(plan, results)
    if args.report:
        Path(args.report).write_text(output, encoding="utf-8")
        print(f"wrote {args.report}")
    else:
        print(output)
    failed = [r for r in results if r["status"] == "fail"]
    return 1 if failed else 0


def starter_config(mode: str) -> Json:
    cfg: Json = {
        "project": "demo-app",
        "env": "prod",
        "region": "ap-shanghai",
        "appid": "1250000000",
        "mode": mode,
        "buckets": {},
        "cors": {
            "origins": ["https://app.example.com", "http://localhost:5173"],
            "methods": ["GET", "PUT", "HEAD", "OPTIONS"],
            "allowed_headers": ["*"],
            "expose_headers": ["ETag", "Content-Length", "Content-Type"],
            "max_age_seconds": 600,
        },
        "cam": {
            "enabled": True,
            "user_name": "demo-cos-prod",
            "create_user": True,
            "create_access_key": False,
            "policy_name": "demo-cos-prod-policy",
        },
        "cdn": {
            "enabled": True,
            "area": "mainland",
            "service_type": "web",
            "private_auth": {
                "type": "tencent_type_a",
                "key_env": "TENCENT_CDN_AUTH_KEY",
                "sign_param": "sign",
                "ttl_seconds": 3600,
            },
        },
        "dns": {
            "enabled": True,
            "zone": "example.com",
            "ttl": 600,
            "replace_existing": False,
        },
    }
    if mode in {"public-only", "public-private"}:
        cfg["buckets"]["public"] = {"base_name": "demo-public-prod", "acl": "public-read"}
        cfg["cdn"]["public_domain"] = "public.example.com"
    if mode in {"private-only", "public-private"}:
        cfg["buckets"]["private"] = {"base_name": "demo-private-prod", "acl": "private"}
        cfg["cdn"]["private_domain"] = "private.example.com"
    return cfg


def build_plan(config: Json) -> Json:
    cfg = normalize_config(config)
    buckets = resolve_buckets(cfg)
    actions: List[Json] = []
    warnings: List[str] = []

    cors = build_cors(cfg.get("cors", {}))
    for bucket in buckets:
        actions.extend(
            [
                action("cos.create_bucket", f"Create or reuse COS bucket {bucket['name']}", {
                    "bucket": bucket["name"],
                    "acl": bucket["cos_acl"],
                    "region": cfg["region"],
                }),
                action("cos.put_bucket_acl", f"Set COS bucket ACL for {bucket['name']}", {
                    "bucket": bucket["name"],
                    "acl": bucket["cos_acl"],
                }),
                action("cos.put_bucket_cors", f"Set COS bucket CORS for {bucket['name']}", {
                    "bucket": bucket["name"],
                    "cors": cors,
                }),
            ]
        )

    cam_policy = build_cam_policy(cfg, buckets)
    cam = cfg.get("cam", {})
    if cam.get("enabled", True):
        if cam.get("create_user", True):
            actions.append(action("cam.add_user", f"Create CAM sub-user {cam['user_name']}", {
                "name": cam["user_name"],
                "remark": f"{cfg['project']} {cfg['env']} COS access",
                "console_login": 0,
                "use_api": 1 if cam.get("create_access_key") else 0,
            }))
            if cam.get("create_access_key"):
                warnings.append("CAM create_access_key is enabled. The returned SecretKey is shown only once by Tencent Cloud and will be redacted by this script.")
        actions.append(action("cam.create_policy", f"Create CAM policy {cam['policy_name']}", {
            "policy_name": cam["policy_name"],
            "description": f"Least-privilege COS access for {cfg['project']} {cfg['env']}",
            "policy_document": cam_policy,
        }))
        if cam.get("create_user", True) or cam.get("user_uin"):
            actions.append(action("cam.attach_user_policy", f"Attach policy to CAM user {cam.get('user_uin') or cam['user_name']}", {
                "user_uin": cam.get("user_uin"),
                "policy_name": cam["policy_name"],
            }))
        else:
            warnings.append("CAM policy will be created but not attached because cam.user_uin is missing and cam.create_user is false.")

    cdn = cfg.get("cdn", {})
    dns_records: List[Json] = []
    if cdn.get("enabled", False):
        for bucket in buckets:
            domain_key = f"{bucket['kind']}_domain"
            domain = cdn.get(domain_key)
            if not domain:
                warnings.append(f"CDN enabled but cdn.{domain_key} is missing; skipped {bucket['kind']} CDN.")
                continue
            origin = cos_origin(bucket["name"], cfg["region"])
            actions.append(action("cdn.add_domain", f"Add CDN domain {domain}", {
                "domain": domain,
                "service_type": cdn.get("service_type", "web"),
                "area": cdn.get("area", "mainland"),
                "origin": origin,
            }))
            if bucket["kind"] == "private":
                auth = cdn.get("private_auth", {})
                if auth.get("type", "tencent_type_a") != "tencent_type_a":
                    raise SkillError("Only tencent_type_a private CDN auth is supported.")
                actions.append(action("cdn.update_type_a_auth", f"Configure CDN TypeA authentication for {domain}", {
                    "domain": domain,
                    "key_env": auth.get("key_env", "TENCENT_CDN_AUTH_KEY"),
                    "sign_param": auth.get("sign_param", "sign"),
                    "ttl_seconds": int(auth.get("ttl_seconds", 3600)),
                }))
                actions.append(action("manual.cos_cdn_service_authorization", f"Confirm COS CDN service authorization for {bucket['name']}", {
                    "bucket": bucket["name"],
                    "domain": domain,
                    "console_path": "COS > bucket > Domain and Transmission > Custom CDN acceleration domain",
                }))
            cname_key = f"{bucket['kind']}_cname_target"
            target = cdn.get(cname_key) or f"{domain}.cdn.dnsv1.com"
            dns_records.append({"domain": domain, "target": target, "kind": bucket["kind"]})

    dns = cfg.get("dns", {})
    if dns.get("enabled", False):
        if not dns.get("zone"):
            raise SkillError("dns.zone is required when dns.enabled is true.")
        for record in dns_records:
            zone, subdomain = split_dns_name(record["domain"], dns["zone"])
            actions.append(action("dnspod.ensure_cname", f"Ensure DNSPod CNAME {record['domain']} -> {record['target']}", {
                "zone": zone,
                "subdomain": subdomain,
                "fqdn": record["domain"],
                "target": record["target"],
                "ttl": int(dns.get("ttl", 600)),
                "replace_existing": bool(dns.get("replace_existing", False)),
            }))

    return {
        "version": 1,
        "generated_at": int(time.time()),
        "config": redact(cfg),
        "buckets": buckets,
        "cam_policy": cam_policy,
        "actions": actions,
        "warnings": warnings,
    }


def normalize_config(config: Json) -> Json:
    cfg = dict(config)
    required = ["project", "env", "region", "mode"]
    missing = [key for key in required if not cfg.get(key)]
    if missing:
        raise SkillError(f"missing required field(s): {', '.join(missing)}")
    if cfg["mode"] not in VALID_MODES:
        raise SkillError(f"mode must be one of {', '.join(sorted(VALID_MODES))}")
    cfg.setdefault("buckets", {})
    cfg.setdefault("cors", {})
    cfg.setdefault("cam", {})
    cfg.setdefault("cdn", {})
    cfg.setdefault("dns", {})
    cfg["cam"].setdefault("enabled", True)
    cfg["cam"].setdefault("user_name", f"{cfg['project']}-cos-{cfg['env']}")
    cfg["cam"].setdefault("create_user", True)
    cfg["cam"].setdefault("create_access_key", False)
    cfg["cam"].setdefault("policy_name", f"{cfg['project']}-cos-{cfg['env']}-policy")
    return cfg


def resolve_buckets(cfg: Json) -> List[Json]:
    needed = []
    if cfg["mode"] in {"public-only", "public-private"}:
        needed.append("public")
    if cfg["mode"] in {"private-only", "public-private"}:
        needed.append("private")

    buckets = []
    for kind in needed:
        spec = cfg.get("buckets", {}).get(kind)
        if not spec:
            raise SkillError(f"buckets.{kind} is required for mode {cfg['mode']}")
        name = spec.get("name")
        base_name = spec.get("base_name")
        appid = str(cfg.get("appid", "")).strip()
        if not name:
            if not base_name or not appid:
                raise SkillError(f"buckets.{kind}.name or buckets.{kind}.base_name + appid is required")
            name = f"{base_name}-{appid}"
        acl = spec.get("acl", "public-read" if kind == "public" else "private")
        cos_acl = normalize_acl(acl)
        buckets.append({
            "kind": kind,
            "name": name,
            "base_name": base_name or name.rsplit("-", 1)[0],
            "acl": acl,
            "cos_acl": cos_acl,
            "resource": f"qcs::cos:{cfg['region']}:uid/{appid}:{name}/*" if appid else f"qcs::cos:{cfg['region']}::*:{name}/*",
            "origin": cos_origin(name, cfg["region"]),
        })
    return buckets


def normalize_acl(acl: str) -> str:
    mapping = {
        "private": "private",
        "public-read": "public-read",
        "public-read-private-write": "public-read",
    }
    if acl not in mapping:
        raise SkillError(f"unsupported bucket acl: {acl}")
    return mapping[acl]


def cos_origin(bucket: str, region: str) -> str:
    return f"{bucket}.cos.{region}.myqcloud.com"


def build_cors(cors: Json) -> Json:
    origins = cors.get("origins") or []
    if not origins:
        raise SkillError("cors.origins must contain at least one origin.")
    methods = cors.get("methods") or ["GET", "PUT", "HEAD", "OPTIONS"]
    methods = [m for m in methods if m != "OPTIONS"]
    return {
        "CORSRule": [{
            "ID": cors.get("id", "app-delivery"),
            "AllowedOrigin": origins,
            "AllowedMethod": methods,
            "AllowedHeader": cors.get("allowed_headers", ["*"]),
            "ExposeHeader": cors.get("expose_headers", ["ETag", "Content-Length", "Content-Type"]),
            "MaxAgeSeconds": int(cors.get("max_age_seconds", 600)),
        }],
        "ResponseVary": bool(cors.get("response_vary", True)),
    }


def build_cam_policy(cfg: Json, buckets: List[Json]) -> Json:
    actions = cfg.get("cam", {}).get("actions") or DEFAULT_COS_ACTIONS
    resources = [bucket["resource"] for bucket in buckets]
    return {
        "version": "2.0",
        "statement": [{
            "effect": "allow",
            "action": actions,
            "resource": resources,
        }],
    }


def action(kind: str, description: str, params: Json) -> Json:
    return {
        "id": f"{kind}:{stable_suffix(description)}",
        "kind": kind,
        "description": description,
        "params": redact(params),
    }


def stable_suffix(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    compact = "-".join(filter(None, "".join(keep).split("-")))
    return compact[:60]


def split_dns_name(fqdn: str, zone: str) -> Tuple[str, str]:
    fqdn = fqdn.rstrip(".")
    zone = zone.rstrip(".")
    if fqdn == zone:
        return zone, "@"
    suffix = "." + zone
    if not fqdn.endswith(suffix):
        raise SkillError(f"{fqdn} is not under DNS zone {zone}")
    return zone, fqdn[: -len(suffix)]


@dataclass
class ApplyContext:
    plan: Json
    creds: Credentials
    replace_dns: bool = False
    cam_user_uin: Optional[int] = None
    cam_policy_id: Optional[int] = None


def apply_action(ctx: ApplyContext, action_obj: Json) -> Json:
    kind = action_obj["kind"]
    params = action_obj.get("params", {})
    try:
        if kind == "cos.create_bucket":
            return apply_cos_create_bucket(ctx, params)
        if kind == "cos.put_bucket_acl":
            return apply_cos_put_acl(ctx, params)
        if kind == "cos.put_bucket_cors":
            return apply_cos_put_cors(ctx, params)
        if kind == "cam.add_user":
            return apply_cam_add_user(ctx, params)
        if kind == "cam.create_policy":
            return apply_cam_create_policy(ctx, params)
        if kind == "cam.attach_user_policy":
            return apply_cam_attach_user_policy(ctx, params)
        if kind == "cdn.add_domain":
            return apply_cdn_add_domain(ctx, params)
        if kind == "cdn.update_type_a_auth":
            return apply_cdn_update_type_a_auth(ctx, params)
        if kind == "dnspod.ensure_cname":
            return apply_dnspod_ensure_cname(ctx, params)
        if kind.startswith("manual."):
            return {"status": "manual", "detail": action_obj["description"], "params": params}
        raise SkillError(f"unknown action kind: {kind}")
    except Exception as exc:  # noqa: BLE001 - convert SDK failures to a report row.
        return {"status": "fail", "detail": str(exc), "action": action_obj["id"]}


def load_credentials() -> Credentials:
    secret_id = os.environ.get("TENCENTCLOUD_SECRET_ID") or os.environ.get("TENCENT_SECRET_ID")
    secret_key = os.environ.get("TENCENTCLOUD_SECRET_KEY") or os.environ.get("TENCENT_SECRET_KEY")
    if not secret_id or not secret_key:
        raise SkillError("export TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY before --apply")
    return Credentials(secret_id=secret_id, secret_key=secret_key)


def cos_client(ctx: ApplyContext, region: str):
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as exc:
        raise SkillError("missing cos-python-sdk-v5; install with: python -m pip install cos-python-sdk-v5") from exc
    config = CosConfig(Region=region, SecretId=ctx.creds.secret_id, SecretKey=ctx.creds.secret_key)
    return CosS3Client(config)


def apply_cos_create_bucket(ctx: ApplyContext, params: Json) -> Json:
    client = cos_client(ctx, params["region"])
    try:
        client.create_bucket(Bucket=params["bucket"], ACL=params["acl"])
        return {"status": "ok", "detail": "created"}
    except Exception as exc:  # noqa: BLE001
        if "BucketAlreadyOwnedByYou" in str(exc):
            return {"status": "ok", "detail": "already exists"}
        raise


def apply_cos_put_acl(ctx: ApplyContext, params: Json) -> Json:
    region = ctx.plan["config"]["region"]
    client = cos_client(ctx, region)
    client.put_bucket_acl(Bucket=params["bucket"], ACL=params["acl"])
    return {"status": "ok", "detail": "acl updated"}


def apply_cos_put_cors(ctx: ApplyContext, params: Json) -> Json:
    region = ctx.plan["config"]["region"]
    client = cos_client(ctx, region)
    client.put_bucket_cors(Bucket=params["bucket"], CORSConfiguration=params["cors"])
    return {"status": "ok", "detail": "cors updated"}


def tencent_client(ctx: ApplyContext, service: str):
    try:
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
    except ImportError as exc:
        raise SkillError("missing tencentcloud-sdk-python; install with: python -m pip install tencentcloud-sdk-python") from exc

    cred = credential.Credential(ctx.creds.secret_id, ctx.creds.secret_key)
    http_profile = HttpProfile()
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile

    if service == "cam":
        from tencentcloud.cam.v20190116 import cam_client, models
        return cam_client.CamClient(cred, "", client_profile), models
    if service == "cdn":
        from tencentcloud.cdn.v20180606 import cdn_client, models
        return cdn_client.CdnClient(cred, "", client_profile), models
    if service == "dnspod":
        from tencentcloud.dnspod.v20210323 import dnspod_client, models
        return dnspod_client.DnspodClient(cred, "", client_profile), models
    raise SkillError(f"unsupported Tencent Cloud service: {service}")


def sdk_call(ctx: ApplyContext, service: str, action_name: str, params: Json) -> Json:
    client, models = tencent_client(ctx, service)
    req_cls = getattr(models, f"{action_name}Request")
    req = req_cls()
    req.from_json_string(json.dumps(params))
    response = getattr(client, action_name)(req)
    return json.loads(response.to_json_string())


def apply_cam_add_user(ctx: ApplyContext, params: Json) -> Json:
    sdk_params = {
        "Name": params["name"],
        "Remark": params.get("remark", ""),
        "ConsoleLogin": int(params.get("console_login", 0)),
        "UseApi": int(params.get("use_api", 0)),
    }
    resp = sdk_call(ctx, "cam", "AddUser", sdk_params)
    ctx.cam_user_uin = int(resp.get("Uin"))
    detail = f"created uin={ctx.cam_user_uin}"
    if resp.get("SecretId"):
        detail += " with access key (secret redacted)"
    return {"status": "ok", "detail": detail, "response": redact(resp)}


def apply_cam_create_policy(ctx: ApplyContext, params: Json) -> Json:
    sdk_params = {
        "PolicyName": params["policy_name"],
        "Description": params.get("description", ""),
        "PolicyDocument": json.dumps(params["policy_document"], separators=(",", ":")),
    }
    resp = sdk_call(ctx, "cam", "CreatePolicy", sdk_params)
    ctx.cam_policy_id = int(resp.get("PolicyId"))
    return {"status": "ok", "detail": f"policy_id={ctx.cam_policy_id}", "response": resp}


def apply_cam_attach_user_policy(ctx: ApplyContext, params: Json) -> Json:
    user_uin = params.get("user_uin") or ctx.cam_user_uin
    policy_id = ctx.cam_policy_id
    if not user_uin:
        raise SkillError("CAM user UIN is missing. Create a user in this run or set cam.user_uin.")
    if not policy_id:
        raise SkillError("CAM policy ID is missing. Create the policy in this run.")
    resp = sdk_call(ctx, "cam", "AttachUserPolicy", {"AttachUin": int(user_uin), "PolicyId": int(policy_id)})
    return {"status": "ok", "detail": "attached", "response": resp}


def apply_cdn_add_domain(ctx: ApplyContext, params: Json) -> Json:
    sdk_params = {
        "Domain": params["domain"],
        "ServiceType": params.get("service_type", "web"),
        "Area": params.get("area", "mainland"),
        "Origin": {
            "OriginType": "domain",
            "Origins": [params["origin"]],
            "ServerName": params["origin"],
        },
    }
    try:
        resp = sdk_call(ctx, "cdn", "AddCdnDomain", sdk_params)
        return {"status": "ok", "detail": "domain added", "response": resp}
    except Exception as exc:  # noqa: BLE001
        if "ResourceInUse.CdnHostExists" in str(exc) or "CdnHostExists" in str(exc):
            return {"status": "ok", "detail": "domain already exists"}
        raise


def apply_cdn_update_type_a_auth(ctx: ApplyContext, params: Json) -> Json:
    key_env = params.get("key_env", "TENCENT_CDN_AUTH_KEY")
    auth_key = os.environ.get(key_env)
    if not auth_key:
        raise SkillError(f"private CDN auth key is missing. Export {key_env}.")
    sdk_params = {
        "Domain": params["domain"],
        "Authentication": {
            "Switch": "on",
            "AuthAlgorithm": "md5",
            "TypeA": {
                "SecretKey": auth_key,
                "SignParam": params.get("sign_param", "sign"),
                "ExpireTime": int(params.get("ttl_seconds", 3600)),
                "ExpireTimeFormat": "decimal",
            },
        },
    }
    resp = sdk_call(ctx, "cdn", "UpdateDomainConfig", sdk_params)
    return {"status": "ok", "detail": "TypeA auth updated", "response": redact(resp)}


def apply_dnspod_ensure_cname(ctx: ApplyContext, params: Json) -> Json:
    zone = params["zone"]
    subdomain = params["subdomain"]
    target = params["target"].rstrip(".")
    replace = bool(params.get("replace_existing")) or ctx.replace_dns
    existing = dnspod_find_records(ctx, zone, subdomain)
    cname = [r for r in existing if str(r.get("Type", "")).upper() == "CNAME"]
    others = [r for r in existing if str(r.get("Type", "")).upper() != "CNAME"]

    if others and not replace:
        raise SkillError(f"conflicting non-CNAME DNS records exist for {params['fqdn']}")
    if cname:
        record = cname[0]
        value = str(record.get("Value", "")).rstrip(".")
        record_id = int(record.get("RecordId") or record.get("RecordId".lower()))
        if value == target:
            return {"status": "ok", "detail": "matching CNAME already exists"}
        if not replace:
            raise SkillError(f"conflicting CNAME exists for {params['fqdn']}: {value}")
        resp = sdk_call(ctx, "dnspod", "ModifyRecord", {
            "Domain": zone,
            "RecordId": record_id,
            "SubDomain": subdomain,
            "RecordType": "CNAME",
            "RecordLine": "Default",
            "Value": target,
            "TTL": int(params.get("ttl", 600)),
        })
        return {"status": "ok", "detail": "CNAME modified", "response": resp}

    resp = sdk_call(ctx, "dnspod", "CreateRecord", {
        "Domain": zone,
        "SubDomain": subdomain,
        "RecordType": "CNAME",
        "RecordLine": "Default",
        "Value": target,
        "TTL": int(params.get("ttl", 600)),
    })
    return {"status": "ok", "detail": "CNAME created", "response": resp}


def dnspod_find_records(ctx: ApplyContext, zone: str, subdomain: str) -> List[Json]:
    resp = sdk_call(ctx, "dnspod", "DescribeRecordList", {
        "Domain": zone,
        "Subdomain": subdomain,
        "Limit": 100,
    })
    return resp.get("RecordList") or []


def verify_plan(plan: Json, timeout: int) -> List[Json]:
    results: List[Json] = []
    for action_obj in plan.get("actions", []):
        if action_obj["kind"] != "dnspod.ensure_cname":
            continue
        params = action_obj["params"]
        fqdn = params["fqdn"]
        target = params["target"].rstrip(".")
        observed = resolve_dns(fqdn)
        if any(item.rstrip(".") == target for item in observed):
            results.append({"check": f"dns:{fqdn}", "status": "pass", "detail": f"CNAME includes {target}"})
        else:
            results.append({"check": f"dns:{fqdn}", "status": "warn", "detail": f"observed {observed or 'no result'}, expected {target}"})
        results.append(check_http(f"https://{fqdn}/", timeout))
    return results


def resolve_dns(name: str) -> List[str]:
    dig = subprocess.run(["/usr/bin/env", "dig", "+short", name], text=True, capture_output=True)
    if dig.returncode == 0 and dig.stdout.strip():
        return [line.strip() for line in dig.stdout.splitlines() if line.strip()]
    try:
        return sorted({item[4][0] for item in socket.getaddrinfo(name, 443)})
    except socket.gaierror:
        return []


def check_http(url: str, timeout: int) -> Json:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "tencent-cos-cdn-setup-skill/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            server = resp.headers.get("Server", "")
            cache = resp.headers.get("X-Cache-Lookup", "")
            return {"check": f"http:{url}", "status": "pass", "detail": f"status={resp.status} server={server} cache={cache}"}
    except urllib.error.HTTPError as exc:
        detail = f"status={exc.code} server={exc.headers.get('Server', '')}"
        status = "warn" if exc.code in {403, 404} else "fail"
        return {"check": f"http:{url}", "status": status, "detail": detail}
    except Exception as exc:  # noqa: BLE001
        return {"check": f"http:{url}", "status": "warn", "detail": str(exc)}


def render_plan_summary(plan: Json) -> str:
    lines = [
        f"Plan version: {plan.get('version')}",
        f"Buckets: {', '.join(bucket['name'] for bucket in plan.get('buckets', [])) or 'none'}",
        f"Actions: {len(plan.get('actions', []))}",
    ]
    for warning in plan.get("warnings", []):
        lines.append(f"Warning: {warning}")
    for item in plan.get("actions", []):
        lines.append(f"- {item['kind']}: {item['description']}")
    return "\n".join(lines)


def render_report(plan: Json) -> str:
    lines = [
        "# Tencent COS/CDN Setup Plan",
        "",
        render_plan_summary(plan),
        "",
        "## CAM Policy",
        "",
        "```json",
        json.dumps(plan.get("cam_policy", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Actions",
        "",
    ]
    for item in plan.get("actions", []):
        lines.extend([
            f"### {item['kind']}",
            "",
            item["description"],
            "",
            "```json",
            json.dumps(item.get("params", {}), indent=2, ensure_ascii=False),
            "```",
            "",
        ])
    return "\n".join(lines)


def render_verify_report(plan: Json, results: List[Json]) -> str:
    lines = ["# Tencent COS/CDN Verification", ""]
    lines.append(f"Generated for {len(plan.get('actions', []))} planned actions.")
    lines.append("")
    for result in results:
        lines.append(f"- {result['status'].upper()} {result['check']}: {result['detail']}")
    return "\n".join(lines)


def load_config(path: Path) -> Json:
    if not path.exists():
        raise SkillError(f"file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise SkillError("YAML requires PyYAML. Install it or use JSON.") from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise SkillError("config/plan must be a JSON object")
    return data


def write_json(path: Path, data: Json) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key.lower() in SECRET_KEYS:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
