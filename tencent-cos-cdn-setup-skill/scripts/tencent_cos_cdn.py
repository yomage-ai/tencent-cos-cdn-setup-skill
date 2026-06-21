#!/usr/bin/env python3
"""Plan, apply, and verify Tencent COS + CDN + DNSPod setups.

The script is intentionally conservative:
- `plan` never contacts Tencent Cloud.
- `apply` is a dry run unless `--apply` is passed.
- secrets are read from environment variables and redacted from output.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import secrets
import socket
import string
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
SECRET_KEYS.update({"secretid", "secret_id", "secretkey", "secret_key", "private_key"})
TYPE_A_KEY_RE = re.compile(r"^[A-Za-z0-9]{6,32}$")
TYPE_A_KEY_CHARS = string.ascii_letters + string.digits
DEFAULT_DNSPOD_RECORD_LINE = "默认"


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
    apply_p.add_argument("--stop-on-failure", action="store_true", help="stop after the first failed action")
    apply_p.add_argument("--state", help="state file for completed actions")
    apply_p.add_argument("--secrets-file", help="local secrets file for generated CDN TypeA keys")
    apply_p.add_argument("--resume", action="store_true", help="skip actions already marked ok in the state file")

    resume = sub.add_parser("resume", help="resume a previous apply run from the state file")
    resume.add_argument("plan")
    resume.add_argument("--from", dest="resume_from", choices=["failed"], default="failed")
    resume.add_argument("--apply", action="store_true", help="perform real cloud changes")
    resume.add_argument("--replace-dns", action="store_true", help="allow replacing conflicting DNSPod CNAME values")
    resume.add_argument("--stop-on-failure", action="store_true", default=True, help="stop after the first failed action")
    resume.add_argument("--state", help="state file for completed actions")
    resume.add_argument("--secrets-file", help="local secrets file for generated CDN TypeA keys")

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
        if args.command == "resume":
            args.resume = True
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
    plan_path = Path(args.plan)
    plan = load_config(plan_path)
    actions = plan.get("actions", [])
    if not actions:
        print("No actions in plan.")
        return 0

    dry_run = not args.apply
    if dry_run:
        print("mode: dry-run")
        print(render_plan_summary(plan))
        print("Dry run only. Re-run with --apply to perform these actions.")
        return 0

    preflight_apply(plan)
    creds = load_credentials()
    print("mode: apply")
    print(render_plan_summary(plan))
    state_path = Path(args.state) if args.state else default_state_path(plan_path)
    secrets_file = Path(args.secrets_file) if args.secrets_file else default_secrets_path(plan_path)
    state = load_state(state_path)
    ctx = ApplyContext(
        plan=plan,
        creds=creds,
        replace_dns=args.replace_dns,
        plan_path=plan_path,
        state_path=state_path,
        secrets_file=secrets_file,
        state=state,
    )
    hydrate_context_from_state(ctx)
    results: List[Json] = []
    for index, action in enumerate(actions, start=1):
        if args.resume and is_action_successful(ctx, action["id"]):
            print(f"[{index}/{len(actions)}] {action['id']}")
            print("  skipped: already ok in state")
            continue
        print(f"[{index}/{len(actions)}] {action['id']}")
        result = apply_action(ctx, action)
        results.append(result)
        remember_action_result(ctx, action, result)
        status = result.get("status", "unknown")
        detail = result.get("detail", "")
        print(f"  {status}{': ' + detail if detail else ''}")
        if status == "fail" and args.stop_on_failure:
            print(f"Stopped after first failure. Fix the issue and run: python3 {Path(__file__).name} resume {plan_path} --apply")
            print(f"State file: {state_path}")
            return 1

    print(json.dumps({"results": redact(results)}, indent=2, ensure_ascii=False))
    print(f"State file: {state_path}")
    if secrets_file.exists():
        print(f"Local secrets file: {secrets_file} (do not commit; save generated CDN TypeA keys to your backend secret store)")
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
                "file_extensions": ["*"],
                "filter_type": "blacklist",
            },
        },
        "dns": {
            "enabled": True,
            "zone": "example.com",
            "ttl": 600,
            "replace_existing": False,
            "record_line": DEFAULT_DNSPOD_RECORD_LINE,
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
                "origin_type": "cos",
                "private_origin": bucket["kind"] == "private",
                "https_enabled": bool(cdn.get("https_enabled", False)),
            }))
            if bucket["kind"] == "private":
                auth = cdn.get("private_auth", {})
                if auth.get("type", "tencent_type_a") != "tencent_type_a":
                    raise SkillError("Only tencent_type_a private CDN auth is supported.")
                actions.append(action("cdn.enable_cos_private_access", f"Enable COS private origin access for {domain}", {
                    "domain": domain,
                    "origin": origin,
                    "origin_type": "cos",
                    "wait_timeout_seconds": int(cdn.get("deploy_wait_seconds", 300)),
                }))
                actions.append(action("cdn.update_type_a_auth", f"Configure CDN TypeA authentication for {domain}", {
                    "domain": domain,
                    "key_env": auth.get("key_env", "TENCENT_CDN_AUTH_KEY"),
                    "sign_param": auth.get("sign_param", "sign"),
                    "ttl_seconds": int(auth.get("ttl_seconds", 3600)),
                    "file_extensions": auth.get("file_extensions", ["*"]),
                    "filter_type": auth.get("filter_type", "blacklist"),
                    "wait_timeout_seconds": int(cdn.get("deploy_wait_seconds", 300)),
                }))
                actions.append(action("manual.cos_cdn_service_authorization", f"Confirm COS CDN service authorization for {bucket['name']}", {
                    "bucket": bucket["name"],
                    "domain": domain,
                    "console_path": "COS > bucket > Domain and Transmission > Custom CDN acceleration domain",
                    "must_check": True,
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
                "record_line": dns.get("record_line", DEFAULT_DNSPOD_RECORD_LINE),
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
    plan_path: Optional[Path] = None
    state_path: Optional[Path] = None
    secrets_file: Optional[Path] = None
    state: Optional[Json] = None
    cam_user_uin: Optional[int] = None
    cam_policy_id: Optional[int] = None


def preflight_apply(plan: Json) -> None:
    missing: List[str] = []
    kinds = {action.get("kind", "") for action in plan.get("actions", [])}
    if any(kind.startswith("cos.") for kind in kinds) and importlib.util.find_spec("qcloud_cos") is None:
        missing.append("cos-python-sdk-v5")
    if any(kind.startswith(("cam.", "cdn.", "dnspod.")) for kind in kinds) and importlib.util.find_spec("tencentcloud") is None:
        missing.append("tencentcloud-sdk-python")
    if missing:
        packages = " ".join(sorted(set(missing)))
        raise SkillError(
            "missing Python dependencies. Install them first:\n"
            f"python3 -m pip install {packages}\n"
            "If your macOS Python blocks global installs, create a virtual environment and run the same command inside it."
        )


def default_state_path(plan_path: Path) -> Path:
    return plan_path.with_name(f"{plan_path.stem}.state.json")


def default_secrets_path(plan_path: Path) -> Path:
    return plan_path.with_name(f"{plan_path.stem}.secrets.json")


def load_state(path: Path) -> Json:
    if not path.exists():
        return {"version": 1, "actions": {}}
    return load_config(path)


def save_state(ctx: ApplyContext) -> None:
    if not ctx.state_path or ctx.state is None:
        return
    write_json(ctx.state_path, ctx.state)


def is_action_successful(ctx: ApplyContext, action_id: str) -> bool:
    action_state = (ctx.state or {}).get("actions", {}).get(action_id) or {}
    return action_state.get("status") in {"ok", "manual", "skipped"}


def remember_action_result(ctx: ApplyContext, action_obj: Json, result: Json) -> None:
    if ctx.state is None:
        return
    ctx.state.setdefault("actions", {})[action_obj["id"]] = {
        "kind": action_obj["kind"],
        "description": action_obj.get("description"),
        "status": result.get("status"),
        "detail": result.get("detail"),
        "response": redact(result.get("response")),
        "updated_at": int(time.time()),
    }
    save_state(ctx)


def hydrate_context_from_state(ctx: ApplyContext) -> None:
    actions = (ctx.state or {}).get("actions", {})
    for item in actions.values():
        if item.get("status") != "ok":
            continue
        response = item.get("response") or {}
        if item.get("kind") == "cam.add_user" and response.get("Uin"):
            ctx.cam_user_uin = int(response["Uin"])
        if item.get("kind") == "cam.create_policy" and response.get("PolicyId"):
            ctx.cam_policy_id = int(response["PolicyId"])


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
        if kind == "cdn.enable_cos_private_access":
            return apply_cdn_enable_cos_private_access(ctx, params)
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
        raise SkillError("missing cos-python-sdk-v5; install with: python3 -m pip install cos-python-sdk-v5") from exc
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
        raise SkillError("missing tencentcloud-sdk-python; install with: python3 -m pip install tencentcloud-sdk-python") from exc

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
    origin_type = params.get("origin_type", "cos")
    origin = {
        "OriginType": origin_type,
        "Origins": [params["origin"]],
        "ServerName": params["origin"],
    }
    if params.get("private_origin"):
        origin["CosPrivateAccess"] = "on"
    sdk_params = {
        "Domain": params["domain"],
        "ServiceType": params.get("service_type", "web"),
        "Area": params.get("area", "mainland"),
        "Origin": origin,
    }
    try:
        resp = sdk_call(ctx, "cdn", "AddCdnDomain", sdk_params)
        return {"status": "ok", "detail": "domain added", "response": resp}
    except Exception as exc:  # noqa: BLE001
        if "ResourceInUse.CdnHostExists" in str(exc) or "CdnHostExists" in str(exc):
            return {"status": "ok", "detail": "domain already exists"}
        raise


def apply_cdn_enable_cos_private_access(ctx: ApplyContext, params: Json) -> Json:
    wait_cdn_domain_ready(ctx, params["domain"], int(params.get("wait_timeout_seconds", 300)))
    resp = sdk_call(ctx, "cdn", "UpdateDomainConfig", {
        "Domain": params["domain"],
        "Origin": {
            "OriginType": params.get("origin_type", "cos"),
            "Origins": [params["origin"]],
            "ServerName": params["origin"],
            "CosPrivateAccess": "on",
        },
    })
    return {"status": "ok", "detail": "COS private origin access enabled", "response": resp}


def apply_cdn_update_type_a_auth(ctx: ApplyContext, params: Json) -> Json:
    wait_cdn_domain_ready(ctx, params["domain"], int(params.get("wait_timeout_seconds", 300)))
    auth_key, key_detail = get_type_a_key(ctx, params)
    sdk_params = {
        "Domain": params["domain"],
        "Authentication": {
            "Switch": "on",
            "AuthAlgorithm": "md5",
            "TypeA": {
                "SecretKey": auth_key,
                "SignParam": params.get("sign_param", "sign"),
                "ExpireTime": int(params.get("ttl_seconds", 3600)),
                "FileExtensions": params.get("file_extensions") or ["*"],
                "FilterType": params.get("filter_type", "blacklist"),
            },
        },
    }
    resp = sdk_call(ctx, "cdn", "UpdateDomainConfig", sdk_params)
    return {"status": "ok", "detail": f"TypeA auth updated; {key_detail}", "response": redact(resp)}


def wait_cdn_domain_ready(ctx: ApplyContext, domain: str, timeout_seconds: int) -> None:
    deadline = time.time() + max(timeout_seconds, 0)
    last_status = "unknown"
    while True:
        status = get_cdn_domain_status(ctx, domain)
        last_status = status or last_status
        if status in {"online", "active"}:
            return
        if time.time() >= deadline:
            raise SkillError(f"CDN domain {domain} is not ready yet; last status={last_status}. Retry resume after deployment completes.")
        time.sleep(10)


def get_cdn_domain_status(ctx: ApplyContext, domain: str) -> Optional[str]:
    try:
        resp = sdk_call(ctx, "cdn", "DescribeDomainsConfig", {"Domains": [domain]})
    except Exception:
        return None
    configs = (
        resp.get("Domains")
        or resp.get("DomainsConfig")
        or resp.get("DomainConfigs")
        or []
    )
    if not configs:
        return None
    status = configs[0].get("Status") or configs[0].get("StatusCode")
    return str(status).lower() if status else None


def get_type_a_key(ctx: ApplyContext, params: Json) -> Tuple[str, str]:
    key_env = params.get("key_env", "TENCENT_CDN_AUTH_KEY")
    env_key = os.environ.get(key_env)
    if env_key:
        if not TYPE_A_KEY_RE.match(env_key):
            raise SkillError(f"{key_env} must be 6-32 letters/digits for Tencent CDN TypeA.")
        return env_key, f"using key from {key_env}"

    secrets_data = load_local_secrets(ctx.secrets_file)
    domain = params["domain"]
    saved_key = (secrets_data.get("cdn_type_a") or {}).get(domain)
    if saved_key:
        if not TYPE_A_KEY_RE.match(saved_key):
            raise SkillError(f"saved TypeA key for {domain} is invalid; delete it and rerun.")
        return saved_key, f"using generated key from {ctx.secrets_file}"

    generated = "".join(secrets.choice(TYPE_A_KEY_CHARS) for _ in range(32))
    secrets_data.setdefault("cdn_type_a", {})[domain] = generated
    save_local_secrets(ctx.secrets_file, secrets_data)
    return generated, f"generated key saved to {ctx.secrets_file}; save it to your backend secret store"


def load_local_secrets(path: Optional[Path]) -> Json:
    if path is None or not path.exists():
        return {}
    return load_config(path)


def save_local_secrets(path: Optional[Path], data: Json) -> None:
    if path is None:
        return
    write_json(path, data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


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
            "RecordLine": params.get("record_line", DEFAULT_DNSPOD_RECORD_LINE),
            "Value": target,
            "TTL": int(params.get("ttl", 600)),
        })
        return {"status": "ok", "detail": "CNAME modified", "response": resp}

    resp = sdk_call(ctx, "dnspod", "CreateRecord", {
        "Domain": zone,
        "SubDomain": subdomain,
        "RecordType": "CNAME",
        "RecordLine": params.get("record_line", DEFAULT_DNSPOD_RECORD_LINE),
        "Value": target,
        "TTL": int(params.get("ttl", 600)),
    })
    return {"status": "ok", "detail": "CNAME created", "response": resp}


def dnspod_find_records(ctx: ApplyContext, zone: str, subdomain: str) -> List[Json]:
    try:
        resp = sdk_call(ctx, "dnspod", "DescribeRecordList", {
            "Domain": zone,
            "Subdomain": subdomain,
            "Limit": 100,
            "ErrorOnEmpty": "no",
        })
    except Exception as exc:  # noqa: BLE001 - Tencent returns NoDataOfRecord for an empty query in some accounts.
        if "ResourceNotFound.NoDataOfRecord" in str(exc) or "NoDataOfRecord" in str(exc):
            return []
        raise
    return resp.get("RecordList") or []


def verify_plan(plan: Json, timeout: int) -> List[Json]:
    results: List[Json] = []
    domain_protocols = planned_domain_protocols(plan)
    for action_obj in plan.get("actions", []):
        if action_obj["kind"] != "dnspod.ensure_cname":
            continue
        params = action_obj["params"]
        fqdn = params["fqdn"]
        target = params["target"].rstrip(".")
        observed = resolve_dns(fqdn)
        cname_chain = resolve_cname_chain(fqdn)
        all_dns = [item.rstrip(".") for item in observed + cname_chain]
        if target in all_dns:
            results.append({"check": f"dns:{fqdn}", "status": "pass", "detail": f"CNAME chain includes {target}"})
        elif any(is_tencent_cdn_name(item) for item in all_dns):
            results.append({"check": f"dns:{fqdn}", "status": "pass", "detail": f"resolved through Tencent CDN chain: {all_dns}"})
        else:
            results.append({"check": f"dns:{fqdn}", "status": "warn", "detail": f"observed {all_dns or 'no result'}, expected {target}"})
        protocol = domain_protocols.get(fqdn, "http")
        if protocol == "https":
            results.append(check_http(f"https://{fqdn}/", timeout))
        else:
            results.append({"check": f"https:{fqdn}", "status": "skipped", "detail": "HTTPS is not enabled in the plan; checking HTTP only."})
            results.append(check_http(f"http://{fqdn}/", timeout))
    return results


def planned_domain_protocols(plan: Json) -> Dict[str, str]:
    protocols = {}
    for item in plan.get("actions", []):
        if item.get("kind") == "cdn.add_domain":
            params = item.get("params", {})
            protocols[params.get("domain")] = "https" if params.get("https_enabled") else "http"
    return {key: value for key, value in protocols.items() if key}


def resolve_dns(name: str) -> List[str]:
    dig = subprocess.run(["/usr/bin/env", "dig", "+short", name], text=True, capture_output=True)
    if dig.returncode == 0 and dig.stdout.strip():
        return [line.strip() for line in dig.stdout.splitlines() if line.strip()]
    try:
        return sorted({item[4][0] for item in socket.getaddrinfo(name, 443)})
    except socket.gaierror:
        return []


def resolve_cname_chain(name: str, max_depth: int = 8) -> List[str]:
    chain: List[str] = []
    current = name.rstrip(".")
    for _ in range(max_depth):
        dig = subprocess.run(["/usr/bin/env", "dig", "+short", "CNAME", current], text=True, capture_output=True)
        if dig.returncode != 0 or not dig.stdout.strip():
            break
        next_name = dig.stdout.splitlines()[0].strip().rstrip(".")
        if not next_name or next_name in chain:
            break
        chain.append(next_name)
        current = next_name
    return chain


def is_tencent_cdn_name(value: str) -> bool:
    lowered = value.lower().rstrip(".")
    return any(token in lowered for token in ("dnsv1.com", "cdntip.com", "cdn.dnsv1.com"))


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
        render_human_plan_summary(plan),
        "",
        "## Must Do Manually",
        "",
    ]
    manual_items = manual_checklist(plan)
    if manual_items:
        for item in manual_items:
            lines.extend([
                f"- **{item['title']}**",
                f"  - Console: {item['console']}",
                f"  - Search: `{item['search']}`",
                f"  - Check: {item['check']}",
                f"  - Action: {item['action']}",
            ])
    else:
        lines.append("- No required manual steps detected in the plan.")
    lines.extend([
        "",
        "## User Acceptance Checklist",
        "",
        "| Resource | Console | Search | Check fields | Expected status |",
        "| --- | --- | --- | --- | --- |",
    ])
    for item in acceptance_checklist(plan):
        lines.append(f"| {item['resource']} | {item['console']} | `{item['search']}` | {item['check']} | {item['expected']} |")
    lines.extend([
        "",
        "## CAM Policy",
        "",
        "```json",
        json.dumps(plan.get("cam_policy", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Technical Details",
        "",
        "Detailed machine-readable actions are in `plan.json`. Most users only need the manual items and acceptance checklist above.",
        "",
    ])
    return "\n".join(lines)


def render_human_plan_summary(plan: Json) -> str:
    lines = [
        "## Summary",
        "",
        f"- Buckets: {', '.join(bucket['name'] for bucket in plan.get('buckets', [])) or 'none'}",
        f"- Planned actions: {len(plan.get('actions', []))}",
    ]
    for warning in plan.get("warnings", []):
        lines.append(f"- Warning: {warning}")
    return "\n".join(lines)


def manual_checklist(plan: Json) -> List[Json]:
    items: List[Json] = []
    for action_obj in plan.get("actions", []):
        if action_obj.get("kind") == "manual.cos_cdn_service_authorization":
            params = action_obj.get("params", {})
            items.append({
                "title": "Private CDN cannot fully work until COS private origin authorization is confirmed",
                "console": "https://console.cloud.tencent.com/cos/bucket",
                "search": params.get("bucket", ""),
                "check": "Domain and Transmission > Custom CDN acceleration domain; confirm the private CDN domain has COS private access / CDN service authorization enabled.",
                "action": "If Tencent Cloud shows an authorization prompt, click the authorization button. If CosPrivateAccess is off, enable private COS origin access.",
            })
    private_auth = next((a for a in plan.get("actions", []) if a.get("kind") == "cdn.update_type_a_auth"), None)
    if private_auth:
        params = private_auth.get("params", {})
        items.append({
            "title": "Save the private CDN TypeA key to the backend secret system",
            "console": "Local generated secrets file or environment variable",
            "search": params.get("domain", ""),
            "check": "The key must be 6-32 letters/digits and must match the backend config that generates signed URLs.",
            "action": "Do not commit the key. Store it in your deployment secret manager.",
        })
    if any(a.get("kind", "").startswith("cdn.") for a in plan.get("actions", [])):
        items.append({
            "title": "HTTPS certificate is not configured by this skill",
            "console": "https://console.cloud.tencent.com/cdn/domains",
            "search": "public/private CDN domains",
            "check": "HTTPS Configuration tab; HTTPS switch and certificate status.",
            "action": "Upload or select certificates if HTTPS access is required.",
        })
    items.append({
        "title": "Clean up temporary installer permissions after acceptance",
        "console": "https://console.cloud.tencent.com/cam",
        "search": "cos-skill-installer-test or the installer CAM user",
        "check": "AdministratorAccess / temporary access key.",
        "action": "Remove AdministratorAccess, disable the access key, or delete the temporary user after testing.",
    })
    return items


def acceptance_checklist(plan: Json) -> List[Json]:
    items: List[Json] = []
    for bucket in plan.get("buckets", []):
        items.append({
            "resource": f"COS bucket {bucket['name']}",
            "console": "https://console.cloud.tencent.com/cos/bucket",
            "search": bucket["name"],
            "check": "Bucket exists; ACL; CORS rules",
            "expected": "Created and configured",
        })
    cam_policy = plan.get("config", {}).get("cam", {}).get("policy_name", "")
    if cam_policy:
        items.append({
            "resource": "CAM app policy",
            "console": "https://console.cloud.tencent.com/cam/policy",
            "search": cam_policy,
            "check": "Policy exists; resource ARNs only include planned buckets",
            "expected": "Created and attached",
        })
    for action_obj in plan.get("actions", []):
        kind = action_obj.get("kind")
        params = action_obj.get("params", {})
        if kind == "cdn.add_domain":
            items.append({
                "resource": f"CDN domain {params.get('domain')}",
                "console": "https://console.cloud.tencent.com/cdn/domains",
                "search": params.get("domain", ""),
                "check": "Status; origin domain; HTTPS switch",
                "expected": "Domain deployed; HTTPS may be off until manually configured",
            })
        if kind == "dnspod.ensure_cname":
            items.append({
                "resource": f"DNSPod CNAME {params.get('fqdn')}",
                "console": "https://console.cloud.tencent.com/cns",
                "search": params.get("fqdn", ""),
                "check": "Record type CNAME; value points to Tencent CDN CNAME",
                "expected": "Created and resolving",
            })
    return items


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
