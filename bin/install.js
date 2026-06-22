#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

const SKILL_NAME = "tencent-cos-cdn-setup-skill";
const CLIENT_ALIASES = {
  codex: "codex",
  openai: "codex",
  "claude-code": "claude-code",
  claude: "claude-code",
  custom: "custom",
};

function usage() {
  console.log(`Install ${SKILL_NAME} into LLM agent skill directories.

Usage:
  npx github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.0 install
  npx github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.0 install --all
  npx github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.0 install --client codex --client claude-code
  npx github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.0 install --dest /path/to/skills

Backward-compatible:
  npx github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.0
  npx github:yomage-ai/tencent-cos-cdn-setup-skill#v0.2.0 --force

Options:
  --client <name>  Install for codex, claude-code, or custom. Can be repeated.
  --all            Install for Codex and Claude Code.
  --dest <dir>     Install into a custom Agent Skills-compatible skills directory.
  --force          Replace an existing installed skill.
  --yes, -y        Run non-interactively with defaults.
  --lang <zh|en>   Set wizard language.
  --help           Show this help.
`);
}

function parseArgs(argv) {
  const args = {
    command: null,
    clients: [],
    dests: [],
    force: false,
    all: false,
    yes: false,
    help: false,
    lang: null,
  };

  const items = [...argv];
  if (items[0] === "install") {
    args.command = "install";
    items.shift();
  } else if (items[0] === "help") {
    args.help = true;
    items.shift();
  }

  for (let i = 0; i < items.length; i += 1) {
    const item = items[i];
    if (item === "--") {
      continue;
    } else if (item === "--help" || item === "-h") {
      args.help = true;
    } else if (item === "--force") {
      args.force = true;
    } else if (item === "--all") {
      args.all = true;
    } else if (item === "--yes" || item === "-y") {
      args.yes = true;
    } else if (item === "--client") {
      i += 1;
      if (!items[i]) throw new Error("--client requires a client name.");
      args.clients.push(...splitList(items[i]));
    } else if (item.startsWith("--client=")) {
      args.clients.push(...splitList(item.slice("--client=".length)));
    } else if (item === "--dest") {
      i += 1;
      if (!items[i]) throw new Error("--dest requires a directory path.");
      args.dests.push(items[i]);
    } else if (item.startsWith("--dest=")) {
      args.dests.push(item.slice("--dest=".length));
    } else if (item === "--lang") {
      i += 1;
      if (!items[i]) throw new Error("--lang requires zh or en.");
      args.lang = parseLang(items[i]);
    } else if (item.startsWith("--lang=")) {
      args.lang = parseLang(item.slice("--lang=".length));
    } else {
      throw new Error(`Unknown option: ${item}`);
    }
  }

  return args;
}

