<div align="center">

# Jira Sync

### From GitHub commits to Jira tickets, without the busywork.

An AI agent skill that groups your commits into real pieces of work, writes each ticket<br>
the way a teammate would, and estimates its story points. You approve every ticket first.

[![Tests](https://img.shields.io/github/actions/workflow/status/lordarcadius/jira-sync/tests.yml?branch=main&label=tests)](https://github.com/lordarcadius/jira-sync/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2EA043)](LICENSE)
[![Works with](https://img.shields.io/badge/works%20with-Claude%20Code%20%7C%20Codex%20%7C%20Antigravity%20%7C%20Copilot-6E56CF)](#install)

**[Install](#install)** · **[Usage](#using-it)** · **[How it works](#how-it-works)** · **[Settings](#settings)**

</div>

---

You write code all week, and then someone asks for Jira tickets. Jira Sync writes them for you, in one command.

## What it does

- **Finds all your work.** It looks at every repository and every branch in your GitHub organization, not just `main`, and picks only your own commits.
- **Groups commits by task.** A feature and its five follow-up fixes become one ticket, not six. The same fix on two branches counts once.
- **Writes tickets that read like a person wrote them.** Short, specific titles and a few plain-English bullets, with links to the commits. No filler and no buzzwords, and the titles follow your team's style.
- **Estimates story points** from the human time the work likely took, not from lines of code.
- **Fills in the details:** epic, sprint, labels, assignee, status, and any other field your Jira project requires.
- **Asks before it acts.** You see a full preview and can change anything. Nothing is created until you say yes.
- **Never creates a ticket twice.** Commits that already have a ticket, or already mention one, are skipped.
- **Warns you about leaked secrets.** If a commit seems to add a password, token or key, the preview tells you which file it is, so you can change the secret. The secret itself never goes into a ticket.

## How it works

```mermaid
flowchart LR
    A[Your commits on GitHub] --> B[Grouped into tasks]
    B --> C[Preview with story points]
    C -->|you edit and approve| D[Tickets created in Jira]
    D --> E[Marked Done and remembered]
```

## A quick look

You type:

```
/jira-sync my-org last 3 days
```

You get a preview like this one (shortened):

```
my-org · Nov 16 → Nov 18 · 23 commits → 5 tickets · 2.5 SP (working hours: ~24 h ≈ 2.7 SP)
Sprint: Team Sprint 7

1. [Task · 0.5 SP] Remember the last payment method at checkout
   Epic: SHOP-120 Payments · Labels: commit-sync, PaymentsApp
   Commits (4): web-app c1 3f2a9c1, c2 8b7d044, c4 a1e9f30, c6 77c0b12
   Effort: ~4.5 h, new feature plus two follow-up fixes
   What was done
   - Checkout pre-selects the card or wallet the customer used last time
   - Customers can still pick another method with one tap

2. [Bug · 0.25 SP] Fix wrong delivery date in order emails
   ...
```

To change the preview, reply in your own words, for example *"merge 2 and 3"*, *"make 1 one point"*, *"drop 4"* or *"use epic SHOP-98 for 2"*. When it looks right, say **create**.

## Before you start

| You need | What it is for | How to get it |
|---|---|---|
| An AI agent that supports skills | Runs Jira Sync | Claude Code, Codex, Antigravity, GitHub Copilot or similar |
| Python 3.9 or newer | Runs the small helper script | [python.org](https://www.python.org/downloads/). On Windows, also run `py -m pip install tzdata` |
| GitHub CLI (`gh`) | Reads your commits | [cli.github.com](https://cli.github.com), then run `gh auth login` |
| Git | Installs and updates Jira Sync | [git-scm.com](https://git-scm.com/downloads) |
| A Jira connection in your agent | Creates the tickets | Add Atlassian's official MCP server (the connector that lets AI agents use Jira) in your agent's settings, then sign in |

> [!TIP]
> You don't need to check this list yourself. Jira Sync checks everything at the start of every run and tells you exactly what to fix.

## Install

Download Jira Sync and connect it to every AI agent on your computer with two commands.

**macOS and Linux**

```bash
git clone https://github.com/lordarcadius/jira-sync.git ~/jira-sync
python3 ~/jira-sync/install.py
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/lordarcadius/jira-sync.git $HOME\jira-sync
py -3 $HOME\jira-sync\install.py
```

The installer finds Claude Code, Codex, Antigravity, GitHub Copilot and Gemini CLI, and adds a shortcut to Jira Sync in each one's skills folder. All agents share the same copy, settings and history, so a commit ticketed in one agent is never proposed again in another. To undo it, run the installer again with `--remove`.

Then start a new session in your agent and type `/jira-sync`. The first run sets itself up:

- It finds your GitHub username, Jira site, account and project fields on its own.
- It asks you only for what it can't find, such as which Jira project to use.

<details>
<summary>Prefer to add the shortcut by hand?</summary>

Run the line for your agent from inside the `jira-sync` folder (macOS and Linux):

| Agent | Command |
|---|---|
| Claude Code | `ln -s "$PWD" ~/.claude/skills/jira-sync` |
| Codex | `mkdir -p ~/.agents/skills && ln -s "$PWD" ~/.agents/skills/jira-sync` |
| Antigravity | `mkdir -p ~/.gemini/config/skills && ln -s "$PWD" ~/.gemini/config/skills/jira-sync` |
| GitHub Copilot | `mkdir -p ~/.copilot/skills && ln -s "$PWD" ~/.copilot/skills/jira-sync` |
| Gemini CLI | `mkdir -p ~/.gemini/skills && ln -s "$PWD" ~/.gemini/skills/jira-sync` |

On Windows, use `New-Item -ItemType Junction -Path <skills folder>\jira-sync -Target $PWD` with the same folders under `$HOME`. Older versions of Antigravity read `~/.gemini/antigravity/skills` instead. Add only one shortcut per agent, or the skill shows up twice.

</details>

## Using it

| Type | To get |
|---|---|
| `/jira-sync` | Tickets for everything since your last sync |
| `/jira-sync last 3 days` | Tickets for a time window |
| `/jira-sync my-org` | Tickets from a different GitHub organization |
| `/jira-sync personal` | Tickets from your own repositories, outside any organization |
| `/jira-sync owner/repo since 2026-11-01` | Tickets from one repository, starting at a date |

In Codex, type `$jira-sync` instead of `/jira-sync`. In any agent you can also just ask, for example *"create Jira tickets from my commits this week"*.

## How story points are worked out

Most code today is written with an AI assistant, so the size of a change says little about the effort behind it. Jira Sync estimates the *human* time instead: understanding the problem, guiding the AI, reviewing, testing and fixing. It then converts that time to points.

- **1 point is one working day**, 9 hours by default.
- Tickets range from **0.25 to 2 points**. Bigger work is split into separate tickets.
- **Estimates go up** for tricky areas (system code, timing issues, install and update flows) and for work that needed many follow-up fixes.
- **Estimates go down** for text, settings and documentation changes.
- **The total stays realistic.** Jira Sync compares the total with the working hours between your commits, and explains any big difference in the preview.

Every estimate comes with a one-line reason, so you can adjust it before anything is created.

## Staying up to date

Each time it runs, Jira Sync checks for a new version and tells you when one is out. Say **"update jira-sync"** and it updates itself. Your settings and history are kept.

To update by hand:

```bash
cd ~/jira-sync && git pull
```

## Settings

Your settings live in `config.json` in the `jira-sync` folder. The first run creates this file, and you rarely need to touch it. These are the settings you may want to change:

| Setting | Default | What it means |
|---|---|---|
| `workHours` | 10:00–19:00, Mon–Fri, `Asia/Kolkata` | Your working hours, used to judge how long work took |
| `storyPoints.hoursPerPoint` | `9` | Hours in one story point |
| `storyPoints.min` / `max` | `0.25` / `2` | Smallest and largest ticket |
| `jira.finalStatus` | `Done` | The status new tickets are moved to |
| `jira.syncLabel` | `commit-sync` | The label added to every ticket Jira Sync creates |
| `jira.logWork` | `false` | Set to `true` to also log the estimated time on each ticket |
| `jira.fieldDefaults` | empty | Answers Jira Sync remembers for extra fields your Jira project requires |
| `firstRunLookbackDays` | `7` | How many days back the very first run looks |

## Your data stays yours

- **Settings and history stay on your computer.** `config.json` holds your settings and `state.json` records which commits already have tickets. Both are listed in `.gitignore`, so they are never committed.
- **It talks only to GitHub and Jira.** Jira Sync reaches GitHub through your own `gh` login and Jira through your agent's connection. Your agent's AI model sees the commit details, as it does with any task.
- **Secrets stay out of tickets and out of the chat.** Jira Sync checks your commits for secrets on your own computer. When it finds one, it names only the file. It never shows the secret in the chat or puts it in a ticket.
- **Nothing is created without your approval.** You approve the preview first.

## Troubleshooting

| Problem | Fix |
|---|---|
| `/jira-sync` doesn't show up | Start a new session in your agent, and run the installer again to check the shortcut |
| "Another jira-sync run is still open" | Finish or cancel the other session. If it was closed without finishing, tell the agent it was abandoned and it will clear it |
| Some repositories are missing | Run `gh auth refresh -s repo,read:org` |
| Jira tools are not available | Connect Atlassian's MCP server in your agent's settings and sign in |

## Files

| File | What it is |
|---|---|
| `SKILL.md` | The main steps your agent follows |
| `references/` | Extra instructions your agent reads only when needed: first-time setup, updates, and how to write tickets |
| `scripts/sync.py` | The helper that reads commits from GitHub and remembers which ones already have tickets |
| `install.py` | Connects Jira Sync to your AI agents |
| `config.example.json` | The template for your settings |
| `tests/` | Automated tests, run on Linux, macOS and Windows for every change |

## License

[MIT](LICENSE). You can use, change and share Jira Sync freely.

## Author

Made by **Vipul Kumar Jha** · [vipuljha.com](https://vipuljha.com) · [hey@vipuljha.com](mailto:hey@vipuljha.com) · [GitHub @lordarcadius](https://github.com/lordarcadius)
