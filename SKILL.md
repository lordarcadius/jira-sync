---
name: jira-sync
description: Turn the user's recent GitHub commits into well-grouped Jira tickets with story points, after showing a preview and getting confirmation. Use when the user runs /jira-sync or $jira-sync, asks to create Jira tickets from their commits or recent work, or asks to update this skill.
license: MIT
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

Run the script as `python3 <skill-dir>/scripts/sync.py <command>`. On Windows, use `py -3` in place of `python3`. A short mention like `sync.py unlock` below means that full command.

Reply to the user in the language they use; write ticket text in English.

**What this skill needs**

- A shell with Python 3.9+ and the GitHub CLI `gh`, logged in.
- The Atlassian MCP server for Jira.
  - Tool names below are that server's own (`createJiraIssue`, …). Your client may show them with a prefix.
  - If a name differs, use the equivalent tool.

## 0. Check prerequisites and setup

Do this at the start of every run, before step 1.

1. **GitHub and config:** run `python3 <skill-dir>/scripts/sync.py check`.
   - It prints `OK`, or one problem per line with its fix. It also creates `config.json` when there is none and adds defaults for new settings.
   - If `python3` itself is not found, the user needs to install Python 3.9 or newer.
   - If it prints `Update available`, tell the user in one line and ask whether to update now. If they agree, follow "Updating this skill" in `<skill-dir>/references/setup.md`. If not, carry on.
2. **Jira:** call `getAccessibleAtlassianResources`.
   - If there are no Jira tools, or the call fails, the user needs to add Atlassian's MCP server to this agent and sign in.
   - If `jira.cloudId` is set but is not in the result, the signed-in Atlassian account cannot reach that site. The user should sign in with the right account, or fix `jira.cloudId`.
3. **Tell the user what to fix:**
   - Put every problem from 1 and 2 in one message, each with its exact fix: the install command, the login command, or the setting to change.
   - Leave out the `missing:` lines; you fill those yourself in 4.
   - Stop until the user says it is done, then run 1 and 2 again.
4. **Fill config gaps:** for `missing:` lines, follow "Filling in config.json" in `<skill-dir>/references/setup.md`.

If the user only asks to update the skill, follow "Updating this skill" in `<skill-dir>/references/setup.md`.

## 1. Fetch commits

```
python3 <skill-dir>/scripts/sync.py fetch [TARGET] [--since VALUE]
```

It starts a run and prints:

- **A fetch id.** Pass it as `--fetch <id>` to `diff`, `record` and `finish`.
- **The working hours before these changes.** Step 4 uses this to check the story-points total.
- **One line per change:** id, repo, authored time, +/- lines, branches, working hours since the user's previous commit, and headline. A change is one commit, or the same patch cherry-picked onto several branches.
- **`WARNING` lines** for changes that seem to add secrets.

Full details (message, files, PR, SHAs, `secrets`) are in the fetch file whose path it prints.

- **Another run is open:** `fetch` refuses to start. Tell the user. Only if they confirm the other run was abandoned, run `sync.py unlock` and fetch again.
- **0 changes:** tell the user, run `sync.py finish --fetch <id>`, and stop.
- **Errors:** mention any `errors` from the fetch file.
- **Already linked:** commits that already reference a Jira key (in the message, a PR, or only on ticket branches) are excluded by the script and listed under `skipped`.

Fetch once per run. Every run must end with `finish` or `unlock` (steps 5 and 6), or the next run is blocked.

## 2. Understand the changes

Read each change's details from the fetch file. Use `jq`, or read it in parts if it is large. Base grouping and effort on the message, file list and stats first. Read a diff only when those cannot settle grouping or story points:

```
python3 <skill-dir>/scripts/sync.py diff --fetch <id> <change id>
```

It prints the change's diff, cut to 6,000 characters. Never read the diff of a change that has `secrets`, so that secret values stay out of the conversation.

Work out what changed for the people using the product, not just what the message says.

## 3. Load Jira context

Make these calls in parallel, all with `jira.cloudId`:

- **Required fields:** `getJiraIssueTypeMetaWithFields` with `jira.projectKey` and `requiredFieldsOnly: true`. Call it for the Task type (`jira.taskIssueTypeId`), and for the Bug type if the project has one (its id is in `getJiraProjectIssueTypesMetadata`).
  - **Extra required fields** are the required fields that have no default (`hasDefaultValue: false`) and that this skill does not fill itself. The skill fills summary, description, issue type, project, assignee, labels, parent, story points and sprint.
  - Note each extra field's id, name, `schema` and `allowedValues`. Step 4 fills them in.
- **Open epics:** `searchJiraIssuesUsingJql`, JQL `project = <projectKey> AND issuetype = Epic AND statusCategory != Done ORDER BY updated DESC`, fields `["summary"]`, `maxResults` 100.
- **Active sprint:** skip this if `jira.fields.sprint` is `null`. Otherwise use JQL `project = <projectKey> AND sprint in openSprints() ORDER BY created DESC`, fields `[<sprint field>]`, `maxResults` 50.
  - Keep sprints with `state` `active` whose name starts with `jira.sprintNamePrefix`. If the prefix is `null`, keep every active sprint.
  - Pick the one with the latest `startDate`.
  - If none matches, tickets go to the backlog. Say so in the preview.
