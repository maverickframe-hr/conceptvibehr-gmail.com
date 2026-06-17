import os
import json
from pathlib import Path
from typing import Optional, Any, Dict
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

APP_NAME = "Maverickframe HH + Rabota.by MVP Bridge"
TOKEN_DIR = Path("/tmp")


def token_store_url() -> Optional[str]:
    return os.getenv("TOKEN_STORE_URL") or os.getenv("GOOGLE_APPS_SCRIPT_URL")

PROVIDERS = {
    "hh": {
        "api": os.getenv("HH_API_URL", "https://api.hh.ru"),
        "auth": os.getenv("HH_AUTH_URL", "https://hh.ru/oauth/authorize"),
        "token": os.getenv("HH_TOKEN_URL", "https://api.hh.ru/token"),
        "client_id": "HH_CLIENT_ID",
        "client_secret": "HH_CLIENT_SECRET",
        "redirect_uri": "HH_REDIRECT_URI",
        "user_agent": "HH_USER_AGENT",
        "default_ua": "Maverickframe HR Assistant (conceptvibehr@gmail.com)",
        "token_file": TOKEN_DIR / "hh_tokens.json",
        "source": "HH",
    },
    "rabota": {
        "api": os.getenv("RABOTA_API_URL", "https://api.hh.ru"),
        "auth": os.getenv("RABOTA_AUTH_URL", "https://rabota.by/oauth/authorize"),
        "token": os.getenv("RABOTA_TOKEN_URL", "https://api.hh.ru/token"),
        "client_id": "RABOTA_CLIENT_ID",
        "client_secret": "RABOTA_CLIENT_SECRET",
        "redirect_uri": "RABOTA_REDIRECT_URI",
        "user_agent": "RABOTA_USER_AGENT",
        "default_ua": "Maverickframe HR Assistant (conceptvibehr@gmail.com)",
        "token_file": TOKEN_DIR / "rabota_tokens.json",
        "source": "Rabota.by",
    },
}

app = FastAPI(title=APP_NAME, version="0.2.0")


def env(name: str, required: bool = True) -> Optional[str]:
    value = os.getenv(name)
    if required and not value:
        raise HTTPException(status_code=500, detail=f"Missing environment variable: {name}")
    return value


def provider(name: str) -> Dict[str, Any]:
    if name not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    return PROVIDERS[name]


async def save_tokens_remote(provider_name: str, tokens: Dict[str, Any]) -> None:
    url = token_store_url()
    if not url:
        return
    payload = {"action": "save_token", "provider": provider_name, "tokens": tokens}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
        if response.status_code >= 400:
            print(f"Token remote save failed for {provider_name}: {response.status_code} {response.text}")
    except Exception as exc:
        print(f"Token remote save error for {provider_name}: {exc}")


async def load_tokens_remote(provider_name: str) -> Optional[Dict[str, Any]]:
    url = token_store_url()
    if not url:
        return None
    payload = {"action": "load_token", "provider": provider_name}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
        if response.status_code >= 400:
            print(f"Token remote load failed for {provider_name}: {response.status_code} {response.text}")
            return None
        data = response.json()
        tokens = data.get("tokens")
        if isinstance(tokens, dict) and tokens.get("access_token"):
            provider(provider_name)["token_file"].write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
            return tokens
    except Exception as exc:
        print(f"Token remote load error for {provider_name}: {exc}")
    return None


async def save_tokens(provider_name: str, tokens: Dict[str, Any]) -> None:
    provider(provider_name)["token_file"].write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
    await save_tokens_remote(provider_name, tokens)


async def load_tokens(provider_name: str) -> Dict[str, Any]:
    token_file = provider(provider_name)["token_file"]
    if token_file.exists():
        return json.loads(token_file.read_text(encoding="utf-8"))
    remote_tokens = await load_tokens_remote(provider_name)
    if remote_tokens:
        return remote_tokens
    raise HTTPException(status_code=401, detail=f"{provider_name} is not authorized yet. Open /auth/{provider_name}/start first.")


