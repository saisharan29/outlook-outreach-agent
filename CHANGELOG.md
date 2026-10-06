# Changelog

## 1.4.0 — 2026-10-06
- Identification without any search key: the obvious domains (.lu, .com, .eu…) are tried and one is kept only when the page names the company.
- The owner's rules: Luxembourg as default country (mobiles 621/661/691), fixed CC recipients on every draft, "Bonjour"/"Bonsoir" by time of day, loud warning when no phone or no mobile is found.
- HTML emails: `.html` templates and an HTML signature block (Webalix); values escaped, signature kept as HTML.
- Languages: French, German, Luxembourgish (`SUPPORTED_LANGUAGES`); the owner's real preview email as the French template, with German and Luxembourgish translations to proofread; a request in an unsupported language is refused.
- Templates page lists one file per language and supports `.html`.

## 1.3.0 — 2026-10-06
- Security: server bound to 127.0.0.1 by default, CSRF (Origin / Sec-Fetch-Site) check, security headers incl. CSP, SameSite=Strict cookie, session expiry (12 h idle / 30 days), server-side logout, nothing in the interface usable before sign-in.
- Speed: companies of a batch run in parallel (4 workers), registry writes serialised with a lock.
- Start scripts pull updates automatically when the folder is a git clone.

## 1.2.0 — 2026-10-05
- Gemini as a third provider (`LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, `GEMINI_MODEL`) through Google's OpenAI-compatible endpoint.
- OpenAI as an alternative model provider (`LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL`): request parsing, web research and the agent mode run on either provider.
- `start.sh` for macOS and Linux.

## 1.1.0 — 2026-10-05
- Interface: report cards, clickable answers, Companies / Activity / Templates / Status pages, light and dark theme, phone layout.
- Chat API returns structured reports; chat history survives a reload; `cancel` clears pending questions.
- Templates editable in the app with validation (Subject line, known placeholders).
- CSV downloads of the registry and the action log; `/healthz`; log file `Agency/Registry/agent.log`.
- Login protected against password guessing (5 failures lock the address for 60 s).
- `scripts/acceptance.py`: runs the research on a CSV of companies without creating drafts and reports the hit rate (acceptance criterion: 80 %).
- `start.ps1` / `start.bat` for Windows, `start.sh` for macOS and Linux; GitHub Actions run the tests on every push.
- `.env` read without Docker; `ONEDRIVE_PATH` for sharing links from a synced folder.

## 1.0.0 — 2026-10-05
- First complete build of the specification: chat (FR/EN, batch), identification, contact research with sources and confidence, MX validation, WhatsApp status, file matching, templates, Outlook drafts with attachments through Microsoft Graph without any send permission, registry and action log, duplicate warning, do-not-contact, large-video fallback, demo mode, 81 tests.
