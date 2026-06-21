#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

const SKILL_NAME = "tencent-cos-cdn-setup-skill";

function usage() {
  console.log(`Install ${SKILL_NAME} into Codex skills.

Usage:
  npx github:yomage-ai/tencent-cos-cdn-setup-skill
  npx github:yomage-ai/tencent-cos-cdn-setup-skill --force
  npx github:yomage-ai/tencent-cos-cdn-setup-skill --dest /path/to/skills

Options:
  --force        Replace an existing installed skill.
  --dest <dir>   Install into a custom skills directory.
  --help         Show this help.
`);
}

function parseArgs(argv) {
  const args = { force: false, dest: null };
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (item === "--") {
      continue;
    } else if (item === "--help" || item === "-h") {
      args.help = true;
    } else if (item === "--force") {
      args.force = true;
    } else if (item === "--dest") {
      i += 1;
      if (!argv[i]) throw new Error("--dest requires a directory path.");
      args.dest = argv[i];
    } else {
      throw new Error(`Unknown option: ${item}`);
    }
  }
  return args;
}

function codexHome() {
  return process.env.CODEX_HOME || path.join(os.homedir(), ".codex");
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
      fs.symlinkSync(target, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function rmDir(target) {
  fs.rmSync(target, { recursive: true, force: true });
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    usage();
    return;
  }

  const packageRoot = path.resolve(__dirname, "..");
  const src = path.join(packageRoot, SKILL_NAME);
  if (!fs.existsSync(path.join(src, "SKILL.md"))) {
    throw new Error(`Skill source not found: ${src}`);
  }

  const destRoot = path.resolve(args.dest || path.join(codexHome(), "skills"));
  const dest = path.join(destRoot, SKILL_NAME);

  if (fs.existsSync(dest)) {
    if (!args.force) {
      console.error(`Already installed: ${dest}`);
      console.error("Re-run with --force to replace it.");
      process.exitCode = 1;
      return;
    }
    rmDir(dest);
  }

  fs.mkdirSync(destRoot, { recursive: true });
  copyDir(src, dest);
  console.log(`Installed ${SKILL_NAME} to ${dest}`);
  console.log("Restart Codex to pick up new skills.");
}

try {
  main();
} catch (error) {
  console.error(`Error: ${error.message}`);
  process.exitCode = 1;
}
