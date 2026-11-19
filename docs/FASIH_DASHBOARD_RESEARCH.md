# Fasih research brief — final operator dashboard (12 Nov 2026)

Hamza’s ask: the current `cim dashboard` is a local demo board and is not the final product. Fasih owns the **research** below (written recommendation). Do **not** implement a new UI or auto-quarantine until Hamza says so. MCP code stays Hamza; skills code stays Fasih; shared UI contracts are joint.

Paste into Claude: *You are assisting Fasih on CIM. Read `docs/FASIH_DASHBOARD_RESEARCH.md`, then `CONTEXT.md`, `DECISIONS.md`, `PROJECT_STATUS.md`, and `docs/FASIH_REVIEW.md`. Produce research notes only. Do not invent new FYP phases. Do not write MCP proxy/gateway code.*

---

## Tasks (Roma)

| Roma | Title |
|------|--------|
| Fasih: research final dashboard form (web app vs website) | Form factor for the final operator surface |
| Fasih: dashboard sections + what each shows (final product) | Information architecture for the final product |
| Fasih: research auto-disconnect for skills + MCP | Observe-only now; disconnect/quarantine design for FYP II |

---

## 1. Form factor — web app vs website vs local board

Decide what we should ship as the **operator surface**:

| Option | Meaning |
|--------|---------|
| Local board (today) | `uv run cim dashboard --db …` — fine for lab / Dec walkthrough, not a product |
| Web app | Authenticated app that talks to CIM store/API; multi-session; real operator workflow |
| Website | Marketing / project story / docs; not the live monitor |
| Split | Website for story + web app for live monitoring |

**Deliverable:** recommendation + pros/cons for FYP I (~1 Dec demo) vs FYP II; what Hamza must expose (read API, live updates, auth); what Fasih owns on the skills side of that UI.

Constraint from ADR-003: FYP I prioritises functional SEE path; product polish can land in FYP II — say explicitly what must exist for Dec C1–C6 vs what waits.

---

## 2. Sections — what each shows in detail (final product)

Propose the **final** dashboard sections. For each section, specify:

- Purpose (one sentence)
- Data source (store kinds, MCP vs skills, chain verify)
- Update behaviour (poll / push / on alert)
- Empty, learning, healthy, warning, disconnected states
- Operator actions allowed from that section

Minimum to cover:

1. Live integrity / hash-chain status  
2. MCP servers and tools in view  
3. Skills activity (Fasih path)  
4. Behaviour / drift warnings (MCP + skills)  
5. Schema / rug-pull changes  
6. Last call / evidence drawer  
7. Operator actions (clear, reconnect, export, verify-chain)  
8. Anything else required for Dec C1–C6 or a credible FYP II product  

Call out MCP-only vs skills-only vs shared.

---

## 3. Auto-disconnect of skills and MCP

FYP I is **observe-only** (alerts, no block). FYP II has **T-29 Automatic quarantine / refusal (March)**. Research the contract now so the dashboard and both paths agree later.

Answer:

- Triggers (alert codes, severity, repeats, human confirm?)
- Soft vs hard: warn, pause tool, drop session, quarantine server/skill
- Who reconnects and how that is logged on the hash chain
- How the UI shows learning / healthy / warning / disconnected
- What stays out of FYP I vs what T-29 implements

**Deliverable:** short design note + proposed state machine + UI copy per state. No HexStrike attack API and no auto-quarantine code until Hamza says implement.

---

## Pointers in this repo

| Path | Why |
|------|-----|
| `src/cim/dashboard/` | Current local board (demo + operator redesign) |
| `docs/setup/cursor-playwright-cim.md` | Stdio live T-16 path |
| `docs/setup/cursor-http-mcp-gateway.md` | HTTP path + OAuth token note |
| `progress/milestones/dec-demo-2026.md` | C1–C6 expectations |
| `docs/decisions/ADR-003-fyp1-dec-scope.md` | FYP I vs polish |

---

## Out of scope for this research

- Implementing a new frontend stack
- Changing MCP proxy / HTTP gateway behaviour
- Enabling auto-quarantine in the lab
- Inventing new graded phases beyond ADR-003 / existing T-numbers
