# Writing the tickets

Rules for step 4 of SKILL.md: how to group changes into tickets, estimate story points and fill in each field. Every limit and field ID comes from `config.json`.

## Grouping

- One ticket is one outcome a non-technical person would recognise, not one commit.
- Put these in the same ticket:
  - every commit for the same feature or bug, with its follow-up fixes and tweaks
  - reverts and re-applies of that work
  - the same change made in several repos or branches
- Fold noise into the most related ticket from the same repo. Noise means version bumps, dependency bumps, formatting, docs and typo fixes.
  - If nothing related exists and it is real standalone work (for example a dependency upgrade that needed fixes), make it a ticket.
  - Otherwise, list it as skipped.
- Do not mix unrelated apps in one ticket.
- If a ticket would exceed `storyPoints.max`, split it along real sub-features so each ticket stands on its own. Use "Part 1/2" only when there is no natural split.
- Every change id must end up in exactly one ticket or in the skipped list.

## Story points

The work is done with an AI coding agent, which writes most of the code quickly. The human time goes into:

- understanding the problem
- guiding the AI
- reviewing its code
- building, flashing and testing on a device
- iterating on what didn't work

Estimate that human time in hours, then convert it: SP = hours / `storyPoints.hoursPerPoint`. Round to the nearest `storyPoints.step` and clamp to `[storyPoints.min, storyPoints.max]`. With the defaults, 1 SP is one 9-hour working day:

| SP | ~Hours | Typical work |
|---|---|---|
| 0.25 | ≤ 2.25 | Text or config tweak, small isolated fix |
| 0.5 | ~4.5 | Bug fix or small feature in one area |
| 0.75 | ~6.75 | Fix or feature touching a few areas |
| 1 | 9 | Multi-part feature that needed device testing |
| 1.5 | 13.5 | Larger feature, or tricky debugging across flows |
| 2 | 18 | Big feature; anything bigger is split |

Signals to weigh:

- A large AI-written diff is not large effort by itself. A tiny fix after a long investigation can be 0.5–1.
- **Points go higher for:** system or framework code, concurrency, reboot/OTA/install flows, device-specific behaviour, and many follow-up fix commits (iterations).
- **Points go lower for:** UI text, config, mechanical refactors and docs.
- `work_hours_since_prev` counts working hours (per `workHours`) between the user's previous commit and this one, capped at one working day.
  - It is a rough upper bound on time spent.
  - Commits made in one batch show 0, which says nothing about effort.

## Fields

- **Issue type:** `Bug` if the work fixes broken behaviour, otherwise `Task`.
- **Summary:** the outcome in plain English, at most 80 characters, sentence case. No code, class or file names.
- **Description:** markdown, short, in this shape:

  ```
  **What was done**
  - 2–4 short bullets in plain language

  **Why it matters**
  - 1–2 bullets on the effect for users or the team

  ---
  Repo: <repo> · Branch: <branches>
  Commits: [abc1234](https://github.com/<owner>/<repo>/commit/<full sha>), ...
  ```

  Keep the text above the `---` line free of jargon. If a technical term is unavoidable, explain it in plain words.
- **Android versions affected** (only if `jira.fields.androidVersions` is set): infer them from branch and repo names.
  - Examples: `15`, `16`, `android-15-dev`, `a15_release`. `11` or `R` means Android 11.
  - If the change is on branches for several versions, use several values.
  - If it is unclear, use the allowed option that covers all versions.
- **Device types affected** (only if `jira.fields.deviceTypes` is set): pick an option only when branch or repo names point to exactly one allowed option. Otherwise use the allowed option that covers all devices.
- **Parent epic:** the open epic that best matches the app or area. If none fits, leave it empty.
- **Labels:** `jira.syncLabel` plus one app label.
  - Reuse an existing label found in SKILL.md step 3 when one fits, keeping its casing (e.g. `PaymentsApp`, `Website`).
  - Otherwise use a short CamelCase app name.
- **Assignee:** `jira.assigneeAccountId`.
- **Sprint:** the sprint found in SKILL.md step 3.
