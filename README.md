# Maverickframe HH + Rabota.by MVP Bridge

FastAPI bridge for ChatGPT Actions/Agents + HH OAuth + Rabota.by OAuth + Google Sheets.

## Render env vars

Existing HH variables:
- `HH_CLIENT_ID`
- `HH_CLIENT_SECRET`
- `HH_REDIRECT_URI` = `https://maverickframe-hh-bridge.onrender.com/auth/hh/callback`
- `HH_USER_AGENT`
- `GOOGLE_APPS_SCRIPT_URL`

Add Rabota.by variables:
- `RABOTA_CLIENT_ID`
- `RABOTA_CLIENT_SECRET`
- `RABOTA_REDIRECT_URI` = `https://maverickframe-hh-bridge.onrender.com/auth/rabota/callback`
- `RABOTA_USER_AGENT` = `Maverickframe HR Assistant (conceptvibehr@gmail.com)`

Optional overrides if Rabota.by requires different endpoints:
- `RABOTA_API_URL` = `https://api.hh.ru`
- `RABOTA_AUTH_URL` = `https://rabota.by/oauth/authorize`
- `RABOTA_TOKEN_URL` = `https://api.hh.ru/token`

## Test URLs

HH:
- `/auth/hh/start`
- `/hh/me`
- `/hh/vacancies`

Rabota.by:
- `/auth/rabota/start`
- `/rabota/me`
- `/rabota/vacancies`

## Important

If `/me` returns `is_applicant=true` and `is_employer=false`, the OAuth token is not employer-level. Contact HH/Rabota.by API support and request Employer API access.
