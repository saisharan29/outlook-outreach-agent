# Changelog

## 1.1.0 — 2026-10-05
- Interface: report cards, clickable answers, Companies / Activity / Templates / Status pages, light and dark theme, phone layout.
- Chat API returns structured reports; chat history survives a reload; `cancel` clears pending questions.
- Templates editable in the app with validation (Subject line, known placeholders).
- CSV downloads of the registry and the action log; `/healthz`; log file `Agency/Registry/agent.log`.
- Login protected against password guessing (5 failures lock the address for 60 s).
- `scripts/acceptance.py`: runs the research on a CSV of companies without creating drafts and reports the hit rate (acceptance criterion: 80 %).
- `start.ps1` / `start.bat` for Windows; GitHub Actions run the tests on every push.
- `.env` read without Docker; `ONEDRIVE_PATH` for sharing links from a synced folder.

## 1.0.0 — 2026-10-05
- First complete build of the specification: chat (FR/EN, batch), identification, contact research with sources and confidence, MX validation, WhatsApp status, file matching, templates, Outlook drafts with attachments through Microsoft Graph without any send permission, registry and action log, duplicate warning, do-not-contact, large-video fallback, demo mode, 81 tests.
