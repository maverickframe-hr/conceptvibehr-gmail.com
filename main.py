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

app = FastAPI(title=APP_NAME, version="0.4.0")


def env(name: str, required: bool = True) -> Optional[str]:
    value = os.getenv(name)
    if required and not value:
        raise HTTPException(status_code=500, detail=f"Missing environment variable: {name}")
    return value


def provider(name: str) -> Dict[str, Any]:
    if name not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    return PROVIDERS[name]


def _safe_json(response: httpx.Response) -> Dict[str, Any]:
    try:
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"ok": False, "raw": data}
    except Exception:
        return {"ok": False, "text": response.text[:2000]}


async def save_tokens_remote(provider_name: str, tokens: Dict[str, Any]) -> bool:
    url = token_store_url()
    if not url:
        print("No TOKEN_STORE_URL / GOOGLE_APPS_SCRIPT_URL configured")
        return False
    payload = {"action": "save_token", "provider": provider_name, "tokens": tokens}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.post(url, json=payload)
        data = _safe_json(response)
        if response.status_code >= 400 or data.get("ok") is False:
            print(f"Token remote save failed for {provider_name}: {response.status_code} {data}")
            return False
        return True
    except Exception as exc:
        print(f"Token remote save error for {provider_name}: {exc}")
        return False


async def load_tokens_remote(provider_name: str) -> Optional[Dict[str, Any]]:
    url = token_store_url()
    if not url:
        return None

    # Primary method: POST JSON to Apps Script doPost.
    payload = {"action": "load_token", "provider": provider_name}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.post(url, json=payload)
        data = _safe_json(response)
        tokens = data.get("tokens") if isinstance(data, dict) else None
        if isinstance(tokens, dict) and tokens.get("access_token"):
            provider(provider_name)["token_file"].write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
            return tokens
        print(f"Token remote POST load did not return token for {provider_name}: {response.status_code} {data}")
    except Exception as exc:
        print(f"Token remote POST load error for {provider_name}: {exc}")

    # Fallback method: GET query to Apps Script doGet. This is useful for debugging and avoids POST redirect issues.
    try:
        params = {"action": "load_token", "provider": provider_name}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url, params=params)
        data = _safe_json(response)
        tokens = data.get("tokens") if isinstance(data, dict) else None
        if isinstance(tokens, dict) and tokens.get("access_token"):
            provider(provider_name)["token_file"].write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
            return tokens
        print(f"Token remote GET load did not return token for {provider_name}: {response.status_code} {data}")
    except Exception as exc:
        print(f"Token remote GET load error for {provider_name}: {exc}")

    return None


async def save_tokens(provider_name: str, tokens: Dict[str, Any]) -> None:
    provider(provider_name)["token_file"].write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
    await save_tokens_remote(provider_name, tokens)


async def load_tokens(provider_name: str) -> Dict[str, Any]:
    token_file = provider(provider_name)["token_file"]
    if token_file.exists():
        try:
            tokens = json.loads(token_file.read_text(encoding="utf-8"))
            if tokens.get("access_token"):
                return tokens
        except Exception:
            pass
    remote_tokens = await load_tokens_remote(provider_name)
    if remote_tokens:
        return remote_tokens
    raise HTTPException(status_code=401, detail=f"{provider_name} is not authorized yet. Open /auth/{provider_name}/start first.")


async def refresh_tokens(provider_name: str, tokens: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return None
    p = provider(provider_name)
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": env(p["client_id"]),
        "client_secret": env(p["client_secret"]),
    }
    headers = {"HH-User-Agent": env(p["user_agent"], required=False) or p["default_ua"]}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.post(p["token"], data=data, headers=headers)
        if response.status_code >= 400:
            print(f"Token refresh failed for {provider_name}: {response.status_code} {response.text}")
            return None
        new_tokens = response.json()
        if "refresh_token" not in new_tokens and refresh_token:
            new_tokens["refresh_token"] = refresh_token
        await save_tokens(provider_name, new_tokens)
        return new_tokens
    except Exception as exc:
        print(f"Token refresh error for {provider_name}: {exc}")
        return None


