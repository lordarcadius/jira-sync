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

**Check the total.** `fetch` prints the working hours before these changes, and their SP equivalent. It is the sum of the per-change gaps, so it leaves out evenings and weekends. Keep the total SP of all tickets close to it.

- If the total is clearly higher (for example, much of the work was done after hours) or clearly lower, keep it only when you can explain why in one line in the preview.
- Otherwise, scale the estimates towards the working hours.

## Fields

- **Issue type:** `Bug` if the work fixes broken behaviour, otherwise `Task`.
- **Summary:** at most 70 characters, written as "Writing style" below says. No code, class or file names.
- **Description:** markdown, in this shape, written as "Writing style" below says:

  ```
  **What was done**
  - 1–4 bullets, one concrete change each

  **Why it matters**
  - one bullet, only when the reason is not already clear from the title and bullets

  ---
  Repo: <repo> · Branch: <branches>
  Commits: [abc1234](https://github.com/<owner>/<repo>/commit/<full sha>), ...
  ```

  Leave out the "Why it matters" section when it would only restate the bullets.
- **Extra required fields** (found in SKILL.md step 3): give each one a value for every ticket.
  - **Fields with allowed values:** choose the value or values that fit the change, reading branch, repo and file names.
    - For example, a version field can often be read from branch names like `15`, `android-15-dev` or `a15_release`, where `11` or `R` means version 11.
    - A field that allows several values gets several when the change is on branches for several versions or products.
    - Pick a specific option only when the names clearly point to it.
  - **When nothing fits clearly, fall back in this order:**
    1. The value stored for that field id in `jira.fieldDefaults`.
    2. The allowed option that means "all", "common", "general" or "not applicable", if there is one.
    3. Otherwise, ask the user once. Then save the answer in `jira.fieldDefaults` (keyed by field id, in the API shape below), so it is not asked again.
  - **Fields without allowed values** (text, number, date): use `jira.fieldDefaults`, or ask the user once and save the answer the same way.
  - **API shape:** shape each value by the field's `schema`.
    - `array` of options: `[{"value": "..."}]`
    - single option: `{"value": "..."}`
    - `string`, `number` or `date`: the plain value
- **Parent epic:** the open epic that best matches the app or area. If none fits, leave it empty.
- **Labels:** `jira.syncLabel` plus one app label.
  - Reuse an existing label found in SKILL.md step 3 when one fits, keeping its casing (e.g. `PaymentsApp`, `Website`).
  - Otherwise use a short CamelCase app name.
- **Assignee:** `jira.assigneeAccountId`.
- **Sprint:** the sprint found in SKILL.md step 3.

## Writing style

Write every ticket the way a teammate would in a minute: plain, specific and short. Someone who doesn't code should still understand what changed.

**Titles**

- **Start with a verb** that says what happened: Add, Fix, Show, Remove, Move, Let, Stop, Send.
  - If the team's recent tickets (SKILL.md step 3) clearly follow another style, match it: length, wording, capitals.
- **Name what users see:** the screen, button, report or message.
- **One outcome per title.** No list titles such as "X: A, B and C". An area prefix such as "Checkout: …" is fine when the team writes titles that way. If the ticket covers several things, title the main one and let the bullets carry the rest.
- **Format:** sentence case, no full stop, no quotes, no emoji.

**Bullets**

- **One fact per bullet,** in about 15 words or fewer. Say what changed, where, and for whom.
- **Be specific:** "Search box on lists longer than 10 items" beats "Improved dropdown usability".
- **Don't repeat the title** as the first bullet.
- **Use the team's own names** for apps and features, without explaining them in brackets.
- **Explain a technical term** in a few plain words only when someone who doesn't code would need it to follow the bullet.
- **Small work gets fewer bullets.** A 0.25 SP fix usually needs one or two.

**Cut anything that sounds generated**

- **Words to avoid:**
  - enhance, robust, seamless, streamline, leverage, comprehensive, ensure, utilize
  - various, overall, significantly, effortlessly, intuitive, powerful
  - user experience, functionality
  - improve, unless you say how
- **Tone and formatting:** no marketing tone, no exclamation marks, no em dashes, and no bold or emoji inside bullets.
- **No vague benefits** such as "better experience" or "easier to use". Say the concrete effect, or drop it.
- **No filler openers** such as "This ticket…" or "Implemented…" when a plain verb works.
- **Last pass:** if a sentence could appear on any ticket, delete it.

**Example**

Instead of:

```
Checkout page: smarter payment selection, faster flow and improved UX
- Implemented robust logic to seamlessly remember the user's preferred payment method
- Why it matters: enhances the overall checkout experience
```

write:

```
Remember the last payment method at checkout
- Checkout pre-selects the card or wallet the customer used last time
- Customers can still pick another method with one tap
```

## Changes with secrets

A change has `secrets` when its files look like they hold passwords, tokens or keys. The fetch file lists the file and the kind of secret, never the value.

- Ticket the change like any other, but describe it in general terms, for example "Build settings are now included in the app".
- Never put secret values, the contents of those files, or the words that reveal them into a ticket.
- List the files in the preview's secrets block (SKILL.md step 5).