async def api_request(provider_name: str, method: str, path: str, **kwargs):
    p = provider(provider_name)
    tokens = await load_tokens(provider_name)
    headers = kwargs.pop("headers", {})
    headers.update({
        "Authorization": f"Bearer {tokens['access_token']}",
        "HH-User-Agent": env(p["user_agent"], required=False) or p["default_ua"],
    })
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(method, f"{p['api']}{path}", headers=headers, **kwargs)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.get("/")
def root():
    return {
        "ok": True,
        "service": APP_NAME,
        "hh_start": "/auth/hh/start",
        "rabota_start": "/auth/rabota/start",
        "hh_me": "/hh/me",
        "rabota_me": "/rabota/me",
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/auth/{provider_name}/start")
def auth_start(provider_name: str):
    p = provider(provider_name)
    params = urlencode({
        "response_type": "code",
        "client_id": env(p["client_id"]),
        "redirect_uri": env(p["redirect_uri"]),
    })
    return RedirectResponse(f"{p['auth']}?{params}")


@app.get("/auth/{provider_name}/callback")
async def auth_callback(provider_name: str, code: str):
    p = provider(provider_name)
    data = {
        "grant_type": "authorization_code",
        "client_id": env(p["client_id"]),
        "client_secret": env(p["client_secret"]),
        "redirect_uri": env(p["redirect_uri"]),
        "code": code,
    }
    headers = {"HH-User-Agent": env(p["user_agent"], required=False) or p["default_ua"]}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(p["token"], data=data, headers=headers)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    tokens = response.json()
    await save_tokens(provider_name, tokens)
    return {"ok": True, "message": f"{provider_name} authorized successfully. You can now use /{provider_name}/me and /{provider_name}/vacancies."}


@app.get("/{provider_name}/me")
async def me(provider_name: str):
    provider(provider_name)
    return await api_request(provider_name, "GET", "/me")


@app.get("/{provider_name}/vacancies")
async def vacancies(provider_name: str, employer_id: Optional[str] = None, page: int = 0, per_page: int = 20):
    provider(provider_name)
    if not employer_id:
        me_data = await api_request(provider_name, "GET", "/me")

        if provider_name == "rabota":
            employer = me_data.get("employer")
            if not employer:
                raise HTTPException(status_code=400, detail="No employer account found for this rabota user.")
            employer_id = employer.get("id")
        else:
            employers = me_data.get("employers") or []
            if not employers:
                raise HTTPException(status_code=400, detail=f"No employer accounts found for this {provider_name} user.")
            employer_id = employers[0].get("id")

    if provider_name == "rabota":
        params = {"employer_id": employer_id, "page": page, "per_page": per_page}
        return await api_request(provider_name, "GET", "/vacancies", params=params)

    params = {"page": page, "per_page": per_page}
    return await api_request(provider_name, "GET", f"/employers/{employer_id}/vacancies", params=params)


@app.get("/{provider_name}/negotiations")
async def negotiations(provider_name: str, vacancy_id: str, page: int = 0, per_page: int = 20):
    provider(provider_name)
    params = {"vacancy_id": vacancy_id, "page": page, "per_page": per_page}
    return await api_request(provider_name, "GET", "/negotiations", params=params)


@app.get("/{provider_name}/responses")
async def responses(provider_name: str, vacancy_id: str, page: int = 0, per_page: int = 20):
    provider(provider_name)
    params = {"vacancy_id": vacancy_id, "page": page, "per_page": per_page}
    return await api_request(provider_name, "GET", "/negotiations/response", params=params)


@app.get("/{provider_name}/resume/{resume_id}")
async def resume(provider_name: str, resume_id: str):
    provider(provider_name)
    return await api_request(provider_name, "GET", f"/resumes/{resume_id}")


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

    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True
    ) as client:
        response = await client.post(
            url,
            json=row.model_dump()
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    return {
        "ok": True,
        "status_code": response.status_code,
        "response": response.text
    }
