# 📜 Third-Party Attributions

This project was inspired by and derives ideas from the following
open-source works. Each source is attributed here as required by its
licence. Individual licence texts live in the files alongside this
document.

> ⚠️ **Non-commercial notice** — `academic-research-skills` is licensed
> under **CC BY-NC 4.0** (non-commercial). Any portion of this project
> that incorporates ideas from that source inherits that restriction for
> that portion. See [`academic-research-skills.LICENSE`](academic-research-skills.LICENSE).

---

## 1. agency-agents

| Field | Value |
|---|---|
| Project | The Agency: AI Specialists Ready to Transform Your Workflow |
| Author / Copyright | AgentLand Contributors |
| Year | 2025 |
| Repository | <https://github.com/msitarzewski/agency-agents> |
| Licence | MIT — see [`agency-agents.LICENSE`](agency-agents.LICENSE) |

**What was derived:**  
Structural patterns for multi-role agent definitions (specialist
roles, deliverable descriptions, process checklists) informed the
shape of vendor entry-point files (`CLAUDE.md`, `GEMINI.md`,
`CONVENTIONS.md`) and the role-persona conventions in
`.agents/skills/collaboration/`.

---

## 2. skills (mattpocock/skills)

| Field | Value |
|---|---|
| Project | skills — AI skills / prompt library |
| Author / Copyright | Matt Pocock |
| Year | 2026 |
| Repository | <https://github.com/mattpocock/skills> |
| Licence | MIT — see [`skills.LICENSE`](skills.LICENSE) |

**What was derived:**  
Skill-file format conventions (name, when-to-use, procedure,
anti-patterns) and several documentation-discipline skill concepts
were informed by this library. Skills influenced:
`.agents/skills/coding/`, `.agents/skills/documentation/`,
`.agents/skills/review/`.

---

## 3. superpowers (obra/superpowers)

| Field | Value |
|---|---|
| Project | Superpowers — software development methodology for coding agents |
| Author / Copyright | Jesse Vincent |
| Year | 2025 |
| Repository | <https://github.com/obra/superpowers> |
| Licence | MIT — see [`superpowers.LICENSE`](superpowers.LICENSE) |

**What was derived:**  
The composable-skills methodology and the idea of a master rulebook
that vendor entry points delegate to were directly inspired by this
project. Core influence on: `AGENTS.md`, `xops/agent/safe-run.sh`
recovery protocol, `xops/agent/session-bootstrap.sh`, and the
majority of skills under `.agents/skills/reliability/`,
`.agents/skills/planning/`, and `.agents/skills/tooling/`.

---

## 4. academic-research-skills (Imbad0202/academic-research-skills)

| Field | Value |
|---|---|
| Project | Academic Research Skills for Claude Code |
| Author / Copyright | Cheng-I Wu |
| Year | 2026 |
| Repository | <https://github.com/Imbad0202/academic-research-skills> |
| Licence | **CC BY-NC 4.0** — see [`academic-research-skills.LICENSE`](academic-research-skills.LICENSE) |

**What was derived:**  
Structured research and verification workflow patterns (cite-before-
claim, evidence hierarchy, systematic literature review steps)
informed `.agents/skills/verification-before-completion/SKILL.md`
and `.agents/skills/systematic-debugging/SKILL.md`.

**Non-commercial restriction:** this source is licensed
**Attribution-NonCommercial 4.0 International**. Any portion of this
project that directly reproduces or adapts content from this source
may only be used for **non-commercial** purposes. If you intend to
use this project commercially, ensure the portions derived from this
source are independently rewritten.

---

## Compliance summary

| Source | Licence | Commercial use | Modifications |
|---|---|---|---|
| agency-agents | MIT | ✅ | Keep copyright notice |
| skills | MIT | ✅ | Keep copyright notice |
| superpowers | MIT | ✅ | Keep copyright notice |
| academic-research-skills | CC BY-NC 4.0 | ❌ Non-commercial only | Indicate modifications; retain attribution |
