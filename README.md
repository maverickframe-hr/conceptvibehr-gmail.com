# Maverickframe HH + Rabota.by resilient auth bridge

Fixes:
- Persistent OAuth token save/load via Google Apps Script with POST and GET fallback.
- Correct Apps Script 301/302/303 handling: POST runs on `/exec`, then the ContentService redirect is fetched with GET.
- GET + POST debug endpoint `/debug/{provider}/token_store_roundtrip`.
- Token refresh on API 401 using refresh_token.
- Short candidate response endpoint `/rabota/responses_short` to avoid oversized GPT Action responses.

After deploy:
1. Redeploy Render so `maverickframe-hh-bridge` runs the updated bridge code.
2. Update Apps Script with `google_apps_script_code.gs`, deploy new version, keep `/exec` URL in `GOOGLE_APPS_SCRIPT_URL`.
   The Apps Script response should include `version: "0.4.1"` after this step.
3. Test: `/debug/rabota/token_store_roundtrip` should return `ok: true`.
4. Authorize once: `/auth/rabota/start`. Callback should show `remote_saved: true`.
5. Test after restart: `/debug/rabota/token_status` should show `remote_token_exists: true`.
