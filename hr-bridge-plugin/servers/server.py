# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp[cli]", "httpx"]
# ///
"""HR Bridge MCP Server — resumes, chat, Telegram via maverickframe-hh-bridge.onrender.com"""

import httpx
from mcp.server.fastmcp import FastMCP

BRIDGE = "https://maverickframe-hh-bridge.onrender.com"
mcp = FastMCP("hr-bridge")

# Employer ids по провайдерам (нужны, чтобы находить актуальные вакансии)
DEFAULT_EMPLOYER_ID = {
    "rabota": "772836",
    "hh": "12669364",
}

# Допустимые статусы отклика (см. правило работы с рабочими сайтами)
VALID_ACTIONS = {
    "discard_by_employer",      # Отказ
    "consider",                 # Рассмотреть / в работу
    "phone_interview",
    "interview",
    "assessment",
    "offer",
    "hired",
    "discard_no_interaction",
    "discard_vacancy_closed",
}


def _fetch_vacancies(employer_id: str, provider: str) -> dict:
    r = httpx.get(f"{BRIDGE}/{provider}/vacancies",
                  params={"employer_id": employer_id}, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "status_code": r.status_code, "text": r.text[:500]}


def _latest_vacancy_id(provider: str) -> str | None:
    """Newest open (non-archived) vacancy id for the default employer, or None."""
    employer_id = DEFAULT_EMPLOYER_ID.get(provider)
    if not employer_id:
        return None
    data = _fetch_vacancies(employer_id, provider)
    items = data.get("items") if isinstance(data, dict) else None
    if not items:
        return None
    open_items = [i for i in items if not i.get("archived")] or items
    open_items.sort(key=lambda i: i.get("published_at") or "", reverse=True)
    return open_items[0].get("id")


@mcp.tool()
def list_responses(vacancy_id: str = "", page: int = 0, per_page: int = 20, provider: str = "rabota") -> dict:
    """List candidate responses. Returns id (use as nid for send_message), resume_id, name.

    vacancy_id is optional: if omitted, the newest open vacancy of the default
    employer is resolved automatically (so the tool never points at a dead
    vacancy). Use list_vacancies to see all ids."""
    if not vacancy_id:
        vacancy_id = _latest_vacancy_id(provider)
        if not vacancy_id:
            return {"ok": False,
                    "error": f"no open vacancies found for {provider}; pass vacancy_id explicitly"}
    r = httpx.get(f"{BRIDGE}/{provider}/responses_short",
                  params={"vacancy_id": vacancy_id, "page": page, "per_page": per_page}, timeout=30)
    try:
        data = r.json()
    except Exception:
        return {"ok": False, "status_code": r.status_code, "text": r.text[:500], "vacancy_id": vacancy_id}
    if isinstance(data, dict):
        data.setdefault("vacancy_id", vacancy_id)
    return data

@mcp.tool()
def get_resume(resume_id: str, provider: str = "rabota") -> dict:
    """Get FULL resume: experience, education, skills, salary, contacts (phone, email, telegram).
    resume_id comes from list_responses. provider: 'hh' or 'rabota'."""
    r = httpx.get(f"{BRIDGE}/{provider}/resume/{resume_id}", timeout=30)
    return r.json()

@mcp.tool()
def read_messages(nid: str, provider: str = "rabota", page: int = 0, per_page: int = 20) -> dict:
    """Read chat with candidate. nid = id field from list_responses. provider: 'hh' or 'rabota'."""
    r = httpx.get(f"{BRIDGE}/{provider}/employer/negotiations/{nid}/messages",
                  params={"page": page, "per_page": per_page}, timeout=30)
    return r.json()

@mcp.tool()
def send_message(nid: str, text: str, provider: str = "rabota") -> dict:
    """Send message to candidate in HH.ru or Rabota.by chat.
    Only call when user explicitly requests. nid = id from list_responses."""
    r = httpx.post(f"{BRIDGE}/{provider}/negotiations/{nid}/messages",
                   json={"message": text}, timeout=30)
    return r.json()

@mcp.tool()
def change_status(nid: str, action: str = "discard_by_employer", message: str = "", provider: str = "rabota") -> dict:
    """Change a candidate response status (move between employer folders) in HH.ru / Rabota.by.

    action: discard_by_employer (Отказ/reject), consider, phone_interview, interview,
    assessment, offer, hired, discard_no_interaction, discard_vacancy_closed.
    nid = id from list_responses. Optional `message` is delivered to the candidate.

    IRREVERSIBLE from the integration (rollback only manually on the site UI).
    Only call when the user explicitly requests it. For bulk actions, confirm the
    target list with the user first."""
    if action not in VALID_ACTIONS:
        return {"ok": False, "error": f"invalid action '{action}'", "valid_actions": sorted(VALID_ACTIONS)}
    payload = {"action": action}
    if message:
        payload["message"] = message
    r = httpx.post(f"{BRIDGE}/{provider}/negotiations/{nid}/change_state",
                   json=payload, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": r.status_code < 400, "status_code": r.status_code, "text": r.text}

@mcp.tool()
def send_telegram_message(chat_id: str, text: str, bot_token: str) -> dict:
    """Send Telegram message via bot API.
    chat_id = @username or numeric id (from get_resume contacts).
    bot_token from @BotFather. Candidate must have messaged your bot first."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    r = httpx.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=20)
    return r.json()

@mcp.tool()
def list_vacancies(employer_id: str = "", provider: str = "rabota") -> dict:
    """List vacancies. employer_id is optional and defaults to
    Rabota employer_id=772836 / HH employer_id=12669364."""
    if not employer_id:
        employer_id = DEFAULT_EMPLOYER_ID.get(provider, "")
        if not employer_id:
            return {"ok": False, "error": f"unknown provider '{provider}'; pass employer_id explicitly"}
    return _fetch_vacancies(employer_id, provider)

@mcp.tool()
def get_me(provider: str = "rabota") -> dict:
    """Get current account info. provider: 'hh' or 'rabota'."""
    r = httpx.get(f"{BRIDGE}/{provider}/me", timeout=20)
    return r.json()

@mcp.tool()
def token_status(provider: str = "rabota") -> dict:
    """Check OAuth token status: expires_at, is_expired, last_refresh_error."""
    r = httpx.get(f"{BRIDGE}/debug/{provider}/token_status", timeout=20)
    return r.json()

@mcp.tool()
def refresh_token(provider: str = "rabota") -> dict:
    """Force an OAuth token refresh. Use when a call fails with token-expired.
    If this returns ok=false, a full re-authorization is needed:
    open {BRIDGE}/auth/{provider}/start in a browser logged in as the employer."""
    r = httpx.post(f"{BRIDGE}/auth/{provider}/refresh", timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "status_code": r.status_code, "text": r.text[:500]}

if __name__ == "__main__":
    mcp.run()
