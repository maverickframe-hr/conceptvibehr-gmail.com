# Maverickframe HH + Rabota.by resilient auth bridge

Fixes:
- Persistent OAuth token save/load via Google Apps Script with POST and GET fallback.
- GET + POST debug endpoint `/debug/{provider}/token_store_roundtrip`.
- Token refresh on API 401 using refresh_token.
- Short candidate response endpoint `/rabota/responses_short` to avoid oversized GPT Action responses.

After deploy:
1. Update Apps Script with `google_apps_script_code.gs`, deploy new version, keep `/exec` URL in `GOOGLE_APPS_SCRIPT_URL`.
2. Test: `/debug/rabota/token_store_roundtrip` should return `ok: true`.
3. Authorize once: `/auth/rabota/start`. Callback should show `remote_saved: true`.
4. Test after restart: `/debug/rabota/token_status` should show `remote_token_exists: true`.
