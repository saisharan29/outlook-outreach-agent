# Deploying the Outlook Outreach Draft Agent — step by step

Two ways to run it. Pick one.

| | A. On the owner's own computer | B. On a small server (phone access from anywhere) |
|---|---|---|
| Needs | Python 3.11+ or Docker, the Agency folder on that machine | Ubuntu server, a domain name, Docker |
| Address | `http://localhost:8080` | `https://outreach.your-domain.com` |
| Files | local folder (`FILE_SOURCE=local`) | OneDrive through Graph (`FILE_SOURCE=onedrive`) or a OneDrive-synced folder on the server |
| Time | 30 minutes | 1 hour |

Both need the same four preparations first (sections 1 to 4).

---

## 1. The Agency folder (the owner, 20 minutes)

Create one folder, anywhere (on the PC, or inside OneDrive so it syncs). Inside it, exactly:

```
Agency/
  Videos/      the preview videos, exported from the Photos app
  Quotes/      the quote PDFs
  Templates/   the email texts and the signature (section 2)
  Registry/    leave empty; the agent writes its database and log here
```

Rename every file to the convention — **this is the one habit that makes the agent reliable**:

```
CompanyName_City_preview_2026-10-02.mp4     → Videos/
CompanyName_City_quote_2026-10-05.pdf       → Quotes/
```

No spaces in the company name (`BoulangerieMartin`, not `Boulangerie Martin`). Accents and
capitals do not matter. The date is the day the file was made; the newest wins.

Shortcut: run `python -m outreach.cli demo` once; it writes a complete sample `Agency/` next to
the code, with README files in each folder. Replace the sample files with the real ones.

## 2. Templates and signature (the owner, 15 minutes)

In `Agency/Templates/`, four text files, first line `Subject:`, blank line, then the body:

| File | What |
|---|---|
| `preview_fr.html`, `preview_de.html`, `preview_lb.html` | the website-preview email in French, German, Luxembourgish (HTML) |
| `quote_fr.html`, `quote_de.html`, `quote_lb.html` | the quote email in the three languages |
| `signature.html` | the signature block (paste the HTML of the Outlook signature, or keep the generated one) |
| `agency.txt` | the agency name, one line (used by `{{agency_name}}`) |

Placeholders you can use: `{{company_name}}` `{{contact_name}}` `{{greeting}}` `{{city}}`
`{{preview_link}}` `{{signature}}` `{{agency_name}}`. `{{greeting}}` becomes "Bonjour Jean
Martin," before 18:00 and "Bonsoir Jean Martin," after, "Bonjour," / "Bonsoir," when no name is known.
Set `CC_RECIPIENTS` in `.env` to the partners who must be in copy of every draft. Keep one opt-out sentence
("Répondez stop pour ne plus recevoir de message") — cold B2B email needs it, and the agent flags
a template that has none. Edit these files any time; the next draft uses the new wording.

## 3. The Microsoft app registration (the developer, 10 minutes, free)

This is what lets the agent create drafts in the owner's Outlook without ever being able to send.

1. Go to https://portal.azure.com (any Microsoft account works) → search **App registrations** →
   **New registration**.
   - Name: `Outreach drafts`
   - Supported account types: **Accounts in any organizational directory (Any Microsoft Entra ID
     tenant - Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)**. This covers both a
     Microsoft 365 business mailbox and a personal Outlook.com mailbox.
   - Redirect URI: platform **Web**, value
     `http://localhost:8080/auth/microsoft/callback` (option A) or
     `https://outreach.your-domain.com/auth/microsoft/callback` (option B). You can add both.
   - Register.
2. **Overview** → copy **Application (client) ID** → this is `MS_CLIENT_ID`.
3. **Certificates & secrets** → **New client secret** → expiry 24 months → Add → copy the
   **Value** column immediately (not "Secret ID"; it is shown once) → this is `MS_CLIENT_SECRET`.
4. **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions** →
   tick exactly: `User.Read`, `Mail.ReadWrite`, `Files.ReadWrite`, `offline_access` → Add.
   **Do not add `Mail.Send`.** No admin consent is needed for these on a personal account; on a
   Microsoft 365 business tenant, the owner accepts them at first sign-in (or an admin grants
   them under *API permissions → Grant admin consent*).
