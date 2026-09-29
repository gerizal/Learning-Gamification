# Porting PlayClass into the solveeducation monorepo

Decision (owner, 2026-09-28): **finish this prototype first, validate with teachers/students, then port.**
Nothing here is merged as-is: the monorepo is TypeScript / Next.js 16 / Drizzle with one Postgres schema per
module. This prototype is the **reference implementation and spec source**, not code to copy.

Audit date: 2026-09-28 (read-only audit of `/Users/rizal/work-SE/solveeducation`). Re-check file:line refs before use.

## What carries over unchanged
- Product flow, UX, screens and copy (README.md, `static/*` as visual reference, `reviews/*` findings).
- API shapes, state machine and scoring rules (`CONTRACT.md`) → become zod contracts in `packages/contracts`.
- Question content (`db/004`, `db/008`) → import into `solveeducation.content_items` (type `mcq`) via CMS.
- Teacher guide (`docs/TEACHER-GUIDE.md`) and content guide.
- Test scenarios (pytest) → re-expressed as Vitest (PGlite) + Playwright, esp. the concurrency cases.

## Gap table

| Prototype | Monorepo convention | Port action |
|---|---|---|
| Python FastAPI + psycopg | TypeScript only unless an ML-allowlisted import is load-bearing (ADR-0022) | Rewrite logic as module `packages/modules/live-quiz`, routes in `apps/web/app/api/v1/…` |
| Tables in `public` | One schema per module (`pgSchema`), ADR per new module (ADR-0011, MODULAR_MONOLITH R1–R12) | ADR first; schema `live_quiz`; no cross-schema FKs (plain `text` ids + facade assert ports) |
| `bigserial` / `uuid` PKs | `text` PKs via `randomUUID()`; `identity.user.id` is text | All PKs/refs `text`; PIN = unique col w/ partial index on non-ended games |
| `db/00N_*.sql` | Central `packages/db/drizzle/migrations/NNNN_*.sql`, contiguous, schema-qualified, checksummed, `migrate-NNNN.test.ts` | One `NNNN_live_quiz_foundation.sql` |
| Own `users`, `classroom`, `student` | `identity.user` (Better Auth), `authz.org_unit` (school/cohort/class) + scoped role `teacher`; offline-programs participants | Hosts = identity users with `teacher` scope; players = anonymous per-game nicknames (no PII kept) |
| `REPORTS_KEY` (required, no default), host/player tokens (`ADMIN_TOKEN` removed 2026-09-28) | Better Auth session + role checks server-side; A→B ownership tests | Host/admin via session; guest player token OK if in plan + rate-limited, not in query string |
| SSE + LISTEN/NOTIFY | SSE precedent only in `apps/automation` (re-read DB row per tick); no Redis; CSP `connect-src 'self'` | Same-origin SSE route handler polling a `game.version` row; keep polling fallback |
| Vosk STT (removed 2026-09-28: quiz-only MVP) | No server STT; browser Web Speech API + `apps/web/lib/speech.ts` | Out of MVP (owner). Later: reuse existing speaking components |
| Vanilla HTML/JS | Next App Router, `components/ui` (Radix), Playwright evidence in `.evidence/` | Rebuild `/host`, `/play`, `/` as App Router routes |
| Fredoka/Nunito, emoji, gradients, hex | Tokens only (`gate:no-raw-style`), Plus Jakarta Sans + Open Sans, no emoji (`gate:icon-seat`), no gradients | Map to tokens; icons via `components/ui/Icon.tsx`; new colours into `packages/tokens/tokens.json` |
| Hand-rolled EN/BM/ID | next-intl, `messages/{en,ms,id,…}.json`, parity gates | New namespace in message catalogs |
| Own points/leaderboard | XP rules `apps/web/lib/points.ts`; `economy.league` shelved (MONEY fence) | Keep per-game score inside `live_quiz`; do not write `economy.*` |
| Own `question` / `question_pack` | `solveeducation.content_items` (`mcq`, `speaking`), CMS module | Reference content ids; only game config lives in `live_quiz` |
| pytest | Vitest + PGlite, frozen tests, named DB-state concurrency tests | Rewrite; model on `packages/db/src/economy-guard.integration.test.ts` |

## Pipeline to follow in the monorepo
ADR (new module) → `/specify` (EARS criteria, IF/THEN per mutation, state diagram) → `/plan` (zod contracts,
auth matrix, idempotency per mutation, migration plan, feature flag default off, one task per ≤400-line diff,
named concurrency tests) → `/derive-tests` → build → `npm run land` → premerge.

## Things to keep port-friendly while we finish the prototype
- Keep business rules in pure functions (`app/scoring.py`) and the contract in `CONTRACT.md` current.
- Don't add prototype-only concepts (own user accounts, emoji-dependent content) to new features.
- Content: avoid emoji-only picture prompts in quiz questions (monorepo bans emoji in UI copy).
