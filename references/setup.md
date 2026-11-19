# Setup and updates

`<skill-dir>` is the folder that contains SKILL.md. Run the script as `python3 <skill-dir>/scripts/sync.py`, or with `py -3` on Windows.

## Filling in config.json

Use this section when `check` reports `missing: <key>` lines. `check` has already created `config.json` from `config.example.json` and added every default.

1. Find each missing value yourself first, using the table.
2. In one message, show the user what you found and ask only for what you could not find.
3. Write the confirmed values into `<skill-dir>/config.json`, then run `check` again.

`null` means "not used". It is allowed only where the table says so.

| Key | How to find it |
|---|---|
| `github.defaultOrg` | `gh api user/orgs --jq '.[].login'`, then ask which one. `personal` means the user's own repos |
| `github.authorLogins` | `gh api user --jq .login` |
| `github.authorEmails` | `git config --global user.email`, plus any other address the user commits with. `null` if none |
| `jira.cloudId`, `jira.site` | `id` and `url` from `getAccessibleAtlassianResources`. Ask if there are several |
| `jira.projectKey` | Ask, offering the projects from `getVisibleJiraProjects` |
| `jira.taskIssueTypeId` | The id of the `Task` issue type, from `getJiraProjectIssueTypesMetadata` |
| `jira.issueKeyPattern` | `\b(<projectKey>)-\d+\b`. Add any other project keys the user's commits mention as alternatives inside the parentheses |
| `jira.assigneeAccountId` | The user's account id from `atlassianUserInfo` |
| `jira.sprintNamePrefix` | The common start of the user's team sprint names, chosen from the active sprints (the sprint query in SKILL.md step 3). `null` means use any active sprint |
| `jira.fields.storyPoints` | The id of the story points field (named like "Story points" or "Story point estimate") from `getJiraIssueTypeMetaWithFields` for the Task type, with `requiredFieldsOnly: false` |
| `jira.fields.sprint` | The id of the field named "Sprint", from the same call. `null` when the project has no sprints |

Settings with defaults, which the user may want to change. List them in one line:

- `finalStatus`: the status new tickets move to
- `syncLabel`: the label added to every ticket
- `storyPoints`: points range and hours per point
- `workHours`: working days, hours and time zone
- `firstRunLookbackDays` and `overlapDays`: how far back runs look
- `logWork`: whether to log the estimated time on each ticket
- `fieldDefaults`: the fallback value for each extra required field, by field id. Usually empty at first; filled in as the user answers questions about those fields

## Updating this skill

Use this section when the user asks to update the skill, or agrees to an update that `check` reported.

1. Run `sync.py update`. It pulls the latest version with git and lists what changed. It does not touch `config.json` or the history in `state.json`.
2. Tell the user what changed. If the update failed, show its message.
3. Read SKILL.md again, because the steps may have changed.
4. Run `check` again. It adds defaults for new settings, and lists new settings that need a value as `missing:` lines.

If the user only asked to update, stop there.