5. Nothing else. The owner signs in with their own account later, from the chat.

## 4. Keys (the owner's accounts, billed to the agency)

| Key | Where | Needed for |
|---|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com → API keys | understanding requests, web research, decision-maker names. Without it the owner types the address in each request (`email: …`). |
| `OPENAI_API_KEY` + `LLM_PROVIDER=openai` | https://platform.openai.com/api-keys | the same, with a ChatGPT API key instead of Claude. |
| `GEMINI_API_KEY` + `LLM_PROVIDER=gemini` | https://aistudio.google.com/apikey (free tier, no card) | the same, with a Google Gemini key. One key of any provider is enough. |
| `GOOGLE_PLACES_API_KEY` | https://console.cloud.google.com → APIs & Services → enable **Places API (New)** → Credentials | phone numbers from the Google Business profile. Optional but recommended. |
| `BRAVE_API_KEY` or `SERPAPI_KEY` | optional | a search API instead of Claude's web search |

Give keys to the developer by a password manager or a one-time secret link, never in chat or email.

---

## A. On the owner's computer

### A0. The short way (recommended: a git clone, so updates arrive by themselves)

```bash
git clone https://github.com/saisharan29/outlook-outreach-agent.git
cd outlook-outreach-agent
./start.sh            # macOS / Linux          (Windows: start.bat)
```

Every later start runs `git pull` first, so the owner always has the latest version without
downloading anything. macOS without git: run `git --version` once, macOS offers to install it.

### A0 bis. The ZIP way

Double-click `start.bat` in the project folder (macOS: open Terminal in the folder and run `./start.sh`). It creates `.env` on the first run and opens it in
Notepad; fill it (A2), run `start.bat` again, and it installs, checks and starts the chat. Steps
A1 to A3 are the same thing by hand.

### A1. Install (once)

Windows: install Python 3.12 from https://www.python.org/downloads/ (tick **Add python.exe to
PATH**) and Git from https://git-scm.com. macOS: `brew install python git`.

```bash
git clone https://github.com/saisharan29/outlook-outreach-agent.git
cd outlook-outreach-agent
pip install -r requirements.txt
```

### A2. Configure

```bash
cp .env.example .env          # Windows: copy .env.example .env
```

Open `.env` in a text editor and set:

```
ANTHROPIC_API_KEY=sk-ant-...
MS_CLIENT_ID=...                           # from step 3
MS_CLIENT_SECRET=...                       # from step 3
MS_REDIRECT_URI=http://localhost:8080/auth/microsoft/callback
FILE_SOURCE=local
AGENCY_ROOT=C:\Users\owner\OneDrive\Agency   # or /Users/owner/OneDrive/Agency — the folder of step 1
APP_PASSWORD=a-password-the-owner-chooses
SECRET_KEY=a-long-random-string            # python -c "import secrets; print(secrets.token_urlsafe(32))"
PUBLIC_URL=http://localhost:8080
GOOGLE_PLACES_API_KEY=...                  # optional
```

### A3. Check, then start

```bash
python -m outreach.cli status             # shows folders, template languages, what is connected
python -m outreach.cli serve              # the chat on http://localhost:8080
```

Open http://localhost:8080 → password → **Connect Outlook** → sign in with the owner's Microsoft
account → accept the four permissions. The header turns green with the account name.

To start it with the computer: Windows → Task Scheduler → *Create Basic Task* → at log on →
program `python`, arguments `-m outreach.cli serve`, start in the `outreach-agent` folder.
macOS → a Login Item or a `launchd` plist running the same command.

To use it from the phone on the same Wi-Fi, set `HOST=0.0.0.0` (the default) and open
`http://<the PC's local IP>:8080`. For access from anywhere, use option B.

---

## B. On a server with HTTPS

### B1. Server and domain

- A small Ubuntu 24.04 server in the EU (1 vCPU, 1 GB RAM is enough; Hetzner CX22, Scaleway
  Stardust, OVH Starter, or Oracle Cloud Always Free).
- A DNS record: `outreach.your-domain.com` → **A** → the server's IP (TTL 600). Wait until
  `ping outreach.your-domain.com` answers from your computer.