function splitList(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseLang(value) {
  const lang = String(value || "").toLowerCase();
  if (lang !== "zh" && lang !== "en") {
    throw new Error("--lang must be zh or en.");
  }
  return lang;
}

function codexHome() {
  return process.env.CODEX_HOME || path.join(os.homedir(), ".codex");
}

function normalizeClient(client) {
  const key = String(client || "").toLowerCase();
  const normalized = CLIENT_ALIASES[key];
  if (!normalized) {
    throw new Error(`Unsupported client: ${client}. Use codex, claude-code, or custom.`);
  }
  return normalized;
}

function clientTarget(client) {
  const normalized = normalizeClient(client);
  if (normalized === "codex") {
    return {
      id: "codex",
      label: "Codex",
      root: path.join(codexHome(), "skills"),
      note: "Restart Codex to pick up newly installed skills.",
    };
  }
  if (normalized === "claude-code") {
    return {
      id: "claude-code",
      label: "Claude Code",
      root: path.join(os.homedir(), ".claude", "skills"),
      note: "Restart Claude Code if the skills directory did not exist before this install.",
    };
  }
  throw new Error("The custom client requires --dest <dir>.");
}

function customTarget(dest, index) {
  return {
    id: `custom-${index}`,
    label: "Custom Agent Skills directory",
    root: dest,
    note: "Restart or reload the target agent if it does not detect skill changes live.",
  };
}

function sourceDir() {
  const packageRoot = path.resolve(__dirname, "..");
  const src = path.join(packageRoot, SKILL_NAME);
  if (!fs.existsSync(path.join(src, "SKILL.md"))) {
    throw new Error(`Skill source not found: ${src}`);
  }
  return src;
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath);
    } else if (entry.isSymbolicLink()) {
      const target = fs.readlinkSync(srcPath);
      symlinkSync(target, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function symlinkSync(target, destPath) {
  try {
    fs.symlinkSync(target, destPath);
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
    fs.rmSync(destPath, { recursive: true, force: true });
    fs.symlinkSync(target, destPath);
  }
}

function installTarget(src, target, options) {
  const root = path.resolve(target.root);
  const dest = path.join(root, SKILL_NAME);

  if (fs.existsSync(dest)) {
    if (!options.force) {
      return {
        status: "skipped",
        target,
        dest,
        message: `Already installed: ${dest}`,
      };
    }
    fs.rmSync(dest, { recursive: true, force: true });
  }

  fs.mkdirSync(root, { recursive: true });
  copyDir(src, dest);
  return {
    status: "installed",
    target,
    dest,
    message: `Installed ${SKILL_NAME} for ${target.label}: ${dest}`,
  };
}

function dedupeTargets(targets) {
  const seen = new Set();
  const deduped = [];
  for (const target of targets) {
    const key = path.resolve(target.root);
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(target);
  }
  return deduped;
}

function targetsFromArgs(args) {
  const targets = [];
  const clients = new Set();
  if (args.all) {
    clients.add("codex");
    clients.add("claude-code");
  }
  for (const client of args.clients) {
    const normalized = normalizeClient(client);
    if (normalized === "custom") {
      if (args.dests.length === 0) {
        throw new Error("--client custom requires --dest <dir>.");
      }
    } else {
      clients.add(normalized);
    }
  }
  for (const client of clients) targets.push(clientTarget(client));
  args.dests.forEach((dest, index) => targets.push(customTarget(dest, index)));

  if (targets.length === 0) {
    targets.push(clientTarget("codex"));
  }
  return dedupeTargets(targets);
}

function printResults(results) {
  for (const result of results) {
    const prefix = result.status === "installed" ? "Installed" : "Skipped";
    console.log(`${prefix}: ${result.target.label}`);
    console.log(`  ${result.dest}`);
    if (result.status === "skipped") {
      console.log("  Re-run with --force to replace it.");
    }
  }

  const notes = [...new Set(results.map((result) => result.target.note).filter(Boolean))];
  for (const note of notes) {
    console.log(note);
  }
}

function runInstall(targets, options) {
  const src = sourceDir();
  const results = targets.map((target) => installTarget(src, target, options));
  printResults(results);
  return results;
}

function loadPrompts() {
  try {
    return require("@clack/prompts");
  } catch (_) {
    throw new Error(
      "Interactive install requires @clack/prompts. Re-run through npx or use --client/--all/--dest with --yes."
    );
  }
}

function messages(lang) {
  if (lang === "en") {
    return {
      intro: `Install ${SKILL_NAME}`,
      lang: "Select language",
      clients: "Choose target agents",
      clientsHint: "Codex and Claude Code use the Agent Skills directory format.",
      force: "Replace existing installs if found?",
      custom: "Add a custom Agent Skills-compatible directory?",
      customPath: "Custom skills directory",
      installing: "Installing skill...",
      done: "Installation complete.",
      cancelled: "Installation cancelled",
    };
  }
  return {
    intro: `安装 ${SKILL_NAME}`,
    lang: "请选择语言 / Select language",
    clients: "选择要安装到哪些 AI 代理",
    clientsHint: "Codex 和 Claude Code 都使用 Agent Skills 目录结构。",
    force: "如果已安装，是否覆盖旧版本？",
    custom: "是否额外安装到自定义 Agent Skills 兼容目录？",
    customPath: "自定义 skills 目录",
    installing: "正在安装 skill...",
    done: "安装完成。",
    cancelled: "安装已取消",
  };
}

function handleCancel(p, value, msg) {
  if (p.isCancel(value)) {
    p.cancel(msg.cancelled);
    process.exit(0);
  }
  return value;
}

async function runInteractive(args) {
  const p = loadPrompts();

  let lang = args.lang;
  if (!lang) {
    const selected = await p.select({
      message: "请选择语言 / Select language",
      options: [
        { value: "zh", label: "中文" },
        { value: "en", label: "English" },
      ],
    });
    lang = handleCancel(p, selected, messages("zh"));
  }

  const msg = messages(lang);
  p.intro(msg.intro);

  const selectedClients = await p.multiselect({
    message: msg.clients,
    options: [
      { value: "codex", label: "Codex", hint: "~/.codex/skills" },
      { value: "claude-code", label: "Claude Code", hint: "~/.claude/skills" },
    ],
    initialValues: args.all
      ? ["codex", "claude-code"]
      : args.clients.map(normalizeClient).filter((client) => client !== "custom"),
    required: true,
  });
  const clients = handleCancel(p, selectedClients, msg);

  const addCustom = await p.confirm({
    message: msg.custom,
    initialValue: args.dests.length > 0,
  });
  const includeCustom = handleCancel(p, addCustom, msg);

  const dests = [...args.dests];
  if (includeCustom && dests.length === 0) {
    const customDir = await p.text({
      message: msg.customPath,
      placeholder: "/path/to/skills",
      validate(value) {
        return String(value || "").trim() ? undefined : "A directory path is required.";
      },
    });
    dests.push(handleCancel(p, customDir, msg));
  }

  let force = args.force;
  const targets = dedupeTargets([
    ...clients.map(clientTarget),
    ...dests.map((dest, index) => customTarget(dest, index)),
  ]);
  const existing = targets.some((target) => fs.existsSync(path.join(path.resolve(target.root), SKILL_NAME)));
  if (existing && !force) {
    const overwrite = await p.confirm({
      message: msg.force,
      initialValue: false,
    });
    force = handleCancel(p, overwrite, msg);
  }

  const spinner = p.spinner();
  spinner.start(msg.installing);
  const src = sourceDir();
  const results = targets.map((target) => installTarget(src, target, { force }));
  spinner.stop(msg.done);

  for (const result of results) {
    if (result.status === "installed") {
      p.log.success(`${result.target.label}: ${result.dest}`);
    } else {
      p.log.warn(`${result.target.label}: ${result.dest}`);
      p.log.info("Already installed. Re-run with --force to replace it.");
    }
  }
  for (const note of [...new Set(results.map((result) => result.target.note).filter(Boolean))]) {
    p.log.info(note);
  }
  p.outro(msg.done);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    usage();
    return;
  }

  const hasExplicitTargets = args.all || args.clients.length > 0 || args.dests.length > 0;
  const shouldUseWizard = process.stdin.isTTY && !args.yes && args.command === "install" && !hasExplicitTargets;

  if (shouldUseWizard) {
    await runInteractive(args);
    return;
  }

  const targets = targetsFromArgs(args);
  runInstall(targets, { force: args.force });
}

main().catch((error) => {
  console.error(`Error: ${error.message}`);
  process.exitCode = 1;
});
