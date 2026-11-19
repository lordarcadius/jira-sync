#!/usr/bin/env python3
"""GitHub side of /jira-sync: list your unticketed commits and remember which ones became tickets.

  check                                    report missing config values and GitHub CLI problems
  update                                   pull the latest version of this skill with git
  fetch [TARGET] [--since 7d|YYYY-MM-DD]   TARGET: org name | personal | owner/repo
  record TICKET_KEY|skipped CHANGE_ID...   mark changes from the last fetch as handled
  finish                                   save the last fetch time as the target's lastSync
"""
import sys

# Checked before the other imports, because zoneinfo needs 3.9.
if sys.version_info < (3, 9):
    sys.exit(f"Python 3.9 or newer is needed (found {sys.version.split()[0]}): install it, then run again")

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_CONFIG_PATH = ROOT / "config.example.json"
STATE_PATH = ROOT / "state.json"
FETCH_PATH = ROOT / ".cache" / "fetch.json"
MAX_FILES_LISTED = 15
MAX_MESSAGE_CHARS = 800
HUNK_HEADER = re.compile(r"^@@[^@]*@@", re.M)

BRANCHES_QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    refs(refPrefix: "refs/heads/", first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { name target { ... on Commit { committedDate } } }
    }
  }
}
"""


def gh(*args):
    result = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh api {args[0]}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def gh_all(path):
    return [item for page in gh(path, "--paginate", "--slurp") for item in page]


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso_utc(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path, default=None):
    if not path.exists():
        if default is None:
            sys.exit(f"Missing {path}")
        return default
    return json.loads(path.read_text())


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def missing_keys(config, example, prefix=""):
    """Dotted keys of the example that are absent or empty ("" or []) in config. null means deliberately unused."""
    missing = []
    for key, sample in example.items():
        path = f"{prefix}{key}"
        if key not in config or config[key] in ("", []):
            missing.append(path)
        elif isinstance(sample, dict):
            missing += missing_keys(config[key] or {}, sample, f"{path}.")
    return missing


def config_problems():
    if not CONFIG_PATH.exists():
        return [f"{CONFIG_PATH.name} does not exist"]
    return [f"missing: {key}" for key in missing_keys(load_json(CONFIG_PATH), load_json(EXAMPLE_CONFIG_PATH))]


def load_config():
    problems = config_problems()
    if problems:
        sys.exit(f"{CONFIG_PATH} is incomplete; run setup (SKILL.md step 0):\n" + "\n".join(problems))
    return load_json(CONFIG_PATH)


def github_problems(config):
    """GitHub CLI problems, each with the fix the user should apply."""
    if shutil.which("gh") is None:
        return ["GitHub CLI `gh` is not installed: install it from https://cli.github.com, then run `gh auth login`"]
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        return ["GitHub CLI is not logged in: run `gh auth login`"]
    problems = []
    headers = subprocess.run(["gh", "api", "--include", "user"], capture_output=True, text=True).stdout
    scopes = re.search(r"^x-oauth-scopes:(.*)$", headers, re.I | re.M)
    # Only classic tokens send this header; fine-grained tokens are not checked here.
    if scopes:
        granted = {scope.strip() for scope in scopes[1].split(",")}
        if "repo" not in granted or not granted & {"read:org", "write:org", "admin:org"}:
            problems.append("GitHub token lacks the `repo` or `read:org` scope, so private and org repos are missed: "
                            "run `gh auth refresh -s repo,read:org`")
    org = ((config or {}).get("github") or {}).get("defaultOrg")
    if org and org != "personal" and "/" not in org:
        try:
            gh(f"orgs/{org}/repos?per_page=1")
        except RuntimeError as error:
            problems.append(f"Cannot list repos of the GitHub org `{org}` ({error}): "
                            "check github.defaultOrg, or ask an org admin for access")
    return problems


def git(*args, timeout=60):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=timeout, env=env)


def update_notice():
    """A line saying how many new changes the upstream branch has; empty when up to date or when it cannot tell."""
    if shutil.which("git") is None or git("rev-parse", "--abbrev-ref", "@{u}").returncode != 0:
        return ""
    try:
        if git("fetch", "--quiet", timeout=15).returncode != 0:
            return ""
    except subprocess.TimeoutExpired:
        return ""
    behind = git("rev-list", "--count", "HEAD..@{u}").stdout.strip()
    return f"Update available: {behind} new change(s). Run `sync.py update`." if behind not in ("", "0") else ""


def cmd_update(_args):
    if shutil.which("git") is None:
        sys.exit("git is not installed: install it, then run `sync.py update` again")
    top = git("rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != ROOT:
        sys.exit(f"{ROOT} was not installed with `git clone`, so it cannot update itself: reinstall it as the README shows")
    before = git("rev-parse", "HEAD").stdout.strip()
    pulled = git("pull", "--ff-only", "--quiet", timeout=120)
    if pulled.returncode != 0:
        sys.exit(f"Update failed: {pulled.stderr.strip()}\nUpdate by hand instead: cd {ROOT} && git pull")
    changes = git("log", "--format=- %s", f"{before}..HEAD").stdout.strip()
    print(f"Updated. What changed:\n{changes}" if changes else "Already up to date")


def cmd_check(_args):
    notice = update_notice()
    if notice:
        print(notice)
    config = load_json(CONFIG_PATH) if CONFIG_PATH.exists() else None
    problems = github_problems(config) + config_problems()
    if problems:
        sys.exit("\n".join(problems))
    print(f"OK: {CONFIG_PATH}")


def load_state():
    state = load_json(STATE_PATH, {})
    for key in ("lastSync", "commits", "patches"):
        state.setdefault(key, {})
    return state


def resolve_since(arg, target, config, state):
    now = datetime.now(timezone.utc)
    if arg:
        days = re.fullmatch(r"(\d+)d", arg)
        if days:
            return now - timedelta(days=int(days[1]))
        moment = datetime.fromisoformat(arg)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=ZoneInfo(config["workHours"]["timezone"]))
        return moment
    last = state["lastSync"].get(target)
    if last:
        # Commits can be pushed days after they are made, so re-scan a window; state skips handled SHAs.
        return parse_time(last) - timedelta(days=config["overlapDays"])
    return now - timedelta(days=config["firstRunLookbackDays"])


def list_repos(target, since):
    if "/" in target:
        return [target]
    base = "user/repos?affiliation=owner" if target == "personal" else f"orgs/{target}/repos?type=all"
    repos, page = [], 1
    while True:
        batch = gh(f"{base}&sort=pushed&direction=desc&per_page=100&page={page}")
        for repo in batch:
            if repo["pushed_at"] is None:
                continue
            if parse_time(repo["pushed_at"]) < since:
                return repos
            repos.append(repo["full_name"])
        if len(batch) < 100:
            return repos
        page += 1


def active_branches(repo, since):
    owner, name = repo.split("/")
    branches, after = [], None
    while True:
        args = ["graphql", "-f", f"query={BRANCHES_QUERY}", "-f", f"owner={owner}", "-f", f"name={name}"]
        if after:
            args += ["-f", f"after={after}"]
        refs = gh(*args)["data"]["repository"]["refs"]
        for node in refs["nodes"]:
            committed = (node["target"] or {}).get("committedDate")
            if committed and parse_time(committed) >= since:
                branches.append(node["name"])
        if not refs["pageInfo"]["hasNextPage"]:
            return branches
        after = refs["pageInfo"]["endCursor"]


def is_mine(commit, logins, emails):
    login = (commit.get("author") or {}).get("login")
    email = (commit["commit"]["author"].get("email") or "").lower()
    return login in logins or email in emails


def scan_repo(repo, since, logins, emails):
    """Return {sha: {"repo", "commit", "branches"}} for your commits on every branch active since `since`."""
    found = {}
    for branch in active_branches(repo, since):
        for commit in gh_all(f"repos/{repo}/commits?sha={quote(branch, safe='')}&since={iso_utc(since)}&per_page=100"):
            if is_mine(commit, logins, emails):
                entry = found.setdefault(commit["sha"], {"repo": repo, "commit": commit, "branches": set()})
                entry["branches"].add(branch)
    return found


def patch_hash(files):
    digest = hashlib.sha256()
    for f in sorted(files, key=lambda f: f["filename"]):
        body = f.get("patch") or f"{f['status']} +{f['additions']} -{f['deletions']}"
        digest.update(f["filename"].encode())
        digest.update(HUNK_HEADER.sub("@@", body).encode())
    return digest.hexdigest()[:16]


def jira_reference(key_re, message, branches, pulls):
    places = [(message, "commit message")]
    places += [(f"{p['title']} {p['head']['ref']}", f"PR #{p['number']}") for p in pulls]
    # A ticket branch also contains every older commit of its base branch, so only trust it when no other branch has the commit.
    if branches and all(key_re.search(branch) for branch in branches):
        places.append((branches[0], f"branch {branches[0]}"))
    for text, where in places:
        match = key_re.search(text)
        if match:
            return f"references {match.group(0)} in {where}"
    return None


def working_hours(start, end, work):
    """Hours of [start, end] that fall inside working hours."""
    tz = ZoneInfo(work["timezone"])
    start, end = start.astimezone(tz), end.astimezone(tz)
    open_at, close_at = time.fromisoformat(work["start"]), time.fromisoformat(work["end"])
    total, day = 0.0, start.date()
    while day <= end.date():
        if day.weekday() in work["days"]:
            window_start = datetime.combine(day, open_at, tz)
            window_end = datetime.combine(day, close_at, tz)
            total += max(0.0, (min(end, window_end) - max(start, window_start)).total_seconds())
        day += timedelta(days=1)
    return total / 3600


def workday_hours(work):
    open_at, close_at = time.fromisoformat(work["start"]), time.fromisoformat(work["end"])
    return (close_at.hour * 60 + close_at.minute - open_at.hour * 60 - open_at.minute) / 60


def cmd_fetch(args):
    config = load_config()
    state = load_state()
    gh_cfg = config["github"]
    target = args.target or gh_cfg["defaultOrg"]
    until = datetime.now(timezone.utc)
    since = resolve_since(args.since, target, config, state)
    logins = set(gh_cfg["authorLogins"])
    emails = {e.lower() for e in gh_cfg["authorEmails"] or []}
    key_re = re.compile(config["jira"]["issueKeyPattern"])

    repos = list_repos(target, since)
    mine, errors = {}, []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for repo, result in zip(repos, pool.map(lambda r: _safe(scan_repo, r, since, logins, emails), repos)):
            if isinstance(result, Exception):
                errors.append(f"{repo}: {result}")
            else:
                mine.update(result)

    candidates = [
        entry for sha, entry in mine.items()
        if sha not in state["commits"] and len(entry["commit"]["parents"]) <= 1
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        details = list(pool.map(
            lambda e: _safe(lambda: (gh(f"repos/{e['repo']}/commits/{e['commit']['sha']}"),
                                     gh(f"repos/{e['repo']}/commits/{e['commit']['sha']}/pulls"))),
            candidates,
        ))

    authored_times = sorted({
        parse_time(e["commit"]["commit"]["author"]["date"])
        for e in mine.values() if len(e["commit"]["parents"]) <= 1
    })
    work = config["workHours"]
    day_hours = workday_hours(work)

    changes, skipped = {}, []
    for entry, detail in zip(candidates, details):
        sha = entry["commit"]["sha"]
        message = entry["commit"]["commit"]["message"]
        headline = message.splitlines()[0] if message else ""
        if isinstance(detail, Exception):
            errors.append(f"{entry['repo']}@{sha[:7]}: {detail}")
            continue
        commit, pulls = detail
        branches = sorted(entry["branches"])
        reference = jira_reference(key_re, message, branches, pulls)
        if reference:
            skipped.append({"repo": entry["repo"], "sha": sha[:7], "headline": headline, "reason": reference})
            continue
        digest = patch_hash(commit.get("files", []))
        if digest in state["patches"]:
            skipped.append({"repo": entry["repo"], "sha": sha[:7], "headline": headline,
                            "reason": f"same change already handled as {state['patches'][digest]}"})
            continue
        authored = parse_time(commit["commit"]["author"]["date"])
        change = changes.setdefault((entry["repo"], digest), {
            "repo": entry["repo"],
            "patch_hash": digest,
            "commits": [],
            "branches": set(),
            "authored": authored,
            "message": message[:MAX_MESSAGE_CHARS],
            "pr": next(({"number": p["number"], "title": p["title"], "branch": p["head"]["ref"]} for p in pulls), None),
            "additions": commit["stats"]["additions"],
            "deletions": commit["stats"]["deletions"],
            "files": [
                f"{f['filename']} +{f['additions']} -{f['deletions']}"
                for f in commit.get("files", [])[:MAX_FILES_LISTED]
            ],
            "more_files": max(0, len(commit.get("files", [])) - MAX_FILES_LISTED),
        })
        change["commits"].append(sha)
        change["branches"].update(branches)
        change["authored"] = min(change["authored"], authored)

    ordered = sorted(changes.values(), key=lambda c: c["authored"])
    tz = ZoneInfo(work["timezone"])
    for index, change in enumerate(ordered, start=1):
        earlier = [t for t in authored_times if t < change["authored"]]
        gap = min(day_hours, working_hours(earlier[-1], change["authored"], work)) if earlier else None
        change["id"] = f"c{index}"
        change["branches"] = sorted(change["branches"])
        change["work_hours_since_prev"] = round(gap, 2) if gap is not None else None
        change["authored"] = change["authored"].astimezone(tz).strftime("%Y-%m-%d %a %H:%M")

    already = sum(1 for sha in mine if sha in state["commits"])
    result = {
        "target": target,
        "since": iso_utc(since),
        "until": iso_utc(until),
        "repos_scanned": len(repos),
        "already_handled": already,
        "errors": errors,
        "skipped": skipped,
        "changes": [{"id": c.pop("id"), **c} for c in ordered],
    }
    save_json(FETCH_PATH, result)
    commit_count = sum(len(c["commits"]) for c in result["changes"])
    print(f"{target}: {len(ordered)} changes ({commit_count} commits) from {result['since']} to {result['until']}; "
          f"{len(skipped)} skipped, {already} already handled, {len(errors)} errors. Details: {FETCH_PATH}")
    for change in result["changes"]:
        gap = change["work_hours_since_prev"]
        print(f"{change['id']}\t{change['repo'].split('/')[1]}\t{change['authored']}\t"
              f"+{change['additions']}/-{change['deletions']}\t[{','.join(change['branches'])}]\t"
              f"{'-' if gap is None else f'{gap}h'}\t{change['message'].splitlines()[0] if change['message'] else ''}")


def _safe(fn, *args):
    try:
        return fn(*args)
    except RuntimeError as error:
        return error


def cmd_record(args):
    fetch = load_json(FETCH_PATH)
    by_id = {c["id"]: c for c in fetch["changes"]}
    unknown = [cid for cid in args.change_ids if cid not in by_id]
    if unknown:
        sys.exit(f"Unknown change ids: {', '.join(unknown)}")
    state = load_state()
    for cid in args.change_ids:
        change = by_id[cid]
        for sha in change["commits"]:
            state["commits"][sha] = args.ticket
        state["patches"][change["patch_hash"]] = args.ticket
    save_json(STATE_PATH, state)
    print(f"Recorded {', '.join(args.change_ids)} as {args.ticket}")


def cmd_finish(_args):
    fetch = load_json(FETCH_PATH)
    state = load_state()
    previous = state["lastSync"].get(fetch["target"])
    if previous is None or parse_time(previous) < parse_time(fetch["until"]):
        state["lastSync"][fetch["target"]] = fetch["until"]
    save_json(STATE_PATH, state)
    print(f"lastSync[{fetch['target']}] = {state['lastSync'][fetch['target']]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check").set_defaults(run=cmd_check)
    sub.add_parser("update").set_defaults(run=cmd_update)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("target", nargs="?")
    fetch.add_argument("--since")
    fetch.set_defaults(run=cmd_fetch)
    record = sub.add_parser("record")
    record.add_argument("ticket")
    record.add_argument("change_ids", nargs="+")
    record.set_defaults(run=cmd_record)
    sub.add_parser("finish").set_defaults(run=cmd_finish)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
