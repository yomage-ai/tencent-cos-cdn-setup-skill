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
import urllib.parse
import urllib.request
import fnmatch
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
AUTO_VENV_ENV = "TENCENT_COS_CDN_SKILL_AUTO_VENV"
APPLY_DEPENDENCIES = {
    "qcloud_cos": "cos-python-sdk-v5",
    "tencentcloud": "tencentcloud-sdk-python",
}
CONSOLE_LINKS = {
    "cos_buckets": "https://console.cloud.tencent.com/cos/bucket",
    "cdn_domains": "https://console.cloud.tencent.com/cdn/domains",
    "dnspod": "https://console.cloud.tencent.com/cns",
    "cam_users": "https://console.cloud.tencent.com/cam/user",
    "cam_policies": "https://console.cloud.tencent.com/cam/policy",
    "ssl": "https://console.cloud.tencent.com/ssl",
}


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

    run_dir = sub.add_parser("run-dir", help="create/print an isolated run directory under the skill cache")
    run_dir.add_argument("--project", default="cos-cdn-setup")
    run_dir.add_argument("--env", default="run")
    run_dir.add_argument("--create", action="store_true", help="create the directory before printing it")

    plan = sub.add_parser("plan", help="generate a plan from config")
    plan.add_argument("config")
    plan.add_argument("--out")
    plan.add_argument("--report", help="combined local report path; defaults to <plan>.report.md")

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
    verify.add_argument("--report", help="combined local report path; defaults to <plan>.report.md")
    verify.add_argument("--timeout", type=int, default=10)

    args = parser.parse_args(argv)

    try:
        if args.command == "init-config":
            return cmd_init_config(args)
        if args.command == "run-dir":
            return cmd_run_dir(args)
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


def cmd_run_dir(args: argparse.Namespace) -> int:
    path = default_run_dir(args.project, args.env)
    if args.create:
        path.mkdir(parents=True, exist_ok=True)
    print(path)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))
    plan = build_plan(config)
    out_path = Path(args.out) if args.out else default_run_dir(
        str(plan.get("config", {}).get("project") or "cos-cdn-setup"),
        str(plan.get("config", {}).get("env") or "run"),
    ) / "plan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, plan)
    print(f"wrote {out_path}")
    report_path = Path(args.report) if args.report else default_report_path(out_path)
    report_path.write_text(render_combined_report(plan, None, None), encoding="utf-8")
    print(f"Report: {report_path}")
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

    ensure_apply_runtime(plan)
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
            report_path = write_combined_report(plan_path, plan, state, secrets_file)
            print(f"Stopped after first failure. Fix the issue and run: python3 {Path(__file__).name} resume {plan_path} --apply")
            print(f"State file: {state_path}")
            print(f"Report: {report_path}")
            return 1

    print(json.dumps({"results": redact(results)}, indent=2, ensure_ascii=False))
    print(f"State file: {state_path}")
    if secrets_file.exists():
        print(f"Local secrets file: {secrets_file} (do not commit; save generated CDN TypeA keys to your backend secret store)")
    report_path = write_combined_report(plan_path, plan, state, secrets_file)
    print(f"Report: {report_path}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    plan = load_config(plan_path)
    results = verify_plan(plan, timeout=args.timeout)
    state_path = default_state_path(plan_path)
    state = load_state(state_path) if state_path.exists() else None
    secrets_file = default_secrets_path(plan_path)
    report_path = Path(args.report) if args.report else default_report_path(plan_path)
    output = render_combined_report(plan, state, secrets_file if secrets_file.exists() else None, results)
    report_path.write_text(output, encoding="utf-8")
    print(f"Report: {report_path}")
    if not args.report:
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


def ensure_apply_runtime(plan: Json) -> None:
    packages = missing_apply_packages(plan)
    if not packages:
        return
    if os.environ.get(AUTO_VENV_ENV) == "1":
        raise SkillError(
            "isolated Python runtime was prepared, but required Tencent Cloud SDK packages are still missing. "
            "Check network access to PyPI and retry."
        )

    venv_dir = skill_cache_dir() / "python-venv"
    python = venv_python(venv_dir)
    print("Preparing isolated Tencent Cloud SDK runtime. This is a one-time setup and does not modify your project Python.", flush=True)
    try:
        if not python.exists():
            subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
        subprocess.check_call([
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            *packages,
        ])
    except subprocess.CalledProcessError as exc:
        raise SkillError(
            "failed to prepare isolated Tencent Cloud SDK runtime. "
            "Check network access to PyPI and retry."
        ) from exc

    env = os.environ.copy()
    env[AUTO_VENV_ENV] = "1"
    os.execve(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]], env)


def missing_apply_packages(plan: Json) -> List[str]:
    missing: List[str] = []
    kinds = {action.get("kind", "") for action in plan.get("actions", [])}
    if any(kind.startswith("cos.") for kind in kinds) and importlib.util.find_spec("qcloud_cos") is None:
        missing.append(APPLY_DEPENDENCIES["qcloud_cos"])
    if any(kind.startswith(("cam.", "cdn.", "dnspod.")) for kind in kinds) and importlib.util.find_spec("tencentcloud") is None:
        missing.append(APPLY_DEPENDENCIES["tencentcloud"])
    return sorted(set(missing))


def skill_cache_dir() -> Path:
    custom = os.environ.get("TENCENT_COS_CDN_SKILL_CACHE")
    if custom:
        return Path(custom).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "tencent-cos-cdn-setup-skill"


