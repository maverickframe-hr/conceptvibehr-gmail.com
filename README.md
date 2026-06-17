# Maverickframe HH + Rabota.by MVP Bridge with persistent token storage

This version fixes the Render Free restart problem.
OAuth tokens are saved to Google Apps Script Script Properties, so Rabota.by stays authorized after Render sleeps or restarts.

## Files

- `main.py` - FastAPI bridge
- `actions_openapi.yaml` - OpenAPI schema for ChatGPT Actions
- `google_apps_script_code.gs` - Google Apps Script code for persistent token storage and candidate saving
- `requirements.txt`
- `Dockerfile`

## Required Render environment variables

Existing HH variables:

- `HH_CLIENT_ID`
- `HH_CLIENT_SECRET`
- `HH_REDIRECT_URI`
- `HH_USER_AGENT`

Rabota.by variables:

- `RABOTA_CLIENT_ID`
- `RABOTA_CLIENT_SECRET`
- `RABOTA_REDIRECT_URI`
- `RABOTA_USER_AGENT`

Google Apps Script:

- `GOOGLE_APPS_SCRIPT_URL` - your deployed Apps Script web app URL

Optional:

- `TOKEN_STORE_URL` - if omitted, backend uses `GOOGLE_APPS_SCRIPT_URL` for token storage.

## What changed

Previously tokens were stored in `/tmp`, so Render Free deleted them after restart.
Now the backend:

1. saves tokens locally for the current session;
2. sends tokens to Google Apps Script with `action=save_token`;
3. after restart, loads tokens back with `action=load_token`.

## After upload

1. Upload these files to GitHub.
2. Wait for Render deploy live.
3. In Apps Script, replace Code.gs with `google_apps_script_code.gs`, deploy a new web app version.
4. Make sure Render has `GOOGLE_APPS_SCRIPT_URL` set to the Apps Script web app URL.
5. Open:

`https://maverickframe-hh-bridge.onrender.com/auth/rabota/start`

Authorize once.

Then test:

`https://maverickframe-hh-bridge.onrender.com/rabota/me`

After Render sleeps/restarts, it should still work.
