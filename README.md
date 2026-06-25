# Maverickframe HH + Rabota.by resilient auth bridge

Fixes:
- Persistent OAuth token save/load via Google Apps Script with POST and GET fallback.
- Correct Apps Script 301/302/303 handling: POST runs on `/exec`, then the ContentService redirect is fetched with GET.
- HH employer OAuth flow: `/auth/hh/employer/start`, `/hh/employer`, `/hh/employer/vacancies`, `/hh/employer/responses_short`.
- Gmail read integration for HH/Rabota notifications: `/gmail/hh/emails`.
- GET + POST debug endpoint `/debug/{provider}/token_store_roundtrip`.
- Token refresh on API 401 using refresh_token.
- Short candidate response endpoints `/hh/responses_short` and `/rabota/responses_short` to avoid oversized GPT Action responses.

Required Render environment:
- `HH_CLIENT_ID`
- `HH_CLIENT_SECRET`
- `HH_REDIRECT_URI` pointing to `https://maverickframe-hh-bridge.onrender.com/auth/hh/callback`
- `HH_USER_AGENT` such as `Maverickframe HR Assistant (conceptvibehr@gmail.com)`
- `GOOGLE_APPS_SCRIPT_URL` or `TOKEN_STORE_URL`

After deploy:
1. Redeploy Render so `maverickframe-hh-bridge` runs the updated bridge code.
2. Update Apps Script with `google_apps_script_code.gs`, deploy new version, keep `/exec` URL in `GOOGLE_APPS_SCRIPT_URL`.
   The Apps Script response should include `version: "0.5.0"` after this step.
   Because Gmail reading uses `GmailApp`, the Apps Script deployment must be re-authorized with Gmail read permissions.
3. Test HH OAuth config: `/debug/hh/oauth_config` should show `client_id_configured`, `client_secret_configured`, and `redirect_uri_configured` as `true`.
4. Authorize HH employer once: `/auth/hh/employer/start`. Callback should show `remote_saved: true`.
5. Test HH employer workflow: `/hh/employer`, `/hh/employer/vacancies`, then `/hh/responses_short?vacancy_id=...`.
6. Test Gmail HH emails: `/gmail/hh/emails?max_results=5&unread_only=false`.
7. Test token persistence after restart: `/debug/hh/token_status` and `/debug/rabota/token_status` should show `remote_token_exists: true`.
