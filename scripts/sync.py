#!/usr/bin/env python3
"""GitHub side of jira-sync: list your unticketed commits and remember which ones became tickets.

  check                                        report problems with Python, the GitHub CLI and config.json
  update                                       pull the latest version of this skill with git
  fetch [TARGET] [--since 7d|YYYY-MM-DD]       start a run; TARGET: org name | personal | owner/repo
  diff --fetch ID CHANGE_ID                    show a change's diff, cut to a readable size
  record --fetch ID KEY|skipped CHANGE_ID...   mark changes of that fetch as handled
  finish --fetch ID                            save the sync time and end the run
  unlock                                       end a run that was cancelled or abandoned
"""
import sys

# Checked before the other imports, because zoneinfo needs 3.9.
if sys.version_info < (3, 9):
    sys.exit(f"Python 3.9 or newer is needed (found {sys.version.split()[0]}): install it, then run again")

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from time import sleep
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_CONFIG_PATH = ROOT / "config.example.json"
STATE_PATH = ROOT / "state.json"
CACHE_DIR = ROOT / ".cache"
RUN_LOCK_PATH = CACHE_DIR / "run.lock"
STATE_LOCK_PATH = CACHE_DIR / "state.lock"
RUN_LOCK_STALE_AFTER = timedelta(hours=12)
FETCH_KEPT_FOR = timedelta(days=7)
MAX_FILES_LISTED = 15
MAX_MESSAGE_CHARS = 800
MAX_DIFF_CHARS = 6000
HUNK_HEADER = re.compile(r"^@@[^@]*@@", re.M)

SECRET_FILE = re.compile(
    r"(^|/)(\.env(\.(?!example|sample|template)[\w.]+)?|id_(rsa|dsa|ecdsa|ed25519)|[^/]+\.(pem|key|p12|pfx|jks|keystore)"
    r"|[^/]*(secret|credential)s?\.(json|ya?ml|env|txt|properties|xml|ini|toml)|keys?/[^/]+\.(json|ya?ml|txt|properties))$",
    re.I,
)
SECRET_TEXT = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("password or secret value", re.compile(
        r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key)[\"']?\s*[:=]\s*[\"'](?![$<{])[^\"'\s]{8,}[\"']")),
]

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


def run(command, **kwargs):
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", **kwargs)


