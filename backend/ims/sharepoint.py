"""Read the inventory workbook from SharePoint using the signed-in user's own access.

Sign-in is the Microsoft device-code flow: the user opens microsoft.com/devicelogin,
types a code, and signs in with their work account. No client secret and no
app registration are needed (see DEFAULT_CLIENT_ID).

Files are read through a sharing link with Microsoft Graph:
  GET /shares/{share-id}/driveItem          -> drive id and item id
  GET /drives/{drive}/items/{item}/content  -> the .xlsx bytes
"""

from __future__ import annotations

import base64
import json
import threading
from dataclasses import dataclass
from pathlib import Path

import msal
import requests

from .db import REPO_ROOT

GRAPH = "https://graph.microsoft.com/v1.0"
# Narrowest delegated permission that can open a file through its sharing link.
# Files.Read.All needed admin approval in the tenant; Files.Read often does not.
SCOPES = ["Files.Read"]
CONFIG_PATH = REPO_ROOT / "data" / "sharepoint.json"
CACHE_PATH = REPO_ROOT / "data" / "msal_cache.bin"

# Link to the workbook in bridgepointeng.sharepoint.com (session parameters removed).
DEFAULT_SHARE_URL = (
    "https://bridgepointeng.sharepoint.com/:x:/r/sites/BridgePoint/_layouts/15/Doc.aspx"
    "?sourcedoc=%7Bd126485a-db1c-47e9-8fc3-d6be6f5f6b0f%7D&action=edit"
)


class SharePointError(Exception):
    """A SharePoint or sign-in problem. The message is shown to the operator."""


# Microsoft Graph Command Line Tools: a public client Microsoft publishes for Graph
# delegated sign-in. It is pre-approved in most tenants, so no app registration is needed.
DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"


@dataclass
class SharePointConfig:
    client_id: str = DEFAULT_CLIENT_ID
    tenant: str = "organizations"
    share_url: str = DEFAULT_SHARE_URL

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "SharePointConfig":
        """Defaults work out of the box. data/sharepoint.json can override them (all keys optional)."""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            client_id=(data.get("client_id") or "").strip() or DEFAULT_CLIENT_ID,
            tenant=data.get("tenant") or "organizations",
            share_url=data.get("share_url") or DEFAULT_SHARE_URL,
        )


def share_id(url: str) -> str:
    """Graph sharing token: 'u!' + base64url(url) without padding."""
    encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
    return f"u!{encoded}"


def validate_share_url(url: str) -> str:
    """Accepts an https link on a SharePoint or OneDrive host. Returns the cleaned link."""
    from urllib.parse import urlparse

    cleaned = (url or "").strip()
    parts = urlparse(cleaned)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not (host.endswith(".sharepoint.com") or host.endswith("-my.sharepoint.com")):
        raise SharePointError("A ligação tem de ser um endereço https do SharePoint (…sharepoint.com)")
    return cleaned


