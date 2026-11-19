---
name: jira-sync
description: Turn the user's recent GitHub commits into well-grouped Jira tickets with story points, after showing a preview and getting confirmation. Use when the user runs /jira-sync or $jira-sync, asks to create Jira tickets from their commits or recent work, or asks to update this skill.
metadata:
  author: Vipul Kumar Jha
  email: hey@vipuljha.com
  website: https://vipuljha.com
  github: https://github.com/lordarcadius
---

# Jira tickets from commits

The user's message may name a target and a time window, for example `/jira-sync my-org last 3 days`:

- **Target:** an org name, `personal`, or `owner/repo`. Default: `github.defaultOrg`.
- **Window:** `7d`, `YYYY-MM-DD`, or words like "last 3 days" (pass `--since 3d`). Default: since the last sync.

`<skill-dir>` below means the folder that contains this SKILL.md. The script keeps `config.json`, `state.json` and `.cache/` there and finds them itself, so its commands work from any working directory. Every Jira ID, field ID and limit below comes from `config.json`.

Reply to the user in the language they use; write ticket text in English.

**What this skill needs**

- A shell with `python3` (3.9+) and the GitHub CLI `gh`, logged in.
- The Atlassian MCP server for Jira.
  - Tool names below are that server's own (`createJiraIssue`, …). Your client may show them with a prefix.
  - If a name differs, use the equivalent tool.

## 0. Check prerequisites and setup

Do this at the start of every run, before step 1.

1. **GitHub and config:** run

   ```
   python3 <skill-dir>/scripts/sync.py check
   ```

   It prints `OK`, or one problem per line with its fix. If `python3` itself is not found, the user needs to install Python 3.9 or newer.

   If it also prints `Update available`, tell the user in one line and ask whether to update now. If they agree, follow "Updating this skill" in `<skill-dir>/references/setup.md`. If not, carry on.
2. **Jira:** call `getAccessibleAtlassianResources`.
   - If there are no Jira tools, or the call fails, the user needs to add Atlassian's MCP server to this agent and sign in.
   - If `jira.cloudId` is set but is not in the result, the signed-in Atlassian account cannot reach that site. The user should sign in with the right account, or fix `jira.cloudId`.
3. **Tell the user what to fix:**
   - Put every problem from 1 and 2 in one message, each with its exact fix: the install command, the login command, or the setting to change.
   - Leave out the `missing:` lines; you fill those yourself in 4.
   - Stop until the user says it is done, then run 1 and 2 again.
4. **Fill config gaps:** for `config.json does not exist` or `missing:` lines, follow "Filling in config.json" in `<skill-dir>/references/setup.md`.

If the user only asks to update the skill, follow "Updating this skill" in `<skill-dir>/references/setup.md`.

## 1. Fetch commits

```
python3 <skill-dir>/scripts/sync.py fetch [TARGET] [--since VALUE]
```

It prints one line per change: id, repo, authored time, +/- lines, branches, working hours since the user's previous commit, and headline. A change is one commit, or the same patch cherry-picked onto several branches. Full details (message, files, PR, SHAs) are in `<skill-dir>/.cache/fetch.json`.

- **0 changes:** tell the user, run `sync.py finish`, and stop.
- **Errors:** mention any `errors` from `fetch.json`.
- **Already linked:** commits that already reference a Jira key (in the message, a PR, or only on ticket branches) are excluded by the script and listed under `skipped`.

Run `fetch` only once per session. `record` and `finish` act on the latest `fetch.json`, and change ids are renumbered on every fetch.

## 2. Understand the changes

Read the details for each change from `fetch.json`. Use `jq`, or read it in parts if it is large. Base grouping and effort on the message, file list and stats first. Read a diff only when those cannot settle grouping or story points, and cap it:

```
gh api repos/OWNER/REPO/commits/SHA -H "Accept: application/vnd.github.diff" | head -c 6000
```

Work out what changed for the people using the product, not just what the message says.

## 3. Load Jira context

Make these calls in parallel, all with `jira.cloudId`:

