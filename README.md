# Maverickframe HH + Rabota.by MVP Bridge

FastAPI bridge for ChatGPT Actions/Agents + HH OAuth + Rabota.by OAuth + Google Sheets.

## Render env vars

Existing HH variables:

- `HH_CLIENT_ID`
- `HH_CLIENT_SECRET`
- `HH_REDIRECT_URI` = `https://maverickframe-hh-bridge.onrender.com/auth/hh/callback`
- `HH_USER_AGENT`
- `GOOGLE_APPS_SCRIPT_URL`

Rabota.by variables:

- `RABOTA_CLIENT_ID`
- `RABOTA_CLIENT_SECRET`
- `RABOTA_REDIRECT_URI` = `https://maverickframe-hh-bridge.onrender.com/auth/rabota/callback`
- `RABOTA_USER_AGENT` = `Maverickframe HR Assistant (conceptvibehr@gmail.com)`

Optional endpoint overrides if Rabota.by requires different endpoints:

- `RABOTA_API_URL` = `https://api.hh.ru`
- `RABOTA_AUTH_URL` = `https://rabota.by/oauth/authorize`
- `RABOTA_TOKEN_URL` = `https://api.hh.ru/token`

## Test URLs

HH:

- `/auth/hh/start`
- `/hh/me`
- `/hh/vacancies`
- `/hh/negotiations?vacancy_id=...`
- `/hh/responses?vacancy_id=...`

Rabota.by:

- `/auth/rabota/start`
- `/rabota/me`
- `/rabota/vacancies`
- `/rabota/negotiations?vacancy_id=...`
- `/rabota/responses?vacancy_id=...`

## What changed in this version

- Fixed Rabota.by employer detection from `/me` response field `employer`.
- Fixed Rabota.by vacancies endpoint to call `/vacancies?employer_id=...`.
- Added `/responses` endpoint for candidate response lists: `/negotiations/response?vacancy_id=...`.
- Added OpenAPI actions for `getHHResponses` and `getRabotaResponses`.