def gh(*args):
    result = run(["gh", "api", *args])
    if result.returncode != 0:
        raise RuntimeError(f"gh api {args[0]}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def gh_all(path):
    return [item for page in gh(path, "--paginate", "--slurp") for item in page]


def git(*args, timeout=60):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return run(["git", "-C", str(ROOT), *args], timeout=timeout, env=env)


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso_utc(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_time(value):
    return parse_time(value).astimezone().strftime("%Y-%m-%d %H:%M")


def load_json(path, default=None):
    if not path.exists():
        if default is None:
            sys.exit(f"Missing {path}")
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)



def sync_config(config, example, prefix=""):
    """Copy absent keys from the example into config; return (added, missing) dotted keys.

    - missing: the value is still a placeholder ("" or []), so the user has to provide it
    - null means "deliberately not used" and counts as set
    """
    added, missing = [], []
    for key, sample in example.items():
        path = f"{prefix}{key}"
        if key not in config:
            config[key] = copy.deepcopy(sample)
            if sample not in ("", []):
                added.append(path)
        value = config[key]
        if isinstance(sample, dict) and isinstance(value, dict):
            sub_added, sub_missing = sync_config(value, sample, f"{path}.")
            added += sub_added
            missing += sub_missing
        elif value in ("", []):
            missing.append(path)
    return added, missing


def config_problems():
    """Create or complete config.json from the example's defaults; return what the user still has to provide."""
    created = not CONFIG_PATH.exists()
    config = {} if created else load_json(CONFIG_PATH)
    added, missing = sync_config(config, load_json(EXAMPLE_CONFIG_PATH))
    if created or added:
        save_json(CONFIG_PATH, config)
    if created:
        print(f"Created {CONFIG_PATH.name} from {EXAMPLE_CONFIG_PATH.name}")
    for key in added if not created else []:
        print(f"Added default: {key}")
    problems = [f"missing: {key}" for key in missing]
    zone = (config.get("workHours") or {}).get("timezone")
    if zone:
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            problems.append(f"Time zone `{zone}` is unknown: fix workHours.timezone, or on Windows run `py -m pip install tzdata`")
    return problems


def load_config():
    problems = config_problems()
    if problems:
        sys.exit("config.json is incomplete; run `sync.py check` and complete the setup:\n" + "\n".join(problems))
    return load_json(CONFIG_PATH)


def github_problems(config):
    """GitHub CLI problems, each with the fix the user should apply."""
    if shutil.which("gh") is None:
        return ["GitHub CLI `gh` is not installed: install it from https://cli.github.com, then run `gh auth login`"]
    if run(["gh", "auth", "status"]).returncode != 0:
        return ["GitHub CLI is not logged in: run `gh auth login`"]
    problems = []
    headers = run(["gh", "api", "--include", "user"]).stdout
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


def skill_version(skill_md):
    """metadata.version from the front matter of a SKILL.md text, or "unknown"."""
    parts = skill_md.split("---", 2)
    match = re.search(r"^\s+version:\s*[\"']?([^\"'\s]+)", parts[1] if len(parts) == 3 else "", re.M)
    return match[1] if match else "unknown"


def current_version():
    return skill_version((ROOT / "SKILL.md").read_text(encoding="utf-8"))


def update_notice():
    """A line about a newer version on the upstream branch; empty when up to date or when it cannot tell."""
    if shutil.which("git") is None or git("rev-parse", "--abbrev-ref", "@{u}").returncode != 0:
        return ""
    try:
        if git("fetch", "--quiet", timeout=15).returncode != 0:
            return ""
    except subprocess.TimeoutExpired:
        return ""
    behind = git("rev-list", "--count", "HEAD..@{u}").stdout.strip()
    if behind in ("", "0"):
        return ""
    current, latest = current_version(), skill_version(git("show", "@{u}:SKILL.md").stdout)
    if latest != current:
        return f"Update available: version {latest} (you have {current}). Run `sync.py update`."
    return f"Update available: {behind} new change(s) since version {current}. Run `sync.py update`."


def cmd_check(_args):
    notice = update_notice()
    if notice:
        print(notice)
    config_issues = config_problems()
    problems = github_problems(load_json(CONFIG_PATH)) + config_issues
    if problems:
        sys.exit("\n".join(problems))
    print(f"OK: jira-sync {current_version()}, {CONFIG_PATH}")


def cmd_update(_args):
    if shutil.which("git") is None:
        sys.exit("git is not installed: install it, then run `sync.py update` again")
    top = git("rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != ROOT:
        sys.exit(f"{ROOT} was not installed with `git clone`, so it cannot update itself: reinstall it as the README shows")
    before, old_version = git("rev-parse", "HEAD").stdout.strip(), current_version()
    pulled = git("pull", "--ff-only", "--quiet", timeout=120)
    if pulled.returncode != 0:
        sys.exit(f"Update failed: {pulled.stderr.strip()}\nUpdate by hand instead: cd {ROOT} && git pull")
    changes = git("log", "--format=- %s", f"{before}..HEAD").stdout.strip()
    new_version = current_version()
    if not changes:
        print(f"Already up to date (version {new_version})")
    elif new_version != old_version:
        print(f"Updated from version {old_version} to {new_version}. What changed:\n{changes}")
    else:
        print(f"Updated (still version {new_version}). What changed:\n{changes}")



def read_run_lock():
    return load_json(RUN_LOCK_PATH) if RUN_LOCK_PATH.exists() else None


def acquire_run_lock(fetch_id, now):
    """Start a run, refusing while another run that is not stale is still open."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    lock = read_run_lock()
    if lock:
        if now - parse_time(lock["started"]) < RUN_LOCK_STALE_AFTER:
            sys.exit(f"Another jira-sync run (fetch {lock['id']}, started {local_time(lock['started'])}) is still open. "
                     "Finish or cancel it first. If it was abandoned, run `sync.py unlock`, then fetch again.")
        print(f"Ending an abandoned run from {local_time(lock['started'])}")
        RUN_LOCK_PATH.unlink()
    try:
        handle = os.open(RUN_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        sys.exit("Another jira-sync run started at the same moment; let it finish first")
    with os.fdopen(handle, "w", encoding="utf-8") as file:
        json.dump({"id": fetch_id, "started": iso_utc(now)}, file)


def release_run_lock(fetch_id=None):
    """Remove the run lock if it belongs to fetch_id (any run when None); return the removed lock."""
    lock = read_run_lock()
    if lock and fetch_id in (None, lock["id"]):
        RUN_LOCK_PATH.unlink()
        return lock
    return None


def load_state():
    state = load_json(STATE_PATH, {})
    for key in ("lastSync", "commits", "patches"):
        state.setdefault(key, {})
    return state


@contextmanager
def locked_state():
    """Yield state.json's content and save it on exit, holding a lock so parallel commands don't lose writes."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    deadline = datetime.now(timezone.utc) + timedelta(seconds=30)
    while True:
        try:
            os.close(os.open(STATE_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            if datetime.now(timezone.utc) > deadline:
                sys.exit(f"state.json is locked by another command. If none is running, delete {STATE_LOCK_PATH}")
            sleep(0.2)
    try:
        state = load_state()
        yield state
        save_json(STATE_PATH, state)
    finally:
        STATE_LOCK_PATH.unlink()


def fetch_path(fetch_id):
    return CACHE_DIR / f"fetch-{fetch_id}.json"


def load_fetch(fetch_id):
    path = fetch_path(fetch_id)
    if not path.exists():
        sys.exit(f"No fetch with id {fetch_id}: use the id printed by `sync.py fetch`")
    return load_json(path)


def find_change(fetch, change_id):
    for change in fetch["changes"]:
        if change["id"] == change_id:
            return change
    sys.exit(f"Unknown change id: {change_id}")



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


def secret_findings(files):
    """'path: kind' for added or changed files that look like they hold secrets. Never includes the values."""
    findings = []
    for f in files:
        if f.get("status") == "removed":
            continue
        added = "\n".join(line[1:] for line in (f.get("patch") or "").splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        kinds = [kind for kind, pattern in SECRET_TEXT if pattern.search(added)]
        if kinds or SECRET_FILE.search(f["filename"]):
            findings.append(f"{f['filename']}: {', '.join(kinds) or 'file name suggests secrets'}")
    return findings


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


def _safe(fn, *args):
    try:
        return fn(*args)
    except RuntimeError as error:
        return error


def collect_changes(target, since, until, config, state):
    """Scan GitHub and build the fetch result: your unticketed changes, oldest first."""
    gh_cfg = config["github"]
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
        files = commit.get("files", [])
        digest = patch_hash(files)
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
            "files": [f"{f['filename']} +{f['additions']} -{f['deletions']}" for f in files[:MAX_FILES_LISTED]],
            "more_files": max(0, len(files) - MAX_FILES_LISTED),
            "secrets": secret_findings(files),
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

    return {
        "target": target,
        "since": iso_utc(since),
        "until": iso_utc(until),
        "repos_scanned": len(repos),
        "already_handled": sum(1 for sha in mine if sha in state["commits"]),
        "work_hours_total": round(sum(c["work_hours_since_prev"] or 0 for c in ordered), 1),
        "errors": errors,
        "skipped": skipped,
        "changes": [{"id": c.pop("id"), **c} for c in ordered],
    }



def cmd_fetch(args):
    config = load_config()
    state = load_state()
    target = args.target or config["github"]["defaultOrg"]
    until = datetime.now(timezone.utc)
    since = resolve_since(args.since, target, config, state)
    fetch_id = until.strftime("%Y%m%d-%H%M%S")
    acquire_run_lock(fetch_id, until)
    try:
        result = {"id": fetch_id, **collect_changes(target, since, until, config, state)}
        save_json(fetch_path(fetch_id), result)
    except BaseException:
        release_run_lock(fetch_id)
        raise
    for old in CACHE_DIR.glob("fetch-*.json"):
        if until - datetime.fromtimestamp(old.stat().st_mtime, timezone.utc) > FETCH_KEPT_FOR:
            old.unlink()

    changes = result["changes"]
    commit_count = sum(len(c["commits"]) for c in changes)
    hours, per_point = result["work_hours_total"], config["storyPoints"]["hoursPerPoint"]
    print(f"Fetch id: {fetch_id} (pass it as --fetch to diff, record and finish)")
    print(f"{target}: {len(changes)} changes ({commit_count} commits) from {result['since']} to {result['until']}; "
          f"{len(result['skipped'])} skipped, {result['already_handled']} already handled, {len(result['errors'])} errors. "
          f"Details: {fetch_path(fetch_id)}")
    print(f"Working hours before these changes: ~{hours} h (about {round(hours / per_point, 2)} SP at {per_point} h per SP)")
    for change in changes:
        gap = change["work_hours_since_prev"]
        print(f"{change['id']}\t{change['repo'].split('/')[1]}\t{change['authored']}\t"
              f"+{change['additions']}/-{change['deletions']}\t[{','.join(change['branches'])}]\t"
              f"{'-' if gap is None else f'{gap}h'}\t{change['message'].splitlines()[0] if change['message'] else ''}")
    for change in changes:
        for finding in change["secrets"]:
            print(f"WARNING {change['id']}: possible secret in {finding}")


def cmd_diff(args):
    change = find_change(load_fetch(args.fetch), args.change_id)
    path = f"repos/{change['repo']}/commits/{change['commits'][0]}"
    result = run(["gh", "api", path, "-H", "Accept: application/vnd.github.diff"])
    if result.returncode != 0:
        sys.exit(f"gh api {path}: {result.stderr.strip()}")
    text = result.stdout
    print(text[:MAX_DIFF_CHARS] + (f"\n... cut at {MAX_DIFF_CHARS} characters" if len(text) > MAX_DIFF_CHARS else ""))


def cmd_record(args):
    fetch = load_fetch(args.fetch)
    changes = [find_change(fetch, cid) for cid in args.change_ids]
    with locked_state() as state:
        for change in changes:
            for sha in change["commits"]:
                state["commits"][sha] = args.ticket
            state["patches"][change["patch_hash"]] = args.ticket
    print(f"Recorded {', '.join(args.change_ids)} as {args.ticket}")


def cmd_finish(args):
    fetch = load_fetch(args.fetch)
    with locked_state() as state:
        previous = state["lastSync"].get(fetch["target"])
        if previous is None or parse_time(previous) < parse_time(fetch["until"]):
            state["lastSync"][fetch["target"]] = fetch["until"]
        last = state["lastSync"][fetch["target"]]
    release_run_lock(args.fetch)
    print(f"lastSync[{fetch['target']}] = {last}. Run finished.")


def cmd_unlock(_args):
    lock = release_run_lock()
    print(f"Ended the open run (fetch {lock['id']}, started {local_time(lock['started'])})" if lock else "No run was open")


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check").set_defaults(run=cmd_check)
    sub.add_parser("update").set_defaults(run=cmd_update)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("target", nargs="?")
    fetch.add_argument("--since")
    fetch.set_defaults(run=cmd_fetch)
    diff = sub.add_parser("diff")
    diff.add_argument("--fetch", required=True)
    diff.add_argument("change_id")
    diff.set_defaults(run=cmd_diff)
    record = sub.add_parser("record")
    record.add_argument("--fetch", required=True)
    record.add_argument("ticket")
    record.add_argument("change_ids", nargs="+")
    record.set_defaults(run=cmd_record)
    finish = sub.add_parser("finish")
    finish.add_argument("--fetch", required=True)
    finish.set_defaults(run=cmd_finish)
    sub.add_parser("unlock").set_defaults(run=cmd_unlock)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