### B2. Prepare the server (once)

```bash
ssh ubuntu@<server-ip>
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/saisharan29/outlook-outreach-agent.git
cd outlook-outreach-agent
sudo ./deploy/install-server.sh        # Docker, firewall (22, 80, 443), swap, security updates
```

### B3. Configure

```bash
cp .env.example .env
nano .env
```

Set, in addition to section A2:

```
MS_REDIRECT_URI=https://outreach.your-domain.com/auth/microsoft/callback
PUBLIC_URL=https://outreach.your-domain.com
DOMAIN=outreach.your-domain.com
ACME_EMAIL=owner@your-domain.com          # Let's Encrypt notices
ENVIRONMENT=production
FILE_SOURCE=onedrive
AGENCY_ROOT=Agency                        # the path of the folder INSIDE the owner's OneDrive
```

With `FILE_SOURCE=onedrive` the server reads the Videos and Quotes folders through Microsoft Graph
with the same sign-in as Outlook, so the owner keeps working in their OneDrive folder on the PC and
phone. The registry and log are written in `./Agency/Registry` on the server (a Docker volume
mount); back that folder up.

`ENVIRONMENT=production` refuses to start with the default `SECRET_KEY` or an empty `APP_PASSWORD`.

### B4. Start

```bash
mkdir -p Agency/Registry
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f agent      # Ctrl-C to leave the logs
```

Caddy obtains the certificate within a minute. Open https://outreach.your-domain.com on the phone
→ password → **Connect Outlook** → sign in → accept. Add the page to the phone's home screen.

### B5. Updates and backups

```bash
cd ~/outlook-outreach-agent && git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Backup: copy `Agency/Registry/` (SQLite database, action log, the encrypted Microsoft token)
somewhere else nightly, for example `rsync -a Agency/Registry/ backup-host:outreach-registry/`.
If `SECRET_KEY` ever changes, the stored token becomes unreadable: sign in again.

---

## 5. First run — the acceptance checklist (owner + developer, 1 hour)

In the chat, in this order:

1. `status` → Outlook connected, files counted, templates `['fr', 'en']` for both types.
2. A company already in the registry or with a known address:
   `Preview email for Boulangerie Martin, Lyon, email: contact@boulangerie-martin.fr`
   → open Outlook on the phone: the draft is in Drafts with the video. Do not send it.
3. The same request again → the duplicate warning; answer `no`.
4. A company with no file → "no draft created" and the closest names.
5. A company with only a name → research runs; check the recipient's source link opens and
   shows the address.
6. `Do not contact <company>` then a request for it → refused.
7. Ten companies in one message separated by `;` → one combined report.
8. Prove it cannot send: on the machine running the agent,
   `python scripts/verify_cannot_send.py` → two PASS lines.
9. Edit `Templates/preview_fr.txt`, request a new preview → the new wording is in the draft.

Then the 20-company test set from section 10 of the specification: count how many got a correct
address without help (target 80 %).

## 6. When something goes wrong

| Symptom | Cause / fix |
|---|---|
| "Microsoft refused the sign-in (…AADSTS7000215)" | wrong secret: copy the **Value** of the client secret, not its ID |
| "…AADSTS50011" | the redirect URI in Azure is not exactly `MS_REDIRECT_URI` (scheme, host, path) |
| "Microsoft granted a send permission; refusing to store this token" | `Mail.Send` was added in Azure: remove it, sign in again |
| "Outlook is not connected" | press Connect Outlook; after a `SECRET_KEY` change, sign in again |
| "Template missing: preview_en.txt" | the company's country is not French-speaking and the English file is absent; add it or write "en français" in the request |
| "No signature file" | add `Templates/signature_fr.txt` / `signature_en.txt` |
| "no sharing link could be created" for a big video | export the video under `MAX_ATTACHMENT_MB` (20) or let the Azure app keep `Files.ReadWrite` so a link can be made |
| Every company "not identified" | no `ANTHROPIC_API_KEY` or search key: give `site: …` or `email: …` in the request |
| Drafts invisible on the phone | they are in the **Drafts** folder of the account that was connected; check `status` for the account name |
| Certificate not issued (option B) | the DNS record does not point to the server yet, or port 80/443 is closed |