async def api_request(provider_name: str, method: str, path: str, **kwargs):
    p = provider(provider_name)
    tokens = await load_tokens(provider_name)
    headers = kwargs.pop("headers", {})
    headers.update({
        "Authorization": f"Bearer {tokens['access_token']}",
        "HH-User-Agent": env(p["user_agent"], required=False) or p["default_ua"],
    })
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.request(method, f"{p['api']}{path}", headers=headers, **kwargs)

    # If access token expired, refresh once and retry.
    if response.status_code == 401:
        new_tokens = await refresh_tokens(provider_name, tokens)
        if new_tokens and new_tokens.get("access_token"):
            headers["Authorization"] = f"Bearer {new_tokens['access_token']}"
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
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
        "token_status": "/debug/rabota/token_status",
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
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.post(p["token"], data=data, headers=headers)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    tokens = response.json()
    remote_saved = await save_tokens_remote(provider_name, tokens)
    provider(provider_name)["token_file"].write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
    return {
        "ok": True,
        "remote_saved": remote_saved,
        "message": f"{provider_name} authorized successfully. You can now use /{provider_name}/me and /{provider_name}/vacancies."
    }


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


@app.get("/{provider_name}/responses_short")
async def responses_short(provider_name: str, vacancy_id: str, page: int = 0, per_page: int = 20):
    provider(provider_name)
    data = await responses(provider_name, vacancy_id, page, per_page)
    short_items = []
    for item in data.get("items", []):
        resume = item.get("resume") or {}
        short_items.append({
            "id": item.get("id"),
            "state": (item.get("state") or {}).get("name") if isinstance(item.get("state"), dict) else item.get("state"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "resume_id": resume.get("id"),
            "first_name": resume.get("first_name"),
            "last_name": resume.get("last_name"),
            "middle_name": resume.get("middle_name"),
            "title": resume.get("title"),
            "age": resume.get("age"),
            "area": (resume.get("area") or {}).get("name") if isinstance(resume.get("area"), dict) else resume.get("area"),
            "url": resume.get("alternate_url") or resume.get("url"),
        })
    return {"found": data.get("found"), "page": data.get("page"), "pages": data.get("pages"), "per_page": data.get("per_page"), "items": short_items}


@app.get("/{provider_name}/resume/{resume_id}")
async def resume(provider_name: str, resume_id: str):
    provider(provider_name)
    return await api_request(provider_name, "GET", f"/resumes/{resume_id}")


@app.get("/debug/{provider_name}/token_status")
async def token_status(provider_name: str):
    provider(provider_name)
    local_exists = provider(provider_name)["token_file"].exists()
    remote_tokens = await load_tokens_remote(provider_name)
    return {
        "ok": True,
        "provider": provider_name,
        "token_store_url_configured": bool(token_store_url()),
        "local_token_exists": local_exists,
        "remote_token_exists": bool(remote_tokens and remote_tokens.get("access_token")),
    }


@app.get("/debug/{provider_name}/remote_token")
async def remote_token(provider_name: str):
    provider(provider_name)
    tokens = await load_tokens_remote(provider_name)
    if not tokens:
        return {"ok": False, "provider": provider_name, "message": "No remote token found"}
    return {"ok": True, "provider": provider_name, "has_access_token": bool(tokens.get("access_token")), "has_refresh_token": bool(tokens.get("refresh_token"))}


@app.get("/debug/{provider_name}/token_store_roundtrip")
@app.post("/debug/{provider_name}/token_store_roundtrip")
async def token_store_roundtrip(provider_name: str):
    provider(provider_name)
    test_provider = provider_name + "_test"
    test_tokens = {"access_token": "test-access-token", "refresh_token": "test-refresh-token"}
    saved = await save_tokens_remote(test_provider, test_tokens)
    loaded = await load_tokens_remote(test_provider)
    return {
        "ok": bool(saved and loaded and loaded.get("access_token") == "test-access-token"),
        "provider": provider_name,
        "saved": saved,
        "loaded_has_access_token": bool(loaded and loaded.get("access_token")),
    }


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
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.post(url, json=row.model_dump())

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = _safe_json(response)
    if isinstance(data, dict) and data.get("ok") is False:
        raise HTTPException(status_code=502, detail=data)

    return {
        "ok": True,
        "saved": True,
        "status_code": response.status_code,
        "apps_script_response": data,
    }