- **Labels in use:** JQL `project = <projectKey> AND labels is not EMPTY AND created >= -90d ORDER BY created DESC`, fields `["labels"]`, `maxResults` 100.
- **Team style:** JQL `project = <projectKey> AND (labels is EMPTY OR labels != <syncLabel>) ORDER BY created DESC`, fields `["summary"]`, `maxResults` 30. These are the team's other tickets, so new titles can match the style the team is used to.
- **Already synced:** JQL `project = <projectKey> AND labels = <syncLabel> AND (text ~ "<sha>" OR text ~ "<sha>" …)` with the 7-character SHA of every commit in the fetch, up to 40 SHAs per query. Use fields `["summary","description"]` and `responseContentFormat` `markdown`.
  - For each ticket found, check that the SHA really appears in its description.
  - Then run `sync.py record --fetch <id> <KEY> <change id>` and leave that change out of the proposal.

## 4. Build the tickets

Read `<skill-dir>/references/writing-tickets.md` and follow it. It covers:

- grouping changes into tickets
- story points, and the check of the total against the working hours from step 1
- every ticket field, including the extra required fields
- how to word titles and descriptions so they read as if a person wrote them
- changes that contain secrets

Every change id must end up in exactly one ticket or in the skipped list.

## 5. Preview and confirmation

Show the proposal in this format:

```
<target> · <since> → <until> · <N> commits → <M> tickets · <total> SP (working hours: ~<H> h ≈ <S> SP)
Sprint: <name, or "none, tickets go to the backlog">

1. [Task · 0.5 SP] <summary>
   Epic: <KEY> <epic name> · Labels: <labels>
   Fields: <field name>: <values> · <field name>: <values>
   Commits (3): <repo> c24 bcc9cea, c25 bbb9fc7, c28 4524aec
   Effort: ~4.5 h, <one-line reason>
   What was done
   - ...
   Why it matters
   - ...

Skipped (no ticket):
- c31 <headline>: <reason>
Excluded by fetch (already reference a Jira ticket): <count>

Possible secrets in commits:
- c58 <file>: <kind>
```

- Leave out the `Fields:` line when there are no extra required fields, and "Why it matters" when the ticket has none.
- Leave out the secrets block when no change has `secrets`. When there are some:
  - name only the file and the kind, never a value
  - suggest rotating those secrets and removing the files from git

Then wait for the user.

- Apply edits such as "merge 2 and 3", "make 4 0.5 SP", "drop 5" or "change the epic of 1 to KEY-123", and show the changed tickets again.
- A dropped ticket's changes become skipped.
- Create nothing until the user clearly confirms.
- If the user cancels, run `sync.py unlock` and stop. Do not run `record` or `finish`.

## 6. Create

For each confirmed ticket, in order:

1. **Create:** call `createJiraIssue` with:
   - `cloudId`, `projectKey`, `issueTypeName`, `summary`, `description`
   - `contentFormat: "markdown"`
   - `assignee_account_id`
   - `parent`: the epic key; omit it if there is no epic
   - `additional_fields`: story points, the sprint if there is one, labels, and every extra required field. Shape the extra fields as `writing-tickets.md` says:

     ```
     { "<storyPoints field>": 0.5,
       "<sprint field>": <sprint id number>,
       "<extra field id>": [{"value": "<allowed value>"}],
       "labels": ["commit-sync", "PaymentsApp"] }
     ```

   - **From the second ticket on,** also pass `transition: {"id": "<first transition id>"}`, the id learnt on the first ticket in 2.
     - If such a create call returns an error, the issue may have been created anyway.
     - Search `labels = <syncLabel> AND text ~ "<first commit's 7-character SHA>"` before retrying.
     - Retry without `transition` only if nothing is found.
   - If the created issue has no epic, set it with `editJiraIssue` and fields `{"parent": {"key": "<epic key>"}}`. For the remaining tickets, pass the epic the same way in `additional_fields` instead of `parent`.
2. **Move to `jira.finalStatus`:**
   - Call `getTransitionsForJiraIssue`. If a transition whose `to.name` equals `finalStatus` is offered, use it.
   - Otherwise apply the one that goes to "In Progress", and check again.
   - Reuse the transition IDs for the same issue type for the rest of the run. Skip any step the create call already applied.
3. **Log work:** only if `jira.logWork` is true. Call `addWorklogToJiraIssue` with:
   - `timeSpent`: the ticket's estimated hours, for example `4h 30m`
   - `started`: the `authored` time of its first change, read in `workHours.timezone`, written as `2026-11-16T10:30:00.000+0530`
4. **Record:** as soon as the issue exists, run `python3 <skill-dir>/scripts/sync.py record --fetch <id> <KEY> <change ids>`.

If a create call fails, report it, do not record that ticket, and continue with the rest. If the issue was created but a later step failed, still record it and report what is missing.

After all tickets:

- Run `sync.py record --fetch <id> skipped <skipped change ids>`.
- End the run:
  - If every change id was ticketed or skipped, run `sync.py finish --fetch <id>`.
  - If the user deferred some changes, run `sync.py unlock` instead, so the next run sees them again.
- End with a table of the created tickets: link (`<jira.site>/browse/<KEY>`), type, SP and status. Add the total SP and list any failures.
