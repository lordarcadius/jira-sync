#!/usr/bin/env python3
"""Connect jira-sync to the AI agents installed on this computer.

  python3 install.py            link jira-sync into every agent found
  python3 install.py --remove   remove those links

Each link points at this folder, so all agents share one copy, one config and one history.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

NAME = "jira-sync"
SKILL_DIR = Path(__file__).resolve().parent


def agents(home):
    """(agent name, skills folder) for each agent that looks installed under home."""
    gemini = home / ".gemini"
    found = []
    if (home / ".claude").exists():
        found.append(("Claude Code", home / ".claude" / "skills"))
    if (home / ".codex").exists():
        found.append(("Codex", home / ".agents" / "skills"))
    # Antigravity reads either folder; linking both would list the skill twice.
    if (gemini / "config").exists():
        found.append(("Antigravity", gemini / "config" / "skills"))
    elif (gemini / "antigravity").exists():
        found.append(("Antigravity", gemini / "antigravity" / "skills"))
    if (home / ".copilot").exists():
        found.append(("GitHub Copilot", home / ".copilot" / "skills"))
    if shutil.which("gemini"):
        found.append(("Gemini CLI", gemini / "skills"))
    return found


def is_link(path):
    if path.is_symlink():
        return True
    return os.name == "nt" and path.exists() and os.path.realpath(path) != os.path.abspath(path)


def points_here(path):
    return Path(os.path.realpath(path)) == SKILL_DIR


def link(skills_dir):
    path = skills_dir / NAME
    if is_link(path):
        return "already linked" if points_here(path) else f"skipped: it already links to {os.path.realpath(path)}"
    if path.exists():
        return "skipped: a folder with this name already exists"
    skills_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        # A junction needs no administrator rights, unlike a Windows symlink.
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(path), str(SKILL_DIR)], capture_output=True, text=True)
        if result.returncode != 0:
            return f"failed: {(result.stdout or result.stderr).strip()}"
    else:
        path.symlink_to(SKILL_DIR, target_is_directory=True)
    return "linked"


def unlink(skills_dir):
    path = skills_dir / NAME
    if not is_link(path) or not points_here(path):
        return "nothing to remove"
    if os.name == "nt":
        os.rmdir(path)
    else:
        path.unlink()
    return "removed"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true", help="remove the links instead of creating them")
    args = parser.parse_args()
    found = agents(Path.home())
    if not found:
        sys.exit("No supported AI agent found in your home folder. Link this folder by hand, as the README shows.")
    action = unlink if args.remove else link
    width = max(len(name) for name, _ in found)
    for name, skills_dir in found:
        print(f"{name:<{width}}  {skills_dir / NAME}  {action(skills_dir)}")
    if not args.remove:
        print("\nStart a new session in each agent, then type /jira-sync (in Codex: $jira-sync).")


if __name__ == "__main__":
    main()
