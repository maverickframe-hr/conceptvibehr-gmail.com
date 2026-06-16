# Maverickframe HH MVP Bridge

Minimal FastAPI bridge for ChatGPT Actions/Agents + HH OAuth + Google Sheets.

## Render env vars

- `HH_CLIENT_ID`
- `HH_CLIENT_SECRET`
- `HH_REDIRECT_URI` = `https://YOUR-RENDER-SERVICE.onrender.com/auth/hh/callback`
- `HH_USER_AGENT` = `Maverickframe HR Assistant (conceptvibehr@gmail.com)`
- `GOOGLE_APPS_SCRIPT_URL` = your Apps Script web app URL

## Important

After Render gives you the service URL, update Redirect URI in HH developer cabinet to:

`https://YOUR-RENDER-SERVICE.onrender.com/auth/hh/callback`

Then open:

`https://YOUR-RENDER-SERVICE.onrender.com/auth/hh/start`

Authorize HH once.
