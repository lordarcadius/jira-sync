# Setup and updates

`<skill-dir>` is the folder that contains SKILL.md.

## Filling in config.json

Use this section when `check` reports `config.json does not exist` or a `missing: <key>` line.

1. If `config.json` does not exist, copy `<skill-dir>/config.example.json` to `<skill-dir>/config.json`.
2. Find each missing value yourself first, using the table.
3. In one message, show the user what you found and ask only for what you could not find.
4. Write the confirmed values into `config.json`, then run `check` again.

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
| `jira.fields.*` | Field ids from `getJiraIssueTypeMetaWithFields` for the Task type, matched by name: story points, sprint, Android version(s) affected, device type(s) affected. `null` when the project has no such field. `storyPoints` cannot be `null` |

`finalStatus`, `syncLabel`, `storyPoints`, `workHours` and the lookback days already have defaults. List them for the user in one line, so they can change them.

## Updating this skill

Use this section when the user asks to update the skill, or agrees to an update that `check` reported.

1. Run `python3 <skill-dir>/scripts/sync.py update`. It pulls the latest version with git and lists what changed. It does not touch `config.json` or the history in `state.json`.
2. Tell the user what changed. If the update failed, show its message, which says what to do.
3. Read SKILL.md again, because the steps may have changed.
4. Run `check` again. Settings added by the new version show up as `missing:` lines.

If the user only asked to update, stop there.
