# Maverickframe HH + Rabota.by Stable Auth MVP

This update fixes the recurring authorization loss on Render Free.

## Key fix
All calls from Render to Google Apps Script now use `follow_redirects=True`, because Apps Script Web Apps normally return a redirect from `script.google.com` to `script.googleusercontent.com`.

Without following that redirect, token saving/loading can silently fail or return HTML (`Moved Temporarily`) instead of JSON.

## Added debug endpoints

- `/debug/rabota/token_status` - checks whether local and remote Rabota tokens exist.
- `/debug/rabota/token_store_roundtrip` - tests saving/loading a test token through Google Apps Script.

## After upload

1. Upload files to GitHub.
2. Wait for Render `Deploy live`.
3. Open `/debug/rabota/token_store_roundtrip`.
4. Authorize Rabota once: `/auth/rabota/start`.
5. Check `/debug/rabota/token_status`.
6. Restart Render and check `/rabota/me` without re-authorizing.
