# Handover — Outlook Outreach Draft Agent

For the developer taking over this project. Read this first, then README.md (how it works) and
DEPLOY.md (how to run it for the owner). Everything here was true on 5 October 2026.

## What this is

A chat agent for the owner of a web agency. One message ("Preview email for Boulangerie Martin,
Lyon") becomes a ready-to-review draft in his Outlook, with the right contact, the right template
and the right video or quote PDF attached. It never sends. Built from the specification
*Outlook Outreach Draft Agent — Technical Specification* (12 pages, 5 Oct 2026).

## State of the work

| Area | State | Evidence |
|---|---|---|
| Spec FR-01 to FR-28, guardrails of section 8, tool list of section 6 | Implemented | `tests/` (88 tests), README "Guardrails" table maps each rule to its test |
| Chat interface, phone-friendly | Done | `outreach/web/static/index.html`, screenshots in the repo history |
| Microsoft sign-in, drafts, attachments, OneDrive | Implemented against the public Graph documentation and tested on a stubbed HTTP layer | `outreach/outlook/`, `tests/test_graph.py` |
| **Live run against a real Outlook account** | **Done once by the developer with a personal account; not yet with the owner's account** | do step 1 of "First week" below |
| Web research (identification, emails, phones) | Implemented; needs an Anthropic key and ideally a Google Places key; not yet measured on real companies | `outreach/research/`, `scripts/acceptance.py` |
| The acceptance test of section 10 (20 companies, 80 % correct emails) | **Not run yet**: the owner has not supplied the list | `scripts/acceptance.py` |
| Owner's real templates, signature, videos, quotes | **Not supplied yet**; samples from `python -m outreach.cli demo` are in place | `Agency/Templates` |
| Deployment | Option A (owner's PC) documented and scripted (`start.ps1`); option B (server + HTTPS) documented with `docker-compose.prod.yml`; neither applied at the owner yet | DEPLOY.md |

Honest summary: the product is complete in code and the demo flow works end to end offline. What
remains is validation with real data and real accounts, which only the owner can enable.

## Still to build or decide

Nothing in the v1 scope is missing. Items below are improvements worth doing after the live run,
roughly in order of value:

1. **Tune research on real companies.** After the acceptance run, the misses will show which
   source matters most (own site vs Google Places vs directories). Add the directories the owner's
   market uses (`DIRECTORY_DOMAINS` in `outreach/research/identify.py`).
2. **Decision-maker names.** Today a name is attached only when a role word sits next to it on the
   page, or when Claude confirms it from an excerpt. LinkedIn is deliberately not scraped.
3. **WhatsApp option A.** If the owner finds the manual tap too slow, plug a validator into
   `WHATSAPP_VALIDATOR_URL` (`outreach/contacts/whatsapp.py` already reads a generic JSON answer).
4. **Multi-user.** Sessions are in memory, one password. If two people use it, move sessions to the
   SQLite database and add users.
5. **WhatsApp message text** (open question of section 12): a third template type, same pipeline.
6. **Follow-ups and sending** are out of scope by design; the no-send guarantee is a feature.

## How to give the project to someone

1. **Code.** GitHub → `outlook-outreach-agent` → Settings → Collaborators → add their GitHub
   account (or Settings → General → Transfer ownership to hand it over completely).
2. **Secrets, never through git or chat.** Send the `.env` values through a password manager or a
   one-time link: `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `ANTHROPIC_API_KEY`, `APP_PASSWORD`,
   `SECRET_KEY`. Rotate anything that was ever pasted in a chat or a screenshot.
3. **Azure app registration.** Either add them as owner (portal.azure.com → App registrations →
   Outreach drafts → Owners → Add) or let them create their own registration in 10 minutes
   (DEPLOY.md step 3) and put the new ID and secret in `.env`.
4. **Microsoft token.** `Agency/Registry/microsoft_token.enc` is bound to `SECRET_KEY`; a new
   machine simply signs in again from the app.
5. **Data.** `Agency/` belongs to the owner (videos, quotes, templates, registry, log). Nothing of
   it is in git.

## First week for the new developer

1. Run the demo: `python -m outreach.cli demo`, `DEMO=1 python -m outreach.cli serve`, try the
   five example requests in the chat. Read a report card.
2. Run the tests: `python -m pytest tests -q`. CI runs them on every push (`.github/workflows`).
3. Connect a real Outlook (yours), create one draft to yourself, check it on the phone, run
   `python scripts/verify_cannot_send.py` and keep the output.
4. Get from the owner: templates (both languages), signature, the Agency folder with renamed
   files, the 20 companies, the do-not-contact list, the Anthropic key, and the answer to
   "Microsoft 365 or Outlook.com?".
5. Run `python scripts/acceptance.py companies.csv --out results.csv`. Fix the misses. Repeat until
   16/20 or better.
6. Deploy per DEPLOY.md option A on the owner's PC (`start.ps1`), or option B.

## Map of the code

```
outreach/
  config.py            settings from .env; every "configurable" value of the spec
  naming.py            file naming convention, tolerant matching, latest version, ambiguity
  templates.py         template files, placeholders, language choice
  registry.py          SQLite: companies (with sources and dates) and the action log
  contacts/            phone (E.164, mobile/landline), email validation (syntax + MX), WhatsApp
  research/            crawler (own site), search providers, Places, identification and contacts
  outlook/             Microsoft OAuth (no send scope), Graph client (send endpoints blocked)
  files/               local folder or OneDrive, one interface
  llm.py               the only module that talks to Claude
  agent/
    tools.py           the six tools of the spec with every guardrail enforced inside
    pipeline.py        the request pipeline in the spec's order (default mode)
    loop.py            Claude driving the same tools (AGENT_MODE=agent)
    intent.py          FR/EN request parsing, answers to pending questions
    report.py          the chat report and its JSON form
    demo.py            a stand-in for Graph so everything runs offline
  web/                 FastAPI app + one HTML page
tests/                 88 tests, no network, no keys
scripts/               verify_cannot_send.py, acceptance.py
```

Design rule that must survive any change: **a recipient must have a source, a file must belong
to the company, a draft exists only when Graph confirmed it, and there is no send tool.** These are
enforced in `agent/tools.py`, not in prompts. Keep them there.

## Known limitations

- Graph `$search` on Drafts/Sent is used for the duplicate check; on some mailboxes search indexing
  lags a few minutes. The registry is the primary duplicate signal and does not lag.
- Personal Microsoft accounts cannot scope file access to one folder; the token can read the whole
  OneDrive. Business tenants can use `Files.SelectedOperations.Selected` if that matters.
- The agent cannot read the Photos app; videos must be exported to the Videos folder.
- A multitenant Azure app without a verified publisher cannot be consented by a plain user of a
  *business* tenant: an admin of that tenant accepts once, or register the app inside that tenant.
