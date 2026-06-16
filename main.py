import os
import json
from pathlib import Path
from typing import Optional, Any, Dict
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel

APP_NAME = "Maverickframe HH MVP Bridge"
HH_API = "https://api.hh.ru"
HH_AUTH = "https://hh.ru/oauth/authorize"
HH_TOKEN = "https://api.hh.ru/token"
TOKEN_FILE = Path("/tmp/hh_tokens.json")

app = FastAPI(title=APP_NAME, version="0.1.0")


def env(name: str, required: bool = True) -> Optional[str]:
    value = os.getenv(name)
    if required and not value:
        raise HTTPException(status_code=500, detail=f"Missing environment variable: {name}")
    return value


def save_tokens(tokens: Dict[str, Any]) -> None:
    TOKEN_FILE.write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")


def load_tokens() -> Dict[str, Any]:
    if not TOKEN_FILE.exists():
        raise HTTPException(status_code=401, detail="HH is not authorized yet. Open /auth/hh/start first.")
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))


async def hh_request(method: str, path: str, **kwargs):
    tokens = load_tokens()
    headers = kwargs.pop("headers", {})
    headers.update({
        "Authorization": f"Bearer {tokens['access_token']}",
        "HH-User-Agent": env("HH_USER_AGENT", required=False) or "Maverickframe HR Assistant (conceptvibehr@gmail.com)",
    })
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(method, f"{HH_API}{path}", headers=headers, **kwargs)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.get("/")
def root():
    return {"ok": True, "service": APP_NAME, "next": "/auth/hh/start"}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/auth/hh/start")
def hh_start():
    client_id = env("HH_CLIENT_ID")
    redirect_uri = env("HH_REDIRECT_URI")
    params = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    })
    return RedirectResponse(f"{HH_AUTH}?{params}")


@app.get("/auth/hh/callback")
async def hh_callback(code: str):
    client_id = env("HH_CLIENT_ID")
    client_secret = env("HH_CLIENT_SECRET")
    redirect_uri = env("HH_REDIRECT_URI")
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    headers = {"HH-User-Agent": env("HH_USER_AGENT", required=False) or "Maverickframe HR Assistant (conceptvibehr@gmail.com)"}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(HH_TOKEN, data=data, headers=headers)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    tokens = response.json()
    save_tokens(tokens)
    return {"ok": True, "message": "HH authorized successfully. You can now use /hh/me and /hh/vacancies."}


@app.get("/hh/me")
async def hh_me():
    return await hh_request("GET", "/me")


@app.get("/hh/vacancies")
async def hh_vacancies(employer_id: Optional[str] = None, page: int = 0, per_page: int = 20):
    if not employer_id:
        me = await hh_request("GET", "/me")
        employers = me.get("employers") or []
        if not employers:
            raise HTTPException(status_code=400, detail="No employer accounts found for this HH user.")
        employer_id = employers[0].get("id")
    params = {"page": page, "per_page": per_page}
    return await hh_request("GET", f"/employers/{employer_id}/vacancies", params=params)


@app.get("/hh/negotiations")
async def hh_negotiations(vacancy_id: str, page: int = 0, per_page: int = 20):
    params = {"vacancy_id": vacancy_id, "page": page, "per_page": per_page}
    return await hh_request("GET", "/negotiations", params=params)


@app.get("/hh/resume/{resume_id}")
async def hh_resume(resume_id: str):
    return await hh_request("GET", f"/resumes/{resume_id}")


class CandidateRow(BaseModel):
    date_added: Optional[str] = None
    source: str = "HH"
    vacancy: Optional[str] = None
    candidate_name: Optional[str] = None
    location: Optional[str] = None
    experience: Optional[str] = None
    skills: Optional[str] = None
    gpt_score: Optional[int] = None
    status: Optional[str] = None
    recruiter_comment: Optional[str] = None
    resume_link: Optional[str] = None
    suggested_reply: Optional[str] = None
    gpt_summary: Optional[str] = None


@app.post("/sheets/save_candidate")
async def save_candidate(row: CandidateRow):
    url = env("GOOGLE_APPS_SCRIPT_URL")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=row.model_dump())
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    try:
        return response.json()
    except Exception:
        return {"ok": True, "response": response.text}