class SharePointService:
    """Holds the MSAL token cache, the file link to sync with, and the pending device-code sign-in."""

    def __init__(
        self,
        config: SharePointConfig,
        cache_path: Path = CACHE_PATH,
        config_path: Path = CONFIG_PATH,
    ):
        self.config = config
        self.cache_path = cache_path
        self.config_path = config_path
        self.cache = msal.SerializableTokenCache()
        if cache_path.exists():
            self.cache.deserialize(cache_path.read_text(encoding="utf-8"))
        self.app = msal.PublicClientApplication(
            config.client_id,
            authority=f"https://login.microsoftonline.com/{config.tenant}",
            token_cache=self.cache,
        )
        self._lock = threading.Lock()
        self._pending_flow: dict | None = None
        self._pending_message: str | None = None
        self._last_error: str | None = None

    # ----- token handling -----

    def _save_cache(self) -> None:
        if self.cache.has_state_changed:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(self.cache.serialize(), encoding="utf-8")

    def silent_token(self) -> str | None:
        accounts = self.app.get_accounts()
        if not accounts:
            return None
        result = self.app.acquire_token_silent(SCOPES, account=accounts[0])
        self._save_cache()
        return result.get("access_token") if result else None

    def signed_in_as(self) -> str | None:
        accounts = self.app.get_accounts()
        return accounts[0].get("username") if accounts else None

    def sign_out(self) -> None:
        """Forgets the signed-in account and deletes the cached tokens on this PC."""
        with self._lock:
            self._pending_flow = None
            self._last_error = None
        for account in self.app.get_accounts():
            self.app.remove_account(account)
        if self.cache_path.exists():
            self.cache_path.unlink()

    # ----- file link -----

    def set_share_url(self, url: str) -> None:
        """Changes the workbook link and saves it to data/sharepoint.json (other settings are kept)."""
        cleaned = validate_share_url(url)
        data = {}
        if self.config_path.exists():
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        data["share_url"] = cleaned
        data.setdefault("client_id", self.config.client_id)
        data.setdefault("tenant", self.config.tenant)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.config.share_url = cleaned

    # ----- device-code sign-in -----

    def begin_sign_in(self) -> dict:
        """Starts the device-code flow. The user opens verification_uri and enters user_code."""
        with self._lock:
            flow = self.app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise SharePointError(flow.get("error_description") or "Não foi possível iniciar o início de sessão")
            self._pending_flow = flow
            self._last_error = None
            self._pending_message = flow["message"]
        threading.Thread(target=self._complete_sign_in, args=(flow,), daemon=True).start()
        return {"user_code": flow["user_code"], "verification_uri": flow["verification_uri"], "message": flow["message"]}

    def _complete_sign_in(self, flow: dict) -> None:
        result = self.app.acquire_token_by_device_flow(flow)  # blocks until the user signs in or it expires
        with self._lock:
            self._pending_flow = None
            if "access_token" in result:
                self._last_error = None
            else:
                self._last_error = result.get("error_description") or "Início de sessão cancelado ou expirado"
            self._save_cache()

    def status(self) -> dict:
        with self._lock:
            pending = self._pending_flow is not None
            error = self._last_error
        return {
            "configured": True,
            "signed_in": self.signed_in_as() is not None,
            "account": self.signed_in_as(),
            "pending": pending,
            "error": error,
            "share_url": self.config.share_url,
        }

    # ----- download -----

    def download_workbook(self, token: str | None = None) -> tuple[str, bytes]:
        token = token or self.silent_token()
        if not token:
            raise SharePointError("Inicie sessão no SharePoint primeiro")
        headers = {"Authorization": f"Bearer {token}"}
        self._granted = token_scopes(token)
        step = "ligação de partilha"
        try:
            meta = requests.get(
                f"{GRAPH}/shares/{share_id(self.config.share_url)}/driveItem", headers=headers, timeout=30
            )
            _raise_for_graph(meta, step, granted=self._granted)
            item = meta.json()
            drive_id = item["parentReference"]["driveId"]
            step = "conteúdo do ficheiro"
            content = requests.get(
                f"{GRAPH}/drives/{drive_id}/items/{item['id']}/content",
                headers=headers,
                timeout=120,
                allow_redirects=True,
            )
            _raise_for_graph(content, step, granted=self._granted)
        except requests.RequestException as exc:
            raise SharePointError("Não foi possível contactar o SharePoint") from exc
        return item.get("name", "inventario.xlsx"), content.content


def token_scopes(token: str) -> str:
    """The permissions inside an access token ('scp' claim). Read locally; the token is not logged."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("scp", "")
    except (IndexError, ValueError):
        return "desconhecidas"


def _raise_for_graph(response: requests.Response, step: str, granted: str = "") -> None:
    """Turn a failed Graph call into a message that says which step failed and Microsoft's error code."""
    if response.status_code < 400:
        return
    code = ""
    try:
        body = response.json() or {}
        code = (body.get("error") or {}).get("code", "")
    except ValueError:
        pass
    detail = f"{response.status_code}{' ' + code if code else ''}"
    if response.status_code in (401, 403):
        raise SharePointError(
            f"Sem permissão para ler o ficheiro ({step}, {detail}). "
            f"Permissões do início de sessão: {granted or 'nenhuma'}. "
            "Confirme que tem acesso ao ficheiro no SharePoint ou inicie sessão novamente."
        )
    raise SharePointError(f"Erro do SharePoint ({step}, {detail})")