def default_run_dir(project: str, env: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return skill_cache_dir() / "runs" / f"{safe_slug(project)}-{safe_slug(env)}-{stamp}"


def safe_slug(value: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower())
    compact = compact.strip("-._")
    return compact[:64] or "run"


def venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def default_state_path(plan_path: Path) -> Path:
    return plan_path.with_name(f"{plan_path.stem}.state.json")


def default_secrets_path(plan_path: Path) -> Path:
    return plan_path.with_name(f"{plan_path.stem}.secrets.json")


def default_report_path(plan_path: Path) -> Path:
    return plan_path.with_name(f"{plan_path.stem}.report.md")


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
        if item.get("kind") == "cam.create_policy" and response.get("reused_policy_id"):
            ctx.cam_policy_id = int(response["reused_policy_id"])


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
        raise SkillError("COS SDK is unavailable after isolated runtime setup. Retry apply; if it repeats, check network access to PyPI.") from exc
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
        raise SkillError("Tencent Cloud SDK is unavailable after isolated runtime setup. Retry apply; if it repeats, check network access to PyPI.") from exc

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
    try:
        resp = sdk_call(ctx, "cam", "AddUser", sdk_params)
        ctx.cam_user_uin = int(resp.get("Uin"))
        detail = f"created uin={ctx.cam_user_uin}"
        if resp.get("SecretId"):
            detail += " with access key (secret redacted)"
        return {"status": "ok", "detail": detail, "response": redact(resp)}
    except Exception as exc:  # noqa: BLE001
        if "SubUserNameInUse" not in str(exc):
            raise
        user = find_cam_user_by_name(ctx, params["name"])
        if not user:
            raise SkillError(f"CAM user {params['name']} already exists, but ListUsers/GetUser could not locate it.")
        ctx.cam_user_uin = int(user["Uin"])
        warnings = []
        if int(user.get("ConsoleLogin") or 0) != int(params.get("console_login", 0)):
            warnings.append("console login setting differs; reused without changing it")
        detail = f"reused existing uin={ctx.cam_user_uin}"
        if warnings:
            detail += f" ({'; '.join(warnings)})"
        return {"status": "ok", "detail": detail, "response": {"reused_user": redact(user)}}


def apply_cam_create_policy(ctx: ApplyContext, params: Json) -> Json:
    sdk_params = {
        "PolicyName": params["policy_name"],
        "Description": params.get("description", ""),
        "PolicyDocument": json.dumps(params["policy_document"], separators=(",", ":")),
    }
    try:
        resp = sdk_call(ctx, "cam", "CreatePolicy", sdk_params)
        ctx.cam_policy_id = int(resp.get("PolicyId"))
        return {"status": "ok", "detail": f"policy_id={ctx.cam_policy_id}", "response": resp}
    except Exception as exc:  # noqa: BLE001
        if "PolicyNameInUse" not in str(exc):
            raise
        policy = find_cam_policy_by_name(ctx, params["policy_name"])
        if not policy:
            raise SkillError(f"CAM policy {params['policy_name']} already exists, but ListPolicies could not locate it.")
        policy_id = int(policy["PolicyId"])
        existing = get_cam_policy_document(ctx, policy_id)
        required = params["policy_document"]
        coverage = policy_coverage(existing, required)
        if coverage == "incompatible":
            raise SkillError(
                f"CAM policy {params['policy_name']} already exists, but its document is not equivalent to the planned least-privilege COS bucket permissions. "
                "This skill did not update the existing policy. Use a new cam.policy_name, provide a compatible existing policy, or manually review/update it in CAM."
            )
        ctx.cam_policy_id = policy_id
        detail = f"reused existing policy_id={ctx.cam_policy_id}; policy document is {coverage}"
        return {"status": "ok", "detail": detail, "response": {"reused_policy_id": policy_id, "coverage": coverage}}


def apply_cam_attach_user_policy(ctx: ApplyContext, params: Json) -> Json:
    user_uin = params.get("user_uin") or ctx.cam_user_uin
    policy_id = ctx.cam_policy_id
    if not user_uin:
        raise SkillError("CAM user UIN is missing. Create a user in this run or set cam.user_uin.")
    if not policy_id:
        raise SkillError("CAM policy ID is missing. Create the policy in this run.")
    if is_policy_attached_to_user(ctx, int(user_uin), int(policy_id)):
        return {"status": "ok", "detail": "already attached", "response": {"AttachUin": int(user_uin), "PolicyId": int(policy_id)}}
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
            existing = get_cdn_domain_config(ctx, params["domain"])
            if not existing:
                raise SkillError(f"CDN domain {params['domain']} already exists, but DescribeDomainsConfig could not read its config.")
            if not cdn_domain_matches_plan(existing, params):
                raise SkillError(
                    f"CDN domain {params['domain']} already exists with a different origin/service configuration. "
                    "This skill did not overwrite it. Use a new CDN domain or manually review the existing domain before reusing it."
                )
            return {"status": "ok", "detail": "reused existing domain; origin/service config matches plan", "response": redact(existing)}
        raise


def find_cam_user_by_name(ctx: ApplyContext, name: str) -> Optional[Json]:
    try:
        user = sdk_call(ctx, "cam", "GetUser", {"Name": name})
        if user.get("Uin"):
            return user
    except Exception:
        pass
    resp = sdk_call(ctx, "cam", "ListUsers", {})
    for user in resp.get("Data") or []:
        if user.get("Name") == name:
            return user
    return None


def find_cam_policy_by_name(ctx: ApplyContext, name: str) -> Optional[Json]:
    page = 1
    while page <= 200:
        resp = sdk_call(ctx, "cam", "ListPolicies", {"Scope": "Local", "Keyword": name, "Page": page, "Rp": 200})
        items = resp.get("List") or []
        for item in items:
            if item.get("PolicyName") == name:
                return item
        total = int(resp.get("TotalNum") or 0)
        if page * 200 >= total or not items:
            break
        page += 1
    return None


def get_cam_policy_document(ctx: ApplyContext, policy_id: int) -> Json:
    resp = sdk_call(ctx, "cam", "GetPolicy", {"PolicyId": int(policy_id)})
    doc = resp.get("PolicyDocument") or {}
    if isinstance(doc, dict):
        return doc
    if not isinstance(doc, str):
        raise SkillError(f"CAM policy {policy_id} returned an unsupported PolicyDocument format.")
    candidates = [doc, urllib.parse.unquote(doc)]
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise SkillError(f"CAM policy {policy_id} returned a PolicyDocument that could not be parsed as JSON.")


def policy_coverage(existing: Json, required: Json) -> str:
    if canonical_policy(existing) == canonical_policy(required):
        return "exact match"
    if policy_has_conflicting_deny(existing, required):
        return "incompatible"
    if policy_allows_required(existing, required) and policy_allows_required(required, existing):
        return "equivalent permissions"
    return "incompatible"


def canonical_policy(policy: Json) -> Json:
    statements = []
    for stmt in policy_statements(policy):
        statements.append({
            "effect": str(stmt.get("effect", stmt.get("Effect", ""))).lower(),
            "action": sorted(normalize_policy_values(stmt.get("action", stmt.get("Action", [])), lower=True)),
            "resource": sorted(normalize_policy_values(stmt.get("resource", stmt.get("Resource", [])), lower=False)),
        })
    return {"version": str(policy.get("version", policy.get("Version", ""))), "statement": sorted(statements, key=json.dumps)}


def policy_has_conflicting_deny(existing: Json, required: Json) -> bool:
    denied = [stmt for stmt in policy_statements(existing) if policy_effect(stmt) == "deny"]
    if not denied:
        return False
    for req in required_pairs(required):
        for stmt in denied:
            if statement_matches_pair(stmt, req["action"], req["resource"]):
                return True
    return False


def policy_allows_required(existing: Json, required: Json) -> bool:
    allow_statements = [stmt for stmt in policy_statements(existing) if policy_effect(stmt) == "allow"]
    if not allow_statements:
        return False
    for req in required_pairs(required):
        if not any(statement_matches_pair(stmt, req["action"], req["resource"]) for stmt in allow_statements):
            return False
    return True


def required_pairs(policy: Json) -> List[Json]:
    pairs: List[Json] = []
    for stmt in policy_statements(policy):
        if policy_effect(stmt) != "allow":
            continue
        for action_name in normalize_policy_values(stmt.get("action", stmt.get("Action", [])), lower=True):
            for resource in normalize_policy_values(stmt.get("resource", stmt.get("Resource", [])), lower=False):
                pairs.append({"action": action_name, "resource": resource})
    return pairs


def statement_matches_pair(stmt: Json, action_name: str, resource: str) -> bool:
    actions = normalize_policy_values(stmt.get("action", stmt.get("Action", [])), lower=True)
    resources = normalize_policy_values(stmt.get("resource", stmt.get("Resource", [])), lower=False)
    return any(policy_pattern_match(pattern, action_name, lower=True) for pattern in actions) and any(
        policy_pattern_match(pattern, resource, lower=False) for pattern in resources
    )


def policy_statements(policy: Json) -> List[Json]:
    statement = policy.get("statement", policy.get("Statement", []))
    if isinstance(statement, dict):
        return [statement]
    if isinstance(statement, list):
        return [item for item in statement if isinstance(item, dict)]
    return []


def policy_effect(stmt: Json) -> str:
    return str(stmt.get("effect", stmt.get("Effect", ""))).lower()


def normalize_policy_values(value: Any, lower: bool) -> List[str]:
    if value is None:
        raw: List[Any] = []
    elif isinstance(value, list):
        raw = value
    else:
        raw = [value]
    values = [str(item).strip() for item in raw if str(item).strip()]
    if lower:
        values = [item.lower() for item in values]
    return values


def policy_pattern_match(pattern: str, value: str, lower: bool) -> bool:
    if lower:
        pattern = pattern.lower()
        value = value.lower()
    return pattern == "*" or fnmatch.fnmatchcase(value, pattern)


def is_policy_attached_to_user(ctx: ApplyContext, user_uin: int, policy_id: int) -> bool:
    page = 1
    while page <= 200:
        resp = sdk_call(ctx, "cam", "ListAttachedUserPolicies", {"TargetUin": int(user_uin), "Page": page, "Rp": 200})
        items = resp.get("List") or resp.get("PolicyList") or []
        for item in items:
            if int(item.get("PolicyId") or item.get("PolicyId".lower()) or 0) == int(policy_id):
                return True
        total = int(resp.get("TotalNum") or 0)
        if page * 200 >= total or not items:
            break
        page += 1
    return False


def get_cdn_domain_config(ctx: ApplyContext, domain: str) -> Optional[Json]:
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
    return next((item for item in configs if item.get("Domain") == domain), configs[0])


def cdn_domain_matches_plan(existing: Json, params: Json) -> bool:
    origin = existing.get("Origin") or {}
    origins = [str(item).rstrip(".") for item in (origin.get("Origins") or [])]
    planned_origin = str(params.get("origin", "")).rstrip(".")
    if planned_origin and planned_origin not in origins:
        return False
    existing_origin_type = str(origin.get("OriginType") or "").lower()
    planned_origin_type = str(params.get("origin_type") or "cos").lower()
    if existing_origin_type and existing_origin_type != planned_origin_type:
        return False
    for key, param_key in [("ServiceType", "service_type"), ("Area", "area")]:
        existing_value = existing.get(key)
        planned_value = params.get(param_key)
        if existing_value and planned_value and str(existing_value).lower() != str(planned_value).lower():
            return False
    return True


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
    matched = next((item for item in configs if item.get("Domain") == domain), configs[0])
    status = matched.get("Status") or matched.get("StatusCode")
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


def render_operator_guide_section(plan: Json) -> str:
    lines = [
        "## 手动操作指南 / Manual Operator Guide",
        "",
        "如果不想让 AI 直接执行云资源变更，可以按本节逐项在腾讯云控制台操作。每一步都带有入口、点击路径、搜索关键词、检查字段和要填写/确认的值。",
        "",
        "| 步骤 | 是否必做 | 控制台入口 | 点击路径 | 搜索关键词 | 应检查字段 | 要做什么 / 填写值 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in operator_guide_items(plan):
        lines.append(
            f"| {md_cell(item['step'])} | {md_cell(item['required'])} | {md_cell(item['console'])} | "
            f"{md_cell(item['path'])} | `{md_cell(item['search'])}` | {md_cell(item['check'])} | {md_cell(item['action'])} |"
        )
    return "\n".join(lines)


def write_combined_report(
    plan_path: Path,
    plan: Json,
    state: Optional[Json],
    secrets_file: Optional[Path],
    verify_results: Optional[List[Json]] = None,
) -> Path:
    report_path = default_report_path(plan_path)
    report_path.write_text(render_combined_report(plan, state, secrets_file, verify_results), encoding="utf-8")
    return report_path


def render_combined_report(
    plan: Json,
    state: Optional[Json],
    secrets_file: Optional[Path],
    verify_results: Optional[List[Json]] = None,
) -> str:
    secrets_text = str(secrets_file) if secrets_file else "generated plan.secrets.json after apply"
    return "\n".join([
        "# Tencent COS/CDN Setup Report",
        "",
        render_human_plan_summary(plan),
        "",
        render_operator_guide_section(plan),
        "",
        render_apply_status_section(plan, state),
        "",
        render_verification_section(plan, verify_results),
        "",
        render_integration_values(plan, secrets_file),
        "",
        render_manual_section(plan, state, secrets_file),
        "",
        render_acceptance_section(plan, state, verify_results),
        "",
        "## CAM Policy",
        "",
        "```json",
        json.dumps(plan.get("cam_policy", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Technical Details",
        "",
        "Detailed machine-readable actions are in the generated plan file. Most users only need the integration values, manual items, and acceptance checklist above.",
        "",
        "## 本地文件 / Local Files",
        "",
        "- Combined report file: `<plan>.report.md` in the run directory, or the path passed with `--report`.",
        f"- TypeA secrets file: `{secrets_text}` if private CDN TypeA generated a key. Do not commit it.",
        "",
    ])


def render_apply_status_section(plan: Json, state: Optional[Json]) -> str:
    lines = [
        "## Apply Results",
        "",
    ]
    if state is None:
        lines.append("- NOT RUN: apply has not run yet.")
        return "\n".join(lines)
    for action_obj in plan.get("actions", []):
        state_item = action_state(state, action_obj)
        if not state_item:
            lines.append(f"- NOT-RUN {action_obj.get('kind', '')}: {action_obj.get('description', '')}")
            continue
        status = str(state_item.get("status", "unknown")).upper()
        detail = state_item.get("detail", "")
        suffix = f": {detail}" if detail else ""
        lines.append(f"- {status} {action_obj.get('kind', '')}: {action_obj.get('description', '')}{suffix}")
    return "\n".join(lines)


def render_verification_section(plan: Json, results: Optional[List[Json]]) -> str:
    lines = [
        "## Verification Results",
        "",
    ]
    if results is None:
        lines.append("- NOT RUN: verification has not run yet.")
        return "\n".join(lines)
    lines.append(f"Generated for {len(plan.get('actions', []))} planned actions.")
    lines.append("")
    for result in results:
        lines.append(f"- {result['status'].upper()} {result['check']}: {result['detail']}")
    return "\n".join(lines)


def render_manual_section(plan: Json, state: Optional[Json], secrets_file: Optional[Path]) -> str:
    lines = [
        "## 必须手动完成 / Must Do Manually",
        "",
        "| 事项 | 是否必做 | 入口链接 | 点击路径/要做什么 | 搜索关键词 | 应检查字段 | 当前状态 | 是否完成 | 未完成原因 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    items = manual_checklist(plan, state, secrets_file)
    if not items:
        lines.append("| 无 | - | - | - | - | - | - | 是 | - |")
    for item in items:
        lines.append(
            f"| {md_cell(item['title'])} | {md_cell(item['required'])} | {md_cell(item['console'])} | {md_cell(item['action'])} | `{md_cell(item['search'])}` | "
            f"{md_cell(item['check'])} | {md_cell(item['current'])} | {md_cell(item['done'])} | {md_cell(item['reason'])} |"
        )
    return "\n".join(lines)


def render_integration_values(plan: Json, secrets_file: Optional[Path]) -> str:
    cfg = plan.get("config", {})
    cdn = cfg.get("cdn", {})
    cors = cfg.get("cors", {})
    lines = [
        "## 项目需要使用的配置数据 / Project Integration Values",
        "",
        "把下面这些值填到项目自己的配置系统里。不要把 SecretKey、TypeA key 明文提交到代码仓库。",
        "",
        "| 配置项 | 值 | 说明 |",
        "| --- | --- | --- |",
        f"| Tencent region | `{cfg.get('region', '')}` | COS bucket 所在地域。 |",
        f"| Tencent APPID | `{cfg.get('appid', '')}` | bucket 名和 COS 资源 ARN 会用到。 |",
    ]
    for bucket in plan.get("buckets", []):
        lines.append(f"| COS {bucket['kind']} bucket | `{bucket['name']}` | {bucket['kind']} 文件使用的 bucket。 |")
        lines.append(f"| COS {bucket['kind']} origin | `{bucket.get('origin') or cos_origin(bucket['name'], cfg.get('region', ''))}` | CDN 回源域名，一般只给后端/运维使用。 |")
    if cdn.get("enabled"):
        if cdn.get("public_domain"):
            lines.append(f"| Public CDN domain | `{cdn.get('public_domain')}` | 公开文件访问域名。 |")
        if cdn.get("private_domain"):
            lines.append(f"| Private CDN domain | `{cdn.get('private_domain')}` | 私有文件签名访问域名。 |")
        private_auth = cdn.get("private_auth") or {}
        if private_auth:
            key_ref = str(secrets_file) if secrets_file else "generated plan.secrets.json after apply"
            lines.append(f"| Private CDN TypeA key | `{private_auth.get('key_env', 'TENCENT_CDN_AUTH_KEY')}` / `{key_ref}` | 必须保存到后端密钥系统，用于生成签名 URL；不要写进前端。 |")
            lines.append(f"| Private CDN sign param | `{private_auth.get('sign_param', 'sign')}` | 后端生成签名 URL 时使用的参数名。 |")
            lines.append(f"| Private CDN URL TTL | `{private_auth.get('ttl_seconds', 3600)}` | 签名 URL 有效期，单位秒。 |")
    dns = cfg.get("dns", {})
    if dns.get("enabled"):
        lines.append(f"| DNS zone | `{dns.get('zone', '')}` | DNSPod 托管的主域名。 |")
    origins = cors.get("origins") or []
    if origins:
        lines.append(f"| Browser CORS origins | `{', '.join(origins)}` | 允许浏览器直传/访问 COS 的前端来源。 |")
    cam = cfg.get("cam", {})
    if cam.get("user_name"):
        lines.append(f"| App CAM user | `{cam.get('user_name')}` | 项目运行期可使用的最小权限子用户；若未创建 access key，需要在控制台按需创建。 |")
    lines.append("")
    return "\n".join(lines)


def render_acceptance_section(plan: Json, state: Optional[Json], verify_results: Optional[List[Json]] = None) -> str:
    lines = [
        "## 用户验收清单 / User Acceptance Checklist",
        "",
        "| 资源 | 是否必做 | 控制台入口 | 点击路径/要做什么 | 搜索关键词 | 应检查字段 | 当前 API/验证状态 | 是否完成 | 未完成原因 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in acceptance_checklist(plan, state, verify_results):
        lines.append(
            f"| {md_cell(item['resource'])} | {md_cell(item['required'])} | {md_cell(item['console'])} | {md_cell(item['action'])} | `{md_cell(item['search'])}` | "
            f"{md_cell(item['check'])} | {md_cell(item['current'])} | {md_cell(item['done'])} | {md_cell(item['reason'])} |"
        )
    return "\n".join(lines)


def operator_guide_items(plan: Json) -> List[Json]:
    cfg = plan.get("config", {})
    cors = cfg.get("cors", {})
    cors_methods = [m for m in (cors.get("methods") or ["GET", "PUT", "HEAD", "OPTIONS"]) if m != "OPTIONS"]
    items: List[Json] = []
    for bucket in plan.get("buckets", []):
        items.append({
            "step": f"创建/确认 COS bucket {bucket['name']}",
            "required": "必做",
            "console": md_link("COS Bucket", CONSOLE_LINKS["cos_buckets"]),
            "path": "COS Bucket -> Create Bucket；如果已存在则搜索 bucket 并进入详情",
            "search": bucket["name"],
            "check": "Bucket name, Region, ACL, CORS rules",
            "action": (
                f"Region 选择 `{cfg.get('region', '')}`；Bucket 名为 `{bucket['name']}`；ACL 设置为 `{bucket['cos_acl']}`；"
                f"CORS AllowedOrigin=`{', '.join(cors.get('origins') or [])}`，AllowedMethod=`{', '.join(cors_methods)}`，"
                f"AllowedHeader=`{', '.join(cors.get('allowed_headers') or ['*'])}`，ExposeHeader=`{', '.join(cors.get('expose_headers') or ['ETag', 'Content-Length', 'Content-Type'])}`。"
            ),
        })

    cam = cfg.get("cam", {})
    if cam.get("enabled", True):
        if cam.get("create_user", True) and cam.get("user_name"):
            items.append({
                "step": f"创建/确认 CAM 子用户 {cam['user_name']}",
                "required": "必做",
                "console": md_link("CAM Users", CONSOLE_LINKS["cam_users"]),
                "path": "Users -> User List -> Create User；如果已存在则搜索用户名并进入详情",
                "search": cam["user_name"],
                "check": "User exists; console login disabled; API access only if project needs access keys",
                "action": (
                    f"用户名填 `{cam['user_name']}`；控制台登录保持关闭；"
                    f"访问密钥/API access 按计划设置为 `{'开启' if cam.get('create_access_key') else '不开启'}`。如果同名用户已存在，只在确认这是本项目/本环境用户后复用。"
                ),
            })
        if cam.get("policy_name"):
            items.append({
                "step": f"创建/确认 CAM 策略 {cam['policy_name']}",
                "required": "必做",
                "console": md_link("CAM Policies", CONSOLE_LINKS["cam_policies"]),
                "path": "Policies -> Create Custom Policy -> Create by Policy Syntax；如果已存在则搜索策略并查看策略语法",
                "search": cam["policy_name"],
                "check": "Policy syntax; effect=allow; action/resource only cover planned COS buckets",
                "action": (
                    f"策略名填 `{cam['policy_name']}`；策略语法使用本报告 `CAM Policy` 一节。"
                    "同名策略只有在语法完全一致或权限等价时才复用；更宽或不匹配的策略不会自动绑定，需换一个策略名或人工审核后再更新。"
                ),
            })
            items.append({
                "step": "绑定 CAM 策略到应用子用户",
                "required": "必做",
                "console": md_link("CAM Users", CONSOLE_LINKS["cam_users"]),
                "path": "Users -> User List -> 搜索子用户 -> Permissions -> Attach Policy",
                "search": cam.get("user_name") or cam.get("user_uin") or "target CAM user",
                "check": "Attached policies include the planned custom policy",
                "action": f"把策略 `{cam['policy_name']}` 绑定到目标子用户；如果已经绑定，保持不变。",
            })

    for action_obj in plan.get("actions", []):
        kind = action_obj.get("kind")
        params = action_obj.get("params", {})
        if kind == "cdn.add_domain":
            items.append({
                "step": f"创建/确认 CDN 域名 {params.get('domain', '')}",
                "required": "CDN enabled 时必做",
                "console": md_link("CDN Domains", CONSOLE_LINKS["cdn_domains"]),
                "path": "CDN Domains -> Add Domain；如果已存在则搜索域名并进入 Manage",
                "search": params.get("domain", ""),
                "check": "Domain, ServiceType, Area, OriginType, Origin domain, Status",
                "action": (
                    f"域名填 `{params.get('domain', '')}`；ServiceType=`{params.get('service_type', 'web')}`；Area=`{params.get('area', 'mainland')}`；"
                    f"源站类型 `{params.get('origin_type', 'cos')}`；源站域名 `{params.get('origin', '')}`。"
                    "同名 CDN 域名只有在源站和服务配置匹配时才复用。"
                ),
            })
        if kind == "cdn.enable_cos_private_access":
            items.append({
                "step": f"开启私有 CDN 回源授权 {params.get('domain', '')}",
                "required": "私有 CDN 必做",
                "console": md_link("CDN Domains", CONSOLE_LINKS["cdn_domains"]),
                "path": "CDN Domains -> 搜索域名 -> Manage -> Origin Configuration",
                "search": params.get("domain", ""),
                "check": "COS private origin access / CosPrivateAccess",
                "action": f"确认域名 `{params.get('domain', '')}` 的 COS 私有回源访问已开启；源站为 `{params.get('origin', '')}`。",
            })
        if kind == "cdn.update_type_a_auth":
            items.append({
                "step": f"配置私有 CDN TypeA 鉴权 {params.get('domain', '')}",
                "required": "私有 CDN 必做",
                "console": md_link("CDN Domains", CONSOLE_LINKS["cdn_domains"]),
                "path": "CDN Domains -> 搜索域名 -> Manage -> Access Control / URL Authentication",
                "search": params.get("domain", ""),
                "check": "Authentication switch, TypeA, SecretKey, SignParam, ExpireTime",
                "action": (
                    f"开启 URL Authentication；类型选 TypeA；签名参数 `{params.get('sign_param', 'sign')}`；有效期 `{params.get('ttl_seconds', 3600)}` 秒；"
                    f"鉴权 key 使用环境变量 `{params.get('key_env', 'TENCENT_CDN_AUTH_KEY')}` 对应值，或使用 apply 后生成的本地 secrets 文件中的值。"
                ),
            })
        if kind == "manual.cos_cdn_service_authorization":
            items.append({
                "step": "确认 COS 控制台里的 CDN 服务授权",
                "required": "私有 CDN 必做",
                "console": md_link("COS Bucket", CONSOLE_LINKS["cos_buckets"]),
                "path": "COS Bucket -> 搜索 bucket -> Domain and Transmission -> Custom CDN acceleration domain",
                "search": params.get("bucket", ""),
                "check": "Private origin authorization / CDN service authorization",
                "action": f"找到私有 CDN 域名 `{params.get('domain', '')}`，如果控制台出现授权提示，点击授权并确认状态正常。",
            })
        if kind == "dnspod.ensure_cname":
            items.append({
                "step": f"创建/确认 DNSPod CNAME {params.get('fqdn', '')}",
                "required": "DNSPod enabled 时必做",
                "console": md_link("DNSPod", CONSOLE_LINKS["dnspod"]),
                "path": "DNSPod -> 点击 DNS zone -> Add Record；如果已存在则搜索子域名",
                "search": params.get("fqdn", ""),
                "check": "Record type, Line, Value, TTL, Status",
                "action": (
                    f"主机记录 `{params.get('subdomain', '')}`；记录类型 `CNAME`；线路 `{params.get('record_line', DEFAULT_DNSPOD_RECORD_LINE)}`；"
                    f"记录值 `{params.get('target', '')}`；TTL `{params.get('ttl', 600)}`。已有不同记录时先人工确认，不要直接覆盖。"
                ),
            })

    if any(a.get("kind", "").startswith("cdn.") for a in plan.get("actions", [])):
        cdn_domains = [a.get("params", {}).get("domain", "") for a in plan.get("actions", []) if a.get("kind") == "cdn.add_domain"]
        items.append({
            "step": "按需配置 HTTPS 证书",
            "required": "需要 HTTPS URL 时必做",
            "console": md_link("CDN Domains", CONSOLE_LINKS["cdn_domains"]),
            "path": "CDN Domains -> 搜索域名 -> Manage -> HTTPS Configuration",
            "search": ", ".join(filter(None, cdn_domains)) or "CDN domain",
            "check": "HTTPS switch, certificate, certificate validity",
            "action": "如果项目要使用 HTTPS URL，上传/选择证书并开启 HTTPS；如果只是临时 HTTP 烟测，可暂不做。",
        })

    items.append({
        "step": "验收后清理临时 installer 权限",
        "required": "必做",
        "console": md_link("CAM Users", CONSOLE_LINKS["cam_users"]),
        "path": "Users -> User List -> 搜索 installer 用户 -> Permissions / Access Keys",
        "search": "cos-skill-installer-test or the installer CAM user",
        "check": "AdministratorAccess, temporary access keys",
        "action": "验收完成后，解除临时 AdministratorAccess，禁用/删除临时访问密钥，或删除临时 installer 用户。",
    })
    return items


def manual_checklist(plan: Json, state: Optional[Json] = None, secrets_file: Optional[Path] = None) -> List[Json]:
    items: List[Json] = []
    for action_obj in plan.get("actions", []):
        if action_obj.get("kind") == "manual.cos_cdn_service_authorization":
            params = action_obj.get("params", {})
            current, done, reason = manual_status(action_obj, state)
            items.append({
                "title": "私有 CDN 必须确认 COS 私有回源授权",
                "required": "必做",
                "console": md_link("COS Bucket", CONSOLE_LINKS["cos_buckets"]),
                "search": params.get("bucket", ""),
                "check": "Domain and Transmission > Custom CDN acceleration domain; confirm COS private access / CDN service authorization.",
                "current": current,
                "done": done,
                "reason": reason,
                "action": "打开入口链接 -> 搜索 bucket -> 点击 bucket -> 进入 Domain and Transmission -> Custom CDN acceleration domain -> 找到私有 CDN 域名 -> 开启/确认 COS 私有回源授权。",
            })
    private_auth = next((a for a in plan.get("actions", []) if a.get("kind") == "cdn.update_type_a_auth"), None)
    if private_auth:
        params = private_auth.get("params", {})
        secrets_ref = str(secrets_file) if secrets_file else "the generated plan.secrets.json file"
        current = "generated in local secrets file" if secrets_file and secrets_file.exists() else action_status_text([action_state(state, private_auth)])
        items.append({
            "title": "保存 private CDN TypeA key 到后端密钥系统",
            "required": "必做",
            "console": "Local file only",
            "search": params.get("domain", ""),
            "check": "The key must be 6-32 letters/digits and must match the backend config that generates signed URLs.",
            "current": current,
            "done": "No",
            "reason": "The skill can generate/configure the CDN key, but a human must store the same key in the backend secret system.",
            "action": f"打开 `{secrets_ref}` -> 复制 `{params.get('domain', '')}` 对应 key -> 保存到后端密钥系统 -> 确认 secrets 文件已加入 `.gitignore`。",
        })
    if any(a.get("kind", "").startswith("cdn.") for a in plan.get("actions", [])):
        cdn_domains = [a.get("params", {}).get("domain", "") for a in plan.get("actions", []) if a.get("kind") == "cdn.add_domain"]
        items.append({
            "title": "HTTPS 证书未由本 skill 配置",
            "required": "按需；需要 HTTPS URL 时必做",
            "console": md_link("CDN Domains", CONSOLE_LINKS["cdn_domains"]),
            "search": ", ".join(filter(None, cdn_domains)) or "public/private CDN domains",
            "check": "HTTPS Configuration tab; HTTPS switch and certificate status.",
            "current": "not configured by this skill",
            "done": "No",
            "reason": "HTTPS certificate upload/selection still requires a certificate decision by the project owner.",
            "action": "打开入口链接 -> 搜索 CDN 域名 -> Manage -> HTTPS Configuration -> 上传/选择证书 -> 如果项目需要 HTTPS URL，则开启 HTTPS。",
        })
    items.append({
        "title": "验收后清理临时 installer 权限",
        "required": "必做",
        "console": md_link("CAM Users", CONSOLE_LINKS["cam_users"]),
        "search": "cos-skill-installer-test or the installer CAM user",
        "check": "AdministratorAccess / temporary access key.",
        "current": "must be checked by user",
        "done": "No",
        "reason": "Temporary installer credentials have broad permissions and should not remain active after acceptance.",
        "action": "打开入口链接 -> 搜索 installer 用户 -> User Permissions 里解除 AdministratorAccess -> Access Keys 里禁用/删除密钥，或测试完成后直接删除该用户。",
    })
    return items


def acceptance_checklist(plan: Json, state: Optional[Json] = None, verify_results: Optional[List[Json]] = None) -> List[Json]:
    items: List[Json] = []
    for bucket in plan.get("buckets", []):
        states = action_states_for(state, plan, {"kind": {"cos.create_bucket", "cos.put_bucket_acl", "cos.put_bucket_cors"}, "bucket": bucket["name"]})
        current, done, reason = aggregate_status(states, state)
        items.append({
            "resource": f"COS bucket {bucket['name']}",
            "required": "必做",
            "console": md_link("COS Bucket", CONSOLE_LINKS["cos_buckets"]),
            "search": bucket["name"],
            "check": "Bucket exists; ACL; CORS rules",
            "current": current,
            "done": done,
            "reason": reason,
            "action": "打开入口链接 -> 搜索 bucket 名 -> 点击 bucket -> 检查 Basic Configuration、Permission Management/ACL、Security Management/CORS。",
        })
    cam = plan.get("config", {}).get("cam", {})
    cam_user = cam.get("user_name", "")
    if cam_user:
        states = action_states_for(state, plan, {"kind": {"cam.add_user"}, "name": cam_user})
        current, done, reason = aggregate_status(states, state)
        items.append({
            "resource": f"CAM user {cam_user}",
            "required": "必做",
            "console": md_link("CAM Users", CONSOLE_LINKS["cam_users"]),
            "search": cam_user,
            "check": "User exists; console login disabled unless intentionally enabled; API access matches plan.",
            "current": current,
            "done": done,
            "reason": reason,
            "action": "打开入口链接 -> 搜索用户 -> 检查 User Details、Access Method、已绑定策略。",
        })
    cam_policy = plan.get("config", {}).get("cam", {}).get("policy_name", "")
    if cam_policy:
        states = action_states_for(state, plan, {"kind": {"cam.create_policy", "cam.attach_user_policy"}, "policy_name": cam_policy})
        current, done, reason = aggregate_status(states, state)
        items.append({
            "resource": "CAM app policy",
            "required": "必做",
            "console": md_link("CAM Policies", CONSOLE_LINKS["cam_policies"]),
            "search": cam_policy,
            "check": "Policy exists; resource ARNs only include planned buckets",
            "current": current,
            "done": done,
            "reason": reason,
            "action": "打开入口链接 -> 搜索策略 -> 查看策略语法 -> 确认 resource 只包含计划中的 COS bucket -> 检查关联用户。",
        })
    for action_obj in plan.get("actions", []):
        kind = action_obj.get("kind")
        params = action_obj.get("params", {})
        if kind == "cdn.add_domain":
            domain = params.get("domain", "")
            states = action_states_for(state, plan, {"kind": {"cdn.add_domain", "cdn.enable_cos_private_access", "cdn.update_type_a_auth"}, "domain": domain})
            current, done, reason = aggregate_status(states, state)
            verify_current = verify_status_for(verify_results, domain)
            if verify_current:
                current = f"{current}; verify: {verify_current}"
            items.append({
                "resource": f"CDN domain {domain}",
                "required": "CDN enabled 时必做",
                "console": md_link("CDN Domains", CONSOLE_LINKS["cdn_domains"]),
                "search": domain,
                "check": "Status; origin domain; HTTPS switch",
                "current": current,
                "done": done,
                "reason": reason,
                "action": "打开入口链接 -> 搜索域名 -> Manage -> 检查 Status、Origin Configuration、HTTPS Configuration；私有 CDN 还要检查 Authentication。",
            })
        if kind == "dnspod.ensure_cname":
            fqdn = params.get("fqdn", "")
            states = action_states_for(state, plan, {"kind": {"dnspod.ensure_cname"}, "fqdn": fqdn})
            current, done, reason = aggregate_status(states, state)
            verify_current = verify_status_for(verify_results, fqdn)
            if verify_current:
                current = f"{current}; verify: {verify_current}"
            items.append({
                "resource": f"DNSPod CNAME {fqdn}",
                "required": "DNSPod enabled 时必做",
                "console": md_link("DNSPod", CONSOLE_LINKS["dnspod"]),
                "search": fqdn,
                "check": "Record type CNAME; value points to Tencent CDN CNAME",
                "current": current,
                "done": done,
                "reason": reason,
                "action": "打开入口链接 -> 点击 DNS zone -> 搜索子域名 -> 检查 Type=CNAME、Line=默认、Value 是 CDN CNAME target、Status 正常。",
            })
    return items


def md_link(label: str, url: str) -> str:
    return f"[{label}]({url})"


def md_cell(value: Any) -> str:
    text = str(value)
    return text.replace("\n", "<br>").replace("|", "\\|")


def manual_status(action_obj: Json, state: Optional[Json]) -> Tuple[str, str, str]:
    state_item = action_state(state, action_obj)
    if state_item and state_item.get("status") == "manual":
        return "manual confirmation required", "No", "The script cannot prove this console-only authorization is complete."
    if state_item and state_item.get("status") == "ok":
        return action_status_text([state_item]), "No", "Still requires human console confirmation."
    if state is None:
        return "planned, not applied", "No", "Apply has not run yet."
    return action_status_text([state_item]), "No", "Manual confirmation has not been recorded."


def action_state(state: Optional[Json], action_obj: Json) -> Optional[Json]:
    if not state:
        return None
    return (state.get("actions") or {}).get(action_obj.get("id"))


def action_states_for(state: Optional[Json], plan: Json, matcher: Json) -> List[Optional[Json]]:
    matched: List[Optional[Json]] = []
    kinds = matcher.get("kind")
    for action_obj in plan.get("actions", []):
        if kinds and action_obj.get("kind") not in kinds:
            continue
        params = action_obj.get("params", {})
        ok = True
        for key, value in matcher.items():
            if key == "kind":
                continue
            if params.get(key) != value:
                ok = False
                break
        if ok:
            matched.append(action_state(state, action_obj))
    return matched


def aggregate_status(states: List[Optional[Json]], state: Optional[Json]) -> Tuple[str, str, str]:
    if state is None:
        return "planned, not applied", "No", "Apply has not run yet."
    if not states:
        return "not planned", "No", "No matching planned action was found."
    statuses = [(item or {}).get("status", "not-run") for item in states]
    if any(status == "fail" for status in statuses):
        return action_status_text(states), "No", first_failure_detail(states) or "At least one API action failed."
    if all(status in {"ok", "skipped"} for status in statuses):
        return action_status_text(states), "Yes", "-"
    if any(status == "manual" for status in statuses):
        return action_status_text(states), "No", "Manual confirmation is still required."
    return action_status_text(states), "No", "Some planned actions have not run yet."


def action_status_text(states: List[Optional[Json]]) -> str:
    compact = []
    for item in states:
        if not item:
            compact.append("not-run")
            continue
        status = item.get("status", "unknown")
        detail = item.get("detail")
        compact.append(f"{status}: {detail}" if detail else status)
    return "; ".join(compact) if compact else "not-run"


def first_failure_detail(states: List[Optional[Json]]) -> str:
    for item in states:
        if item and item.get("status") == "fail":
            return str(item.get("detail") or "")
    return ""


def verify_status_for(results: Optional[List[Json]], token: str) -> str:
    if not results or not token:
        return ""
    matched = [item for item in results if token in item.get("check", "")]
    if not matched:
        return ""
    return "; ".join(f"{item.get('status')}: {item.get('detail')}" for item in matched)


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