- **Field options:** `getJiraIssueTypeMetaWithFields`, with `jira.projectKey`, `jira.taskIssueTypeId` and `requiredFieldsOnly: true`. For the Android-version and device fields, use only the `allowedValues` it returns.
- **Open epics:** `searchJiraIssuesUsingJql`, JQL `project = <projectKey> AND issuetype = Epic AND statusCategory != Done ORDER BY updated DESC`, fields `["summary"]`, `maxResults` 100.
- **Active sprint:** skip this if `jira.fields.sprint` is `null`. Otherwise use JQL `project = <projectKey> AND sprint in openSprints() ORDER BY created DESC`, fields `[<sprint field>]`, `maxResults` 50.
  - Keep sprints with `state` `active` whose name starts with `jira.sprintNamePrefix`. If the prefix is `null`, keep every active sprint.
  - Pick the one with the latest `startDate`.
  - If none matches, tickets go to the backlog. Say so in the preview.
- **Labels in use:** JQL `project = <projectKey> AND labels is not EMPTY AND created >= -90d ORDER BY created DESC`, fields `["labels"]`, `maxResults` 100.
- **Already synced:** JQL `project = <projectKey> AND labels = <syncLabel> AND created >= -60d`, fields `["summary","description"]`, `responseContentFormat` `markdown`, `maxResults` 100.
  - If a change's 7-character SHA appears in one of these descriptions, it already has a ticket.
  - Run `sync.py record <KEY> <id>` for it and leave it out of the proposal.

## 4. Build the tickets

Read `<skill-dir>/references/writing-tickets.md` and follow it. It covers how to group changes into tickets, how to estimate story points, and how to fill in every field. Every change id must end up in exactly one ticket or in the skipped list.

## 5. Preview and confirmation

Show the proposal in this format:

```
<target> · <since> → <until> · <N> commits → <M> tickets · <total> SP
Sprint: <name, or "none, tickets go to the backlog">

1. [Task · 0.5 SP] <summary>
   Epic: <KEY> <epic name> · Labels: <labels>
   Android: <values> · Device: <values>
   Commits (3): <repo> c24 bcc9cea, c25 bbb9fc7, c28 4524aec
   Effort: ~4.5 h, <one-line reason>
   What was done
   - ...
   Why it matters
   - ...

Skipped (no ticket):
- c31 <headline>: <reason>
Excluded by fetch (already reference a Jira ticket): <count>
```

Leave out the Android and Device line for fields that are `null` in the config.

Then wait for the user.

- Apply edits such as "merge 2 and 3", "make 4 0.5 SP", "drop 5" or "change the epic of 1 to KEY-123", and show the changed tickets again.
- A dropped ticket's changes become skipped.
- Create nothing until the user clearly confirms.
- If the user cancels, stop without running `record` or `finish`.

## 6. Create

For each confirmed ticket, in order:

1. **Create:** call `createJiraIssue` with:
   - `cloudId`, `projectKey`, `issueTypeName`, `summary`, `description`
   - `contentFormat: "markdown"`
   - `assignee_account_id`
   - `parent`: the epic key; omit it if there is no epic
   - `additional_fields`, using the IDs from `jira.fields`. Leave out fields that are `null`, and the sprint when there is none:

     ```
     { "<storyPoints>": 0.5,
       "<androidVersions>": [{"value": "Android 15"}],
       "<deviceTypes>": [{"value": "<allowed value>"}],
       "<sprint>": <sprint id number>,
       "labels": ["commit-sync", "PaymentsApp"] }
     ```

   - If the created issue has no epic, set it with `editJiraIssue` and fields `{"parent": {"key": "<epic key>"}}`. For the remaining tickets, pass the epic the same way in `additional_fields` instead of `parent`.
2. **Move to `jira.finalStatus`:**
   - Call `getTransitionsForJiraIssue`. If a transition whose `to.name` equals `finalStatus` is offered, use it.
   - Otherwise apply the one that goes to "In Progress", and check again.
   - Reuse the transition IDs for the same issue type for the rest of the run.
3. **Record:** as soon as the issue exists, run `python3 <skill-dir>/scripts/sync.py record <KEY> <change ids>`.

If a create call fails, report it, do not record that ticket, and continue with the rest. If the issue was created but a later step failed, still record it and report what is missing.

After all tickets:

- Run `sync.py record skipped <skipped change ids>`.
- Run `sync.py finish`, but only if every change id was either ticketed or skipped. If the user deferred some, skip `finish` so the next run sees them again.
- End with a table of the created tickets: link (`<jira.site>/browse/<KEY>`), type, SP and status. Add the total SP and list any failures.
