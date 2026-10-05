# Outlook Outreach Draft Agent

One chat message with a company name in, one ready-to-review Outlook draft out. The agent finds the
contact details, checks the phone number for WhatsApp, picks the right preview video or quote PDF
from the owner's folders, fills the owner's template and creates the draft in Outlook. **It never
sends:** the Microsoft permission to send is not requested, the client blocks every send endpoint,
and there is no send tool.

Built from the technical specification of 5 October 2026 (sections 1 to 12). Deployment steps: [DEPLOY.md](DEPLOY.md). Every functional
requirement FR-01 to FR-28 and every guardrail of section 8 is implemented and covered by a test.

| | |
|---|---|
| Run it in 2 minutes, no account needed | [Demo mode](#demo-mode-no-keys-no-account) |
| What the owner must provide | [Inputs from the owner](#what-the-owner-provides-spec-section-12) |
| Microsoft setup (Azure, 10 minutes) | [Connecting Outlook](#connecting-outlook-microsoft-sign-in) |
| How it decides things | [Design](#design) · [Guardrails](#guardrails-spec-section-8) |
| Acceptance criteria | [Mapping](#acceptance-criteria-spec-section-10) |

## Demo mode (no keys, no account)

```bash
git clone https://github.com/saisharan29/outlook-outreach-agent.git
cd outlook-outreach-agent
pip install -r requirements.txt
python -m outreach.cli demo                     # writes ./Agency with templates, sample files, 2 companies
DEMO=1 python -m outreach.cli "Preview email for Boulangerie Martin, Lyon"
DEMO=1 python -m outreach.cli "Devis pour Garage Dupont; Boulangerie Martin, Lyon; Fleuriste Rose, Nantes"
DEMO=1 python -m outreach.cli serve             # the chat on http://localhost:8080 (password: APP_PASSWORD, empty = none)
python -m pytest tests -q                       # 81 tests
```

In demo mode drafts are written to `Agency/Registry/demo_drafts.json` instead of Outlook, and
the two sample companies already have contact details in the registry, so the whole flow runs
offline. Everything else (file matching, templates, duplicate warning, do-not-contact, batch,
log) is the real code.

## Real setup

```bash
cp .env.example .env            # fill ANTHROPIC_API_KEY, MS_CLIENT_ID, MS_CLIENT_SECRET, APP_PASSWORD, SECRET_KEY
docker compose up -d --build    # or: python -m outreach.cli serve
```

Open the chat, sign in with the password, press **Connect Outlook**, accept the Microsoft
permissions once. Point `AGENCY_ROOT` at the owner's folder (see [Folders](#folders-and-file-naming-spec-section-7)).

### Connecting Outlook (Microsoft sign-in)

1. https://portal.azure.com → *App registrations* → *New registration*. Name: "Outreach drafts".
   Supported account types: *Accounts in any organizational directory and personal Microsoft
   accounts* (this covers a Microsoft 365 business mailbox **and** a personal Outlook.com mailbox,
   which answers the first open question of section 12; `MS_TENANT=common`).
   Redirect URI (Web): `http://localhost:8080/auth/microsoft/callback` (or the public address).
2. *Certificates & secrets* → new client secret → copy the **Value** into `MS_CLIENT_SECRET`.
   *Overview* → Application (client) ID into `MS_CLIENT_ID`.
3. *API permissions* → Microsoft Graph → Delegated: `User.Read`, `Mail.ReadWrite`, `Files.ReadWrite`,
   `offline_access`. **Do not add `Mail.Send`.** The agent requests exactly these scopes
   (`outreach/outlook/auth.py`) and refuses to store a token that carries a send permission.
4. In the chat: **Connect Outlook**. The token is stored encrypted in `Agency/Registry/microsoft_token.enc`
   (key derived from `SECRET_KEY`). The owner revokes access at any time at
   https://account.microsoft.com/privacy/app-access (personal) or https://myapps.microsoft.com (business).
5. Prove it cannot send: `python scripts/verify_cannot_send.py` (attempts a send on purpose and
   expects Microsoft to refuse it).

`Files.ReadWrite` rather than `Files.Read` is needed for one thing only: creating a view-only
sharing link when a preview video is above `MAX_ATTACHMENT_MB`. Set `FILE_SOURCE=onedrive` to
read the folders through Graph; keep `local` when the folder is on the machine (or synced by the
OneDrive client, in which case sharing links still work through Graph).

### Research keys (phase 2)

| Variable | Role | Needed? |
|---|---|---|
| `ANTHROPIC_API_KEY` | Understands free-text requests in FR/EN; web search for company identification and directories when no search API is set; names the decision-maker from page excerpts | Recommended. Without it: regex request parser, owner types the address (`email: …`) |
| `SEARCH_PROVIDER` + `BRAVE_API_KEY` / `SERPAPI_KEY` | A search API instead of Claude's web search | Optional |
| `GOOGLE_PLACES_API_KEY` | Google Business profile: the reliable phone number source | Optional, recommended |
| `WHATSAPP_VALIDATOR_URL` / `_KEY` | Section 6 option A (third-party check) | Optional; B + C are built in |

Model: `claude-opus-5-5` with the server-side refusal fallback enabled (`fallbacks: "default"`);
the call falls back to the plain endpoint on platforms that reject the parameter.

## What the owner provides (spec section 12)

Phase 1 cannot start without the first four:

- [ ] **The two email texts in each language** → `Agency/Templates/preview_fr.txt`, `preview_en.txt`,
      `quote_fr.txt`, `quote_en.txt`. Format: first line `Subject: …`, blank line, body.
      Placeholders: `{{company_name}} {{contact_name}} {{greeting}} {{city}} {{preview_link}} {{signature}} {{agency_name}}`.
      `python -m outreach.cli demo` writes working examples to start from.
- [ ] **The signature** → `Agency/Templates/signature_fr.txt` and `signature_en.txt` (or one `signature.txt`).
- [ ] **Access to the Outlook account** → press *Connect Outlook* once (needs the Azure app above).
- [ ] **The Videos and Quotes folders**, files renamed to the convention below. The videos in the
      Photos app must be exported or synced into `Agency/Videos`; the agent cannot read Photos.
- [ ] A list of 20 real companies for the acceptance test.
- [ ] Companies that must never be contacted: tell the chat `Do not contact <company>`.

Open questions of section 12, with the choice made here (change in `.env`):

| Question | Answer in this build |
|---|---|
| Microsoft 365 or personal Outlook.com? | Both work (`MS_TENANT=common`). Ask the owner which, only to set the Azure account type. |
| Where do files live? | Local/synced folder by default; OneDrive through Graph with `FILE_SOURCE=onedrive`. |
| Which countries? | `DEFAULT_COUNTRY=FR`, language French for FR/BE/CH/LU/MC, English otherwise; override per request ("in English"). |
| WhatsApp option? | B + C shipped (wa.me link + mobile/landline hint, reported as *unverified*). Option A plugs in via `WHATSAPP_VALIDATOR_URL`. |
| Companies per week? | Sizes the Claude/search spend only; one request runs 4 to 8 model calls at most. |
| WhatsApp message text? | Not built (out of scope v1); the report already carries the one-tap link. |

## Folders and file naming (spec section 7)

```
Agency/
  Videos/      BoulangerieMartin_Lyon_preview_2026-10-02.mp4
  Quotes/      BoulangerieMartin_Lyon_quote_2026-10-05.pdf
  Templates/   preview_fr.txt preview_en.txt quote_fr.txt quote_en.txt signature_fr.txt signature_en.txt agency.txt
  Registry/    registry.sqlite (companies + action log) · registry.csv / actions.csv (export) · microsoft_token.enc
```

`CompanyName_City_type_YYYY-MM-DD.ext`. Matching ignores accents, capitals, spacing and
punctuation; the newest date wins and the report says which version was picked; the city separates
two companies with the same name; two different companies that could match stop the agent with a
question. A file that does not follow the convention is never considered.

## Using the chat

```
Preview email for Boulangerie Martin, Lyon
Quote email for Garage Dupont
Devis pour Garage Dupont; Boulangerie Martin, Lyon; Fleuriste Rose, Nantes        (batch)
Preview email for Café Léon, Lyon, email: leon@cafeleon.fr                        (address given by hand)
Preview email for Boulangerie Martin, Lyon, site: boulangerie-martin.fr, in English
Do not contact Garage Dupont
status · help
```

The agent asks instead of guessing: which company (several match), which file (two companies could
match), confirm (an email of the same type already exists), preview or quote (type missing). Reply
with the number, *yes*/*no*, or *preview*/*quote*.

Each report shows, per company: recipient with confidence and source URL, contact name and role,
phone in international format with WhatsApp status and `wa.me` link, file attached (or sharing link
inserted), draft status with the Outlook link, sources checked, and a **Needs your attention**
list. Every action is logged (date, company, type, recipient, file, result): `status` in the chat,
`GET /api/log`, or `python -m outreach.cli export`.

## Design

```
chat (FastAPI, one HTML page, phone-friendly)
   │  message
   ▼
intent parser  ── Claude structured output (FR/EN), regex fallback; an address must appear in the owner's text
   │  CompanyRequest(s)
   ▼
pipeline (rules, spec order)        tools (strict, the only actions that exist)
   1 identify ───────────────────▶  identify_company   registry → Places / search / Claude web search
   2 contacts ───────────────────▶  find_contacts      own site (contact, footer, legal) → Places → directories
   3 whatsapp ───────────────────▶  check_whatsapp     wa.me + heuristic (+ optional validator)
   4 file ───────────────────────▶  find_file          naming convention, latest version, ambiguity → ask
   5 draft ──────────────────────▶  create_draft       template → placeholders → Graph draft → attachment
   6 report                          registry_read / registry_write
```

- **Rules decide, the model proposes.** `AGENT_MODE=pipeline` (default) runs the six steps in the
  spec's order; Claude is used only where language matters (parsing, identification, naming the
  decision-maker). `AGENT_MODE=agent` lets Claude drive the same tools itself (section 6's
  tool-calling agent). Both share the tools, so both share the guardrails.
- **No address is ever invented.** Every email the agent uses was read by the agent itself from a
  page it fetched (source URL and date kept), or typed by the owner. The model may suggest *where*
  to look, never *what* the address is. A pattern guess cannot reach `create_draft`: the tool
  refuses any recipient without a source.
- **Confidence** (FR-11): high = the company's own site; medium = a directory; low = an address
  whose domain is neither the site's nor confirmed. Low → "VERIFY RECIPIENT" in the report.
- **Email validation** (FR-12): syntax, junk filter (noreply, image names, placeholders), MX lookup
  with A/AAAA fallback; a domain that cannot receive mail is dropped and reported.
- **Registry** (section 7): SQLite in the owner's folder, one row per company with aliases, city,
  website, contact, email/phone with source and date, WhatsApp status, preview/quote dates and
  files, do-not-contact. Details older than `REGISTRY_MAX_AGE_DAYS` (90) are re-researched.
- **Attachments**: under 3 MB direct, above through a Graph upload session; a preview video above
  `MAX_ATTACHMENT_MB` (20) is replaced by a view-only sharing link and the report says so. If no
  link can be made, no draft is created (never a "see attached" email without the video).
- **A draft exists only when Graph confirmed it**; if the attachment then fails, the half-draft is
  deleted and the failure reported.
- **Web content is data.** Page text reaches the model only inside tagged excerpts with an
  instruction to treat it as data, and nothing the model says about it is used without the agent's
  own fetch confirming it.

### Guardrails (spec section 8)

| Situation | Behaviour | Test |
|---|---|---|
| Several companies match | lists candidates with city and website, asks | `test_ambiguous_company_asks_then_proceeds` |
| No email found | no draft; phone and sources reported | `test_no_email_found_means_no_draft_with_sources` |
| Low-confidence email | draft created, flagged "VERIFY RECIPIENT" | `test_low_confidence_recipient_is_flagged` |
| Domain cannot receive mail | address not used, reported | `test_dead_domain_excluded_from_best`, `test_check_email_uses_mx` |
| No matching file | no draft; closest names listed | `test_missing_file_means_no_draft_and_a_clear_message` |
| Several files could match | asks; never picks between companies | `test_ambiguous_files_never_picked` |
| Video above size limit | sharing link, or refusal when no link is possible | `test_large_video_links_or_refuses` |
| Same type already drafted or sent | warns, asks for confirmation; same type only | `test_duplicate_warns_then_creates_on_confirmation` |
| Do not contact | refuses with the reason | `test_do_not_contact_is_refused` |
| Outlook unavailable | failure reported; never "draft created" | `test_outlook_down_is_reported_not_claimed`, `test_attachment_failure_removes_the_draft` |
| One company fails in a batch | others continue; failure in the report | `test_batch_continues_after_failure_and_returns_one_report` |
| File of another company | refused by the tool itself | `test_file_of_another_company_is_refused` |
| Invented recipient | refused by the tool itself | `test_recipient_without_source_is_refused` |
| Unfilled placeholder | refused | `test_unfilled_placeholder_blocks_the_draft` |
| Cannot send | no scope, blocked endpoints, no tool, live probe | `test_send_endpoints_are_blocked_client_side`, `test_scopes_have_no_send_permission`, `scripts/verify_cannot_send.py` |

## Acceptance criteria (spec section 10)

| Criterion | How it is met / verified |
|---|---|
| Preview request → correct recipient, template, video | pipeline + `test_preview_request_creates_a_correct_draft`; live on the 20-company set |
| Quote request → correct recipient, template, PDF | `test_quote_request_uses_pdf_and_quote_template` |
| Zero files attached for the wrong company | enforced in `create_draft`; `test_file_of_another_company_is_refused` |
| Zero invented addresses; every address has a source link | enforced in `create_draft`; crawler keeps the source URL of every value |
| ≥ 80 % of companies get a correct email without help | measured on the owner's 20 companies (phase 2); research order per FR-07 |
| Every phone in international format with WhatsApp status | `phonenumbers` E.164; status yes/no/unverified + wa.me |
| Ambiguous names produce a question | `test_ambiguous_company_asks_then_proceeds` |
| Missing file → clear message, no draft | `test_missing_file_means_no_draft_and_a_clear_message` |
| Second request → duplicate warning | `test_duplicate_warns_then_creates_on_confirmation` |
| Batch of 10 completes with one report | `test_batch_continues_after_failure_and_returns_one_report` (3 companies; the loop is per company) |
| Agent cannot send, verified by attempting | `python scripts/verify_cannot_send.py` against the live account |
| Owner edits a template, next draft uses it | templates are read from disk on every draft; `test_owner_edits_template_and_next_draft_uses_it` |
| Drafts visible on the phone | Graph `POST /me/messages` creates a server-side draft, synced to every Outlook client |
| Single request under 2 minutes | bounded fetches (home + up to 6 pages + 1 Places call + directory pages), one model call per step |

## Delivery phases (spec section 11)

| Phase | Status in this build |
|---|---|
| 1. Core draft pipeline | Done: sign-in, folder access (local/OneDrive), file matching, templates, draft + attachment, details by hand (`email: …`). |
| 2. Research | Done in code: identification, email/phone with sources and confidence, MX validation, WhatsApp status, report. Needs keys and the live run on 20 companies to tune. |
| 3. Scale and safety | Done: registry, action log, duplicate warning, do-not-contact, batch, large-video fallback. |

## Commands

```bash
python -m outreach.cli "Quote email for Garage Dupont"   # one request from the terminal (answers questions interactively)
python -m outreach.cli status                             # connection state, folders, last actions
python -m outreach.cli export                             # registry.csv + actions.csv
python -m outreach.cli verify-cannot-send                 # the "cannot send" probe
python -m outreach.cli serve                              # the web chat
python -m pytest tests -q
```

API: `POST /api/login` · `POST /api/chat {message}` · `GET /api/status` · `GET /api/log` ·
`GET /api/registry` · `POST /api/registry/export` · `GET /auth/microsoft` · `POST /auth/microsoft/disconnect`.

## Security and privacy (spec section 9)

Microsoft OAuth with the owner's account; secrets only in `.env` and the encrypted token file;
scopes without send; endpoints blocked client-side; one password for the chat with a signed
cookie; only business contact details from public sources are stored, each with its source, in the
owner's own folder; the opt-out sentence is part of the templates and a missing one is flagged in
the report; `Do not contact X` honours an opt-out permanently.

## Out of scope (v1)

Sending, WhatsApp messaging, follow-up sequences, generating quotes or videos, reading incoming
mail, CRM features.
