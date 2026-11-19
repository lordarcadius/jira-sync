# Changelog

What changed in each version of Jira Sync. Version numbers follow [semantic versioning](https://semver.org).

<!-- To release: set metadata.version in SKILL.md, add a section below, commit, then push a tag such as v1.1.0. The release workflow publishes that section as the GitHub release. -->

## 1.0.0 (2026-11-19)

First public release.

- Turns your GitHub commits into grouped Jira tickets with story points, after a preview you approve
- Works in any agent that supports skills: Claude Code, Codex, Antigravity, GitHub Copilot and Gemini CLI
- `install.py` connects it to every agent on your computer
- Sets itself up on the first run, and checks Python, the GitHub CLI, the Jira connection and your settings on every run
- Fills in whatever fields your Jira project requires, and remembers your answers
- Writes short, specific tickets that follow your team's style
- Never creates a ticket twice, and allows only one run at a time
- Warns you about commits that seem to add passwords, tokens or keys
- Updates itself when a new version is out
- Can log the estimated time on each ticket
