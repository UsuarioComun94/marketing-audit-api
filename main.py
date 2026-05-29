from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib import robotparser

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover
    BeautifulSoup = None

try:
    import trafilatura  # type: ignore
except Exception:  # pragma: no cover
    trafilatura = None

try:
    import extruct  # type: ignore
except Exception:  # pragma: no cover
    extruct = None

try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover
    feedparser = None

try:
    import phonenumbers  # type: ignore
except Exception:  # pragma: no cover
    phonenumbers = None

try:
    import tldextract  # type: ignore
except Exception:  # pragma: no cover
    tldextract = None


try:
    from browserbase import Browserbase  # type: ignore
except Exception:  # pragma: no cover
    Browserbase = None

try:
    from playwright.async_api import async_playwright  # type: ignore
except Exception:  # pragma: no cover
    async_playwright = None

APP_VERSION = "public-presence-collector-mvp-0.9.34"
API_KEY = os.getenv("API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://marketing-audit-api.onrender.com").rstrip("/")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "").strip()
BROWSERBASE_API_KEY = os.getenv("BROWSERBASE_API_KEY", "").strip()
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY", "").strip()
COMPOSIO_API_BASE = os.getenv("COMPOSIO_API_BASE", "https://backend.composio.dev/api/v3.1").rstrip("/")
COMPOSIO_DEFAULT_USER_ID = os.getenv("COMPOSIO_DEFAULT_USER_ID", "default").strip() or "default"
COMPOSIO_CONNECTED_ACCOUNT_ID = os.getenv("COMPOSIO_CONNECTED_ACCOUNT_ID", "").strip()
COMPOSIO_SEARCH_TOOL_SLUG = os.getenv("COMPOSIO_SEARCH_TOOL_SLUG", "").strip()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()

TEXT_REPORTS: Dict[str, Dict[str, Any]] = {}
SCREENSHOTS: Dict[str, Dict[str, Any]] = {}

USER_AGENT = (
    "Mozilla/5.0 (compatible; MarketingAuditorPublicCollector/0.1; "
    "+https://marketing-audit-api.onrender.com)"
)

SOCIAL_PLATFORMS = ["instagram", "facebook", "linkedin", "youtube", "tiktok", "x"]

EXPECTED_FIELDS: Dict[str, List[str]] = {
    "website": [
        "http_status",
        "final_url",
        "title",
        "meta_description",
        "headings",
        "visible_text",
        "internal_links",
        "external_links",
        "social_links",
        "cta",
        "phones",
        "emails",
        "whatsapp",
        "forms",
        "services_or_products",
        "pricing",
        "faq",
        "blog_or_news",
        "testimonials_or_clients",
        "website_claims",
        "tracking_scripts",
        "structured_data",
        "robots_txt",
        "sitemap_xml",
    ],
    "instagram": [
        "profile_title",
        "profile_description",
        "external_link",
        "followers_count",
        "following_count",
        "posts_count",
        "latest_posts",
        "post_dates",
        "likes_comments_views",
    ],
    "facebook": [
        "page_title",
        "page_description",
        "external_link",
        "followers_or_likes",
        "recent_posts",
        "post_dates",
        "reactions_comments_shares",
        "contact_or_hours",
    ],
    "linkedin": [
        "company_title",
        "company_description",
        "industry_location_size",
        "followers_count",
        "employees_visible",
        "recent_posts",
        "post_dates",
        "reactions_comments",
    ],
    "youtube": [
        "channel_id",
        "channel_title",
        "channel_description",
        "published_at",
        "subscriber_count",
        "video_count",
        "view_count",
        "latest_videos",
        "video_dates",
        "video_views",
        "posting_frequency_estimate",
    ],
    "tiktok": [
        "profile_title",
        "profile_description",
        "external_link",
        "followers_count",
        "following_count",
        "likes_total",
        "latest_videos",
        "video_dates",
        "views_likes_comments",
    ],
    "x": [
        "profile_title",
        "profile_description",
        "external_link",
        "followers_count",
        "following_count",
        "posts_count",
        "recent_posts",
        "post_dates",
        "likes_reposts_replies_views",
        "account_created_at",
    ],
    "search": [
        "public_search_results",
        "possible_profiles",
        "mentions",
        "provider_used",
        "fallback_attempts",
    ],
}

REASON_MESSAGES_ES = {
    "missing_input": "No se recibi\u00f3 un link para esta fuente.",
    "missing_api_key": "La herramienta necesaria no est\u00e1 configurada en el backend mediante variable de entorno.",
    "blocked_by_platform": "La plataforma limit\u00f3 la lectura p\u00fablica, requiri\u00f3 login o bloque\u00f3 el acceso automatizado.",
    "not_publicly_available": "El dato no est\u00e1 disponible p\u00fablicamente de forma confiable.",
    "requires_owner_access": "Este dato requiere autorizaci\u00f3n del propietario de la cuenta o acceso del cliente.",
    "robots_disallowed": "El archivo robots.txt no permite recolectar esta URL con el user-agent actual.",
    "http_error": "La URL respondi\u00f3 con error HTTP.",
    "timeout": "La solicitud agot\u00f3 el tiempo de espera.",
    "parse_error": "Se pudo descargar contenido, pero no se pudo interpretar de forma confiable.",
    "js_render_required": "El contenido parece depender de JavaScript/renderizado din\u00e1mico.",
    "rate_limited": "La plataforma o API limit\u00f3 la cantidad de solicitudes.",
    "unsupported_platform": "La plataforma no est\u00e1 soportada por este MVP.",
    "collector_not_implemented": "El collector est\u00e1 reconocido, pero todav\u00eda no est\u00e1 implementado en esta versi\u00f3n m\u00ednima.",
    "insufficient_public_data": "La fuente p\u00fablica entreg\u00f3 informaci\u00f3n insuficiente para ese campo.",
    "private_metric": "Es una m\u00e9trica privada de performance; no puede obtenerse desde links p\u00fablicos.",
    "all_search_providers_failed": "Todos los proveedores de b\u00fasqueda configurados fallaron o no devolvieron resultados \u00fatiles.",
    "no_search_results": "La b\u00fasqueda p\u00fablica no devolvi\u00f3 resultados \u00fatiles con los proveedores configurados.",
}

HOW_TO_COLLECT_ES = {
    "website": {
        "generic": [
            "Verificar que la URL sea p\u00fablica y correcta.",
            "Probar lectura con Firecrawl si el HTML p\u00fablico viene pobre.",
            "Usar Browserbase/Playwright si el contenido depende de JavaScript.",
            "Pedir al cliente la landing exacta si la p\u00e1gina p\u00fablica no contiene la informaci\u00f3n comercial.",
        ]
    },
    "instagram": {
        "generic": [
            "Solicitar link correcto del perfil p\u00fablico.",
            "Si se requieren m\u00e9tricas reales, conectar cuenta profesional mediante Meta/Instagram API con autorizaci\u00f3n del cliente.",
            "Como alternativa operativa, pedir captura o export manual desde Meta Business Suite con fecha de captura.",
        ]
    },
    "facebook": {
        "generic": [
            "Solicitar link correcto de la p\u00e1gina p\u00fablica.",
            "Para insights reales, el cliente debe autorizar Meta/Facebook Page mediante permisos de p\u00e1gina.",
            "Como alternativa, pedir capturas o export manual desde Meta Business Suite.",
        ]
    },
    "linkedin": {
        "generic": [
            "Solicitar URL correcta de p\u00e1gina de empresa o perfil.",
            "Para estad\u00edsticas reales, el cliente debe autorizar LinkedIn API/OAuth o entregar export/capturas.",
            "LinkedIn limita mucha informaci\u00f3n p\u00fablica sin login; registrar la limitaci\u00f3n si no expone posts o m\u00e9tricas.",
        ]
    },
    "youtube": {
        "generic": [
            "Verificar que el link corresponda a un canal, handle o video p\u00fablico.",
            "Configurar YOUTUBE_API_KEY si falta la clave.",
            "Si el conteo de suscriptores est\u00e1 oculto por el canal, marcarlo como no p\u00fablico.",
        ]
    },
    "tiktok": {
        "generic": [
            "Solicitar link correcto del perfil p\u00fablico.",
            "Si la plataforma oculta m\u00e9tricas, pedir captura manual del perfil y contenidos recientes.",
            "Para m\u00e9tricas internas reales, se requiere acceso del cliente o export de la plataforma.",
        ]
    },
    "x": {
        "generic": [
            "Solicitar link correcto del perfil p\u00fablico.",
            "Si las m\u00e9tricas no son visibles, marcar como no disponible p\u00fablicamente.",
            "Para datos estructurados, usar API de X si existe acceso y condiciones habilitadas.",
        ]
    },
    "search": {
        "generic": [
            "Configurar TAVILY_API_KEY y SERPER_API_KEY para b\u00fasqueda p\u00fablica con fallback.",
            "Si un proveedor responde 429, esperar reset de cuota o usar fallback.",
            "Usar Firecrawl despu\u00e9s de la b\u00fasqueda para extraer contenido real de URLs encontradas.",
            "No tratar snippets de SERP como evidencia definitiva; usarlos para descubrir fuentes.",
        ]
    },
}

app = FastAPI(
    title="Marketing Auditor - Public Presence Collector MVP",
    version=APP_VERSION,
    description=(
        "MVP de recolecci\u00f3n pasiva/semi-pasiva de presencia p\u00fablica. "
        "No diagnostica performance, no genera recomendaciones comerciales y no inventa datos."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# HOTFIX 4H.3-R: outgoing JSON mojibake cleaner.
def _ma_runtime_clean_mojibake_text(value: str) -> str:
    if not isinstance(value, str) or not value:
        return value

    pairs = {
        chr(0x00C3) + chr(0x00A1): "\u00e1",
        chr(0x00C3) + chr(0x00A9): "\u00e9",
        chr(0x00C3) + chr(0x00AD): "\u00ed",
        chr(0x00C3) + chr(0x00B3): "\u00f3",
        chr(0x00C3) + chr(0x00BA): "\u00fa",
        chr(0x00C3) + chr(0x00B1): "\u00f1",
        chr(0x00C3) + chr(0x00BC): "\u00fc",
        chr(0x00C3) + chr(0x0081): "\u00c1",
        chr(0x00C3) + chr(0x0089): "\u00c9",
        chr(0x00C3) + chr(0x008D): "\u00cd",
        chr(0x00C3) + chr(0x0093): "\u00d3",
        chr(0x00C3) + chr(0x009A): "\u00da",
        chr(0x00C3) + chr(0x0091): "\u00d1",
        chr(0x00C2) + chr(0x00BF): "\u00bf",
        chr(0x00C2) + chr(0x00A1): "\u00a1",
        chr(0x00C2) + chr(0x00A0): " ",
        chr(0x00E2) + chr(0x0080) + chr(0x0099): "'",
        chr(0x00E2) + chr(0x0080) + chr(0x0098): "'",
        chr(0x00E2) + chr(0x0080) + chr(0x009C): '"',
        chr(0x00E2) + chr(0x0080) + chr(0x009D): '"',
        chr(0x00E2) + chr(0x0080) + chr(0x0093): "-",
        chr(0x00E2) + chr(0x0080) + chr(0x0094): "-",
        chr(0x00E2) + chr(0x0080) + chr(0x00A6): "...",
        chr(0xFFFD): "",
    }

    out = value
    for bad, good in pairs.items():
        out = out.replace(bad, good)
    return out


def _ma_runtime_clean_json_payload(value):
    if isinstance(value, str):
        return _ma_runtime_clean_mojibake_text(value)
    if isinstance(value, list):
        return [_ma_runtime_clean_json_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_ma_runtime_clean_json_payload(item) for item in value)
    if isinstance(value, dict):
        return {
            _ma_runtime_clean_json_payload(k): _ma_runtime_clean_json_payload(v)
            for k, v in value.items()
        }
    return value


@app.middleware("http")
async def _ma_clean_json_mojibake_middleware(request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")

    if "application/json" not in content_type.lower():
        return response

    body = b""
    try:
        async for chunk in response.body_iterator:
            body += chunk

        data = json.loads(body.decode("utf-8", errors="replace"))
        data = _ma_runtime_clean_json_payload(data)
        new_body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")

        headers = dict(response.headers)
        headers["content-length"] = str(len(new_body))

        return Response(
            content=new_body,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )
    except Exception:
        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=content_type or "application/json",
        )



class AssetsInput(BaseModel):
    website: Optional[str] = None
    instagram: Optional[str] = None
    facebook: Optional[str] = None
    linkedin: Optional[str] = None
    youtube: Optional[str] = None
    tiktok: Optional[str] = None
    x: Optional[str] = None


class PublicPresenceCollectRequest(BaseModel):
    company_name: Optional[str] = None
    website: Optional[str] = None
    website_url: Optional[str] = None
    instagram: Optional[str] = None
    facebook: Optional[str] = None
    linkedin: Optional[str] = None
    youtube: Optional[str] = None
    tiktok: Optional[str] = None
    x: Optional[str] = None
    assets: Optional[AssetsInput] = None
    collection_depth: str = Field(default="basic", description="basic | standard")
    max_website_pages: int = Field(default=5, ge=1, le=10)


class BrowserRenderRequest(BaseModel):
    url: str
    viewport: str = Field(default="desktop", description="desktop | mobile")
    wait_ms: int = Field(default=1500, ge=0, le=8000)
    timeout_ms: int = Field(default=30000, ge=5000, le=90000)
    full_page: bool = Field(default=True, description="Si true, captura full page; si false, captura viewport.")



class VisualSiteAuditRequest(BaseModel):
    url: Optional[str] = Field(default=None, description="URL p\u00fablica del sitio.")
    website: Optional[str] = Field(default=None, description="Alias de url.")
    company_name: Optional[str] = None
    max_internal_pages: int = Field(default=3, ge=0, le=5)
    viewports: List[str] = Field(default_factory=lambda: ["desktop", "mobile"])
    wait_ms: int = Field(default=1500, ge=0, le=8000)
    timeout_ms: int = Field(default=45000, ge=5000, le=90000)
    full_page: bool = Field(default=True, description="Capturar p\u00e1gina completa.")


class SearchProviderDebugRequest(BaseModel):
    query: str = Field(..., min_length=2, description="Consulta p\u00fablica a ejecutar.")
    max_results: int = Field(default=8, ge=1, le=10)
    gl: str = Field(default="ar", min_length=2, max_length=5, description="Pa\u00eds para Serper/Google, por ejemplo ar o us.")
    hl: str = Field(default="es", min_length=2, max_length=5, description="Idioma para Serper/Google, por ejemplo es o en.")
    use_fallbacks: bool = Field(default=True, description="Si true, intenta Tavily -> Serper -> Composio.")



async def verify_api_key(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    if not API_KEY:
        return
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()
    elif x_api_key:
        provided = x_api_key.strip()
    if provided != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    value = url.strip()
    if not value:
        return None
    if not re.match(r"^https?://", value, flags=re.I):
        value = "https://" + value
    return value


def safe_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().replace("www.", "")


def root_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def hash_payload(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def truncate(text: str, limit: int = 600) -> str:
    text = collapse_ws(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


def make_evidence(
    evidence_id: str,
    platform: str,
    source_url: Optional[str],
    collector: str,
    data_type: str,
    value: Any,
    confidence: str = "medium",
    raw_excerpt: Optional[str] = None,
    limitations: Optional[List[str]] = None,
    evidence_type: str = "public_observed",
) -> Dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "platform": platform,
        "source_url": source_url,
        "collector": collector,
        "data_type": data_type,
        "value": value,
        "raw_excerpt": truncate(raw_excerpt or "", 900) if raw_excerpt else None,
        "confidence": confidence,
        "retrieved_at": now_iso(),
        "limitations": limitations or [],
        "evidence_type": evidence_type,
    }


class EvidenceBuilder:
    def __init__(self) -> None:
        self.items: List[Dict[str, Any]] = []
        self._counter = 1

    def add(
        self,
        platform: str,
        source_url: Optional[str],
        collector: str,
        data_type: str,
        value: Any,
        confidence: str = "medium",
        raw_excerpt: Optional[str] = None,
        limitations: Optional[List[str]] = None,
        evidence_type: str = "public_observed",
    ) -> str:
        eid = f"ev_{self._counter:03d}"
        self._counter += 1
        self.items.append(
            make_evidence(
                eid,
                platform,
                source_url,
                collector,
                data_type,
                value,
                confidence,
                raw_excerpt,
                limitations,
                evidence_type,
            )
        )
        return eid


async def fetch_url(url: str, timeout: int = 15) -> Dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    started = time.time()
    if httpx is not None:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers) as client:
                resp = await client.get(url)
            return {
                "ok": 200 <= resp.status_code < 400,
                "status_code": resp.status_code,
                "final_url": str(resp.url),
                "content_type": resp.headers.get("content-type", ""),
                "text": resp.text or "",
                "elapsed_ms": int((time.time() - started) * 1000),
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "status_code": None, "final_url": url, "content_type": "", "text": "", "elapsed_ms": int((time.time() - started) * 1000), "error": str(exc)}

    def _urllib_fetch() -> Dict[str, Any]:
        import urllib.request

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec - controlled URL input for public collector
            raw = response.read(2_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            return {
                "ok": 200 <= response.status < 400,
                "status_code": response.status,
                "final_url": response.url,
                "content_type": response.headers.get("content-type", ""),
                "text": raw.decode(charset, errors="replace"),
                "elapsed_ms": int((time.time() - started) * 1000),
                "error": None,
            }

    try:
        return await asyncio.to_thread(_urllib_fetch)
    except Exception as exc:
        return {"ok": False, "status_code": None, "final_url": url, "content_type": "", "text": "", "elapsed_ms": int((time.time() - started) * 1000), "error": str(exc)}


def soup_from_html(doc: str) -> Any:
    if BeautifulSoup is None:
        return None
    try:
        return BeautifulSoup(doc or "", "html.parser")
    except Exception:
        return None


def extract_visible_text(doc: str) -> str:
    if not doc:
        return ""
    if trafilatura is not None:
        try:
            extracted = trafilatura.extract(doc, include_comments=False, include_tables=False, favor_precision=True)
            if extracted and len(extracted.strip()) > 120:
                return collapse_ws(html.unescape(extracted))
        except Exception:
            pass
    soup = soup_from_html(doc)
    if soup is not None:
        for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
            tag.decompose()
        return collapse_ws(html.unescape(soup.get_text(" ")))
    cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", doc)
    cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    return collapse_ws(html.unescape(cleaned))


def extract_meta_and_links(doc: str, base_url: str) -> Dict[str, Any]:
    soup = soup_from_html(doc)
    out: Dict[str, Any] = {
        "title": None,
        "meta_description": None,
        "headings": [],
        "links": [],
        "forms_count": 0,
        "buttons": [],
        "open_graph": {},
        "structured_data_count": 0,
        "scripts_src": [],
        "images_alt": [],
    }
    if soup is None:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", doc, flags=re.I | re.S)
        if title_match:
            out["title"] = collapse_ws(html.unescape(title_match.group(1)))
        return out

    title = soup.find("title")
    if title:
        out["title"] = collapse_ws(title.get_text(" "))

    meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if meta_desc and meta_desc.get("content"):
        out["meta_description"] = collapse_ws(meta_desc.get("content"))

    for tag in soup.find_all(["h1", "h2", "h3"]):
        txt = collapse_ws(tag.get_text(" "))
        if txt and len(txt) >= 2:
            out["headings"].append(txt)
    out["headings"] = list(dict.fromkeys(out["headings"]))[:30]

    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a.get("href"))
        text = collapse_ws(a.get_text(" "))
        links.append({"url": href, "text": text})
    out["links"] = links

    out["forms_count"] = len(soup.find_all("form"))

    buttons = []
    for tag in soup.find_all(["button", "a"]):
        txt = collapse_ws(tag.get_text(" "))
        if txt and any(k in txt.lower() for k in ["contact", "contacto", "consult", "cotiz", "compr", "agenda", "reserv", "llamar", "whatsapp", "empez", "demo", "presupuesto"]):
            buttons.append(txt)
    out["buttons"] = list(dict.fromkeys(buttons))[:25]

    og = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name")
        content = meta.get("content")
        if prop and content and (str(prop).startswith("og:") or str(prop).startswith("twitter:")):
            og[str(prop)] = collapse_ws(str(content))
    out["open_graph"] = og

    out["structured_data_count"] = len(soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}))

    scripts = []
    for s in soup.find_all("script", src=True):
        scripts.append(urljoin(base_url, s.get("src")))
    out["scripts_src"] = scripts[:100]

    img_alts = []
    for img in soup.find_all("img"):
        alt = collapse_ws(img.get("alt") or "")
        if alt:
            img_alts.append(alt)
    out["images_alt"] = list(dict.fromkeys(img_alts))[:50]

    return out


def split_links(base_url: str, links: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, List[str]]]:
    base_domain = safe_domain(base_url)
    internal: List[Dict[str, str]] = []
    external: List[Dict[str, str]] = []
    socials: Dict[str, List[str]] = {p: [] for p in SOCIAL_PLATFORMS}
    socials.update({"whatsapp": [], "google_maps": []})
    for link in links:
        u = link.get("url") or ""
        if not u or u.startswith("mailto:") or u.startswith("tel:"):
            continue
        domain = safe_domain(u) if re.match(r"^https?://", u) else ""
        low = u.lower()
        if "instagram.com" in low:
            socials["instagram"].append(u)
        elif "facebook.com" in low or "fb.com" in low:
            socials["facebook"].append(u)
        elif "linkedin.com" in low:
            socials["linkedin"].append(u)
        elif "youtube.com" in low or "youtu.be" in low:
            socials["youtube"].append(u)
        elif "tiktok.com" in low:
            socials["tiktok"].append(u)
        elif "twitter.com" in low or "x.com" in low:
            socials["x"].append(u)
        elif "wa.me" in low or "api.whatsapp.com" in low:
            socials["whatsapp"].append(u)
        elif "google.com/maps" in low or "maps.app.goo.gl" in low:
            socials["google_maps"].append(u)
        if domain and domain == base_domain:
            internal.append(link)
        elif domain:
            external.append(link)
    for k in socials:
        socials[k] = list(dict.fromkeys(socials[k]))[:10]
    return internal, external, socials


def extract_contacts(text: str, links: List[Dict[str, str]]) -> Dict[str, List[str]]:
    emails = sorted(set(re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text)))[:20]
    whatsapp = []
    tel_links = []
    for link in links:
        u = link.get("url") or ""
        low = u.lower()
        if "wa.me" in low or "api.whatsapp.com" in low:
            whatsapp.append(u)
        if low.startswith("tel:"):
            tel_links.append(u.replace("tel:", ""))
    phones: List[str] = []
    if phonenumbers is not None:
        try:
            for match in phonenumbers.PhoneNumberMatcher(text[:120_000], None):
                phones.append(phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL))
        except Exception:
            pass
    if not phones:
        rough = re.findall(r"(?:\+?\d[\d\s().\-]{7,}\d)", text)
        phones.extend([collapse_ws(x) for x in rough])
    phones.extend([collapse_ws(x) for x in tel_links])
    return {
        "emails": list(dict.fromkeys(emails))[:20],
        "phones": list(dict.fromkeys(phones))[:20],
        "whatsapp": list(dict.fromkeys(whatsapp))[:20],
    }


def detect_content_features(text: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    low = text.lower()
    headings = " ".join(meta.get("headings", [])).lower()
    both = low + " " + headings
    features = {
        "pricing": any(k in both for k in ["precio", "precios", "pricing", "$", "usd", "ars", "mensual", "/mes", "month"]),
        "faq": any(k in both for k in ["faq", "preguntas frecuentes", "frequently asked"]),
        "blog_or_news": any(k in both for k in ["blog", "noticias", "news", "art\u00edculo", "articulos", "podcast", "newsletter"]),
        "testimonials_or_clients": any(k in both for k in ["testimonio", "testimonios", "clientes", "casos", "rese\u00f1as", "reviews", "logos", "empresas que conf\u00edan", "conf\u00edan en"]),
        "services_or_products": any(k in both for k in ["servicio", "servicios", "producto", "productos", "soluciones", "plans", "planes", "consultor\u00eda", "consultoria"]),
        "website_claims": any(k in both for k in ["a\u00f1os de experiencia", "clientes satisfechos", "tasa de \u00e9xito", "premios", "l\u00edder", "lider", "garant\u00eda", "garantia", "%", "casos de \u00e9xito"]),
    }
    tracking_keywords = {
        "google_tag_manager": ["googletagmanager", "gtm.js"],
        "google_analytics": ["google-analytics", "gtag/js", "gtag("],
        "meta_pixel": ["fbq(", "connect.facebook.net"],
        "tiktok_pixel": ["analytics.tiktok.com", "ttq."],
        "linkedin_insight": ["snap.licdn.com", "linkedin_partner_id"],
        "hotjar": ["hotjar"],
        "clarity": ["clarity.ms", "clarity("],
        "hubspot": ["hubspot", "hs-scripts"],
    }
    html_blob = low
    tracking = [name for name, keys in tracking_keywords.items() if any(k in html_blob for k in keys)]
    features["tracking_scripts"] = tracking
    return features


def choose_internal_pages(home_url: str, internal_links: List[Dict[str, str]], max_pages: int) -> List[str]:
    priority = ["contact", "contacto", "servicio", "services", "precio", "pricing", "faq", "preguntas", "blog", "noticia", "news", "nosotros", "about", "caso", "testimonio"]
    candidates: List[Tuple[int, str]] = []
    seen = set()
    for link in internal_links:
        u = (link.get("url") or "").split("#")[0]
        if not u or u in seen:
            continue
        seen.add(u)
        low = (u + " " + link.get("text", "")).lower()
        score = 0
        for idx, kw in enumerate(priority):
            if kw in low:
                score += 100 - idx
        if score > 0:
            candidates.append((score, u))
    ranked = [u for _, u in sorted(candidates, reverse=True)]
    urls = [home_url]
    for u in ranked:
        if u not in urls:
            urls.append(u)
        if len(urls) >= max_pages:
            break
    return urls[:max_pages]


def collector_report(
    collector: str,
    platform: str,
    status: str,
    tool_used: str,
    input_url: Optional[str] = None,
    intended_data: Optional[List[str]] = None,
    collected_fields: Optional[List[str]] = None,
    missing_fields: Optional[List[str]] = None,
    reason_code: Optional[str] = None,
    reason: Optional[str] = None,
    confidence: str = "medium",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reason_text = reason or (REASON_MESSAGES_ES.get(reason_code or "", None))
    return {
        "collector": collector,
        "platform": platform,
        "status": status,
        "tool_used": tool_used,
        "input_url": input_url,
        "intended_data": intended_data or EXPECTED_FIELDS.get(platform, []),
        "collected_fields": collected_fields or [],
        "missing_fields": missing_fields or [],
        "reason_code": reason_code,
        "reason": reason_text,
        "how_to_collect_missing": HOW_TO_COLLECT_ES.get(platform, {}).get("generic", []),
        "confidence": confidence,
        "details": details or {},
    }


def build_recovery_guide(collector_reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    guide: List[Dict[str, Any]] = []
    for report in collector_reports:
        platform = report.get("platform") or "unknown"
        status = report.get("status")
        missing_fields = report.get("missing_fields") or []
        if status == "skipped_missing_input":
            guide.append(
                {
                    "platform": platform,
                    "field": f"{platform}.all_public_fields",
                    "label_es": f"Datos p\u00fablicos de {platform}",
                    "status": "not_collected",
                    "why_not_collected": "No se recibi\u00f3 un link para esta fuente.",
                    "attempted_tools": [report.get("tool_used")],
                    "importance": "media",
                    "can_be_collected_publicly": "variable",
                    "how_to_collect": [f"Proveer el link p\u00fablico correcto de {platform}."] + report.get("how_to_collect_missing", []),
                    "requires_client_permission": False,
                }
            )
            continue
        if status == "skipped_missing_api_key":
            guide.append(
                {
                    "platform": platform,
                    "field": f"{platform}.api_fields",
                    "label_es": f"Datos por API de {platform}",
                    "status": "not_collected",
                    "why_not_collected": report.get("reason") or "Falta API key.",
                    "attempted_tools": [report.get("tool_used")],
                    "importance": "media-alta",
                    "can_be_collected_publicly": "s\u00ed, si la API key est\u00e1 configurada y el dato es p\u00fablico",
                    "how_to_collect": report.get("how_to_collect_missing", []),
                    "requires_client_permission": False,
                }
            )
            continue
        for field in missing_fields:
            requires_owner = field in {
                "insights",
                "reach",
                "impressions",
                "profile_visits",
                "link_clicks",
                "demographics",
                "saved_posts",
                "crm",
                "conversions",
                "revenue",
            } or platform in {"instagram", "facebook", "linkedin", "tiktok"} and field in {"engagement_metrics", "likes_comments_views", "reactions_comments_shares", "followers_count", "post_dates", "latest_posts"}
            guide.append(
                {
                    "platform": platform,
                    "field": f"{platform}.{field}",
                    "label_es": field.replace("_", " "),
                    "status": "not_collected",
                    "why_not_collected": report.get("reason") or "El dato no apareci\u00f3 en la recolecci\u00f3n p\u00fablica.",
                    "attempted_tools": [report.get("tool_used")],
                    "importance": "alta" if requires_owner else "media",
                    "can_be_collected_publicly": "variable" if not requires_owner else "normalmente no",
                    "how_to_collect": report.get("how_to_collect_missing", []),
                    "requires_client_permission": bool(requires_owner),
                }
            )
    # Add always-private performance fields as explicit guidance.
    for field, label in [
        ("ga4.conversions", "conversiones reales"),
        ("meta_ads.reach_impressions_clicks", "alcance, impresiones y clics de campa\u00f1as"),
        ("crm.lead_quality", "calidad de lead"),
        ("sales.revenue_close", "ventas, revenue y cierre"),
    ]:
        guide.append(
            {
                "platform": field.split(".")[0],
                "field": field,
                "label_es": label,
                "status": "requires_owner_access",
                "why_not_collected": "No es informaci\u00f3n p\u00fablica; requiere acceso del cliente o export manual.",
                "attempted_tools": [],
                "importance": "alta",
                "can_be_collected_publicly": "no",
                "how_to_collect": [
                    "Solicitar acceso del cliente a la plataforma correspondiente.",
                    "Aceptar export CSV/Excel o capturas fechadas si no se puede conectar API.",
                    "Registrar per\u00edodo analizado y fuente exacta del dato.",
                ],
                "requires_client_permission": True,
            }
        )
    return guide


async def collect_robots_and_sitemap(base_url: str, evidence: EvidenceBuilder) -> Tuple[List[Dict[str, Any]], List[str]]:
    reports: List[Dict[str, Any]] = []
    collected: List[str] = []
    robots_url = urljoin(base_url, "/robots.txt")
    sitemap_url = urljoin(base_url, "/sitemap.xml")
    robots_resp = await fetch_url(robots_url, timeout=8)
    if robots_resp.get("ok") and robots_resp.get("text"):
        collected.append("robots_txt")
        evidence.add("website", robots_url, "robots_txt_collector", "robots_txt", "robots.txt disponible", "medium", robots_resp.get("text", "")[:1000])
    sitemap_resp = await fetch_url(sitemap_url, timeout=8)
    if sitemap_resp.get("ok") and sitemap_resp.get("text"):
        collected.append("sitemap_xml")
        evidence.add("website", sitemap_url, "sitemap_collector", "sitemap_xml", "sitemap.xml disponible", "medium", sitemap_resp.get("text", "")[:1000])
    reports.append(
        collector_report(
            "robots_sitemap_collector",
            "website",
            "completed" if collected else "partial",
            "httpx+urllib.robotparser",
            base_url,
            intended_data=["robots_txt", "sitemap_xml"],
            collected_fields=collected,
            missing_fields=[f for f in ["robots_txt", "sitemap_xml"] if f not in collected],
            reason_code=None if collected else "insufficient_public_data",
            confidence="medium",
        )
    )
    return reports, collected


async def collect_website_static(url: Optional[str], max_pages: int, evidence: EvidenceBuilder) -> Dict[str, Any]:
    platform = "website"
    collector = "website_static_collector"
    if not url:
        return {
            "reports": [collector_report(collector, platform, "skipped_missing_input", "httpx+bs4+trafilatura", None, reason_code="missing_input", confidence="none")],
            "summary": {},
        }
    normalized = normalize_url(url)
    assert normalized is not None
    base = root_url(normalized)
    reports, _ = await collect_robots_and_sitemap(base, evidence)
    home = await fetch_url(normalized, timeout=18)
    if not home.get("ok"):
        reason_code = "http_error" if home.get("status_code") else "timeout"
        reports.append(collector_report(collector, platform, "failed_runtime", "httpx+bs4+trafilatura", normalized, reason_code=reason_code, reason=home.get("error"), confidence="none"))
        return {"reports": reports, "summary": {"fetch_error": home.get("error"), "http_status": home.get("status_code")}}

    home_doc = home.get("text") or ""
    home_meta = extract_meta_and_links(home_doc, home.get("final_url") or normalized)
    home_text = extract_visible_text(home_doc)
    internal, external, socials = split_links(home.get("final_url") or normalized, home_meta.get("links", []))
    pages_to_fetch = choose_internal_pages(home.get("final_url") or normalized, internal, max_pages=max_pages)

    pages: List[Dict[str, Any]] = []
    collected_fields = ["http_status", "final_url"]
    all_text = home_text
    all_links = list(home_meta.get("links", []))
    all_headings = list(home_meta.get("headings", []))
    all_buttons = list(home_meta.get("buttons", []))
    forms_count = int(home_meta.get("forms_count") or 0)
    scripts_src: List[str] = list(home_meta.get("scripts_src", []))
    open_graph = dict(home_meta.get("open_graph", {}))
    structured_data_count = int(home_meta.get("structured_data_count") or 0)

    page_fetches = []
    for page_url in pages_to_fetch[1:]:
        page_fetches.append(fetch_url(page_url, timeout=12))
    fetched_pages = await asyncio.gather(*page_fetches, return_exceptions=True) if page_fetches else []

    page_docs = [(home.get("final_url") or normalized, home_doc, home_meta, home_text)]
    for idx, result in enumerate(fetched_pages):
        page_url = pages_to_fetch[idx + 1]
        if isinstance(result, Exception) or not result.get("ok"):
            continue
        doc = result.get("text") or ""
        meta = extract_meta_and_links(doc, result.get("final_url") or page_url)
        text = extract_visible_text(doc)
        page_docs.append((result.get("final_url") or page_url, doc, meta, text))
        all_text += " " + text
        all_links.extend(meta.get("links", []))
        all_headings.extend(meta.get("headings", []))
        all_buttons.extend(meta.get("buttons", []))
        forms_count += int(meta.get("forms_count") or 0)
        scripts_src.extend(meta.get("scripts_src", []))
        open_graph.update(meta.get("open_graph", {}))
        structured_data_count += int(meta.get("structured_data_count") or 0)

    internal_all, external_all, socials_all = split_links(home.get("final_url") or normalized, all_links)
    contacts = extract_contacts(all_text, all_links)
    features = detect_content_features(all_text + " " + home_doc, {"headings": list(dict.fromkeys(all_headings)), "scripts_src": scripts_src})

    if home_meta.get("title"):
        collected_fields.append("title")
        evidence.add(platform, normalized, collector, "title", home_meta.get("title"), "high")
    if home_meta.get("meta_description"):
        collected_fields.append("meta_description")
        evidence.add(platform, normalized, collector, "meta_description", home_meta.get("meta_description"), "high")
    if all_headings:
        collected_fields.append("headings")
        evidence.add(platform, normalized, collector, "headings", list(dict.fromkeys(all_headings))[:20], "medium-high")
    if len(all_text) > 200:
        collected_fields.append("visible_text")
        evidence.add(platform, normalized, collector, "visible_text_sample", truncate(all_text, 1400), "medium", raw_excerpt=all_text[:1600])
    if internal_all:
        collected_fields.append("internal_links")
    if external_all:
        collected_fields.append("external_links")
    if any(socials_all.values()):
        collected_fields.append("social_links")
        evidence.add(platform, normalized, collector, "social_links_detected", {k: v for k, v in socials_all.items() if v}, "medium-high")
    if all_buttons:
        collected_fields.append("cta")
        evidence.add(platform, normalized, collector, "cta_detected", list(dict.fromkeys(all_buttons))[:20], "medium-high")
    if contacts["phones"]:
        collected_fields.append("phones")
        evidence.add(platform, normalized, collector, "phones_detected", contacts["phones"], "medium-high")
    if contacts["emails"]:
        collected_fields.append("emails")
        evidence.add(platform, normalized, collector, "emails_detected", contacts["emails"], "medium-high")
    if contacts["whatsapp"]:
        collected_fields.append("whatsapp")
        evidence.add(platform, normalized, collector, "whatsapp_detected", contacts["whatsapp"], "medium-high")
    if forms_count:
        collected_fields.append("forms")
        evidence.add(platform, normalized, collector, "forms_detected", f"{forms_count} formulario(s) detectado(s)", "medium")
    for fname, dtype, label in [
        ("services_or_products", "services_or_products", "Se\u00f1ales de servicios/productos detectadas"),
        ("pricing", "pricing", "Se\u00f1ales de precios/planes detectadas"),
        ("faq", "faq", "Se\u00f1ales de FAQ/preguntas frecuentes detectadas"),
        ("blog_or_news", "blog_or_news", "Se\u00f1ales de blog/noticias/contenido detectadas"),
        ("testimonials_or_clients", "testimonials_or_clients", "Se\u00f1ales de testimonios/clientes/logos detectadas"),
        ("website_claims", "website_claims", "Claims del sitio detectados; requieren verificaci\u00f3n externa"),
    ]:
        if features.get(fname):
            collected_fields.append(dtype)
            evidence_type = "website_claim" if dtype == "website_claims" else "website_observed"
            evidence.add(platform, normalized, collector, dtype, label, "medium", raw_excerpt=all_text[:1200], evidence_type=evidence_type)
    if features.get("tracking_scripts"):
        collected_fields.append("tracking_scripts")
        evidence.add(platform, normalized, collector, "tracking_scripts_detected", features["tracking_scripts"], "medium", limitations=["Detectar un script no prueba que el tracking est\u00e9 bien configurado."])
    if open_graph or structured_data_count:
        collected_fields.append("structured_data")
        evidence.add(platform, normalized, collector, "metadata_structured_data", {"open_graph_keys": list(open_graph.keys()), "json_ld_blocks": structured_data_count}, "medium")

    collected_fields = list(dict.fromkeys(collected_fields))
    missing_fields = [f for f in EXPECTED_FIELDS[platform] if f not in collected_fields]

    for page_url, _doc, meta, text in page_docs:
        pages.append(
            {
                "url": page_url,
                "title": meta.get("title"),
                "word_count": len(text.split()),
                "headings_sample": meta.get("headings", [])[:8],
            }
        )

    reports.append(
        collector_report(
            collector,
            platform,
            "completed" if len(collected_fields) >= 8 else "partial",
            "httpx+bs4+trafilatura",
            normalized,
            collected_fields=collected_fields,
            missing_fields=missing_fields,
            reason_code=None if len(collected_fields) >= 8 else "insufficient_public_data",
            confidence="medium-high" if len(collected_fields) >= 8 else "medium",
            details={
                "http_status": home.get("status_code"),
                "final_url": home.get("final_url"),
                "elapsed_ms": home.get("elapsed_ms"),
                "pages_read": len(page_docs),
                "pages": pages,
                "word_count_total": len(all_text.split()),
                "internal_links_count": len(internal_all),
                "external_links_count": len(external_all),
                "social_links": {k: v for k, v in socials_all.items() if v},
                "contact_summary": contacts,
                "features": features,
            },
        )
    )

    return {
        "reports": reports,
        "summary": {
            "status": "completed",
            "pages_read": len(page_docs),
            "word_count_total": len(all_text.split()),
            "social_links": {k: v for k, v in socials_all.items() if v},
            "contacts": contacts,
            "features": features,
        },
    }


async def collect_firecrawl(url: Optional[str], evidence: EvidenceBuilder) -> Dict[str, Any]:
    platform = "website"
    collector = "firecrawl_website_collector"
    if not url:
        return {"reports": [collector_report(collector, platform, "skipped_missing_input", "firecrawl_api", None, reason_code="missing_input", confidence="none")], "summary": {}}
    if not FIRECRAWL_API_KEY:
        return {"reports": [collector_report(collector, platform, "skipped_missing_api_key", "firecrawl_api", url, reason_code="missing_api_key", confidence="none")], "summary": {}}
    normalized = normalize_url(url)
    assert normalized is not None
    if httpx is None:
        return {"reports": [collector_report(collector, platform, "failed_runtime", "firecrawl_api", normalized, reason="httpx no est\u00e1 disponible en el entorno.", confidence="none")], "summary": {}}
    try:
        async with httpx.AsyncClient(timeout=35) as client:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"},
                json={"url": normalized, "formats": ["markdown", "html"], "onlyMainContent": True},
            )
        if resp.status_code >= 400:
            reason_code = "rate_limited" if resp.status_code == 429 else "http_error"
            return {"reports": [collector_report(collector, platform, "failed_runtime", "firecrawl_api", normalized, reason_code=reason_code, reason=f"Firecrawl HTTP {resp.status_code}: {truncate(resp.text, 300)}", confidence="none")], "summary": {}}
        data = resp.json()
        payload = data.get("data") if isinstance(data, dict) else None
        markdown = (payload or {}).get("markdown") or ""
        title = ((payload or {}).get("metadata") or {}).get("title")
        collected = []
        if markdown:
            collected.append("visible_text")
            evidence.add(platform, normalized, collector, "firecrawl_markdown_sample", truncate(markdown, 1600), "medium-high", raw_excerpt=markdown[:1800])
        if title:
            collected.append("title")
            evidence.add(platform, normalized, collector, "title", title, "medium-high")
        missing = [f for f in ["visible_text", "title", "meta_description", "internal_links"] if f not in collected]
        return {
            "reports": [
                collector_report(
                    collector,
                    platform,
                    "completed" if markdown else "partial",
                    "firecrawl_api",
                    normalized,
                    intended_data=["markdown", "html", "metadata"],
                    collected_fields=collected,
                    missing_fields=missing,
                    reason_code=None if markdown else "insufficient_public_data",
                    confidence="medium-high" if markdown else "low",
                    details={"markdown_length": len(markdown), "metadata": (payload or {}).get("metadata", {})},
                )
            ],
            "summary": {"markdown_length": len(markdown), "title": title},
        }
    except Exception as exc:
        return {"reports": [collector_report(collector, platform, "failed_runtime", "firecrawl_api", normalized, reason=str(exc), confidence="none")], "summary": {}}



def _session_value(session: Any, key: str) -> Optional[str]:
    if isinstance(session, dict):
        return session.get(key)
    value = getattr(session, key, None)
    if value is not None:
        return value
    camel = key.replace("_", "")
    value = getattr(session, camel, None)
    if value is not None:
        return value
    return None


def _viewport_size(viewport: str) -> Dict[str, int]:
    v = (viewport or "desktop").lower().strip()
    if v == "mobile":
        return {"width": 390, "height": 844}
    return {"width": 1366, "height": 900}


def _detect_cta_texts(texts: List[str]) -> List[str]:
    cta_keywords = [
        "comprar",
        "agregar",
        "carrito",
        "ver",
        "consultar",
        "contactar",
        "whatsapp",
        "cotizar",
        "registrarme",
        "iniciar sesi\u00f3n",
        "login",
        "mayorista",
        "pedir",
        "enviar",
        "suscribirme",
        "finalizar",
        "checkout",
    ]
    out: List[str] = []
    for t in texts:
        clean = collapse_ws(str(t or ""))
        if not clean or len(clean) > 120:
            continue
        low = clean.lower()
        if any(k in low for k in cta_keywords):
            out.append(clean)
    return list(dict.fromkeys(out))[:30]


async def render_browserbase_visual(req: BrowserRenderRequest) -> Dict[str, Any]:
    normalized = normalize_url(req.url)
    if not normalized:
        raise HTTPException(status_code=400, detail="URL inv\u00e1lida.")

    if not BROWSERBASE_API_KEY:
        return {
            "status": "skipped_missing_api_key",
            "collector": "browserbase_visual_debug",
            "url": normalized,
            "reason": "BROWSERBASE_API_KEY no est\u00e1 configurada.",
            "confidence": "none",
        }

    if Browserbase is None or async_playwright is None:
        return {
            "status": "missing_dependency",
            "collector": "browserbase_visual_debug",
            "url": normalized,
            "reason": "Faltan dependencias browserbase/playwright en el entorno.",
            "required_dependencies": ["browserbase", "playwright"],
            "confidence": "none",
        }

    viewport_size = _viewport_size(req.viewport)
    browser = None
    page = None
    session_id = None

    try:
        bb = Browserbase(api_key=BROWSERBASE_API_KEY)

        def _create_session() -> Any:
            return bb.sessions.create()

        session = await asyncio.to_thread(_create_session)
        session_id = _session_value(session, "id")
        connect_url = _session_value(session, "connect_url") or _session_value(session, "connectUrl")

        if not connect_url:
            return {
                "status": "failed_runtime",
                "collector": "browserbase_visual_debug",
                "url": normalized,
                "reason": "Browserbase no devolvi\u00f3 connect_url.",
                "session_id": session_id,
                "confidence": "none",
            }

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(connect_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context(viewport=viewport_size)
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                await page.set_viewport_size(viewport_size)
            except Exception:
                pass

            response = await page.goto(normalized, wait_until="domcontentloaded", timeout=req.timeout_ms)

            try:
                await page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass

            if req.wait_ms:
                await page.wait_for_timeout(req.wait_ms)

            final_url = page.url
            page_title = await page.title()
            rendered_html = await page.content()

            try:
                body_text = await page.locator("body").inner_text(timeout=5000)
            except Exception:
                body_text = extract_visible_text(rendered_html)

            buttons_text = await page.locator("button, a, input[type='button'], input[type='submit']").evaluate_all(
                """els => els.map(e => (e.innerText || e.value || e.getAttribute('aria-label') || e.getAttribute('title') || '').trim()).filter(Boolean).slice(0, 150)"""
            )

            images = await page.locator("img").evaluate_all(
                """els => els.map(e => ({
                    alt: e.getAttribute('alt') || '',
                    src: e.currentSrc || e.src || '',
                    width: e.naturalWidth || 0,
                    height: e.naturalHeight || 0
                })).slice(0, 150)"""
            )

            forms_count = await page.locator("form").count()
            links_count = await page.locator("a").count()

            screenshot_bytes = await page.screenshot(full_page=bool(req.full_page), type="png")
            screenshot_id = uuid.uuid4().hex
            SCREENSHOTS[screenshot_id] = {
                "content": screenshot_bytes,
                "created_at": now_iso(),
                "url": final_url,
                "viewport": req.viewport,
                "filename": f"browser_render_{screenshot_id[:8]}.png",
            }

            meta = extract_meta_and_links(rendered_html, final_url)
            visible_ctas = _detect_cta_texts([str(x) for x in buttons_text])
            images_without_alt = [
                img for img in images
                if not str(img.get("alt") or "").strip()
            ]

            try:
                await browser.close()
            except Exception:
                pass

            return {
                "status": "completed",
                "collector": "browserbase_visual_debug",
                "url_requested": normalized,
                "final_url": final_url,
                "http_status": response.status if response else None,
                "page_title": page_title,
                "session_id": session_id,
                "viewport": {
                    "name": req.viewport,
                    "width": viewport_size["width"],
                    "height": viewport_size["height"],
                    "full_page": bool(req.full_page),
                },
                "screenshot": {
                    "available": True,
                    "screenshot_id": screenshot_id,
                    "screenshot_url": f"{PUBLIC_BASE_URL}/deliverables/screenshot/{screenshot_id}.png",
                    "media_type": "image/png",
                },
                "visual_dom_summary": {
                    "text_sample": truncate(collapse_ws(body_text), 1800),
                    "buttons_text": [collapse_ws(str(x)) for x in buttons_text[:80]],
                    "visible_ctas": visible_ctas,
                    "links_count": links_count,
                    "forms_count": forms_count,
                    "images_count": len(images),
                    "images_without_alt_count": len(images_without_alt),
                    "image_alt_samples": [str(img.get("alt") or "") for img in images if str(img.get("alt") or "").strip()][:30],
                    "headings": meta.get("headings", [])[:30],
                    "meta_description": meta.get("meta_description"),
                    "structured_data_count": meta.get("structured_data_count"),
                    "open_graph": meta.get("open_graph", {}),
                },
                "confidence": "medium-high",
                "limitations": [
                    "El screenshot permite evaluar evidencia visual, pero no reemplaza test de UX con usuarios.",
                    "No afirma conversi\u00f3n, ventas, velocidad, Core Web Vitals ni performance.",
                    "Las plataformas con login o bloqueo pueden devolver contenido parcial.",
                ],
                "retrieved_at": now_iso(),
            }

    except Exception as exc:
        try:
            if browser:
                await browser.close()
        except Exception:
            pass

        return {
            "status": "failed_runtime",
            "collector": "browserbase_visual_debug",
            "url": normalized,
            "session_id": session_id,
            "reason": str(exc),
            "confidence": "none",
            "retrieved_at": now_iso(),
        }



async def collect_browserbase_placeholder(url: Optional[str]) -> Dict[str, Any]:
    platform = "website"
    collector = "browserbase_render_collector"
    if not url:
        status = "skipped_missing_input"
        reason_code = "missing_input"
    elif not BROWSERBASE_API_KEY:
        status = "skipped_missing_api_key"
        reason_code = "missing_api_key"
    else:
        status = "collector_not_implemented"
        reason_code = "collector_not_implemented"
    return {
        "reports": [
            collector_report(
                collector,
                platform,
                status,
                "browserbase_api",
                url,
                intended_data=["rendered_dom", "screenshot", "js_loaded_content"],
                collected_fields=[],
                missing_fields=["rendered_dom", "screenshot", "js_loaded_content"],
                reason_code=reason_code,
                confidence="none",
                details={"available_env_key": bool(BROWSERBASE_API_KEY)},
            )
        ],
        "summary": {},
    }


def parse_social_public_fields(platform: str, text: str, meta: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    collected: List[str] = []
    data: Dict[str, Any] = {}
    title = meta.get("title") or (meta.get("open_graph") or {}).get("og:title")
    desc = meta.get("meta_description") or (meta.get("open_graph") or {}).get("og:description")
    if title:
        key = "profile_title" if platform not in {"facebook", "linkedin"} else ("page_title" if platform == "facebook" else "company_title")
        collected.append(key)
        data[key] = title
    if desc:
        key = "profile_description" if platform not in {"facebook", "linkedin"} else ("page_description" if platform == "facebook" else "company_description")
        collected.append(key)
        data[key] = desc
    low = text.lower()
    number_patterns = {
        "followers_count": [r"([\d.,]+\s*[kKmM]?)\s+(?:followers|seguidores)", r"(?:followers|seguidores)\s*[:\-]?\s*([\d.,]+\s*[kKmM]?)"],
        "following_count": [r"([\d.,]+\s*[kKmM]?)\s+(?:following|seguidos)", r"(?:following|seguidos)\s*[:\-]?\s*([\d.,]+\s*[kKmM]?)"],
        "posts_count": [r"([\d.,]+\s*[kKmM]?)\s+(?:posts|publicaciones|tweets)", r"(?:posts|publicaciones|tweets)\s*[:\-]?\s*([\d.,]+\s*[kKmM]?)"],
        "likes_total": [r"([\d.,]+\s*[kKmM]?)\s+(?:likes|me gusta)"]
    }
    for field, patterns in number_patterns.items():
        for pat in patterns:
            m = re.search(pat, low, flags=re.I)
            if m:
                collected.append(field)
                data[field] = m.group(1)
                break
    if "http" in text and any(k in low for k in ["http://", "https://", "www."]):
        collected.append("external_link")
    return list(dict.fromkeys(collected)), data


async def collect_social_public(platform: str, url: Optional[str], evidence: EvidenceBuilder) -> Dict[str, Any]:
    collector = f"{platform}_public_collector"
    if not url:
        return {"reports": [collector_report(collector, platform, "skipped_missing_input", "public_html_best_effort", None, reason_code="missing_input", confidence="none")], "summary": {}}
    normalized = normalize_url(url)
    assert normalized is not None
    resp = await fetch_url(normalized, timeout=16)
    if not resp.get("ok"):
        status_code = resp.get("status_code")
        reason_code = "blocked_by_platform" if status_code in {401, 403, 429} else "http_error"
        return {"reports": [collector_report(collector, platform, "blocked_by_platform" if reason_code == "blocked_by_platform" else "failed_runtime", "public_html_best_effort", normalized, reason_code=reason_code, reason=resp.get("error") or f"HTTP {status_code}", confidence="none")], "summary": {}}
    doc = resp.get("text") or ""
    meta = extract_meta_and_links(doc, resp.get("final_url") or normalized)
    text = extract_visible_text(doc)
    collected, parsed_data = parse_social_public_fields(platform, text, meta)
    if collected:
        evidence.add(platform, normalized, collector, "public_profile_metadata", parsed_data or {"title": meta.get("title"), "description": meta.get("meta_description")}, "low", raw_excerpt=text[:1000], limitations=["Datos p\u00fablicos best-effort; la plataforma puede ocultar m\u00e9tricas o requerir login."])
    if len(text.split()) > 40:
        evidence.add(platform, normalized, collector, "public_text_sample", truncate(text, 900), "low", raw_excerpt=text[:1000], limitations=["No equivale a insights nativos de la plataforma."])
    expected = EXPECTED_FIELDS.get(platform, [])
    missing = [f for f in expected if f not in collected]
    status = "partial" if collected or len(text.split()) > 40 else "blocked_by_platform"
    reason_code = "insufficient_public_data" if status == "partial" else "blocked_by_platform"
    return {
        "reports": [
            collector_report(
                collector,
                platform,
                status,
                "public_html_best_effort",
                normalized,
                collected_fields=collected,
                missing_fields=missing,
                reason_code=reason_code,
                confidence="low" if status == "partial" else "none",
                details={"http_status": resp.get("status_code"), "final_url": resp.get("final_url"), "word_count": len(text.split()), "parsed_public_data": parsed_data},
            )
        ],
        "summary": {"parsed_public_data": parsed_data, "word_count": len(text.split())},
    }


def parse_youtube_identifier(url: str) -> Dict[str, Optional[str]]:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    parts = path.split("/") if path else []
    out = {"channel_id": None, "handle": None, "query": None}
    if not parts:
        return out
    if parts[0] == "channel" and len(parts) > 1:
        out["channel_id"] = parts[1]
    elif parts[0].startswith("@"):
        out["handle"] = parts[0].lstrip("@")
    elif parts[0] in {"c", "user"} and len(parts) > 1:
        out["query"] = parts[1]
    elif "youtu.be" in parsed.netloc or parts[0] == "watch":
        out["query"] = url
    else:
        out["query"] = parts[-1]
    return out


async def youtube_api_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if httpx is None:
        raise RuntimeError("httpx no est\u00e1 disponible")
    params = dict(params)
    params["key"] = YOUTUBE_API_KEY
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"https://www.googleapis.com/youtube/v3/{path}", params=params)
    if resp.status_code >= 400:
        raise RuntimeError(f"YouTube API HTTP {resp.status_code}: {truncate(resp.text, 300)}")
    return resp.json()


async def collect_youtube(url: Optional[str], evidence: EvidenceBuilder) -> Dict[str, Any]:
    platform = "youtube"
    collector = "youtube_data_api_collector"
    if not url:
        return {"reports": [collector_report(collector, platform, "skipped_missing_input", "youtube_data_api", None, reason_code="missing_input", confidence="none")], "summary": {}}
    if not YOUTUBE_API_KEY:
        return {"reports": [collector_report(collector, platform, "skipped_missing_api_key", "youtube_data_api", url, reason_code="missing_api_key", confidence="none")], "summary": {}}
    normalized = normalize_url(url)
    assert normalized is not None
    try:
        ident = parse_youtube_identifier(normalized)
        channel_data = None
        if ident.get("channel_id"):
            channel_data = await youtube_api_get("channels", {"part": "snippet,statistics,contentDetails", "id": ident["channel_id"]})
        elif ident.get("handle"):
            # YouTube supports forHandle on channels.list for public handles.
            channel_data = await youtube_api_get("channels", {"part": "snippet,statistics,contentDetails", "forHandle": ident["handle"]})
        if not channel_data or not channel_data.get("items"):
            query = ident.get("query") or ident.get("handle") or normalized
            search = await youtube_api_get("search", {"part": "snippet", "q": query, "type": "channel", "maxResults": 1})
            items = search.get("items") or []
            if items:
                channel_id = items[0].get("snippet", {}).get("channelId")
                channel_data = await youtube_api_get("channels", {"part": "snippet,statistics,contentDetails", "id": channel_id})
        items = channel_data.get("items") if channel_data else []
        if not items:
            return {"reports": [collector_report(collector, platform, "partial", "youtube_data_api", normalized, reason="No se pudo resolver el canal desde el link recibido.", missing_fields=EXPECTED_FIELDS[platform], confidence="low")], "summary": {}}
        channel = items[0]
        snippet = channel.get("snippet", {})
        stats = channel.get("statistics", {})
        content = channel.get("contentDetails", {})
        collected = ["channel_id", "channel_title", "channel_description", "published_at", "video_count", "view_count"]
        if "subscriberCount" in stats:
            collected.append("subscriber_count")
        latest_videos: List[Dict[str, Any]] = []
        uploads = (((content.get("relatedPlaylists") or {}).get("uploads")))
        if uploads:
            pl = await youtube_api_get("playlistItems", {"part": "snippet,contentDetails", "playlistId": uploads, "maxResults": 5})
            video_ids = [it.get("contentDetails", {}).get("videoId") for it in (pl.get("items") or []) if it.get("contentDetails", {}).get("videoId")]
            if video_ids:
                vids = await youtube_api_get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(video_ids), "maxResults": 5})
                for v in vids.get("items") or []:
                    latest_videos.append(
                        {
                            "video_id": v.get("id"),
                            "title": v.get("snippet", {}).get("title"),
                            "published_at": v.get("snippet", {}).get("publishedAt"),
                            "view_count": (v.get("statistics") or {}).get("viewCount"),
                            "like_count": (v.get("statistics") or {}).get("likeCount"),
                            "comment_count": (v.get("statistics") or {}).get("commentCount"),
                        }
                    )
                collected.extend(["latest_videos", "video_dates", "video_views"])
        collected = list(dict.fromkeys(collected))
        missing = [f for f in EXPECTED_FIELDS[platform] if f not in collected]
        summary = {
            "channel_id": channel.get("id"),
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "published_at": snippet.get("publishedAt"),
            "statistics": stats,
            "latest_videos": latest_videos,
        }
        evidence.add(platform, normalized, collector, "youtube_channel_statistics", summary, "high", limitations=["subscriberCount puede estar oculto por configuraci\u00f3n del canal."])
        return {
            "reports": [
                collector_report(
                    collector,
                    platform,
                    "completed" if len(collected) >= 6 else "partial",
                    "youtube_data_api",
                    normalized,
                    collected_fields=collected,
                    missing_fields=missing,
                    reason_code=None if len(collected) >= 6 else "insufficient_public_data",
                    confidence="high",
                    details=summary,
                )
            ],
            "summary": summary,
        }
    except Exception as exc:
        return {"reports": [collector_report(collector, platform, "failed_runtime", "youtube_data_api", normalized, reason=str(exc), confidence="none")], "summary": {}}


async def composio_api_request(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout_seconds: float = 45.0,
) -> Dict[str, Any]:
    if httpx is None:
        return {
            "ok": False,
            "status_code": None,
            "error": "missing_dependency_httpx",
            "data": None,
        }

    if not COMPOSIO_API_KEY:
        return {
            "ok": False,
            "status_code": None,
            "error": "missing_composio_api_key",
            "data": None,
        }

    url = f"{COMPOSIO_API_BASE}{path}"
    headers = {
        "x-api-key": COMPOSIO_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.request(
                method.upper(),
                url,
                headers=headers,
                params=params,
                json=json_body,
            )

        try:
            data = resp.json()
        except Exception:
            data = {"raw_text": resp.text[:5000]}

        return {
            "ok": 200 <= resp.status_code < 300,
            "status_code": resp.status_code,
            "error": None if 200 <= resp.status_code < 300 else "composio_http_error",
            "data": data,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "error": f"composio_request_exception: {exc}",
            "data": None,
        }


async def composio_list_tools(toolkit_slug: str = "search_api", query: str = "search") -> Dict[str, Any]:
    params = {
        "toolkit_versions": "latest",
        "limit": 50,
    }
    if toolkit_slug:
        params["toolkit_slug"] = toolkit_slug
    if query:
        params["query"] = query

    return await composio_api_request("GET", "/tools", params=params)


async def composio_execute_tool(
    tool_slug: str,
    text: Optional[str] = None,
    arguments: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    connected_account_id: Optional[str] = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "user_id": user_id or COMPOSIO_DEFAULT_USER_ID,
    }

    account_id = connected_account_id or COMPOSIO_CONNECTED_ACCOUNT_ID
    if account_id:
        body["connected_account_id"] = account_id

    if arguments:
        body["arguments"] = arguments
    else:
        body["text"] = text or "Search public web and return relevant public URLs."

    return await composio_api_request("POST", f"/tools/execute/{tool_slug}", json_body=body, timeout_seconds=60.0)



def build_search_query(company_name: Optional[str] = None, website: Optional[str] = None, raw_query: Optional[str] = None) -> str:
    parts: List[str] = []
    if raw_query:
        parts.append(str(raw_query).strip())
    if company_name:
        parts.append(str(company_name).strip())
    if website:
        parts.append(str(website).strip())
    return " ".join([p for p in parts if p]).strip()


def classify_provider_error(status_code: Optional[int], text: str = "") -> Optional[str]:
    if status_code == 429:
        return "rate_limited"
    if status_code in {401, 403}:
        return "auth_error"
    if status_code and status_code >= 500:
        return "provider_server_error"
    if status_code and status_code >= 400:
        return "provider_http_error"
    if text:
        low = text.lower()
        if "rate limit" in low or "quota" in low or "credits" in low:
            return "rate_limited"
    return None


def normalize_search_results(provider: str, data: Any, max_results: int = 10) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    def _add(title: Any, url: Any, snippet: Any = None, position: Optional[int] = None, score: Any = None, kind: str = "organic") -> None:
        if not url:
            return
        url_str = str(url).strip()
        if not url_str:
            return
        results.append(
            {
                "provider": provider,
                "kind": kind,
                "title": truncate(str(title or ""), 180),
                "url": url_str,
                "snippet": truncate(str(snippet or ""), 320),
                "position": position,
                "score": score,
            }
        )

    if not isinstance(data, dict):
        return results

    if provider == "tavily":
        for idx, item in enumerate(data.get("results") or [], start=1):
            if isinstance(item, dict):
                _add(
                    item.get("title"),
                    item.get("url"),
                    item.get("content") or item.get("raw_content"),
                    idx,
                    item.get("score"),
                )

    elif provider == "serper":
        kg = data.get("knowledgeGraph")
        if isinstance(kg, dict):
            _add(kg.get("title"), kg.get("website") or kg.get("descriptionLink"), kg.get("description"), 0, None, "knowledge_graph")
        for idx, item in enumerate(data.get("organic") or [], start=1):
            if isinstance(item, dict):
                _add(item.get("title"), item.get("link"), item.get("snippet"), item.get("position") or idx)
        places = data.get("places") or data.get("localResults", {}).get("places") if isinstance(data.get("localResults"), dict) else []
        if isinstance(places, list):
            for idx, item in enumerate(places[:3], start=1):
                if isinstance(item, dict):
                    _add(item.get("title"), item.get("website") or item.get("link"), item.get("address") or item.get("phone"), idx, None, "local")

    elif provider == "composio":
        # Composio/SearchApi can wrap data in multiple shapes depending on toolkit/version.
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        for key in ("organic_results", "organic"):
            for idx, item in enumerate(payload.get(key) or [], start=1):
                if isinstance(item, dict):
                    _add(item.get("title"), item.get("link") or item.get("url"), item.get("snippet") or item.get("description"), item.get("position") or idx)

    seen = set()
    deduped: List[Dict[str, Any]] = []
    for item in results:
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
        if len(deduped) >= max_results:
            break
    return deduped


async def tavily_search(query: str, max_results: int = 8) -> Dict[str, Any]:
    provider = "tavily"
    if not TAVILY_API_KEY:
        return {"provider": provider, "ok": False, "status_code": None, "error": "missing_api_key", "results": [], "raw": None}
    if httpx is None:
        return {"provider": provider, "ok": False, "status_code": None, "error": "missing_dependency_httpx", "results": [], "raw": None}

    payload = {
        "query": query,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
        "max_results": max_results,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                headers={
                    "Authorization": f"Bearer {TAVILY_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                },
                json=payload,
            )

        try:
            data = resp.json()
        except Exception:
            data = {"raw_text": resp.text[:5000]}

        results = normalize_search_results(provider, data, max_results=max_results)
        error = classify_provider_error(resp.status_code, resp.text)
        if 200 <= resp.status_code < 300 and results:
            return {"provider": provider, "ok": True, "status_code": resp.status_code, "error": None, "results": results, "raw": data}
        return {
            "provider": provider,
            "ok": False,
            "status_code": resp.status_code,
            "error": error or ("no_search_results" if 200 <= resp.status_code < 300 else "provider_http_error"),
            "results": results,
            "raw": data,
        }
    except Exception as exc:
        return {"provider": provider, "ok": False, "status_code": None, "error": f"provider_exception: {exc}", "results": [], "raw": None}


async def serper_search(query: str, max_results: int = 8, gl: str = "ar", hl: str = "es") -> Dict[str, Any]:
    provider = "serper"
    if not SERPER_API_KEY:
        return {"provider": provider, "ok": False, "status_code": None, "error": "missing_api_key", "results": [], "raw": None}
    if httpx is None:
        return {"provider": provider, "ok": False, "status_code": None, "error": "missing_dependency_httpx", "results": [], "raw": None}

    payload = {
        "q": query,
        "num": max_results,
        "gl": gl,
        "hl": hl,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": SERPER_API_KEY,
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                },
                json=payload,
            )

        try:
            data = resp.json()
        except Exception:
            data = {"raw_text": resp.text[:5000]}

        results = normalize_search_results(provider, data, max_results=max_results)
        error = classify_provider_error(resp.status_code, resp.text)
        if 200 <= resp.status_code < 300 and results:
            return {"provider": provider, "ok": True, "status_code": resp.status_code, "error": None, "results": results, "raw": data}
        return {
            "provider": provider,
            "ok": False,
            "status_code": resp.status_code,
            "error": error or ("no_search_results" if 200 <= resp.status_code < 300 else "provider_http_error"),
            "results": results,
            "raw": data,
        }
    except Exception as exc:
        return {"provider": provider, "ok": False, "status_code": None, "error": f"provider_exception: {exc}", "results": [], "raw": None}


async def composio_search_fallback(query: str, max_results: int = 8) -> Dict[str, Any]:
    provider = "composio_search_api"
    if not COMPOSIO_API_KEY:
        return {"provider": provider, "ok": False, "status_code": None, "error": "missing_api_key", "results": [], "raw": None}
    if not COMPOSIO_SEARCH_TOOL_SLUG:
        return {"provider": provider, "ok": False, "status_code": None, "error": "missing_composio_search_tool_slug", "results": [], "raw": None}

    arguments = {"engine": "google", "q": query, "gl": "ar", "hl": "es", "num": max_results}
    result = await composio_execute_tool(
        tool_slug=COMPOSIO_SEARCH_TOOL_SLUG,
        arguments=arguments,
        user_id=COMPOSIO_DEFAULT_USER_ID,
    )

    data = result.get("data")
    results = normalize_search_results("composio", data, max_results=max_results)
    if result.get("ok") and results:
        return {"provider": provider, "ok": True, "status_code": result.get("status_code"), "error": None, "results": results, "raw": data}

    raw_text = json.dumps(data, ensure_ascii=False, default=str)[:1500] if data is not None else ""
    return {
        "provider": provider,
        "ok": False,
        "status_code": result.get("status_code"),
        "error": classify_provider_error(result.get("status_code"), raw_text) or result.get("error") or "provider_failed",
        "results": results,
        "raw": data,
    }


def build_search_provider_config() -> Dict[str, Any]:
    return {
        "configured": {
            "tavily": bool(TAVILY_API_KEY),
            "serper": bool(SERPER_API_KEY),
            "composio_search_api": bool(COMPOSIO_API_KEY and COMPOSIO_SEARCH_TOOL_SLUG),
            "firecrawl_extractor": bool(FIRECRAWL_API_KEY),
        },
        "provider_order": [
            "tavily",
            "serper",
            "composio_search_api",
        ],
        "notes": {
            "tavily": "Proveedor principal de discovery/search. No reemplaza Firecrawl para extracci\u00f3n profunda.",
            "serper": "Fallback SERP Google. Usar para discovery cuando Tavily falla o no devuelve URLs suficientes.",
            "composio_search_api": "Fallback final; hoy depende de SearchApi.io y puede fallar por cuota 429.",
            "firecrawl_extractor": "Extractor/crawler complementario para leer URLs encontradas.",
        },
    }


async def run_search_provider_router(
    query: str,
    max_results: int = 8,
    gl: str = "ar",
    hl: str = "es",
    use_fallbacks: bool = True,
) -> Dict[str, Any]:
    query = collapse_ws(query)
    if not query:
        return {
            "status": "skipped_missing_input",
            "query": query,
            "selected_provider": None,
            "results": [],
            "attempts": [],
            "reason_code": "missing_input",
            "provider_config": build_search_provider_config(),
        }

    attempts: List[Dict[str, Any]] = []

    provider_calls = [
        ("tavily", lambda: tavily_search(query, max_results=max_results)),
        ("serper", lambda: serper_search(query, max_results=max_results, gl=gl, hl=hl)),
        ("composio_search_api", lambda: composio_search_fallback(query, max_results=max_results)),
    ]

    for provider_name, call in provider_calls:
        if attempts and not use_fallbacks:
            break

        result = await call()
        raw = result.pop("raw", None)
        safe_attempt = dict(result)
        safe_attempt["raw_sample"] = truncate(json.dumps(raw, ensure_ascii=False, default=str), 1200) if raw is not None else None
        attempts.append(safe_attempt)

        if result.get("ok") and result.get("results"):
            return {
                "status": "completed",
                "query": query,
                "selected_provider": provider_name,
                "results": result.get("results", []),
                "attempts": attempts,
                "reason_code": None,
                "provider_config": build_search_provider_config(),
            }

    configured_any = bool(TAVILY_API_KEY or SERPER_API_KEY or (COMPOSIO_API_KEY and COMPOSIO_SEARCH_TOOL_SLUG))
    return {
        "status": "failed_runtime" if configured_any else "skipped_missing_api_key",
        "query": query,
        "selected_provider": None,
        "results": [],
        "attempts": attempts,
        "reason_code": "all_search_providers_failed" if configured_any else "missing_api_key",
        "provider_config": build_search_provider_config(),
    }



async def collect_public_search_enrichment(
    company_name: Optional[str],
    website: Optional[str],
    evidence: Optional[EvidenceBuilder] = None,
) -> Dict[str, Any]:
    collector = "public_search_provider_router"
    platform = "search"

    query = build_search_query(company_name=company_name, website=website)
    if not query:
        return {
            "reports": [
                collector_report(
                    collector,
                    platform,
                    "skipped_missing_input",
                    "search_provider_router",
                    None,
                    intended_data=EXPECTED_FIELDS["search"],
                    reason_code="missing_input",
                    confidence="none",
                )
            ],
            "summary": {},
        }

    result = await run_search_provider_router(query=query, max_results=8, gl="ar", hl="es", use_fallbacks=True)
    results = result.get("results") or []
    selected_provider = result.get("selected_provider")
    status = result.get("status") or "failed_runtime"
    reason_code = result.get("reason_code")

    if evidence is not None:
        for item in results[:8]:
            evidence.add(
                platform,
                item.get("url"),
                collector,
                "public_search_result",
                {
                    "provider": item.get("provider"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("snippet"),
                    "position": item.get("position"),
                },
                "medium",
                raw_excerpt=item.get("snippet") or "",
                limitations=[
                    "Resultado de b\u00fasqueda usado para discovery; el snippet no reemplaza extracci\u00f3n directa de la fuente.",
                    "Usar Firecrawl/Browserbase para validar contenido de URLs relevantes.",
                ],
            )

    summary = {
        "query": query,
        "selected_provider": selected_provider,
        "status": status,
        "results_count": len(results),
        "results": results,
        "attempts": result.get("attempts") or [],
        "provider_config": result.get("provider_config") or build_search_provider_config(),
    }

    return {
        "reports": [
            collector_report(
                collector,
                platform,
                status,
                selected_provider or "search_provider_router",
                website,
                intended_data=EXPECTED_FIELDS["search"],
                collected_fields=["public_search_results", "provider_used", "fallback_attempts"] if results else [],
                missing_fields=[] if results else ["public_search_results", "possible_profiles", "mentions"],
                reason_code=reason_code,
                confidence="medium" if results else "none",
                details=summary,
            )
        ],
        "summary": summary,
    }


async def collect_composio_search_placeholder(company_name: Optional[str], website: Optional[str]) -> Dict[str, Any]:
    # Backward-compatible wrapper. New logic uses Tavily -> Serper -> Composio fallback.
    return await collect_public_search_enrichment(company_name, website, evidence=None)

def merge_assets(req: PublicPresenceCollectRequest) -> Dict[str, Optional[str]]:
    assets = {
        "website": req.website or req.website_url,
        "instagram": req.instagram,
        "facebook": req.facebook,
        "linkedin": req.linkedin,
        "youtube": req.youtube,
        "tiktok": req.tiktok,
        "x": req.x,
    }
    if req.assets:
        nested = req.assets
        for key in assets.keys():
            val = getattr(nested, key, None)
            if val and not assets.get(key):
                assets[key] = val
    return {k: normalize_url(v) if v else None for k, v in assets.items()}


def summarize_execution(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for r in reports:
        counts[r.get("status", "unknown")] = counts.get(r.get("status", "unknown"), 0) + 1
    hard_fail = counts.get("failed_runtime", 0)
    completed = counts.get("completed", 0)
    partial = counts.get("partial", 0)
    limitations = counts.get("blocked_by_platform", 0) + counts.get("skipped_missing_api_key", 0) + counts.get("collector_not_implemented", 0) + partial
    if completed and not hard_fail and not limitations:
        status = "completed"
    elif completed or partial:
        status = "completed_with_limitations"
    elif hard_fail:
        status = "failed"
    else:
        status = "not_collected"
    return {
        "overall_status": status,
        "collectors_attempted_or_evaluated": len(reports),
        "collectors_completed": completed,
        "collectors_partial": partial,
        "collectors_skipped": counts.get("skipped_missing_input", 0) + counts.get("skipped_missing_api_key", 0),
        "collectors_failed": hard_fail,
        "collectors_blocked_by_platform": counts.get("blocked_by_platform", 0),
        "collectors_not_implemented": counts.get("collector_not_implemented", 0),
        "status_counts": counts,
    }


def _status_rank(status: Optional[str]) -> int:
    order = {
        "completed": 6,
        "completed_with_limitations": 5,
        "partial": 4,
        "collector_not_implemented": 3,
        "skipped_missing_api_key": 2,
        "skipped_missing_input": 1,
        "blocked_by_platform": 1,
        "failed_runtime": 0,
    }
    return order.get(str(status or "unknown"), 0)


def aggregate_platform_status(collector_reports: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    platforms: Dict[str, Dict[str, Any]] = {}
    for report in collector_reports:
        platform = report.get("platform") or "unknown"
        bucket = platforms.setdefault(
            platform,
            {
                "statuses": [],
                "collectors": [],
                "best_status": "unknown",
                "aggregate_status": "unknown",
                "confidence": "none",
                "completed_collectors": 0,
                "partial_collectors": 0,
                "failed_collectors": 0,
                "limitations": [],
            },
        )
        status = str(report.get("status") or "unknown")
        bucket["statuses"].append(status)
        bucket["collectors"].append(report.get("collector"))
        if status == "completed":
            bucket["completed_collectors"] += 1
        elif status == "partial":
            bucket["partial_collectors"] += 1
        elif status == "failed_runtime":
            bucket["failed_collectors"] += 1
        if _status_rank(status) > _status_rank(bucket.get("best_status")):
            bucket["best_status"] = status
            bucket["confidence"] = report.get("confidence") or bucket.get("confidence") or "none"
        if report.get("reason"):
            bucket["limitations"].append(report.get("reason"))

    for platform, bucket in platforms.items():
        statuses = bucket.get("statuses") or []
        if "completed" in statuses and any(s in statuses for s in ["partial", "collector_not_implemented", "skipped_missing_api_key", "blocked_by_platform", "failed_runtime"]):
            aggregate = "completed_with_limitations"
        elif "completed" in statuses:
            aggregate = "completed"
        elif "partial" in statuses:
            aggregate = "partial"
        elif "collector_not_implemented" in statuses:
            aggregate = "not_implemented"
        elif any(s.startswith("skipped") for s in statuses):
            aggregate = "not_collected"
        elif "failed_runtime" in statuses:
            aggregate = "failed"
        else:
            aggregate = bucket.get("best_status") or "unknown"
        bucket["aggregate_status"] = aggregate
        bucket["collectors"] = [c for c in dict.fromkeys([c for c in bucket.get("collectors", []) if c])]
        bucket["limitations"] = list(dict.fromkeys([str(x) for x in bucket.get("limitations", []) if x]))[:6]
    return platforms


def build_metrics_summary(evidence_items: List[Dict[str, Any]], collector_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_platform: Dict[str, Dict[str, Any]] = {}
    platform_status = aggregate_platform_status(collector_reports)
    for ev in evidence_items:
        platform = ev.get("platform") or "unknown"
        bucket = by_platform.setdefault(platform, {"evidence_count": 0, "data_types": []})
        bucket["evidence_count"] += 1
        bucket["data_types"].append(ev.get("data_type"))
    for platform in set(list(by_platform.keys()) + list(platform_status.keys())):
        bucket = by_platform.setdefault(platform, {"evidence_count": 0, "data_types": []})
        bucket["data_types"] = sorted(set([x for x in bucket.get("data_types", []) if x]))
        status_info = platform_status.get(platform) or {}
        bucket["collector_status"] = status_info.get("aggregate_status", "n/d")
        bucket["best_collector_status"] = status_info.get("best_status", "n/d")
        bucket["confidence"] = status_info.get("confidence", "n/d")
        bucket["collectors"] = status_info.get("collectors", [])
        bucket["limitations"] = status_info.get("limitations", [])
    return by_platform


def dedupe_recovery_guide(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    priority_status = {"requires_owner_access": 4, "not_collected": 3, "partial": 2}
    priority_importance = {"alta": 4, "media-alta": 3, "media": 2, "baja": 1}
    selected: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for item in items:
        platform = str(item.get("platform") or "unknown")
        field = str(item.get("field") or item.get("label_es") or "unknown")
        key = (platform, field)
        current = selected.get(key)
        score = priority_status.get(str(item.get("status")), 0) * 10 + priority_importance.get(str(item.get("importance")), 0)
        current_score = -1
        if current:
            current_score = priority_status.get(str(current.get("status")), 0) * 10 + priority_importance.get(str(current.get("importance")), 0)
        if current is None or score > current_score:
            selected[key] = item
    return sorted(
        selected.values(),
        key=lambda x: (
            0 if x.get("requires_client_permission") else 1,
            -priority_importance.get(str(x.get("importance")), 0),
            str(x.get("platform") or ""),
            str(x.get("field") or ""),
        ),
    )


def _evidence_values(evidence_items: List[Dict[str, Any]], platform: Optional[str] = None, data_type: Optional[str] = None) -> List[Dict[str, Any]]:
    out = []
    for ev in evidence_items:
        if platform and ev.get("platform") != platform:
            continue
        if data_type and ev.get("data_type") != data_type:
            continue
        out.append(ev)
    return out


def build_public_presence_score(payload: Dict[str, Any]) -> Dict[str, Any]:
    evidence_items = payload.get("evidence_registry") or []
    reports = payload.get("collector_reports") or []
    metrics = payload.get("metrics_summary") or {}

    website_types = set((metrics.get("website") or {}).get("data_types") or [])
    social_platforms = ["instagram", "facebook", "linkedin", "tiktok", "youtube", "x"]
    social_detected = [p for p in social_platforms if (metrics.get(p) or {}).get("evidence_count", 0) > 0]
    search_completed = any(r.get("collector") == "public_search_provider_router" and r.get("status") == "completed" for r in reports)
    firecrawl_completed = any(r.get("collector") == "firecrawl_website_collector" and r.get("status") == "completed" for r in reports)
    website_completed = any(r.get("platform") == "website" and r.get("status") == "completed" for r in reports)

    website_score = 0
    if website_completed:
        website_score += 12
    if firecrawl_completed:
        website_score += 8
    for dtype in ["title", "visible_text_sample", "firecrawl_markdown_sample", "services_or_products", "pricing", "website_claims", "robots_txt", "sitemap_xml"]:
        if dtype in website_types:
            website_score += 2
    website_score = min(35, website_score)

    search_score = 20 if search_completed else 0
    search_evidence_count = len(_evidence_values(evidence_items, "search", "public_search_result"))
    search_score += min(5, search_evidence_count)
    search_score = min(25, search_score)

    social_score = min(20, len(social_detected) * 4)
    if "linkedin" in social_detected:
        social_score += 2
    social_score = min(20, social_score)

    data_quality_score = 0
    if len(evidence_items) >= 10:
        data_quality_score += 5
    if len(evidence_items) >= 20:
        data_quality_score += 5
    if any(ev.get("limitations") for ev in evidence_items):
        data_quality_score += 3
    if payload.get("field_recovery_guide"):
        data_quality_score += 2
    data_quality_score = min(15, data_quality_score)

    guardrail_score = 5
    total = int(min(100, website_score + search_score + social_score + data_quality_score + guardrail_score))

    if total >= 75:
        level = "fuerte"
    elif total >= 55:
        level = "media"
    elif total >= 35:
        level = "b\u00e1sica"
    else:
        level = "d\u00e9bil"

    return {
        "score": total,
        "level": level,
        "scale": "0-100",
        "components": {
            "website_public_evidence": website_score,
            "search_discovery": search_score,
            "social_public_presence": social_score,
            "data_quality_and_traceability": data_quality_score,
            "guardrails": guardrail_score,
        },
        "interpretation": "Score de presencia p\u00fablica observable. No mide ventas, ROAS, CPA, CPL, conversi\u00f3n ni calidad de lead.",
        "signals": {
            "website_completed": website_completed,
            "firecrawl_completed": firecrawl_completed,
            "search_completed": search_completed,
            "social_profiles_detected": social_detected,
            "search_results_count": search_evidence_count,
        },
    }


def build_executive_public_audit(payload: Dict[str, Any]) -> Dict[str, Any]:
    evidence_items = payload.get("evidence_registry") or []
    metrics = payload.get("metrics_summary") or {}
    score = payload.get("public_presence_score") or build_public_presence_score(payload)
    assets = payload.get("assets_received") or {}

    website_texts = _evidence_values(evidence_items, "website")
    search_results = _evidence_values(evidence_items, "search", "public_search_result")
    linkedin_samples = _evidence_values(evidence_items, "linkedin")

    findings: List[Dict[str, Any]] = []
    if (metrics.get("website") or {}).get("evidence_count", 0):
        findings.append({
            "area": "Sitio web",
            "finding": "El sitio p\u00fablico fue le\u00eddo con collector est\u00e1tico y Firecrawl; hay evidencia de propuesta comercial, productos, claims y p\u00e1ginas indexables.",
            "evidence": "website_static_collector + firecrawl_website_collector",
            "risk_or_opportunity": "Base suficiente para auditor\u00eda p\u00fablica inicial, pero conviene profundizar p\u00e1ginas internas cr\u00edticas como compras mayoristas, contacto y categor\u00edas.",
        })
    if search_results:
        findings.append({
            "area": "B\u00fasqueda p\u00fablica",
            "finding": f"El router de b\u00fasqueda encontr\u00f3 {len(search_results)} resultados p\u00fablicos relevantes usando Tavily.",
            "evidence": ", ".join([str(ev.get("source_url")) for ev in search_results[:4] if ev.get("source_url")]),
            "risk_or_opportunity": "Hay superficie p\u00fablica suficiente para discovery; los snippets deben validarse con extracci\u00f3n directa antes de usarse como prueba fuerte.",
        })
    social_detected = [p for p in ["instagram", "facebook", "linkedin", "tiktok"] if (metrics.get(p) or {}).get("evidence_count", 0) > 0]
    if social_detected:
        findings.append({
            "area": "Redes sociales",
            "finding": "Se detectaron perfiles p\u00fablicos en: " + ", ".join(social_detected) + ".",
            "evidence": "metadata p\u00fablica best-effort",
            "risk_or_opportunity": "Las plataformas limitan m\u00e9tricas y posteos sin autorizaci\u00f3n; para an\u00e1lisis de performance hacen falta accesos o export manual del cliente.",
        })
    if linkedin_samples:
        findings.append({
            "area": "LinkedIn",
            "finding": "LinkedIn entreg\u00f3 se\u00f1ales p\u00fablicas \u00fatiles, incluyendo t\u00edtulo, muestra textual y followers visibles cuando estuvieron disponibles.",
            "evidence": "linkedin_public_collector",
            "risk_or_opportunity": "Puede usarse como evidencia p\u00fablica de posicionamiento B2B, no como insight interno de performance.",
        })

    recommendations = [
        {
            "priority": "alta",
            "action": "Validar y extraer p\u00e1ginas internas descubiertas por b\u00fasqueda: sobre-nosotros, compras-mayoristas, sucursales-contacto y categor\u00edas comerciales.",
            "impact": "alto",
            "effort": "medio",
            "reason": "El discovery ya encontr\u00f3 URLs de valor; falta convertirlas en evidencia extra\u00edda y resumida.",
        },
        {
            "priority": "alta",
            "action": "Separar claramente evidencia p\u00fablica, claims declarados y datos que requieren acceso privado.",
            "impact": "alto",
            "effort": "bajo",
            "reason": "Evita inferencias falsas sobre ventas, performance o calidad de lead.",
        },
        {
            "priority": "media-alta",
            "action": "Usar Browserbase visual debug para capturar screenshots de home, contacto, compras mayoristas y perfiles sociales prioritarios.",
            "impact": "medio-alto",
            "effort": "medio",
            "reason": "Aporta prueba visual cuando HTML/Firecrawl no alcanza o la p\u00e1gina depende de JavaScript.",
        },
        {
            "priority": "media",
            "action": "Solicitar al cliente exports o capturas fechadas de Meta Business Suite, LinkedIn, TikTok, GA4, Search Console y CRM si se quiere diagnosticar performance.",
            "impact": "alto",
            "effort": "alto",
            "reason": "Los datos internos no son p\u00fablicos y no deben inferirse desde presencia p\u00fablica.",
        },
    ]

    matrix = [
        {"initiative": "Deduplicar y compactar datos faltantes en el reporte", "impact": "medio", "effort": "bajo"},
        {"initiative": "Extraer p\u00e1ginas internas descubiertas por Tavily con Firecrawl", "impact": "alto", "effort": "medio"},
        {"initiative": "Capturar screenshots con Browserbase para evidencia visual", "impact": "medio-alto", "effort": "medio"},
        {"initiative": "Conectar datos privados del cliente para performance real", "impact": "muy alto", "effort": "alto"},
    ]

    return {
        "summary": f"La presencia p\u00fablica observable es {score.get('level')} ({score.get('score')}/100). El sistema encontr\u00f3 sitio, evidencia textual, perfiles/redes y resultados p\u00fablicos; las m\u00e9tricas de performance siguen fuera de alcance sin acceso del cliente.",
        "readiness_level": score.get("level"),
        "score": score.get("score"),
        "key_findings": findings,
        "priority_recommendations": recommendations,
        "impact_effort_matrix": matrix,
        "critical_limitations": [
            "No mide ventas, ROAS, CPA, CPL, conversi\u00f3n ni calidad de lead.",
            "Los snippets de b\u00fasqueda sirven para discovery, no como prueba definitiva.",
            "Instagram, Facebook, LinkedIn y TikTok pueden ocultar m\u00e9tricas o requerir login/API/autorizaci\u00f3n.",
        ],
        "next_data_requests": [
            "GA4 / Search Console para tr\u00e1fico org\u00e1nico, eventos y p\u00e1ginas principales.",
            "Google Ads / Meta Ads para inversi\u00f3n, leads, costos y conversiones.",
            "Meta Business Suite / LinkedIn / TikTok exports para alcance, interacciones y posteos.",
            "CRM/ventas para calidad de lead, cierre y revenue.",
        ],
        "assets_analyzed": assets,
    }


def _format_json_value(value: Any, limit: int = 1200) -> str:
    if isinstance(value, (dict, list)):
        return truncate(json.dumps(value, ensure_ascii=False, indent=2), limit)
    return truncate(str(value), limit)


def build_txt_report(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    score = payload.get("public_presence_score") or {}
    audit = payload.get("executive_public_audit") or {}
    metrics = payload.get("metrics_summary") or {}
    recovery_deduped = dedupe_recovery_guide(payload.get("field_recovery_guide") or [])
    evidence_items = payload.get("evidence_registry") or []

    lines.append("AUDITOR\u00cdA DE PRESENCIA DIGITAL P\u00daBLICA")
    lines.append("=" * 58)
    lines.append("")
    lines.append(f"Empresa: {payload.get('company_name') or 'No informada'}")
    lines.append(f"Fecha de recolecci\u00f3n: {payload.get('created_at')}")
    lines.append(f"Versi\u00f3n del collector: {payload.get('collector_version')}")
    lines.append(f"Estado general: {payload.get('collection_status')}")
    lines.append(f"Hash de recolecci\u00f3n: {payload.get('collection_hash')}")
    lines.append("")

    lines.append("1. RESUMEN EJECUTIVO")
    lines.append(audit.get("summary") or "No se gener\u00f3 resumen ejecutivo.")
    lines.append("")
    lines.append(f"Score de presencia p\u00fablica: {score.get('score', 'n/d')}/100")
    lines.append(f"Nivel: {score.get('level', 'n/d')}")
    lines.append("Nota: este score mide presencia p\u00fablica observable, no performance comercial.")
    lines.append("")

    lines.append("2. FUENTES RECIBIDAS")
    for k, v in (payload.get("assets_received") or {}).items():
        lines.append(f"- {k}: {v or 'no recibido'}")
    lines.append("")

    lines.append("3. SCORE Y COMPONENTES")
    for name, value in (score.get("components") or {}).items():
        lines.append(f"- {name}: {value}")
    signals = score.get("signals") or {}
    if signals:
        lines.append("Se\u00f1ales usadas:")
        for k, v in signals.items():
            lines.append(f"  - {k}: {v}")
    lines.append("")

    lines.append("4. HALLAZGOS PRINCIPALES")
    findings = audit.get("key_findings") or []
    if findings:
        for idx, item in enumerate(findings, start=1):
            lines.append(f"{idx}. {item.get('area')}: {item.get('finding')}")
            lines.append(f"   Evidencia: {item.get('evidence')}")
            lines.append(f"   Implicancia: {item.get('risk_or_opportunity')}")
    else:
        lines.append("- No se generaron hallazgos principales.")
    lines.append("")

    lines.append("5. RECOMENDACIONES PRIORIZADAS")
    for idx, item in enumerate(audit.get("priority_recommendations") or [], start=1):
        lines.append(f"{idx}. [{item.get('priority')}] {item.get('action')}")
        lines.append(f"   Impacto: {item.get('impact')} | Esfuerzo: {item.get('effort')}")
        lines.append(f"   Motivo: {item.get('reason')}")
    lines.append("")

    lines.append("6. MATRIZ IMPACTO / ESFUERZO")
    for item in audit.get("impact_effort_matrix") or []:
        lines.append(f"- {item.get('initiative')} | Impacto: {item.get('impact')} | Esfuerzo: {item.get('effort')}")
    lines.append("")

    lines.append("7. ESTADO POR PLATAFORMA")
    for platform, data in metrics.items():
        lines.append(f"\n{platform.upper()}")
        lines.append(f"- Estado agregado: {data.get('collector_status', 'n/d')}")
        lines.append(f"- Evidencias registradas: {data.get('evidence_count', 0)}")
        lines.append(f"- Confianza: {data.get('confidence', 'n/d')}")
        types = data.get("data_types") or []
        if types:
            lines.append("- Datos observados: " + ", ".join(types[:18]))
        limitations = data.get("limitations") or []
        if limitations:
            lines.append("- Limitaciones: " + " | ".join(limitations[:3]))
    lines.append("")

    lines.append("8. EVIDENCIA DESTACADA")
    preferred = []
    preferred.extend(_evidence_values(evidence_items, "website", "firecrawl_markdown_sample")[:1])
    preferred.extend(_evidence_values(evidence_items, "website", "visible_text_sample")[:1])
    preferred.extend(_evidence_values(evidence_items, "linkedin", "public_text_sample")[:1])
    preferred.extend(_evidence_values(evidence_items, "search", "public_search_result")[:6])
    if not preferred:
        preferred = evidence_items[:8]
    for ev in preferred[:10]:
        lines.append("")
        lines.append(f"{ev.get('evidence_id')} | {ev.get('platform')} | {ev.get('data_type')}")
        lines.append(f"Fuente: {ev.get('source_url') or 'n/d'}")
        lines.append(f"Collector: {ev.get('collector')} | Confianza: {ev.get('confidence')}")
        lines.append("Valor observado:")
        lines.append(_format_json_value(ev.get("value"), limit=1200))
        if ev.get("limitations"):
            lines.append("Limitaciones: " + " | ".join([str(x) for x in ev.get("limitations", [])[:3]]))
    lines.append("")

    lines.append("9. DATOS FALTANTES CR\u00cdTICOS")
    critical = [x for x in recovery_deduped if x.get("requires_client_permission") or x.get("importance") in {"alta", "media-alta"}]
    if critical:
        for item in critical[:18]:
            lines.append("")
            lines.append(f"Campo: {item.get('label_es')} ({item.get('field')})")
            lines.append(f"Plataforma: {item.get('platform')} | Importancia: {item.get('importance')} | Permiso cliente: {'s\u00ed' if item.get('requires_client_permission') else 'no'}")
            lines.append(f"Motivo: {item.get('why_not_collected')}")
            how = item.get("how_to_collect") or []
            if how:
                lines.append("C\u00f3mo recuperarlo: " + " | ".join([str(x) for x in how[:3]]))
    else:
        lines.append("- No se detectaron faltantes cr\u00edticos.")
    lines.append("")

    lines.append("10. DATOS QUE REQUIEREN ACCESO DEL CLIENTE")
    for item in audit.get("next_data_requests") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("11. LIMITACIONES Y GUARDRAILS")
    for item in audit.get("critical_limitations") or []:
        lines.append(f"- {item}")
    lines.append("- Los claims del sitio se registran como claims declarados, no como hechos verificados externamente.")
    lines.append("- Este reporte no afirma ROAS, CPA, CPL, conversi\u00f3n, ventas ni calidad de lead.")
    lines.append("")

    lines.append("12. ANEXO T\u00c9CNICO - RESUMEN DE EJECUCI\u00d3N")
    rep = payload.get("collection_execution_report") or {}
    for key in ["collectors_attempted_or_evaluated", "collectors_completed", "collectors_partial", "collectors_skipped", "collectors_failed", "collectors_blocked_by_platform", "collectors_not_implemented"]:
        lines.append(f"- {key}: {rep.get(key, 0)}")
    lines.append("")
    lines.append("Collectors evaluados:")
    for r in payload.get("collector_reports", []):
        lines.append(f"- {r.get('collector')} | plataforma={r.get('platform')} | estado={r.get('status')} | herramienta={r.get('tool_used')}")

    return "\n".join(lines) + "\n"


def build_api_capabilities() -> Dict[str, Any]:
    return {
        "current_scope": "public_presence_collection",
        "implemented": {
            "website_static": True,
            "firecrawl_website": bool(FIRECRAWL_API_KEY),
            "browserbase_visual_debug": bool(BROWSERBASE_API_KEY),
            "visual_site_summary_endpoint": bool(BROWSERBASE_API_KEY),
            "youtube_data_api": bool(YOUTUBE_API_KEY),
            "text_report": True,
            "public_social_limited": True,
            "search_provider_router": bool(TAVILY_API_KEY or SERPER_API_KEY or (COMPOSIO_API_KEY and COMPOSIO_SEARCH_TOOL_SLUG)),
            "executive_public_audit_report": True,
            "public_presence_score": True,
        },
        "configured_but_not_implemented": {
            "browserbase_collect_integration": False,
            "composio_search_enrichment": False,
        },
        "not_implemented": {
            "visual_report_url": False,
            "visual_quality_summary_integrated": False,
            "analysis_trace": True,
            "commercial_score": True,
            "funnel_blueprint": True,
            "private_performance_audit": True,
            "automatic_mercado_libre_scraping": True,
        },
        "guards": [
            "No afirmar ventas, ROAS, CPA, CPL, trafico, conversion, margen ni calidad de lead sin evidencia privada.",
            "Detectar scripts de tracking no prueba medicion correcta.",
            "Browserbase visual debug permite screenshot/render, pero no reemplaza test de UX, PageSpeed ni datos de conversion.",
            "Mercado Libre no esta integrado automaticamente en este backend.",
        ],
    }


def build_collector_notes() -> Dict[str, str]:
    return {
        "browserbase": "Browserbase visual debug implementado en POST /debug/browser-render. Todavia no esta integrado automaticamente dentro de collectPublicPresence.",
        "search": "Router de busqueda implementado: Tavily -> Serper -> Composio/SearchApi como fallback final.",
        "report": "Reporte ejecutivo v0.5: score de presencia publica, hallazgos, recomendaciones y anexo tecnico.",
        "composio": "Integracion Composio mantenida para debug y fallback final. SEARCH_API_SEARCH puede fallar por cuota 429 de SearchApi.io.",
        "visual": "GET /deliverables/screenshot/{screenshot_id}.png devuelve screenshots generados por debugBrowserRender.",
        "visual_site": "POST /audit/visual-site renderiza home y p\u00e1ginas internas candidatas en desktop/mobile para resumen visual estructurado.",
    }


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "marketing-auditor-public-presence-collector",
        "version": APP_VERSION,
        "endpoints": [
            "GET /api/status",
            "GET /debug/search-provider-config",
            "POST /debug/search-test",
            "POST /debug/browser-render",
            "POST /audit/visual-site",
            "POST /audit/social-public",
            "POST /audit/social-auth-render",
            "GET /deliverables/social-text/{report_id}.txt",
            "POST /deliverables/upload-to-drive",
            "POST /deliverables/upload-screenshot-to-drive",
            "GET /debug/composio-tools",
            "POST /debug/composio-execute",
            "POST /collect/public-presence",
            "POST /collect/public-presence-compact",
            "GET /deliverables/screenshot/{screenshot_id}.png",
            "GET /deliverables/text/{report_id}.txt",
        ],
    }


@app.get("/api/status")
async def api_status(_: None = Depends(verify_api_key)) -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "marketing-auditor-public-presence-collector",
        "version": APP_VERSION,
        "public_base_url": PUBLIC_BASE_URL,
        "configured_tools": {
            "firecrawl": bool(FIRECRAWL_API_KEY),
            "browserbase": bool(BROWSERBASE_API_KEY),
            "composio": bool(COMPOSIO_API_KEY),
            "tavily": bool(TAVILY_API_KEY),
            "serper": bool(SERPER_API_KEY),
            "youtube": bool(YOUTUBE_API_KEY),
        },
        "capabilities": build_api_capabilities(),
        "endpoints": [
            "GET /",
            "GET /api/status",
            "GET /debug/collector-config",
            "GET /debug/social-auth-config",
            "GET /debug/search-provider-config",
            "POST /debug/search-test",
            "POST /debug/browser-render",
            "POST /audit/visual-site",
            "POST /audit/social-public",
            "POST /audit/social-auth-render",
            "GET /deliverables/social-text/{report_id}.txt",
            "POST /deliverables/upload-to-drive",
            "POST /deliverables/upload-screenshot-to-drive",
            "GET /debug/composio-tools",
            "POST /debug/composio-execute",
            "POST /collect/public-presence",
            "POST /collect/public-presence-compact",
            "GET /deliverables/screenshot/{screenshot_id}.png",
            "GET /deliverables/text/{report_id}.txt"
        ]
    }



@app.get("/debug/composio-tools")
async def debug_composio_tools(
    toolkit_slug: str = "search_api",
    query: str = "search",
    _: None = Depends(verify_api_key),
) -> Dict[str, Any]:
    result = await composio_list_tools(toolkit_slug=toolkit_slug, query=query)
    data = result.get("data") or {}
    items = data.get("items") if isinstance(data, dict) else None
    tool_slugs = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                tool_slugs.append({
                    "slug": item.get("slug"),
                    "name": item.get("name"),
                    "toolkit": (item.get("toolkit") or {}).get("slug") if isinstance(item.get("toolkit"), dict) else None,
                    "input_parameters": item.get("input_parameters"),
                })

    return {
        "status": "ok" if result.get("ok") else "failed",
        "composio_status_code": result.get("status_code"),
        "toolkit_slug": toolkit_slug,
        "query": query,
        "tool_slugs": tool_slugs,
        "raw": data,
    }


@app.post("/debug/composio-execute")
async def debug_composio_execute(payload: Dict[str, Any], _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    tool_slug = str(payload.get("tool_slug") or COMPOSIO_SEARCH_TOOL_SLUG or "").strip()
    if not tool_slug:
        raise HTTPException(status_code=400, detail="Falta tool_slug o COMPOSIO_SEARCH_TOOL_SLUG.")

    user_id = str(payload.get("user_id") or COMPOSIO_DEFAULT_USER_ID or "default").strip()
    connected_account_id = str(payload.get("connected_account_id") or COMPOSIO_CONNECTED_ACCOUNT_ID or "").strip()
    text = payload.get("text") or payload.get("query") or "Search public web for Cotill\u00f3n Chialvo C\u00f3rdoba and return public URLs."
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else None

    result = await composio_execute_tool(
        tool_slug=tool_slug,
        text=str(text),
        arguments=arguments,
        user_id=user_id,
        connected_account_id=connected_account_id or None,
    )

    return {
        "status": "ok" if result.get("ok") else "failed",
        "tool_slug": tool_slug,
        "user_id": user_id,
        "connected_account_id": connected_account_id or None,
        "composio_status_code": result.get("status_code"),
        "composio_error": result.get("error"),
        "raw": result.get("data"),
    }


@app.get("/debug/search-provider-config")
async def debug_search_provider_config(_: None = Depends(verify_api_key)) -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": APP_VERSION,
        **build_search_provider_config(),
    }


@app.post("/debug/search-test")
async def debug_search_test(req: SearchProviderDebugRequest, _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    result = await run_search_provider_router(
        query=req.query,
        max_results=req.max_results,
        gl=req.gl,
        hl=req.hl,
        use_fallbacks=req.use_fallbacks,
    )
    return {
        "status": result.get("status"),
        "query": result.get("query"),
        "selected_provider": result.get("selected_provider"),
        "results_count": len(result.get("results") or []),
        "results": result.get("results"),
        "attempts": result.get("attempts"),
        "provider_config": result.get("provider_config"),
        "reason_code": result.get("reason_code"),
    }



def _visual_url_domain(url: str) -> str:
    try:
        parse = __import__("urllib.parse", fromlist=["urlparse"]).urlparse
        return parse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _visual_join_url(base_url: str, href: str) -> str:
    try:
        join = __import__("urllib.parse", fromlist=["urljoin"]).urljoin
        return join(base_url, href)
    except Exception:
        return href


def _visual_clean_url(url: str) -> str:
    try:
        parse = __import__("urllib.parse", fromlist=["urlparse"]).urlparse
        parsed = parse(url)
        clean = parsed._replace(fragment="").geturl()
        return clean.rstrip("/")
    except Exception:
        return str(url or "").strip().rstrip("/")


def _visual_page_type(url: str, text: str = "") -> str:
    raw = f"{url} {text}".lower()

    if any(k in raw for k in ["contacto", "contact", "whatsapp"]):
        return "contact"
    if any(k in raw for k in ["carrito", "cart", "checkout", "finalizar"]):
        return "cart"
    if any(k in raw for k in ["politica", "devolucion", "envio", "shipping", "returns"]):
        return "policy"
    if any(k in raw for k in ["producto", "product", "comprar-online", "/p/"]):
        return "product"
    if any(k in raw for k in ["categoria", "category", "productos", "ofertas", "eventos", "reposteria", "decoracion"]):
        return "category"
    return "internal"


def _visual_candidate_priority(page_type: str) -> int:
    order = {
        "category": 1,
        "product": 2,
        "contact": 3,
        "cart": 4,
        "policy": 5,
        "internal": 9,
    }
    return order.get(page_type, 9)


async def _visual_fetch_html_for_links(url: str, timeout_seconds: float = 25.0) -> str:
    if httpx is None:
        return ""

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                return ""
            return resp.text or ""
    except Exception:
        return ""


def _visual_extract_links_from_html(base_url: str, html: str, limit: int = 30) -> List[Dict[str, str]]:
    if not html:
        return []

    base_domain = _visual_url_domain(base_url)
    candidates: List[Dict[str, str]] = []
    seen = set()

    soup_cls = globals().get("BeautifulSoup")

    if soup_cls is not None:
        try:
            soup = soup_cls(html, "html.parser")
            anchors = soup.find_all("a", href=True)
            for a in anchors:
                href = str(a.get("href") or "").strip()
                text = collapse_ws(a.get_text(" ", strip=True))
                if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue

                joined = _visual_clean_url(_visual_join_url(base_url, href))
                if not joined.startswith(("http://", "https://")):
                    continue
                if _visual_url_domain(joined) != base_domain:
                    continue
                if joined == _visual_clean_url(base_url):
                    continue
                if joined in seen:
                    continue

                seen.add(joined)
                page_type = _visual_page_type(joined, text)
                candidates.append({
                    "url": joined,
                    "text": truncate(text, 120),
                    "page_type": page_type,
                    "source": "html_anchor",
                })

                if len(candidates) >= limit:
                    break
        except Exception:
            pass

    if candidates:
        return candidates

    # Fallback regex b\u00e1sico si BeautifulSoup no estuviera disponible.
    try:
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html, flags=re.I):
            href = match.group(1).strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue

            joined = _visual_clean_url(_visual_join_url(base_url, href))
            if not joined.startswith(("http://", "https://")):
                continue
            if _visual_url_domain(joined) != base_domain:
                continue
            if joined == _visual_clean_url(base_url):
                continue
            if joined in seen:
                continue

            seen.add(joined)
            page_type = _visual_page_type(joined, "")
            candidates.append({
                "url": joined,
                "text": "",
                "page_type": page_type,
                "source": "html_regex",
            })

            if len(candidates) >= limit:
                break
    except Exception:
        pass

    return candidates


def _visual_select_representative_pages(base_url: str, candidates: List[Dict[str, str]], max_internal_pages: int) -> List[Dict[str, str]]:
    selected: List[Dict[str, str]] = []
    used_types = set()
    used_urls = {_visual_clean_url(base_url)}

    ordered = sorted(
        candidates,
        key=lambda x: (_visual_candidate_priority(x.get("page_type", "internal")), len(x.get("url", "")))
    )

    # Primero uno por tipo importante.
    for item in ordered:
        if len(selected) >= max_internal_pages:
            break

        page_type = item.get("page_type", "internal")
        clean = _visual_clean_url(item.get("url", ""))

        if not clean or clean in used_urls:
            continue

        if page_type in used_types and page_type != "internal":
            continue

        selected.append({
            "page_type": page_type,
            "url": clean,
            "source": item.get("source", "candidate"),
            "anchor_text": item.get("text", ""),
        })
        used_types.add(page_type)
        used_urls.add(clean)

    # Completar con otras internas si faltan.
    for item in ordered:
        if len(selected) >= max_internal_pages:
            break

        clean = _visual_clean_url(item.get("url", ""))

        if not clean or clean in used_urls:
            continue

        selected.append({
            "page_type": item.get("page_type", "internal"),
            "url": clean,
            "source": item.get("source", "candidate"),
            "anchor_text": item.get("text", ""),
        })
        used_urls.add(clean)

    return selected


def _visual_compact_render(page_type: str, source_url: str, viewport: str, result: Dict[str, Any]) -> Dict[str, Any]:
    summary = result.get("visual_dom_summary") or {}
    screenshot = result.get("screenshot") or {}

    return {
        "page_type": page_type,
        "requested_url": source_url,
        "viewport": viewport,
        "status": result.get("status"),
        "final_url": result.get("final_url"),
        "http_status": result.get("http_status"),
        "page_title": result.get("page_title"),
        "screenshot_url": screenshot.get("screenshot_url"),
        "screenshot_id": screenshot.get("screenshot_id"),
        "full_page": (result.get("viewport") or {}).get("full_page"),
        "links_count": summary.get("links_count"),
        "forms_count": summary.get("forms_count"),
        "images_count": summary.get("images_count"),
        "images_without_alt_count": summary.get("images_without_alt_count"),
        "visible_ctas": summary.get("visible_ctas") or [],
        "buttons_text_sample": (summary.get("buttons_text") or [])[:25],
        "image_alt_samples": (summary.get("image_alt_samples") or [])[:20],
        "text_sample": truncate(summary.get("text_sample") or "", 900),
        "limitations": result.get("limitations") or [],
        "reason": result.get("reason"),
    }


def _visual_analyze_render_metrics(renders: List[Dict[str, Any]]) -> Dict[str, Any]:
    completed = [r for r in renders if r.get("status") == "completed"]

    def _ratio(n, d):
        try:
            if not d:
                return None
            return round(float(n) / float(d), 4)
        except Exception:
            return None

    by_viewport: Dict[str, Any] = {}
    for viewport in ["desktop", "mobile"]:
        items = [r for r in completed if r.get("viewport") == viewport]
        if not items:
            by_viewport[viewport] = {
                "renders_completed": 0,
                "notes": ["No hay renders completados para este viewport."],
            }
            continue

        total_links = sum(int(r.get("links_count") or 0) for r in items)
        total_forms = sum(int(r.get("forms_count") or 0) for r in items)
        total_images = sum(int(r.get("images_count") or 0) for r in items)
        total_images_without_alt = sum(int(r.get("images_without_alt_count") or 0) for r in items)

        ctas: List[str] = []
        for r in items:
            for cta in r.get("visible_ctas") or []:
                clean = collapse_ws(str(cta))
                if clean and clean not in ctas:
                    ctas.append(clean)

        by_viewport[viewport] = {
            "renders_completed": len(items),
            "total_links_count": total_links,
            "total_forms_count": total_forms,
            "total_images_count": total_images,
            "total_images_without_alt_count": total_images_without_alt,
            "images_without_alt_ratio": _ratio(total_images_without_alt, total_images),
            "unique_visible_ctas_sample": ctas[:40],
            "signals": {
                "high_link_density": total_links >= 250,
                "many_forms_detected": total_forms >= 10,
                "image_alt_gap_detected": (_ratio(total_images_without_alt, total_images) or 0) >= 0.2,
                "ctas_detected": len(ctas) > 0,
            },
        }

    all_ctas: List[str] = []
    for r in completed:
        for cta in r.get("visible_ctas") or []:
            clean = collapse_ws(str(cta))
            if clean and clean not in all_ctas:
                all_ctas.append(clean)

    return {
        "renders_attempted": len(renders),
        "renders_completed": len(completed),
        "viewports": by_viewport,
        "cross_viewport_ctas_sample": all_ctas[:50],
        "interpretation_rules": [
            "Alta cantidad de links puede indicar cat\u00e1logo amplio o navegaci\u00f3n compleja; no prueba mala conversi\u00f3n por s\u00ed sola.",
            "Im\u00e1genes sin alt afectan accesibilidad/SEO b\u00e1sico observable; no prueban ranking org\u00e1nico.",
            "Screenshots permiten evaluar fricci\u00f3n visual observable; no reemplazan UX research, PageSpeed ni datos de conversi\u00f3n.",
        ],
    }


async def audit_visual_site_summary(req: VisualSiteAuditRequest) -> Dict[str, Any]:
    raw_url = req.url or req.website
    normalized = normalize_url(raw_url)

    if not normalized:
        raise HTTPException(status_code=400, detail="URL inv\u00e1lida. Enviar url o website.")

    requested_viewports = []
    for v in req.viewports or ["desktop", "mobile"]:
        clean = str(v or "").lower().strip()
        if clean in ("desktop", "mobile") and clean not in requested_viewports:
            requested_viewports.append(clean)

    if not requested_viewports:
        requested_viewports = ["desktop", "mobile"]

    pages: List[Dict[str, str]] = [{
        "page_type": "home",
        "url": normalized,
        "source": "input",
        "anchor_text": "",
    }]

    candidates: List[Dict[str, str]] = []

    if req.max_internal_pages > 0:
        html = await _visual_fetch_html_for_links(normalized)
        candidates = _visual_extract_links_from_html(normalized, html, limit=80)
        pages.extend(_visual_select_representative_pages(normalized, candidates, req.max_internal_pages))

    renders: List[Dict[str, Any]] = []

    for page in pages:
        for viewport in requested_viewports:
            render_req = BrowserRenderRequest(
                url=page["url"],
                viewport=viewport,
                wait_ms=req.wait_ms,
                timeout_ms=req.timeout_ms,
                full_page=req.full_page,
            )
            result = await render_browserbase_visual(render_req)
            renders.append(_visual_compact_render(page["page_type"], page["url"], viewport, result))

    completed = [r for r in renders if r.get("status") == "completed"]

    overall_status = "completed" if completed and len(completed) == len(renders) else ("partial" if completed else "completed_with_limitations")

    selected_pages = [
        {
            "page_type": p.get("page_type"),
            "url": p.get("url"),
            "source": p.get("source"),
            "anchor_text": p.get("anchor_text"),
        }
        for p in pages
    ]

    return {
        "status": overall_status,
        "collector": "visual_site_summary",
        "version": APP_VERSION,
        "company_name": req.company_name,
        "url_requested": normalized,
        "full_page": req.full_page,
        "viewports_requested": requested_viewports,
        "pages_selected": selected_pages,
        "candidate_links_found": len(candidates),
        "renders": renders,
        "visual_site_summary": _visual_analyze_render_metrics(renders),
        "confidence": "medium-high" if completed else "low",
        "limitations": [
            "Este endpoint recolecta evidencia visual p\u00fablica observable; no mide conversiones, ventas, ROAS, CPA ni margen.",
            "No reemplaza PageSpeed, Core Web Vitals, heatmaps ni pruebas de usuario.",
            "La selecci\u00f3n de categor\u00eda/producto/contacto es heur\u00edstica sobre links p\u00fablicos; puede requerir validaci\u00f3n manual.",
            "Algunas p\u00e1ginas pueden variar por cookies, geolocalizaci\u00f3n, login, stock o contenido din\u00e1mico.",
        ],
        "retrieved_at": now_iso(),
    }






# ============================================================
# Social Public Exhaustive Audit - isolated module
# ============================================================

SOCIAL_TEXT_REPORTS: Dict[str, str] = {}


class SocialPublicAuditRequest(BaseModel):
    company_name: Optional[str] = None
    website: Optional[str] = None
    instagram: Optional[str] = None
    facebook: Optional[str] = None
    linkedin: Optional[str] = None
    tiktok: Optional[str] = None
    youtube: Optional[str] = None
    x: Optional[str] = None

    fetch_static_pages: bool = True
    use_search_discovery: bool = True
    use_browser_render: bool = False

    max_search_results: int = Field(default=8, ge=0, le=10)
    max_posts_extract: int = Field(default=20, ge=0, le=40)
    max_visible_text_chars: int = Field(default=3500, ge=500, le=9000)

    wait_ms: int = Field(default=1500, ge=0, le=8000)
    timeout_ms: int = Field(default=45000, ge=5000, le=90000)


def _sp_ws(value: Any) -> str:
    import re as _re
    return _re.sub(r"\s+", " ", str(value or "")).strip()


def _sp_trunc(value: Any, max_chars: int = 800) -> str:
    text = _sp_ws(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _sp_public_base_url() -> str:
    import os as _os
    return (_os.environ.get("PUBLIC_BASE_URL") or "https://marketing-audit-api.onrender.com").rstrip("/")


def _sp_norm_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    clean = str(url).strip()
    if not clean:
        return None
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean
    return clean


def _sp_inputs(req: SocialPublicAuditRequest) -> Dict[str, str]:
    raw_inputs = {
        "instagram": req.instagram,
        "facebook": req.facebook,
        "linkedin": req.linkedin,
        "tiktok": req.tiktok,
        "youtube": req.youtube,
        "x": req.x,
    }

    out: Dict[str, str] = {}
    for platform, url in raw_inputs.items():
        normalized = _sp_norm_url(url)
        if normalized:
            out[platform] = normalized
    return out


async def _sp_http_get(url: str, timeout_seconds: float = 30.0) -> Dict[str, Any]:
    httpx_mod = globals().get("httpx")

    if httpx_mod is None:
        return {
            "status": "skipped_missing_dependency",
            "reason": "httpx no disponible.",
            "url": url,
            "html": "",
        }

    try:
        headers = {
            "User-Agent": globals().get("USER_AGENT", "Mozilla/5.0 MarketingAuditor/0.8"),
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        async with httpx_mod.AsyncClient(timeout=timeout_seconds, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)

        html = resp.text or ""

        return {
            "status": "completed" if resp.status_code < 400 else "partial",
            "url": url,
            "final_url": str(resp.url),
            "http_status": resp.status_code,
            "content_type": resp.headers.get("content-type"),
            "html_length": len(html),
            "html": html,
            "reason": None if resp.status_code < 400 else f"HTTP {resp.status_code}",
        }

    except Exception as exc:
        return {
            "status": "failed",
            "url": url,
            "final_url": None,
            "http_status": None,
            "content_type": None,
            "html_length": 0,
            "html": "",
            "reason": str(exc),
        }


def _sp_meta_from_html(platform: str, url: str, html: str, max_visible_text_chars: int) -> Dict[str, Any]:
    import re as _re

    soup_cls = globals().get("BeautifulSoup")

    title = None
    meta_description = None
    og_title = None
    og_description = None
    canonical = None
    links: List[Dict[str, str]] = []
    visible_text = ""

    if soup_cls is not None and html:
        try:
            soup = soup_cls(html, "html.parser")

            if soup.title and soup.title.string:
                title = _sp_trunc(soup.title.string, 240)

            def meta_content(**attrs):
                m = soup.find("meta", attrs=attrs)
                if m and m.get("content"):
                    return _sp_trunc(m.get("content"), 700)
                return None

            meta_description = meta_content(name="description")
            og_title = meta_content(property="og:title")
            og_description = meta_content(property="og:description")

            can = soup.find("link", attrs={"rel": "canonical"})
            if can and can.get("href"):
                canonical = str(can.get("href"))

            for a in soup.find_all("a", href=True):
                href = str(a.get("href") or "").strip()
                text = _sp_trunc(a.get_text(" ", strip=True), 140)

                if not href:
                    continue

                if len(links) >= 80:
                    break

                links.append({
                    "href": href,
                    "text": text,
                })

            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            visible_text = _sp_trunc(soup.get_text(" ", strip=True), max_visible_text_chars)

        except Exception:
            pass

    if not title and html:
        m = _re.search(r"<title[^>]*>(.*?)</title>", html, flags=_re.I | _re.S)
        if m:
            title = _sp_trunc(m.group(1), 240)

    if not visible_text and html:
        visible_text = _sp_trunc(_re.sub(r"<[^>]+>", " ", html), max_visible_text_chars)

    return {
        "platform": platform,
        "url": url,
        "title": title,
        "meta_description": meta_description,
        "og_title": og_title,
        "og_description": og_description,
        "canonical": canonical,
        "links_sample": links[:40],
        "visible_text_sample": visible_text,
    }


def _sp_extract_metric_candidates(text: str) -> Dict[str, Any]:
    import re as _re

    source = _sp_ws(text)
    lower = source.lower()

    patterns = {
        "followers": [
            r"([\d\.,]+[kKmM]?)\s+(followers|seguidores)",
            r"(followers|seguidores)\s+([\d\.,]+[kKmM]?)",
            r"([\d\.,]+[kKmM]?)\s+personas siguen",
        ],
        "following": [
            r"([\d\.,]+[kKmM]?)\s+(following|seguidos|siguiendo)",
            r"(following|seguidos|siguiendo)\s+([\d\.,]+[kKmM]?)",
        ],
        "posts": [
            r"([\d\.,]+[kKmM]?)\s+(posts|publicaciones|posteos)",
            r"(posts|publicaciones|posteos)\s+([\d\.,]+[kKmM]?)",
        ],
        "likes": [
            r"([\d\.,]+[kKmM]?)\s+(likes|me gusta|reacciones)",
            r"([\d\.,]+[kKmM]?)\s+likes?",
        ],
        "comments": [
            r"([\d\.,]+[kKmM]?)\s+(comments|comentarios)",
            r"([\d\.,]+[kKmM]?)\s+comments?",
        ],
        "views": [
            r"([\d\.,]+[kKmM]?)\s+(views|visualizaciones|reproducciones|vistas)",
            r"([\d\.,]+[kKmM]?)\s+views?",
        ],
        "shares": [
            r"([\d\.,]+[kKmM]?)\s+(shares|compartidos|veces compartido)",
        ],
    }

    found: Dict[str, List[str]] = {}

    for metric, metric_patterns in patterns.items():
        values: List[str] = []

        for pat in metric_patterns:
            for match in _re.finditer(pat, lower, flags=_re.I):
                groups = list(match.groups())
                nums = [g for g in groups if g and _re.search(r"\d", str(g))]
                for n in nums:
                    clean = _sp_ws(n)
                    if clean and clean not in values:
                        values.append(clean)

                if len(values) >= 12:
                    break

            if len(values) >= 12:
                break

        found[metric] = values[:12]

    date_patterns = [
        r"\b\d{1,2}\s+de\s+[a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+\s+de\s+\d{4}\b",
        r"\b\d{1,2}\s+de\s+[a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\b",
        r"\b\d+\s+(d|h|min|days|hours|minutes|d\u00edas|horas|minutos)\b",
        r"\b(ayer|hoy|anteayer)\b",
    ]

    dates: List[str] = []
    for pat in date_patterns:
        for match in _re.finditer(pat, source, flags=_re.I):
            clean = _sp_ws(match.group(0))
            if clean not in dates:
                dates.append(clean)

            if len(dates) >= 20:
                break

        if len(dates) >= 20:
            break

    return {
        "followers_visible_values": found.get("followers", []),
        "following_visible_values": found.get("following", []),
        "posts_visible_values": found.get("posts", []),
        "likes_visible_values": found.get("likes", []),
        "comments_visible_values": found.get("comments", []),
        "views_visible_values": found.get("views", []),
        "shares_visible_values": found.get("shares", []),
        "dates_visible_values": dates,
    }


def _sp_extract_content_signals(text: str) -> Dict[str, Any]:
    lower = _sp_ws(text).lower()

    buckets = {
        "product_or_catalog": ["producto", "productos", "cat\u00e1logo", "catalogo", "stock", "comprar", "precio", "oferta"],
        "promotions": ["promo", "promoci\u00f3n", "promocion", "descuento", "off", "cuotas", "env\u00edo", "envio"],
        "events": ["evento", "eventos", "cumplea\u00f1os", "egresados", "fiesta", "cumple", "casamiento", "despedida"],
        "b2b_or_wholesale": ["mayorista", "minorista", "revendedor", "distribuci\u00f3n", "distribucion", "importador", "importadores"],
        "social_proof": ["cliente", "clientes", "testimonio", "rese\u00f1a", "reviews", "seguidores"],
        "video_or_reels": ["reel", "reels", "video", "videos", "viral", "visualizaciones", "views"],
        "cta": ["link", "whatsapp", "mensaje", "consult", "comprar", "contact", "contacto", "ver m\u00e1s", "ver mas"],
    }

    detected: Dict[str, bool] = {}
    samples: Dict[str, List[str]] = {}

    words = lower.split()

    for bucket, terms in buckets.items():
        present_terms = [t for t in terms if t in lower]
        detected[bucket] = bool(present_terms)
        samples[bucket] = present_terms[:12]

    return {
        "detected": detected,
        "matched_terms": samples,
        "text_length": len(lower),
        "word_count_approx": len(words),
    }


def _sp_extract_post_like_items(text: str, max_items: int) -> List[Dict[str, Any]]:
    import re as _re

    source = _sp_ws(text)

    if not source:
        return []

    separators = [
        ". ",
        " \u00b7 ",
        " | ",
        "\n",
    ]

    chunks = [source]

    for sep in separators:
        new_chunks = []
        for chunk in chunks:
            new_chunks.extend(chunk.split(sep))
        chunks = new_chunks

    items: List[Dict[str, Any]] = []

    signal_regex = _re.compile(
        r"(like|likes|me gusta|comentario|comentarios|comments|views|visualizaciones|reproducciones|followers|seguidores|reel|post|publicaci[o\u00f3]n|hoy|ayer|\d{1,2}/\d{1,2}/\d{2,4}|october|november|december|january|february|march|april|may|june|july|august|september)",
        flags=_re.I,
    )

    for chunk in chunks:
        clean = _sp_trunc(chunk, 360)

        if len(clean) < 20:
            continue

        if signal_regex.search(clean):
            metrics = _sp_extract_metric_candidates(clean)
            if clean not in [x.get("text") for x in items]:
                items.append({
                    "text": clean,
                    "metrics_detected": metrics,
                })

        if len(items) >= max_items:
            break

    return items


def _sp_platform_domains(platform: str) -> List[str]:
    mapping = {
        "instagram": ["instagram.com"],
        "facebook": ["facebook.com", "fb.com"],
        "linkedin": ["linkedin.com"],
        "tiktok": ["tiktok.com"],
        "youtube": ["youtube.com", "youtu.be"],
        "x": ["x.com", "twitter.com"],
    }
    return mapping.get(str(platform or "").lower().strip(), [])


def _sp_domain_from_url(url: Optional[str]) -> str:
    if not url:
        return ""

    try:
        parse = __import__("urllib.parse", fromlist=["urlparse"]).urlparse
        netloc = parse(str(url)).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def _sp_url_matches_platform(platform: str, url: Optional[str]) -> bool:
    domain = _sp_domain_from_url(url)
    allowed = _sp_platform_domains(platform)

    if not domain or not allowed:
        return False

    return any(domain == d or domain.endswith("." + d) for d in allowed)


async def _sp_search(company_name: Optional[str], platform: str, url: str, max_results: int) -> Dict[str, Any]:
    import os as _os

    if max_results <= 0:
        return {
            "status": "skipped",
            "reason": "max_search_results=0",
            "results": [],
            "platform_results": [],
            "external_results": [],
        }

    httpx_mod = globals().get("httpx")
    tavily_key = _os.environ.get("TAVILY_API_KEY")

    if httpx_mod is None:
        return {
            "status": "skipped_missing_dependency",
            "reason": "httpx no disponible.",
            "results": [],
            "platform_results": [],
            "external_results": [],
        }

    if not tavily_key:
        return {
            "status": "skipped_missing_api_key",
            "reason": "TAVILY_API_KEY no configurada.",
            "results": [],
            "platform_results": [],
            "external_results": [],
        }

    allowed_domains = _sp_platform_domains(platform)
    primary_domain = allowed_domains[0] if allowed_domains else ""

    # Query deliberadamente filtrada por plataforma para reducir contaminaci\u00f3n cruzada.
    if primary_domain:
        query = _sp_ws(
            f'{company_name or ""} {platform} site:{primary_domain} {url} followers seguidores posts publicaciones likes comments comentarios views reels fecha'
        )
    else:
        query = _sp_ws(
            f'{company_name or ""} {platform} {url} followers seguidores posts publicaciones likes comments comentarios views reels fecha'
        )

    try:
        async with httpx_mod.AsyncClient(timeout=35.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )

        data = resp.json() if resp.text else {}
        all_results = []
        platform_results = []
        external_results = []

        for i, item in enumerate((data.get("results") or [])[:max_results], start=1):
            result_url = item.get("url")

            packed = {
                "position": i,
                "title": _sp_trunc(item.get("title"), 220),
                "url": result_url,
                "snippet": _sp_trunc(item.get("content"), 700),
                "score": item.get("score"),
                "domain": _sp_domain_from_url(result_url),
                "matches_platform": _sp_url_matches_platform(platform, result_url),
            }

            all_results.append(packed)

            if packed["matches_platform"]:
                platform_results.append(packed)
            else:
                external_results.append(packed)

        return {
            "status": "completed" if resp.status_code < 400 else "partial",
            "provider": "tavily",
            "query": query,
            "platform_filter_domains": allowed_domains,
            "http_status": resp.status_code,
            "results_count": len(all_results),
            "platform_results_count": len(platform_results),
            "external_results_count": len(external_results),
            "results": all_results,
            "platform_results": platform_results,
            "external_results": external_results,
            "reason": None if resp.status_code < 400 else _sp_trunc(resp.text, 700),
            "source_filter_policy": (
                "Solo platform_results se usan para extraer m\u00e9tricas candidatas de la plataforma. "
                "external_results quedan como discovery externo y no alimentan visible_metrics."
            ),
        }

    except Exception as exc:
        return {
            "status": "failed",
            "provider": "tavily",
            "query": query,
            "results": [],
            "platform_results": [],
            "external_results": [],
            "reason": str(exc),
        }




def _sp_social_render_classification(platform: str, final_url: Optional[str], page_title: Optional[str], text_sample: Optional[str]) -> Dict[str, Any]:
    platform_clean = str(platform or "").lower().strip()
    url = str(final_url or "").lower()
    title = str(page_title or "").lower()
    text = str(text_sample or "").lower()
    combined = " ".join([url, title, text])

    login_markers = [
        "/login",
        "accounts/login",
        "login?",
        "iniciar sesi\u00f3n",
        "inicia sesi\u00f3n",
        "log in",
        "sign in",
        "registrarte",
        "create an account",
        "entrar",
    ]

    block_markers = [
        "captcha",
        "unusual traffic",
        "temporarily blocked",
        "access denied",
        "forbidden",
        "not available",
        "content isn't available",
        "contenido no est\u00e1 disponible",
        "something went wrong",
    ]

    public_profile_markers_by_platform = {
        "instagram": ["publicaciones", "seguidores", "siguiendo", "posts", "followers", "following"],
        "facebook": ["me gusta", "followers", "seguidores", "publicaciones", "reels", "fotos", "opiniones"],
        "linkedin": ["employees", "empleados", "seguidores", "followers", "overview", "about", "publicaciones"],
        "tiktok": ["following", "followers", "likes"],
        "youtube": ["subscribers", "videos", "views"],
        "x": ["followers", "posts", "following"],
    }

    matched_login = [m for m in login_markers if m in combined]
    matched_block = [m for m in block_markers if m in combined]
    matched_public = [
        m for m in public_profile_markers_by_platform.get(platform_clean, [])
        if m in combined
    ]

    is_login_wall = False

    if platform_clean == "instagram" and "instagram.com/accounts/login" in url:
        is_login_wall = True

    if platform_clean == "facebook" and ("facebook.com/login" in url or "facebook.com/login.php" in url):
        is_login_wall = True

    if platform_clean == "linkedin" and ("linkedin.com/login" in url or "authwall" in url):
        is_login_wall = True

    if matched_login:
        is_login_wall = True

    is_blocked = bool(matched_block)

    if is_login_wall:
        classification = "login_wall"
        evidence_grade = "not_profile_evidence"
        usable_profile_visual_evidence = False
        reason = "El render termin\u00f3 en login/auth wall; screenshot \u00fatil solo como evidencia de bloqueo, no como vista del perfil."
    elif is_blocked:
        classification = "blocked_or_unavailable"
        evidence_grade = "not_profile_evidence"
        usable_profile_visual_evidence = False
        reason = "El render muestra bloqueo, contenido no disponible o respuesta restrictiva."
    elif matched_public:
        classification = "public_profile_candidate"
        evidence_grade = "partial_public_profile_evidence"
        usable_profile_visual_evidence = True
        reason = "El render contiene se\u00f1ales p\u00fablicas compatibles con perfil/p\u00e1gina, pero no reemplaza analytics nativo."
    else:
        classification = "unknown_or_partial"
        evidence_grade = "weak_visual_evidence"
        usable_profile_visual_evidence = False
        reason = "El render complet\u00f3, pero no hay se\u00f1ales suficientes para tratarlo como perfil p\u00fablico visible."

    return {
        "classification": classification,
        "evidence_grade": evidence_grade,
        "usable_profile_visual_evidence": usable_profile_visual_evidence,
        "is_login_wall": is_login_wall,
        "is_blocked_or_unavailable": is_blocked,
        "matched_login_markers": matched_login[:10],
        "matched_block_markers": matched_block[:10],
        "matched_public_profile_markers": matched_public[:10],
        "reason": reason,
    }


async def _sp_browser_render(platform: str, url: str, req: SocialPublicAuditRequest) -> Dict[str, Any]:
    if not req.use_browser_render:
        return {
            "status": "skipped",
            "reason": "use_browser_render=false",
            "render_classification": {
                "classification": "skipped",
                "evidence_grade": "not_attempted",
                "usable_profile_visual_evidence": False,
                "reason": "Browser render social no fue solicitado.",
            },
        }

    if "render_browserbase_visual" not in globals():
        return {
            "status": "skipped_missing_dependency",
            "reason": "render_browserbase_visual no disponible.",
            "render_classification": {
                "classification": "skipped_missing_dependency",
                "evidence_grade": "not_attempted",
                "usable_profile_visual_evidence": False,
                "reason": "No est\u00e1 disponible el helper de Browserbase render.",
            },
        }

    try:
        render_req = BrowserRenderRequest(
            url=url,
            viewport="desktop",
            wait_ms=req.wait_ms,
            timeout_ms=req.timeout_ms,
            full_page=True,
        )

        result = await render_browserbase_visual(render_req)
        summary = result.get("visual_dom_summary") or {}
        screenshot = result.get("screenshot") or {}

        text_sample = _sp_trunc(summary.get("text_sample"), req.max_visible_text_chars)
        final_url = result.get("final_url")
        page_title = result.get("page_title")

        render_status = result.get("status")

        if render_status != "completed":
            classification = {
                "classification": "failed_runtime",
                "evidence_grade": "not_profile_evidence",
                "usable_profile_visual_evidence": False,
                "is_login_wall": False,
                "is_blocked_or_unavailable": False,
                "matched_login_markers": [],
                "matched_block_markers": [],
                "matched_public_profile_markers": [],
                "reason": "El render social no complet\u00f3 correctamente; no hay evidencia visual usable del perfil.",
            }
        else:
            classification = _sp_social_render_classification(
                platform=platform,
                final_url=final_url,
                page_title=page_title,
                text_sample=text_sample,
            )

        limitations = list(result.get("limitations") or [])

        if render_status != "completed":
            limitations.append("Render social failed_runtime; no se debe tratar como evidencia visual del perfil.")

        if classification.get("classification") == "login_wall":
            limitations.append("Render social termin\u00f3 en login/auth wall; screenshot no prueba vista p\u00fablica del perfil.")
        elif classification.get("classification") == "blocked_or_unavailable":
            limitations.append("Render social muestra bloqueo o contenido no disponible.")
        elif classification.get("classification") == "unknown_or_partial":
            limitations.append("Render social completado, pero evidencia visual d\u00e9bil o parcial.")

        return {
            "status": result.get("status"),
            "final_url": final_url,
            "http_status": result.get("http_status"),
            "page_title": page_title,
            "screenshot_url": screenshot.get("screenshot_url"),
            "screenshot_id": screenshot.get("screenshot_id"),
            "text_sample": text_sample,
            "links_count": summary.get("links_count"),
            "forms_count": summary.get("forms_count"),
            "images_count": summary.get("images_count"),
            "visible_ctas": summary.get("visible_ctas") or [],
            "render_classification": classification,
            "limitations": limitations,
        }

    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
            "render_classification": {
                "classification": "failed_runtime",
                "evidence_grade": "not_profile_evidence",
                "usable_profile_visual_evidence": False,
                "reason": "Fall\u00f3 el render social en runtime.",
            },
        }




def _sp_merge_metrics(*metric_sets: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}

    keys = [
        "followers_visible_values",
        "following_visible_values",
        "posts_visible_values",
        "likes_visible_values",
        "comments_visible_values",
        "views_visible_values",
        "shares_visible_values",
        "dates_visible_values",
    ]

    for key in keys:
        values: List[str] = []

        for metrics in metric_sets:
            for item in metrics.get(key) or []:
                clean = _sp_ws(item)
                if clean and clean not in values:
                    values.append(clean)

        merged[key] = values[:25]

    has_followers = bool(merged.get("followers_visible_values"))
    has_interactions = bool(
        merged.get("likes_visible_values")
        or merged.get("comments_visible_values")
        or merged.get("views_visible_values")
        or merged.get("shares_visible_values")
    )
    has_dates = bool(merged.get("dates_visible_values"))
    has_posts = bool(merged.get("posts_visible_values"))

    # Guardrail de fiabilidad:
    # Los valores extra\u00eddos desde HTML/snippets/render son candidatos textuales.
    # No son una muestra estructurada de posts ni analytics nativo.
    merged["public_metric_candidates_detected"] = bool(
        has_followers or has_interactions or has_dates or has_posts
    )
    merged["engagement_candidate_detected"] = bool(has_followers and has_interactions)
    merged["frequency_candidate_detected"] = bool(has_dates or has_posts)

    # Mantener en False hasta tener dataset estructurado suficiente.
    merged["can_calculate_engagement"] = False
    merged["can_calculate_frequency"] = False

    merged["calculation_policy"] = {
        "engagement": "blocked_public_candidates_only",
        "frequency": "blocked_public_candidates_only",
        "reason": (
            "Las m\u00e9tricas visibles son candidatos textuales de HTML/snippets/render. "
            "Para calcular engagement o frecuencia hace falta dataset estructurado de posts "
            "con seguidores, fechas e interacciones, o export nativo de la plataforma."
        ),
    }

    return merged




def _sp_quality(metrics: Dict[str, Any], fetch_status: str, search_status: str, render_status: str) -> Dict[str, Any]:
    visible_groups = [
        "followers_visible_values",
        "following_visible_values",
        "posts_visible_values",
        "likes_visible_values",
        "comments_visible_values",
        "views_visible_values",
        "shares_visible_values",
        "dates_visible_values",
    ]

    visible_count = sum(1 for k in visible_groups if metrics.get(k))

    # M\u00e1ximo medium porque la evidencia p\u00fablica social puede venir de HTML/snippets/render,
    # no de exports nativos ni dataset estructurado de publicaciones.
    if visible_count >= 5:
        confidence = "medium"
    elif visible_count >= 3:
        confidence = "low-medium"
    elif visible_count >= 1:
        confidence = "low-medium"
    else:
        confidence = "low"

    limitations = []

    limitations.append(
        "Las m\u00e9tricas sociales visibles se tratan como candidatos p\u00fablicos, no como analytics nativo."
    )

    if fetch_status != "completed":
        limitations.append("La lectura p\u00fablica directa fue parcial, fallida o bloqueada.")

    if search_status not in ("completed", "skipped"):
        limitations.append("La b\u00fasqueda p\u00fablica fue parcial, fallida o no disponible.")

    if render_status not in ("completed", "skipped"):
        limitations.append("El render visual social fue parcial, fallido o no disponible.")

    limitations.append(
        "No se calcula engagement desde candidatos textuales; se requiere export nativo o dataset estructurado de posts."
    )

    limitations.append(
        "No se calcula frecuencia desde candidatos textuales; se requieren fechas/posteos estructurados."
    )

    return {
        "confidence": confidence,
        "visible_metric_groups": visible_count,
        "engagement_candidate_detected": metrics.get("engagement_candidate_detected"),
        "frequency_candidate_detected": metrics.get("frequency_candidate_detected"),
        "engagement_calculable": False,
        "frequency_calculable": False,
        "limitations": limitations,
    }




def _sp_real_data_contrast_plan(platform: str) -> List[Dict[str, str]]:
    common = [
        {
            "public_observed_field": "perfil p\u00fablico / identidad",
            "real_data_to_request": "captura fechada o acceso autorizado al perfil/cuenta",
            "source_expected": "plataforma nativa o captura fechada",
            "why": "Validar que el perfil le\u00eddo corresponde a la marca y no a un resultado ambiguo.",
        },
        {
            "public_observed_field": "seguidores visibles",
            "real_data_to_request": "seguidores actuales y evoluci\u00f3n \u00faltimos 90/180 d\u00edas",
            "source_expected": "Insights nativos",
            "why": "Contrastar visibilidad p\u00fablica contra crecimiento real.",
        },
        {
            "public_observed_field": "posts/fechas/interacciones visibles",
            "real_data_to_request": "export de \u00faltimos 30/60/90 contenidos con fecha, formato, alcance, impresiones, views, likes, comentarios, guardados, compartidos, clics y mensajes",
            "source_expected": "Meta Business Suite / LinkedIn Analytics / TikTok Analytics / YouTube Studio",
            "why": "Calcular frecuencia, engagement y performance real con datos confiables.",
        },
        {
            "public_observed_field": "clics / mensajes / leads",
            "real_data_to_request": "clics al link, clics a WhatsApp, mensajes, formularios, leads y tasa de respuesta",
            "source_expected": "Insights + CRM + WhatsApp/Inbox",
            "why": "Medir si el contenido genera acciones comerciales, no solo interacci\u00f3n.",
        },
        {
            "public_observed_field": "ventas atribuidas",
            "real_data_to_request": "ventas/leads por campa\u00f1a, contenido, UTMs o CRM",
            "source_expected": "GA4, Ads, CRM, ecommerce backend",
            "why": "No inferir ventas desde m\u00e9tricas sociales p\u00fablicas.",
        },
    ]

    if platform == "linkedin":
        common.append({
            "public_observed_field": "se\u00f1al B2B",
            "real_data_to_request": "impresiones, clics, seguidores, visitantes, leads, cargos/industrias y posteos de empresa",
            "source_expected": "LinkedIn Analytics / CRM",
            "why": "Validar si LinkedIn aporta confianza B2B o generaci\u00f3n de demanda.",
        })

    return common


async def _sp_collect_one(platform: str, url: str, req: SocialPublicAuditRequest) -> Dict[str, Any]:
    fetch = {
        "status": "skipped",
        "reason": "fetch_static_pages=false",
        "html": "",
    }

    if req.fetch_static_pages:
        fetch = await _sp_http_get(url)

    meta = _sp_meta_from_html(platform, url, fetch.get("html") or "", req.max_visible_text_chars)

    static_text = " ".join([
        meta.get("title") or "",
        meta.get("meta_description") or "",
        meta.get("og_title") or "",
        meta.get("og_description") or "",
        meta.get("visible_text_sample") or "",
    ])

    static_metrics = _sp_extract_metric_candidates(static_text)
    static_signals = _sp_extract_content_signals(static_text)
    static_post_like = _sp_extract_post_like_items(static_text, req.max_posts_extract)

    search = {
        "status": "skipped",
        "reason": "use_search_discovery=false",
        "results": [],
    }

    if req.use_search_discovery:
        search = await _sp_search(req.company_name, platform, url, req.max_search_results)

    # Solo resultados del mismo dominio/plataforma alimentan m\u00e9tricas candidatas.
    # Resultados externos quedan como discovery, no como visible_metrics.
    search_metric_results = search.get("platform_results") or []
    search_text = " ".join([
        str(r.get("title") or "") + " " + str(r.get("snippet") or "")
        for r in search_metric_results
    ])

    search_metrics = _sp_extract_metric_candidates(search_text)
    search_signals = _sp_extract_content_signals(search_text)
    search_post_like = _sp_extract_post_like_items(search_text, req.max_posts_extract)

    render = await _sp_browser_render(platform, url, req)
    render_text = render.get("text_sample") or ""
    render_metrics = _sp_extract_metric_candidates(render_text)
    render_signals = _sp_extract_content_signals(render_text)
    render_post_like = _sp_extract_post_like_items(render_text, req.max_posts_extract)

    metrics = _sp_merge_metrics(static_metrics, search_metrics, render_metrics)

    quality = _sp_quality(
        metrics,
        fetch.get("status"),
        search.get("status"),
        render.get("status"),
    )

    post_like_items = []
    seen_texts = set()

    for source_name, items in [
        ("static_html", static_post_like),
        ("search_discovery", search_post_like),
        ("browser_render", render_post_like),
    ]:
        for item in items:
            text = item.get("text")
            if not text or text in seen_texts:
                continue

            seen_texts.add(text)
            post_like_items.append({
                "source": source_name,
                "text": text,
                "metrics_detected": item.get("metrics_detected") or {},
            })

            if len(post_like_items) >= req.max_posts_extract:
                break

        if len(post_like_items) >= req.max_posts_extract:
            break

    return {
        "platform": platform,
        "url_requested": url,
        "fetch": {
            "status": fetch.get("status"),
            "http_status": fetch.get("http_status"),
            "final_url": fetch.get("final_url"),
            "content_type": fetch.get("content_type"),
            "html_length": fetch.get("html_length"),
            "reason": fetch.get("reason"),
        },
        "public_identity": {
            "title": meta.get("title"),
            "meta_description": meta.get("meta_description"),
            "og_title": meta.get("og_title"),
            "og_description": meta.get("og_description"),
            "canonical": meta.get("canonical"),
            "links_sample": meta.get("links_sample") or [],
        },
        "visible_metrics": metrics,
        "content_signals": {
            "static_html": static_signals,
            "search_discovery": search_signals,
            "browser_render": render_signals,
        },
        "post_like_items_sample": post_like_items,
        "search_discovery": {
            "status": search.get("status"),
            "provider": search.get("provider"),
            "query": search.get("query"),
            "platform_filter_domains": search.get("platform_filter_domains"),
            "source_filter_policy": search.get("source_filter_policy"),
            "http_status": search.get("http_status"),
            "results_count": search.get("results_count"),
            "platform_results_count": search.get("platform_results_count"),
            "external_results_count": search.get("external_results_count"),
            "results_sample": search.get("results", [])[:req.max_search_results],
            "platform_results_sample": search.get("platform_results", [])[:req.max_search_results],
            "external_results_sample": search.get("external_results", [])[:req.max_search_results],
            "reason": search.get("reason"),
        },
        "browser_render": render,
        "data_quality": quality,
        "contrast_plan": _sp_real_data_contrast_plan(platform),
        "visible_text_sample": meta.get("visible_text_sample"),
    }


def _sp_summary(platform_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    platforms_with_any_metrics: List[str] = []
    platforms_with_engagement_possible: List[str] = []
    platforms_with_frequency_possible: List[str] = []
    platforms_blocked_or_partial: List[str] = []
    platforms_with_login_wall: List[str] = []
    platforms_with_public_visual_evidence: List[str] = []
    platforms_with_blocked_visual_evidence: List[str] = []

    for report in platform_reports:
        platform = report.get("platform")
        metrics = report.get("visible_metrics") or {}

        has_any = any(
            metrics.get(k)
            for k in [
                "followers_visible_values",
                "following_visible_values",
                "posts_visible_values",
                "likes_visible_values",
                "comments_visible_values",
                "views_visible_values",
                "shares_visible_values",
                "dates_visible_values",
            ]
        )

        if has_any:
            platforms_with_any_metrics.append(platform)

        if metrics.get("can_calculate_engagement"):
            platforms_with_engagement_possible.append(platform)

        if metrics.get("can_calculate_frequency"):
            platforms_with_frequency_possible.append(platform)

        fetch_status = (report.get("fetch") or {}).get("status")
        if fetch_status != "completed":
            platforms_blocked_or_partial.append(platform)

        render = report.get("browser_render") or {}
        classification = (render.get("render_classification") or {}).get("classification")
        usable_visual = (render.get("render_classification") or {}).get("usable_profile_visual_evidence")

        if classification == "login_wall":
            platforms_with_login_wall.append(platform)

        if classification in {"blocked_or_unavailable", "failed_runtime"}:
            platforms_with_blocked_visual_evidence.append(platform)

        if usable_visual:
            platforms_with_public_visual_evidence.append(platform)

    return {
        "platforms_analyzed": len(platform_reports),
        "platforms_with_any_visible_metrics": platforms_with_any_metrics,
        "platforms_with_engagement_possible": platforms_with_engagement_possible,
        "platforms_with_frequency_possible": platforms_with_frequency_possible,
        "platforms_partial_or_blocked": platforms_blocked_or_partial,
        "platforms_with_login_wall_render": platforms_with_login_wall,
        "platforms_with_public_visual_evidence": platforms_with_public_visual_evidence,
        "platforms_with_blocked_visual_evidence": platforms_with_blocked_visual_evidence,
        "global_limitations": [
            "Las plataformas sociales pueden ocultar datos p\u00fablicos, requerir login, bloquear HTML o entregar contenido regionalizado.",
            "Los snippets de b\u00fasqueda sirven como discovery y evidencia d\u00e9bil/media, no reemplazan analytics nativos.",
            "Screenshots de login/auth wall prueban bloqueo de acceso p\u00fablico renderizado, no visibilidad real del perfil.",
            "No afirmar engagement, frecuencia, alcance, clics, mensajes, ventas ni calidad de audiencia sin datos suficientes.",
            "Calcular engagement solo si existen seguidores visibles e interacciones visibles suficientes.",
            "Calcular frecuencia solo si existen fechas y publicaciones visibles suficientes.",
        ],
        "owner_exports_required": [
            "Meta Business Suite: alcance, impresiones, seguidores, clics, mensajes, guardados, compartidos y contenidos \u00faltimos 90 d\u00edas.",
            "Instagram Insights: posts/reels con fecha, formato, alcance, views, likes, comentarios, guardados, shares y clics.",
            "Facebook Insights: alcance, reacciones, comentarios, compartidos, clics, mensajes y crecimiento.",
            "LinkedIn Analytics: followers, impresiones, clics, visitantes, interacciones, posteos y datos de audiencia.",
            "TikTok Analytics: videos, views, retenci\u00f3n, likes, comentarios, shares, seguidores y tr\u00e1fico al perfil.",
            "YouTube Studio: videos, views, retenci\u00f3n, CTR, suscriptores, tr\u00e1fico y engagement.",
            "CRM/WhatsApp: consultas, tasa de respuesta, calidad de lead, cierre y ventas atribuidas.",
        ],
    }




def _sp_txt(payload: Dict[str, Any]) -> str:
    lines: List[str] = []

    lines.append("AUDITOR\u00cdA SOCIAL P\u00daBLICA EXHAUSTIVA")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Empresa: {payload.get('company_name') or 'No especificada'}")
    lines.append(f"Fecha de recolecci\u00f3n: {payload.get('retrieved_at')}")
    lines.append(f"Versi\u00f3n del collector: {payload.get('version')}")
    lines.append(f"Estado: {payload.get('status')}")
    lines.append(f"Report ID: {payload.get('report_id')}")
    lines.append("")
    lines.append("1. FUENTES ANALIZADAS")
    lines.append("-" * 72)

    for platform, url in (payload.get("sources_received") or {}).items():
        lines.append(f"- {platform}: {url}")

    lines.append("")
    lines.append("2. RESUMEN EJECUTIVO SOCIAL")
    lines.append("-" * 72)

    summary = payload.get("social_public_summary") or {}
    lines.append(f"Plataformas analizadas: {summary.get('platforms_analyzed')}")
    lines.append(f"Con alguna m\u00e9trica visible: {summary.get('platforms_with_any_visible_metrics')}")
    lines.append(f"Engagement calculable con evidencia p\u00fablica estructurada: {summary.get('platforms_with_engagement_possible')}")
    lines.append(f"Frecuencia calculable con evidencia p\u00fablica estructurada: {summary.get('platforms_with_frequency_possible')}")
    lines.append(f"Parciales o bloqueadas: {summary.get('platforms_partial_or_blocked')}")

    lines.append("")
    lines.append("3. RESULTADO POR PLATAFORMA")
    lines.append("-" * 72)

    for report in payload.get("platform_reports") or []:
        platform = report.get("platform")
        lines.append("")
        lines.append("=" * 72)
        lines.append(f"PLATAFORMA: {platform}")
        lines.append("=" * 72)
        lines.append(f"URL solicitada: {report.get('url_requested')}")

        fetch = report.get("fetch") or {}
        lines.append("")
        lines.append("Lectura p\u00fablica directa")
        lines.append(f"- status: {fetch.get('status')}")
        lines.append(f"- http_status: {fetch.get('http_status')}")
        lines.append(f"- final_url: {fetch.get('final_url')}")
        lines.append(f"- content_type: {fetch.get('content_type')}")
        lines.append(f"- html_length: {fetch.get('html_length')}")
        lines.append(f"- reason: {fetch.get('reason')}")

        identity = report.get("public_identity") or {}
        lines.append("")
        lines.append("Identidad p\u00fablica detectada")
        lines.append(f"- title: {identity.get('title')}")
        lines.append(f"- meta_description: {identity.get('meta_description')}")
        lines.append(f"- og_title: {identity.get('og_title')}")
        lines.append(f"- og_description: {identity.get('og_description')}")
        lines.append(f"- canonical: {identity.get('canonical')}")

        lines.append("")
        lines.append("Links visibles sample")
        for item in identity.get("links_sample") or []:
            lines.append(f"- {item.get('text')} | {item.get('href')}")

        metrics = report.get("visible_metrics") or {}
        lines.append("")
        lines.append("M\u00e9tricas visibles detectadas")
        lines.append(f"- followers: {metrics.get('followers_visible_values')}")
        lines.append(f"- following: {metrics.get('following_visible_values')}")
        lines.append(f"- posts: {metrics.get('posts_visible_values')}")
        lines.append(f"- likes: {metrics.get('likes_visible_values')}")
        lines.append(f"- comments: {metrics.get('comments_visible_values')}")
        lines.append(f"- views: {metrics.get('views_visible_values')}")
        lines.append(f"- shares: {metrics.get('shares_visible_values')}")
        lines.append(f"- fechas: {metrics.get('dates_visible_values')}")
        lines.append(f"- engagement calculable: {metrics.get('can_calculate_engagement')}")
        lines.append(f"- frecuencia calculable: {metrics.get('can_calculate_frequency')}")

        lines.append("")
        lines.append("Contenido/post-like items detectados")
        for item in report.get("post_like_items_sample") or []:
            lines.append(f"- source: {item.get('source')}")
            lines.append(f"  text: {item.get('text')}")
            lines.append(f"  metrics: {item.get('metrics_detected')}")

        lines.append("")
        lines.append("Search discovery")
        search = report.get("search_discovery") or {}
        lines.append(f"- status: {search.get('status')}")
        lines.append(f"- provider: {search.get('provider')}")
        lines.append(f"- query: {search.get('query')}")
        lines.append(f"- results_count: {search.get('results_count')}")
        lines.append(f"- platform_results_count: {search.get('platform_results_count')}")
        lines.append(f"- external_results_count: {search.get('external_results_count')}")
        lines.append(f"- source_filter_policy: {search.get('source_filter_policy')}")
        lines.append(f"- reason: {search.get('reason')}")

        for r in search.get("platform_results_sample") or []:
            lines.append(f"  * PLATFORM {r.get('position')}. {r.get('title')}")
            lines.append(f"    URL: {r.get('url')}")
            lines.append(f"    Snippet: {r.get('snippet')}")

        render = report.get("browser_render") or {}
        lines.append("")
        lines.append("Browser/render social")
        lines.append(f"- status: {render.get('status')}")
        lines.append(f"- final_url: {render.get('final_url')}")
        lines.append(f"- http_status: {render.get('http_status')}")
        lines.append(f"- page_title: {render.get('page_title')}")
        rc = render.get("render_classification") or {}
        lines.append(f"- render_classification: {rc.get('classification')}")
        lines.append(f"- evidence_grade: {rc.get('evidence_grade')}")
        lines.append(f"- usable_profile_visual_evidence: {rc.get('usable_profile_visual_evidence')}")
        lines.append(f"- render_classification_reason: {rc.get('reason')}")
        lines.append(f"- screenshot_url: {render.get('screenshot_url')}")
        lines.append(f"- links_count: {render.get('links_count')}")
        lines.append(f"- forms_count: {render.get('forms_count')}")
        lines.append(f"- images_count: {render.get('images_count')}")
        lines.append(f"- visible_ctas: {render.get('visible_ctas')}")
        lines.append(f"- reason: {render.get('reason')}")

        quality = report.get("data_quality") or {}
        lines.append("")
        lines.append("Calidad de evidencia")
        lines.append(f"- confidence: {quality.get('confidence')}")
        lines.append(f"- visible_metric_groups: {quality.get('visible_metric_groups')}")
        lines.append(f"- engagement_calculable: {quality.get('engagement_calculable')}")
        lines.append(f"- frequency_calculable: {quality.get('frequency_calculable')}")
        for limitation in quality.get("limitations") or []:
            lines.append(f"- limitaci\u00f3n: {limitation}")

        lines.append("")
        lines.append("Plan de contraste contra datos reales")
        for row in report.get("contrast_plan") or []:
            lines.append(f"- Campo p\u00fablico: {row.get('public_observed_field')}")
            lines.append(f"  Dato real a pedir: {row.get('real_data_to_request')}")
            lines.append(f"  Fuente esperada: {row.get('source_expected')}")
            lines.append(f"  Motivo: {row.get('why')}")

        lines.append("")
        lines.append("Texto visible sample")
        lines.append(str(report.get("visible_text_sample") or "")[:3000])

    lines.append("")
    lines.append("4. LIMITACIONES GLOBALES")
    lines.append("-" * 72)

    for item in summary.get("global_limitations") or []:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("5. EXPORTS / ACCESOS A PEDIR")
    lines.append("-" * 72)

    for item in summary.get("owner_exports_required") or []:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("6. GUARDRAILS")
    lines.append("-" * 72)
    lines.append("- No afirmar engagement, frecuencia, alcance, clics, mensajes, ventas ni calidad de lead sin evidencia suficiente.")
    lines.append("- No calcular likes promedio, comentarios promedio, engagement rate ni frecuencia si no hay base observable suficiente.")
    lines.append("- Los snippets de b\u00fasqueda son se\u00f1ales de discovery, no analytics nativo.")
    lines.append("- La informaci\u00f3n social p\u00fablica puede estar incompleta por login, bloqueo, regi\u00f3n, HTML din\u00e1mico o cambios de plataforma.")
    lines.append("- Para contraste real, usar exports nativos, capturas fechadas, CRM, GA4 y datos de ventas.")

    return "\n".join(lines) + "\n"


@app.get("/deliverables/social-text/{report_id}.txt")
async def get_social_text_report(report_id: str, _: None = Depends(verify_api_key)):
    txt = SOCIAL_TEXT_REPORTS.get(report_id)

    if not txt:
        raise HTTPException(status_code=404, detail="Social report not found")

    from fastapi.responses import PlainTextResponse as _PlainTextResponse

    return _PlainTextResponse(
        txt,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="social_public_{report_id}.txt"'
        },
    )



# ============================================================
# Drive Upload - isolated deliverables module
# ============================================================

DRIVE_UPLOADS: Dict[str, Any] = {}


class DriveUploadRequest(BaseModel):
    report_id: str
    report_type: str = Field(default="public_presence")
    filename: Optional[str] = None
    drive_folder_name: Optional[str] = None


def _drive_collapse_ws(value: Any) -> str:
    import re as _re
    return _re.sub(r"\s+", " ", str(value or "")).strip()


def _drive_safe_filename(value: Optional[str], fallback: str) -> str:
    import re as _re

    raw_name = _drive_collapse_ws(value or fallback)
    raw_name = _re.sub(r'[\\/:*?"<>|#%{}~&]+', "_", raw_name)
    raw_name = _re.sub(r"\s+", " ", raw_name).strip()

    if not raw_name:
        raw_name = fallback

    if not raw_name.lower().endswith(".txt"):
        raw_name += ".txt"

    return raw_name[:180]


def _drive_public_base_url() -> str:
    import os as _os
    return (_os.environ.get("PUBLIC_BASE_URL") or "https://marketing-audit-api.onrender.com").rstrip("/")


def _drive_report_url(report_type: str, report_id: str) -> str:
    base = _drive_public_base_url()
    kind = _drive_collapse_ws(report_type).lower()

    if kind in {"social", "social_public", "audit_social", "social-public"}:
        return f"{base}/deliverables/social-text/{report_id}.txt"

    return f"{base}/deliverables/text/{report_id}.txt"


def _drive_default_filename(report_type: str, report_id: str) -> str:
    kind = _drive_collapse_ws(report_type).lower()

    if kind in {"social", "social_public", "audit_social", "social-public"}:
        return f"social_public_{report_id}.txt"

    return f"public_presence_{report_id}.txt"


async def _drive_fetch_report_text(report_type: str, report_id: str) -> Dict[str, Any]:
    import os as _os

    httpx_mod = globals().get("httpx")

    if httpx_mod is None:
        import httpx as httpx_mod

    api_key = _os.environ.get("API_KEY") or _os.environ.get("MARKETING_AUDIT_API_KEY") or ""
    url = _drive_report_url(report_type, report_id)

    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    async with httpx_mod.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "failed",
                "reason": "Could not fetch report text before Drive upload",
                "source_url": url,
                "http_status": resp.status_code,
                "body_sample": (resp.text or "")[:500],
            },
        )

    return {
        "status": "completed",
        "source_url": url,
        "text": resp.text or "",
        "bytes": len((resp.text or "").encode("utf-8")),
    }


async def _drive_upload_text(filename: str, text: str, folder_name: Optional[str] = None) -> Dict[str, Any]:
    import os as _os

    httpx_mod = globals().get("httpx")

    if httpx_mod is None:
        import httpx as httpx_mod

    webapp_url = (_os.environ.get("DRIVE_UPLOAD_WEBAPP_URL") or "").strip()
    secret = (_os.environ.get("DRIVE_UPLOAD_SECRET") or "").strip()

    if not webapp_url or not secret:
        return {
            "status": "skipped_missing_config",
            "reason": "DRIVE_UPLOAD_WEBAPP_URL or DRIVE_UPLOAD_SECRET not configured",
        }

    payload = {
        "secret": secret,
        "filename": filename,
        "mime_type": "text/plain",
        "content": text,
    }

    if folder_name:
        payload["folder_name"] = folder_name

    try:
        async with httpx_mod.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            resp = await client.post(
                webapp_url,
                json=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
            )

        try:
            data = resp.json()
        except Exception:
            data = {
                "status": "failed",
                "reason": "Drive uploader returned non-JSON response",
                "body_sample": (resp.text or "")[:700],
            }

        data["http_status"] = resp.status_code

        if resp.status_code >= 400 and data.get("status") == "completed":
            data["status"] = "failed"

        return data

    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
        }



# ============================================================
# Drive Screenshot Upload - isolated deliverables module
# ============================================================


class DriveScreenshotUploadRequest(BaseModel):
    screenshot_id: str
    filename: Optional[str] = None
    drive_folder_name: Optional[str] = None


def _drive_screenshot_default_filename(screenshot_id: str) -> str:
    clean = _drive_collapse_ws(screenshot_id)
    return f"screenshot_{clean}.png"


def _drive_screenshot_url(screenshot_id: str) -> str:
    base = _drive_public_base_url()
    clean = _drive_collapse_ws(screenshot_id)
    return f"{base}/deliverables/screenshot/{clean}.png"


async def _drive_fetch_screenshot_bytes(screenshot_id: str) -> Dict[str, Any]:
    import os as _os

    httpx_mod = globals().get("httpx")

    if httpx_mod is None:
        import httpx as httpx_mod

    clean = _drive_collapse_ws(screenshot_id)
    url = _drive_screenshot_url(clean)

    api_key = _os.environ.get("API_KEY") or _os.environ.get("MARKETING_AUDIT_API_KEY") or ""

    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    async with httpx_mod.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "failed",
                "reason": "Could not fetch screenshot before Drive upload",
                "source_url": url,
                "http_status": resp.status_code,
                "body_sample": (resp.text or "")[:500],
            },
        )

    content_type = resp.headers.get("content-type") or "image/png"

    return {
        "status": "completed",
        "source_url": url,
        "content": resp.content,
        "bytes": len(resp.content or b""),
        "content_type": content_type,
    }


async def _drive_upload_binary(filename: str, content: bytes, mime_type: str, folder_name: Optional[str] = None) -> Dict[str, Any]:
    import os as _os
    import base64 as _base64

    httpx_mod = globals().get("httpx")

    if httpx_mod is None:
        import httpx as httpx_mod

    webapp_url = (_os.environ.get("DRIVE_UPLOAD_WEBAPP_URL") or "").strip()
    secret = (_os.environ.get("DRIVE_UPLOAD_SECRET") or "").strip()

    if not webapp_url or not secret:
        return {
            "status": "skipped_missing_config",
            "reason": "DRIVE_UPLOAD_WEBAPP_URL or DRIVE_UPLOAD_SECRET not configured",
        }

    payload = {
        "secret": secret,
        "filename": filename,
        "mime_type": mime_type or "image/png",
        "content_base64": _base64.b64encode(content or b"").decode("ascii"),
    }

    if folder_name:
        payload["folder_name"] = folder_name

    try:
        async with httpx_mod.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            resp = await client.post(
                webapp_url,
                json=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
            )

        try:
            data = resp.json()
        except Exception:
            data = {
                "status": "failed",
                "reason": "Drive uploader returned non-JSON response",
                "body_sample": (resp.text or "")[:700],
            }

        data["http_status"] = resp.status_code

        if resp.status_code >= 400 and data.get("status") == "completed":
            data["status"] = "failed"

        return data

    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
        }


@app.post("/deliverables/upload-screenshot-to-drive")
async def upload_screenshot_to_drive(req: DriveScreenshotUploadRequest, _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    import uuid as _uuid

    screenshot_id = _drive_collapse_ws(req.screenshot_id)

    if not screenshot_id:
        raise HTTPException(status_code=400, detail="screenshot_id requerido")

    filename = _drive_safe_filename(
        req.filename,
        _drive_screenshot_default_filename(screenshot_id),
    )

    if not filename.lower().endswith(".png"):
        filename = filename.rsplit(".", 1)[0] + ".png"

    fetched = await _drive_fetch_screenshot_bytes(screenshot_id)
    upload = await _drive_upload_binary(
        filename=filename,
        content=fetched["content"],
        mime_type=fetched.get("content_type") or "image/png",
        folder_name=req.drive_folder_name,
    )

    upload_id = _uuid.uuid4().hex
    status = "completed" if upload.get("status") == "completed" else "failed"

    payload: Dict[str, Any] = {
        "status": status,
        "collector": "drive_screenshot_upload",
        "version": APP_VERSION,
        "upload_id": upload_id,
        "screenshot_id": screenshot_id,
        "filename": filename,
        "source_url": fetched.get("source_url"),
        "source_bytes": fetched.get("bytes"),
        "source_content_type": fetched.get("content_type"),
        "drive_status": upload.get("status"),
        "drive_file_id": upload.get("file_id"),
        "drive_file_name": upload.get("file_name"),
        "drive_url": upload.get("drive_url"),
        "drive_folder_id": upload.get("folder_id"),
        "drive_folder_name": upload.get("folder_name"),
        "drive_folder_url": upload.get("folder_url"),
        "public_sharing": upload.get("public_sharing"),
        "drive_http_status": upload.get("http_status"),
        "reason": upload.get("reason"),
        "uploaded_at": now_iso(),
        "limitations": [
            "Drive upload only confirms screenshot persistence in Google Drive.",
            "No interpreta el contenido visual por s\u00ed solo.",
            "No vuelve p\u00fablico el archivo salvo que Apps Script tenga PUBLIC_SHARING=true.",
        ],
    }

    DRIVE_UPLOADS[upload_id] = payload

    return payload




@app.post("/deliverables/upload-to-drive")
async def upload_report_to_drive(req: DriveUploadRequest, _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    import uuid as _uuid

    report_id = _drive_collapse_ws(req.report_id)

    if not report_id:
        raise HTTPException(status_code=400, detail="report_id requerido")

    report_type = _drive_collapse_ws(req.report_type or "public_presence")
    filename = _drive_safe_filename(req.filename, _drive_default_filename(report_type, report_id))

    fetched = await _drive_fetch_report_text(report_type, report_id)
    upload = await _drive_upload_text(
        filename,
        fetched["text"],
        folder_name=req.drive_folder_name,
    )

    upload_id = _uuid.uuid4().hex

    status = "completed" if upload.get("status") == "completed" else "failed"

    payload: Dict[str, Any] = {
        "status": status,
        "collector": "drive_upload",
        "version": APP_VERSION,
        "upload_id": upload_id,
        "report_id": report_id,
        "report_type": report_type,
        "filename": filename,
        "source_url": fetched.get("source_url"),
        "source_bytes": fetched.get("bytes"),
        "drive_status": upload.get("status"),
        "drive_file_id": upload.get("file_id"),
        "drive_file_name": upload.get("file_name"),
        "drive_url": upload.get("drive_url"),
        "drive_folder_id": upload.get("folder_id"),
        "drive_folder_name": upload.get("folder_name"),
        "drive_folder_url": upload.get("folder_url"),
        "public_sharing": upload.get("public_sharing"),
        "drive_http_status": upload.get("http_status"),
        "reason": upload.get("reason"),
        "uploaded_at": now_iso(),
        "limitations": [
            "Drive upload only confirms file persistence in Google Drive.",
            "No modifica el contenido del reporte.",
            "No vuelve p\u00fablico el archivo salvo que Apps Script tenga PUBLIC_SHARING=true.",
        ],
    }

    DRIVE_UPLOADS[upload_id] = payload

    return payload




@app.post("/audit/social-public")
async def audit_social_public(req: SocialPublicAuditRequest, _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    import uuid as _uuid

    sources = _sp_inputs(req)

    if not sources:
        raise HTTPException(
            status_code=400,
            detail="Enviar al menos un link social p\u00fablico: instagram, facebook, linkedin, tiktok, youtube o x.",
        )

    platform_reports: List[Dict[str, Any]] = []

    for platform, url in sources.items():
        platform_reports.append(await _sp_collect_one(platform, url, req))

    report_id = _uuid.uuid4().hex
    download_url = f"{_sp_public_base_url()}/deliverables/social-text/{report_id}.txt"

    payload: Dict[str, Any] = {
        "status": "completed_with_limitations",
        "collector": "social_public_exhaustive_audit",
        "version": APP_VERSION,
        "company_name": req.company_name,
        "sources_received": sources,
        "platform_reports": platform_reports,
        "social_public_summary": _sp_summary(platform_reports),
        "report_id": report_id,
        "download_url": download_url,
        "txt_report": {
            "available": True,
            "report_id": report_id,
            "download_url": download_url,
            "endpoint": f"/deliverables/social-text/{report_id}.txt",
        },
        "limitations": [
            "M\u00f3dulo basado en evidencia p\u00fablica observable, HTML p\u00fablico, search discovery y render opcional.",
            "No reemplaza Meta Business Suite, Instagram Insights, Facebook Insights, LinkedIn Analytics, TikTok Analytics, YouTube Studio ni CRM.",
            "No calcula engagement/frecuencia si faltan seguidores, fechas, publicaciones o interacciones visibles suficientes.",
            "No afirma ventas, ROAS, CPA, CPL, tr\u00e1fico, conversi\u00f3n, margen ni calidad de lead.",
        ],
        "retrieved_at": now_iso(),
    }

    SOCIAL_TEXT_REPORTS[report_id] = _sp_txt(payload)

    return payload




@app.post("/audit/visual-site")
async def audit_visual_site(req: VisualSiteAuditRequest, _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    return await audit_visual_site_summary(req)


@app.post("/debug/browser-render")
async def debug_browser_render(req: BrowserRenderRequest, _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    return await render_browserbase_visual(req)



# ============================================================
# Social Auth Config - safe diagnostics only
# ============================================================


def _mask_secret_value(value: Optional[str]) -> Dict[str, Any]:
    raw = str(value or "").strip()

    if not raw:
        return {
            "configured": False,
            "masked": None,
            "length": 0,
        }

    if len(raw) <= 4:
        masked = "*" * len(raw)
    else:
        masked = raw[:2] + ("*" * max(0, len(raw) - 4)) + raw[-2:]

    return {
        "configured": True,
        "masked": masked,
        "length": len(raw),
    }


def _social_auth_env_config() -> Dict[str, Any]:
    import os as _os

    enabled_raw = str(_os.environ.get("SOCIAL_AUTH_ENABLED") or "").strip().lower()
    enabled = enabled_raw in {"1", "true", "yes", "on"}

    instagram_username = _os.environ.get("INSTAGRAM_AUDIT_USERNAME")
    instagram_password = _os.environ.get("INSTAGRAM_AUDIT_PASSWORD")
    facebook_username = _os.environ.get("FACEBOOK_AUDIT_USERNAME")
    facebook_password = _os.environ.get("FACEBOOK_AUDIT_PASSWORD")

    return {
        "social_auth_enabled": enabled,
        "social_auth_enabled_raw_present": bool(enabled_raw),
        "instagram": {
            "username": _mask_secret_value(instagram_username),
            "password": {
                "configured": bool(str(instagram_password or "").strip()),
                "length": len(str(instagram_password or "")),
            },
            "ready_for_login_attempt": bool(enabled and str(instagram_username or "").strip() and str(instagram_password or "").strip()),
        },
        "facebook": {
            "username": _mask_secret_value(facebook_username),
            "password": {
                "configured": bool(str(facebook_password or "").strip()),
                "length": len(str(facebook_password or "")),
            },
            "ready_for_login_attempt": bool(enabled and str(facebook_username or "").strip() and str(facebook_password or "").strip()),
        },
        "safety_policy": {
            "credentials_exposed": False,
            "captcha_bypass_supported": False,
            "checkpoint_bypass_supported": False,
            "private_profiles_supported": False,
            "dm_access_supported": False,
            "write_actions_supported": False,
            "allowed_scope": [
                "public profile/page viewing",
                "screenshots",
                "visible text extraction",
                "classification of login_wall/captcha/checkpoint/blocked/profile_visible",
            ],
        },
    }


@app.get("/debug/social-auth-config")
async def debug_social_auth_config(_: None = Depends(verify_api_key)) -> Dict[str, Any]:
    return {
        "status": "completed",
        "service": "marketing-auditor-social-auth-config",
        "version": APP_VERSION,
        "config": _social_auth_env_config(),
        "notes": [
            "Este endpoint no devuelve credenciales.",
            "Solo confirma si las variables necesarias existen.",
            "No realiza login autom\u00e1tico.",
            "CAPTCHA, 2FA o checkpoint deben reportarse como challenge_required; no se resuelven autom\u00e1ticamente.",
        ],
    }





# ============================================================
# Social Auth Render - controlled authenticated public profile view
# ============================================================


class SocialAuthRenderRequest(BaseModel):
    platform: str = Field(..., description="instagram o facebook")
    profile_url: str = Field(..., description="URL publica del perfil/pagina a auditar")
    company_name: Optional[str] = None
    wait_ms: int = Field(default=3500, ge=1000, le=12000)
    timeout_ms: int = Field(default=90000, ge=15000, le=180000)
    full_page: bool = True
    upload_to_drive: bool = False
    drive_folder_name: Optional[str] = None
    filename: Optional[str] = None


def _sar_bool_env(name: str) -> bool:
    import os as _os
    return str(_os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _sar_get_credentials(platform: str) -> Dict[str, Any]:
    import os as _os

    p = str(platform or "").strip().lower()

    if p == "instagram":
        username = _os.environ.get("INSTAGRAM_AUDIT_USERNAME")
        password = _os.environ.get("INSTAGRAM_AUDIT_PASSWORD")
    elif p == "facebook":
        username = _os.environ.get("FACEBOOK_AUDIT_USERNAME")
        password = _os.environ.get("FACEBOOK_AUDIT_PASSWORD")
    else:
        username = None
        password = None

    return {
        "platform": p,
        "enabled": _sar_bool_env("SOCIAL_AUTH_ENABLED"),
        "username": username,
        "password": password,
        "ready": bool(
            _sar_bool_env("SOCIAL_AUTH_ENABLED")
            and str(username or "").strip()
            and str(password or "").strip()
        ),
    }



def _sar_storage_state_from_env(platform: str) -> Dict[str, Any]:
    import os as _os
    import base64 as _base64
    import json as _json

    p = str(platform or "").strip().lower()

    if p == "facebook":
        env_name = "FACEBOOK_STORAGE_STATE_B64"
    elif p == "instagram":
        env_name = "INSTAGRAM_STORAGE_STATE_B64"
    else:
        env_name = ""

    mode = str(_os.environ.get("SOCIAL_AUTH_STATE_MODE") or "").strip().lower()
    raw_value = _os.environ.get(env_name) if env_name else None

    info = {
        "enabled": mode in {"storage_state", "auto", "1", "true", "yes", "on"},
        "mode": mode,
        "platform": p,
        "env_name": env_name,
        "configured": bool(str(raw_value or "").strip()),
        "available": False,
        "cookies_count": 0,
        "origins_count": 0,
        "state": None,
        "error": None,
    }

    if not info["enabled"]:
        return info

    if not info["configured"]:
        info["error"] = "storage_state_env_missing"
        return info

    try:
        decoded = _base64.b64decode(str(raw_value).strip()).decode("utf-8")
        state = _json.loads(decoded)

        if not isinstance(state, dict):
            raise ValueError("storage_state decoded value is not a JSON object")

        info["cookies_count"] = len(state.get("cookies") or [])
        info["origins_count"] = len(state.get("origins") or [])
        info["state"] = state
        info["available"] = True
        return info

    except Exception as exc:
        info["error"] = f"storage_state_decode_failed: {exc}"
        return info


def _sar_storage_state_public_info(info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": bool(info.get("enabled")),
        "mode": info.get("mode"),
        "platform": info.get("platform"),
        "env_name": info.get("env_name"),
        "configured": bool(info.get("configured")),
        "available": bool(info.get("available")),
        "cookies_count": int(info.get("cookies_count") or 0),
        "origins_count": int(info.get("origins_count") or 0),
        "error": info.get("error"),
    }


def _sar_auth_state_from_classification(classification: str) -> str:
    c = str(classification or "").strip()

    if c == "authenticated_profile_visible":
        return "authenticated_session"
    if c == "profile_visible_with_login_prompt":
        return "profile_visible_public_partial"
    if c in {"login_wall", "login_form_not_found", "login_submit_not_found"}:
        return "login_wall"
    if c == "captcha_required":
        return "captcha_required"
    if c == "checkpoint_required":
        return "checkpoint_required"
    if c in {"failed_runtime", "playwright_unavailable"}:
        return "failed_runtime"
    if c in {"blocked_or_unavailable"}:
        return "blocked_or_unavailable"
    return "unknown_or_partial"


def _sar_visual_access_type(classification: str) -> str:
    c = str(classification or "").strip()

    if c == "authenticated_profile_visible":
        return "authenticated_session"
    if c == "profile_visible_with_login_prompt":
        return "public_partial"
    if c == "login_wall":
        return "none_login_wall"
    if c in {"captcha_required", "checkpoint_required"}:
        return "none_challenge"
    return "none_or_unknown"



def _sar_classify_auth_state(platform: str, final_url: Optional[str], title: Optional[str], text: Optional[str]) -> Dict[str, Any]:
    p = str(platform or "").lower().strip()
    url = str(final_url or "").lower()
    ttl = str(title or "").lower()
    body = str(text or "").lower()
    combined = " ".join([url, ttl, body])

    captcha_markers = [
        "captcha",
        "recaptcha",
        "security check",
        "verificaci\u00f3n de seguridad",
        "confirm you are human",
        "comprueba que eres humano",
    ]

    checkpoint_markers = [
        "checkpoint",
        "two-factor",
        "two factor",
        "2fa",
        "verification code",
        "c\u00f3digo de seguridad",
        "c\u00f3digo de verificaci\u00f3n",
        "approve your login",
        "confirma tu identidad",
        "confirm your identity",
        "suspicious login",
        "login approval",
    ]

    login_markers = [
        "/login",
        "accounts/login",
        "iniciar sesi\u00f3n",
        "inicia sesi\u00f3n",
        "iniciar sesi",
        "inicia sesi",
        "log in",
        "sign in",
        "email or phone",
        "email address",
        "correo electr\u00f3nico",
        "correo electronico",
        "correo electr",
        "n\u00famero de tel\u00e9fono",
        "numero de telefono",
        "contrase\u00f1a",
        "contrasena",
        "contrase",
        "forgot password",
        "olvidaste la cuenta",
        "olvidaste tu contrase\u00f1a",
        "olvidaste tu contrase",
        "crear cuenta nueva",
        "create new account",
        "escanea el c\u00f3digo qr",
        "escanea el codigo qr",
        "c\u00f3digo qr",
        "codigo qr",
        "confirma que coinciden los c\u00f3digos",
        "confirma que coinciden los codigos",
    ]

    visible_markers = {
        "instagram": ["publicaciones", "seguidores", "siguiendo", "posts", "followers", "following"],
        "facebook": ["me gusta", "followers", "seguidores", "publicaciones", "reels", "fotos", "opiniones", "about"],
    }.get(p, [])

    matched_captcha = [m for m in captcha_markers if m in combined]
    matched_checkpoint = [m for m in checkpoint_markers if m in combined]
    matched_login = [m for m in login_markers if m in combined]
    matched_visible = [m for m in visible_markers if m in combined]

    if matched_captcha:
        classification = "captcha_required"
        evidence_grade = "not_profile_evidence"
        usable = False
        reason = "La plataforma solicit\u00f3 CAPTCHA/verificaci\u00f3n humana. No se intenta resolver autom\u00e1ticamente."
    elif matched_checkpoint:
        classification = "checkpoint_required"
        evidence_grade = "not_profile_evidence"
        usable = False
        reason = "La plataforma solicit\u00f3 checkpoint/2FA/verificaci\u00f3n adicional. No se intenta evadir."
    elif matched_visible and matched_login:
        classification = "profile_visible_with_login_prompt"
        evidence_grade = "partial_public_profile_evidence"
        usable = True
        reason = "El perfil/p\u00e1gina p\u00fablica es visible, pero la pantalla conserva prompt de login; sirve como evidencia visual p\u00fablica parcial, no como prueba de sesi\u00f3n autenticada plena."
    elif matched_login:
        classification = "login_wall"
        evidence_grade = "not_profile_evidence"
        usable = False
        reason = "La navegaci\u00f3n termin\u00f3 en login wall o no mantuvo sesi\u00f3n usable."
    elif matched_visible:
        classification = "authenticated_profile_visible"
        evidence_grade = "authenticated_public_profile_evidence"
        usable = True
        reason = "El perfil/p\u00e1gina p\u00fablica fue visible tras login autom\u00e1tico controlado sin prompt de login dominante."
    else:
        classification = "unknown_or_partial"
        evidence_grade = "weak_visual_evidence"
        usable = False
        reason = "La p\u00e1gina carg\u00f3, pero no hay se\u00f1ales suficientes para confirmar perfil p\u00fablico visible."

    return {
        "classification": classification,
        "evidence_grade": evidence_grade,
        "usable_profile_visual_evidence": usable,
        "matched_captcha_markers": matched_captcha[:10],
        "matched_checkpoint_markers": matched_checkpoint[:10],
        "matched_login_markers": matched_login[:10],
        "matched_profile_visible_markers": matched_visible[:10],
        "reason": reason,
        "policy": {
            "captcha_bypass_attempted": False,
            "checkpoint_bypass_attempted": False,
            "private_profile_access_attempted": False,
            "write_actions_attempted": False,
        },
    }



async def _sar_safe_page_title(page: Any) -> str:
    try:
        return await page.title()
    except Exception:
        return ""


async def _sar_safe_page_text(page: Any, timeout_ms: int = 6000, limit: int = 5000) -> str:
    try:
        txt = await page.locator("body").inner_text(timeout=timeout_ms)
        return (txt or "")[:limit]
    except Exception:
        return ""


async def _sar_fill_first_visible(page: Any, selectors: List[str], value: str, timeout_ms: int = 7000) -> Optional[str]:
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout_ms)
            await loc.fill(value, timeout=timeout_ms)
            return selector
        except Exception:
            continue
    return None


async def _sar_click_first_visible(page: Any, selectors: List[str], timeout_ms: int = 5000) -> Optional[str]:
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout_ms)
            await loc.click(timeout=timeout_ms)
            return selector
        except Exception:
            continue
    return None


async def _sar_capture_diagnostic_failure(
    req: SocialAuthRenderRequest,
    page: Any,
    platform: str,
    classification: str,
    reason: str,
    auth_stage: str = "login_attempt",
    extra_limitations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    import uuid as _uuid
    from datetime import datetime as _datetime

    try:
        final_url = page.url
    except Exception:
        final_url = None

    page_title = await _sar_safe_page_title(page)
    visible_text = await _sar_safe_page_text(page, timeout_ms=6000, limit=5000)

    base_classification = _sar_classify_auth_state(
        platform=platform,
        final_url=final_url,
        title=page_title,
        text=visible_text,
    )

    if base_classification.get("classification") in {"captcha_required", "checkpoint_required", "login_wall"}:
        auth_classification = base_classification
    else:
        auth_classification = {
            "classification": classification,
            "evidence_grade": "not_profile_evidence",
            "usable_profile_visual_evidence": False,
            "matched_captcha_markers": base_classification.get("matched_captcha_markers", []),
            "matched_checkpoint_markers": base_classification.get("matched_checkpoint_markers", []),
            "matched_login_markers": base_classification.get("matched_login_markers", []),
            "matched_profile_visible_markers": base_classification.get("matched_profile_visible_markers", []),
            "reason": reason,
            "policy": {
                "captcha_bypass_attempted": False,
                "checkpoint_bypass_attempted": False,
                "private_profile_access_attempted": False,
                "write_actions_attempted": False,
            },
        }

    screenshot_id = None
    drive_upload = None

    try:
        screenshot_bytes = await page.screenshot(full_page=True, type="png")
        screenshot_id = "auth_diag_" + _uuid.uuid4().hex

        if req.upload_to_drive and "_drive_upload_binary" in globals():
            filename = req.filename or f"{platform}_{auth_classification.get('classification')}_{screenshot_id}.png"
            drive_upload = await _drive_upload_binary(
                filename=filename,
                content=screenshot_bytes,
                mime_type="image/png",
                folder_name=req.drive_folder_name,
            )
    except Exception as shot_exc:
        if extra_limitations is None:
            extra_limitations = []
        extra_limitations.append(f"No se pudo capturar/subir screenshot diagnostico: {shot_exc}")

    limitations = [
        "Fallo de login/carga diagnosticado sin intentar bypass.",
        "El screenshot diagnostico, si existe, representa la pantalla alcanzada, no evidencia del perfil.",
        "No se resuelve CAPTCHA, checkpoint ni 2FA.",
    ]

    if extra_limitations:
        limitations.extend(extra_limitations)

    return {
        "status": "completed_with_limitations",
        "platform": platform,
        "company_name": req.company_name,
        "profile_url": req.profile_url,
        "auth_stage": auth_stage,
        "final_url": final_url,
        "page_title": page_title,
        "screenshot_id": screenshot_id,
        "screenshot_stored_in_backend": False,
        "drive_upload": drive_upload,
        "auth_render_classification": auth_classification,
        "text_sample": visible_text[:5000],
        "retrieved_at": _datetime.utcnow().isoformat() + "Z",
        "limitations": limitations,
    }


async def _sar_perform_login(platform: str, page: Any, creds: Dict[str, Any], req: SocialAuthRenderRequest) -> Optional[Dict[str, Any]]:
    if platform == "instagram":
        login_url = "https://www.instagram.com/accounts/login/"
        await page.goto(login_url, wait_until="domcontentloaded", timeout=req.timeout_ms)
        await page.wait_for_timeout(2500)

        await _sar_click_first_visible(
            page,
            [
                "text=Allow all cookies",
                "text=Permitir todas las cookies",
                "text=Accept all cookies",
                "text=Aceptar todas",
                "button:has-text('Allow all cookies')",
                "button:has-text('Permitir')",
                "button:has-text('Aceptar')",
            ],
            timeout_ms=1500,
        )

        username_selector = await _sar_fill_first_visible(
            page,
            [
                'input[name="username"]',
                'input[autocomplete="username"]',
                'input[aria-label*="Phone"]',
                'input[aria-label*="tel\u00e9fono"]',
                'input[aria-label*="Tel\u00e9fono"]',
                'input[type="text"]',
            ],
            str(creds["username"]),
            timeout_ms=7000,
        )

        if not username_selector:
            return await _sar_capture_diagnostic_failure(
                req=req,
                page=page,
                platform=platform,
                classification="login_form_not_found",
                reason="No se encontr\u00f3 campo visible de usuario en el login de Instagram.",
                auth_stage="login_form_detection",
            )

        password_selector = await _sar_fill_first_visible(
            page,
            [
                'input[name="password"]',
                'input[autocomplete="current-password"]',
                'input[aria-label*="Password"]',
                'input[aria-label*="Contrase\u00f1a"]',
                'input[type="password"]',
            ],
            str(creds["password"]),
            timeout_ms=7000,
        )

        if not password_selector:
            return await _sar_capture_diagnostic_failure(
                req=req,
                page=page,
                platform=platform,
                classification="login_form_not_found",
                reason="No se encontr\u00f3 campo visible de password en el login de Instagram.",
                auth_stage="login_form_detection",
            )

        clicked = await _sar_click_first_visible(
            page,
            [
                'button[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Iniciar sesi\u00f3n")',
                'div[role="button"]:has-text("Log in")',
                'div[role="button"]:has-text("Iniciar sesi\u00f3n")',
            ],
            timeout_ms=7000,
        )

        if not clicked:
            try:
                await page.keyboard.press("Enter")
            except Exception:
                return await _sar_capture_diagnostic_failure(
                    req=req,
                    page=page,
                    platform=platform,
                    classification="login_submit_not_found",
                    reason="No se encontr\u00f3 bot\u00f3n submit ni se pudo enviar el formulario de Instagram con Enter.",
                    auth_stage="login_submit_detection",
                )

        await page.wait_for_timeout(req.wait_ms)
        return None

    if platform == "facebook":
        login_url = "https://www.facebook.com/login"
        await page.goto(login_url, wait_until="domcontentloaded", timeout=req.timeout_ms)
        await page.wait_for_timeout(2500)

        await _sar_click_first_visible(
            page,
            [
                "text=Allow all cookies",
                "text=Permitir todas las cookies",
                "text=Accept all cookies",
                "text=Aceptar todas",
                "button:has-text('Allow all cookies')",
                "button:has-text('Permitir')",
                "button:has-text('Aceptar')",
            ],
            timeout_ms=1500,
        )

        email_selector = await _sar_fill_first_visible(
            page,
            [
                'input[name="email"]',
                'input#email',
                'input[type="email"]',
                'input[autocomplete="username"]',
                'input[aria-label*="Email"]',
                'input[aria-label*="Correo"]',
                'input[type="text"]',
            ],
            str(creds["username"]),
            timeout_ms=7000,
        )

        if not email_selector:
            return await _sar_capture_diagnostic_failure(
                req=req,
                page=page,
                platform=platform,
                classification="login_form_not_found",
                reason="No se encontr\u00f3 campo visible de usuario/email en el login de Facebook.",
                auth_stage="login_form_detection",
            )

        password_selector = await _sar_fill_first_visible(
            page,
            [
                'input[name="pass"]',
                'input#pass',
                'input[autocomplete="current-password"]',
                'input[aria-label*="Password"]',
                'input[aria-label*="Contrase\u00f1a"]',
                'input[type="password"]',
            ],
            str(creds["password"]),
            timeout_ms=7000,
        )

        if not password_selector:
            return await _sar_capture_diagnostic_failure(
                req=req,
                page=page,
                platform=platform,
                classification="login_form_not_found",
                reason="No se encontr\u00f3 campo visible de password en el login de Facebook.",
                auth_stage="login_form_detection",
            )

        clicked = await _sar_click_first_visible(
            page,
            [
                'button[name="login"]',
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Iniciar sesi\u00f3n")',
            ],
            timeout_ms=7000,
        )

        if not clicked:
            try:
                await page.keyboard.press("Enter")
            except Exception:
                return await _sar_capture_diagnostic_failure(
                    req=req,
                    page=page,
                    platform=platform,
                    classification="login_submit_not_found",
                    reason="No se encontr\u00f3 bot\u00f3n submit ni se pudo enviar el formulario de Facebook con Enter.",
                    auth_stage="login_submit_detection",
                )

        await page.wait_for_timeout(req.wait_ms)
        return None

    return await _sar_capture_diagnostic_failure(
        req=req,
        page=page,
        platform=platform,
        classification="unsupported_platform",
        reason="Plataforma no soportada por el login autenticado.",
        auth_stage="unsupported_platform",
    )



async def _sar_login_and_capture(req: SocialAuthRenderRequest) -> Dict[str, Any]:
    import asyncio as _asyncio
    import uuid as _uuid
    from datetime import datetime as _datetime

    platform = str(req.platform or "").strip().lower()
    creds = _sar_get_credentials(platform)

    if platform not in {"instagram", "facebook"}:
        return {
            "status": "failed",
            "classification": "unsupported_platform",
            "reason": "Solo se soporta instagram o facebook en esta etapa.",
        }

    if not creds.get("ready"):
        return {
            "status": "failed",
            "classification": "missing_auth_config",
            "reason": "SOCIAL_AUTH_ENABLED y credenciales de la plataforma deben estar configuradas en Render.",
            "auth_config": {
                "enabled": creds.get("enabled"),
                "username_configured": bool(str(creds.get("username") or "").strip()),
                "password_configured": bool(str(creds.get("password") or "").strip()),
            },
        }

    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        return {
            "status": "failed_runtime",
            "classification": "playwright_unavailable",
            "reason": f"Playwright no est\u00e1 disponible en runtime: {exc}",
        }

    browser = None
    context = None
    page = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            storage_state_info = _sar_storage_state_from_env(platform)

            context_kwargs = {
                "viewport": {"width": 1365, "height": 900},
                "locale": "es-AR",
                "timezone_id": "America/Argentina/Cordoba",
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            }

            if storage_state_info.get("available") and storage_state_info.get("state") is not None:
                context_kwargs["storage_state"] = storage_state_info["state"]

            context = await browser.new_context(**context_kwargs)

            page = await context.new_page()
            page.set_default_timeout(req.timeout_ms)

            if storage_state_info.get("available"):
                await page.goto(str(req.profile_url), wait_until="domcontentloaded", timeout=req.timeout_ms)
                await page.wait_for_timeout(req.wait_ms)

                final_url = page.url
                page_title = await page.title()

                visible_text = ""
                try:
                    visible_text = await page.locator("body").inner_text(timeout=12000)
                except Exception:
                    visible_text = ""

                classification = _sar_classify_auth_state(
                    platform=platform,
                    final_url=final_url,
                    title=page_title,
                    text=visible_text,
                )

                class_name = classification.get("classification")
                auth_state = _sar_auth_state_from_classification(class_name)
                visual_access_type = _sar_visual_access_type(class_name)

                screenshot_bytes = await page.screenshot(full_page=req.full_page, type="png")
                screenshot_id = "state_" + _uuid.uuid4().hex

                links_count = 0
                images_count = 0
                forms_count = 0

                try:
                    links_count = await page.locator("a").count()
                    images_count = await page.locator("img").count()
                    forms_count = await page.locator("form").count()
                except Exception:
                    pass

                drive_upload = None
                if req.upload_to_drive and "_drive_upload_binary" in globals():
                    filename = req.filename or f"{platform}_storage_state_render_{screenshot_id}.png"
                    drive_upload = await _drive_upload_binary(
                        filename=filename,
                        content=screenshot_bytes,
                        mime_type="image/png",
                        folder_name=req.drive_folder_name,
                    )

                await context.close()
                await browser.close()

                return {
                    "status": "completed" if classification.get("usable_profile_visual_evidence") else "completed_with_limitations",
                    "platform": platform,
                    "company_name": req.company_name,
                    "profile_url": req.profile_url,
                    "auth_stage": "storage_state_profile_view",
                    "auth_method": "storage_state",
                    "storage_state": _sar_storage_state_public_info(storage_state_info),
                    "login_attempted": False,
                    "login_successful": class_name == "authenticated_profile_visible",
                    "session_authenticated": class_name == "authenticated_profile_visible",
                    "session_reused": True,
                    "session_expired": class_name in {"login_wall", "login_form_not_found", "login_submit_not_found"},
                    "auth_state": auth_state,
                    "visual_access_type": visual_access_type,
                    "final_url": final_url,
                    "page_title": page_title,
                    "screenshot_id": screenshot_id,
                    "screenshot_stored_in_backend": False,
                    "drive_upload": drive_upload,
                    "auth_render_classification": classification,
                    "text_sample": (visible_text or "")[:5000],
                    "links_count": links_count,
                    "forms_count": forms_count,
                    "images_count": images_count,
                    "retrieved_at": _datetime.utcnow().isoformat() + "Z",
                    "limitations": [
                        "Se us\u00f3 storage_state persistente generado localmente.",
                        "No se expone storage_state, cookies ni credenciales.",
                        "No se resuelve CAPTCHA, checkpoint ni 2FA.",
                        "No se realizan acciones de escritura.",
                        "Si session_expired=true, regenerar storage_state localmente.",
                    ],
                }

            login_failure = await _sar_perform_login(platform, page, creds, req)

            if login_failure is not None:
                await context.close()
                await browser.close()
                return login_failure

            post_login_url = page.url
            post_login_title = await page.title()
            post_login_text = ""
            try:
                post_login_text = await page.locator("body").inner_text(timeout=8000)
            except Exception:
                post_login_text = ""

            post_login_classification = _sar_classify_auth_state(
                platform=platform,
                final_url=post_login_url,
                title=post_login_title,
                text=post_login_text,
            )

            if post_login_classification.get("classification") in {"captcha_required", "checkpoint_required"}:
                screenshot_bytes = await page.screenshot(full_page=True, type="png")
                screenshot_id = "auth_" + _uuid.uuid4().hex

                drive_upload = None
                if req.upload_to_drive and "_drive_upload_binary" in globals():
                    filename = req.filename or f"{platform}_auth_challenge_{screenshot_id}.png"
                    drive_upload = await _drive_upload_binary(
                        filename=filename,
                        content=screenshot_bytes,
                        mime_type="image/png",
                        folder_name=req.drive_folder_name,
                    )

                await context.close()
                await browser.close()

                return {
                    "status": "completed_with_limitations",
                    "platform": platform,
                    "profile_url": req.profile_url,
                    "auth_stage": "post_login",
                    "final_url": post_login_url,
                    "page_title": post_login_title,
                    "screenshot_id": screenshot_id,
                    "screenshot_stored_in_backend": False,
                    "drive_upload": drive_upload,
                    "auth_render_classification": post_login_classification,
                    "text_sample": (post_login_text or "")[:2500],
                    "retrieved_at": _datetime.utcnow().isoformat() + "Z",
                    "limitations": [
                        "Se detect\u00f3 challenge/captcha/checkpoint; no se intenta resolver autom\u00e1ticamente.",
                        "El screenshot representa el bloqueo, no evidencia visual del perfil.",
                    ],
                }

            await page.goto(str(req.profile_url), wait_until="domcontentloaded", timeout=req.timeout_ms)
            await page.wait_for_timeout(req.wait_ms)

            final_url = page.url
            page_title = await page.title()

            visible_text = ""
            try:
                visible_text = await page.locator("body").inner_text(timeout=12000)
            except Exception:
                visible_text = ""

            classification = _sar_classify_auth_state(
                platform=platform,
                final_url=final_url,
                title=page_title,
                text=visible_text,
            )

            screenshot_bytes = await page.screenshot(full_page=req.full_page, type="png")
            screenshot_id = "auth_" + _uuid.uuid4().hex

            links_count = 0
            images_count = 0
            forms_count = 0

            try:
                links_count = await page.locator("a").count()
                images_count = await page.locator("img").count()
                forms_count = await page.locator("form").count()
            except Exception:
                pass

            drive_upload = None
            if req.upload_to_drive and "_drive_upload_binary" in globals():
                filename = req.filename or f"{platform}_authenticated_render_{screenshot_id}.png"
                drive_upload = await _drive_upload_binary(
                    filename=filename,
                    content=screenshot_bytes,
                    mime_type="image/png",
                    folder_name=req.drive_folder_name,
                )

            await context.close()
            await browser.close()

            return {
                "status": "completed",
                "platform": platform,
                "company_name": req.company_name,
                "profile_url": req.profile_url,
                "auth_stage": "profile_view",
                "final_url": final_url,
                "page_title": page_title,
                "screenshot_id": screenshot_id,
                "screenshot_stored_in_backend": False,
                "drive_upload": drive_upload,
                "auth_render_classification": classification,
                "text_sample": (visible_text or "")[:5000],
                "links_count": links_count,
                "forms_count": forms_count,
                "images_count": images_count,
                "retrieved_at": _datetime.utcnow().isoformat() + "Z",
                "limitations": [
                    "Login autom\u00e1tico controlado con cuenta dedicada.",
                    "No se accede a perfiles privados, DMs ni datos no p\u00fablicos.",
                    "No se realizan acciones de escritura.",
                    "CAPTCHA, 2FA o checkpoint se reportan; no se resuelven autom\u00e1ticamente.",
                    "La evidencia autenticada visible no reemplaza exports nativos de Meta/Instagram Insights.",
                ],
            }

    except Exception as exc:
        try:
            if context:
                await context.close()
        except Exception:
            pass
        try:
            if browser:
                await browser.close()
        except Exception:
            pass

        return {
            "status": "failed_runtime",
            "platform": platform,
            "profile_url": req.profile_url,
            "auth_render_classification": {
                "classification": "failed_runtime",
                "evidence_grade": "not_profile_evidence",
                "usable_profile_visual_evidence": False,
                "reason": str(exc),
                "policy": {
                    "captcha_bypass_attempted": False,
                    "checkpoint_bypass_attempted": False,
                    "private_profile_access_attempted": False,
                    "write_actions_attempted": False,
                },
            },
            "limitations": [
                "Fall\u00f3 el render autenticado en runtime.",
                "No se debe tratar como evidencia visual del perfil.",
            ],
        }


@app.post("/audit/social-auth-render")
async def audit_social_auth_render(
    req: SocialAuthRenderRequest,
    _: None = Depends(verify_api_key),
) -> Dict[str, Any]:
    result = await _sar_login_and_capture(req)
    return {
        "collector": "social_auth_render",
        "version": APP_VERSION,
        **result,
    }




@app.get("/debug/collector-config")
async def collector_config(_: None = Depends(verify_api_key)) -> Dict[str, Any]:
    return {
        "version": APP_VERSION,
        "configured_tools": {
            "firecrawl": bool(FIRECRAWL_API_KEY),
            "browserbase": bool(BROWSERBASE_API_KEY),
            "composio": bool(COMPOSIO_API_KEY),
            "tavily": bool(TAVILY_API_KEY),
            "serper": bool(SERPER_API_KEY),
            "youtube": bool(YOUTUBE_API_KEY),
        },
        "notes": build_collector_notes(),
    }



def _compact_value_for_action(value: Any, max_chars: int = 700) -> Any:
    if value is None:
        return None

    if isinstance(value, (int, float, bool)):
        return value

    if isinstance(value, str):
        return truncate(collapse_ws(value), max_chars)

    if isinstance(value, list):
        out = []
        for item in value[:20]:
            out.append(_compact_value_for_action(item, max_chars=max_chars))
        return out

    if isinstance(value, dict):
        blocked_keys = {
            "raw",
            "raw_html",
            "html",
            "markdown",
            "content",
            "page_content",
            "body",
            "text",
            "screenshot_base64",
            "base64",
            "debug_raw",
        }

        out: Dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            low = key.lower()

            if low in blocked_keys:
                out[key] = "[omitted_large_field]"
                continue

            if any(token in low for token in ["raw", "html", "markdown", "base64"]):
                out[key] = "[omitted_large_field]"
                continue

            out[key] = _compact_value_for_action(v, max_chars=max_chars)

            if len(out) >= 30:
                break

        return out

    return truncate(collapse_ws(str(value)), max_chars)


def _compact_report_item(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {"value": _compact_value_for_action(item, 300)}

    keys = [
        "collector",
        "platform",
        "status",
        "source",
        "url",
        "reason",
        "confidence",
        "data_quality",
        "fields_collected",
        "fields_missing",
    ]

    out: Dict[str, Any] = {}
    for key in keys:
        if key in item:
            out[key] = _compact_value_for_action(item.get(key), 350)

    details = item.get("details")
    if isinstance(details, dict):
        detail_out: Dict[str, Any] = {}
        for k, v in details.items():
            lk = str(k).lower()
            if any(token in lk for token in ["raw", "html", "markdown", "content", "base64"]):
                continue
            detail_out[str(k)] = _compact_value_for_action(v, 350)
            if len(detail_out) >= 12:
                break
        if detail_out:
            out["details"] = detail_out

    return out


def _compact_evidence_item(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {"value": _compact_value_for_action(item, 300)}

    keys = [
        "source",
        "platform",
        "field",
        "value",
        "url",
        "confidence",
        "retrieved_at",
        "notes",
    ]

    out: Dict[str, Any] = {}
    for key in keys:
        if key in item:
            out[key] = _compact_value_for_action(item.get(key), 500)

    return out


def _compact_txt_report_info(txt_report: Any) -> Dict[str, Any]:
    if not isinstance(txt_report, dict):
        return {}

    allowed = [
        "report_id",
        "download_url",
        "url",
        "filename",
        "media_type",
        "available",
        "created_at",
    ]

    out: Dict[str, Any] = {}
    for key in allowed:
        if key in txt_report:
            out[key] = txt_report.get(key)

    for key, value in txt_report.items():
        lk = str(key).lower()
        if "id" in lk and "report_id" not in out:
            out["report_id"] = value
        if "url" in lk and "download_url" not in out:
            out["download_url"] = value

    return out


def compact_public_presence_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    execution = payload.get("collection_execution_report") or {}
    collector_reports = payload.get("collector_reports") or []
    evidence_registry = payload.get("evidence_registry") or []
    unavailable_data = payload.get("unavailable_data") or []
    requires_owner_access = payload.get("requires_owner_access") or []
    field_recovery_guide = payload.get("field_recovery_guide") or []

    compact_reports = [_compact_report_item(x) for x in collector_reports[:35]]
    compact_evidence = [_compact_evidence_item(x) for x in evidence_registry[:40]]

    txt_report = _compact_txt_report_info(payload.get("txt_report") or {})

    return {
        "collection_status": payload.get("collection_status"),
        "collector_version": payload.get("collector_version"),
        "created_at": payload.get("created_at"),
        "company_name": payload.get("company_name"),
        "assets_received": _compact_value_for_action(payload.get("assets_received"), 500),
        "collection_depth": payload.get("collection_depth"),
        "collection_hash": payload.get("collection_hash"),
        "response_mode": "compact_for_gpt_action",
        "txt_report": txt_report,
        "report_id": txt_report.get("report_id"),
        "download_url": txt_report.get("download_url") or txt_report.get("url"),
        "execution_summary": {
            "overall_status": execution.get("overall_status"),
            "collectors_attempted_or_evaluated": execution.get("collectors_attempted_or_evaluated"),
            "collectors_completed": execution.get("collectors_completed"),
            "collectors_partial": execution.get("collectors_partial"),
            "collectors_skipped": execution.get("collectors_skipped"),
            "collectors_failed": execution.get("collectors_failed"),
            "collectors_not_implemented": execution.get("collectors_not_implemented"),
            "status_counts": execution.get("status_counts"),
        },
        "metrics_summary_compact": _compact_value_for_action(payload.get("metrics_summary"), 700),
        "tool_summaries_compact": _compact_value_for_action(payload.get("tool_summaries"), 700),
        "collector_reports_count": len(collector_reports),
        "collector_reports_sample": compact_reports,
        "evidence_registry_count": len(evidence_registry),
        "evidence_registry_sample": compact_evidence,
        "unavailable_data_count": len(unavailable_data),
        "unavailable_data_sample": _compact_value_for_action(unavailable_data[:20], 450),
        "requires_owner_access_count": len(requires_owner_access),
        "requires_owner_access_sample": _compact_value_for_action(requires_owner_access[:20], 450),
        "field_recovery_guide_sample": _compact_value_for_action(field_recovery_guide[:20], 450),
        "limitations": [
            "Respuesta compactada para evitar ResponseTooLargeError en GPT Actions.",
            "Usar getTextReport con report_id/download_url para revisar el informe completo.",
            "No afirmar ventas, ROAS, CPA, conversion, margen, trafico ni calidad de lead sin acceso privado.",
        ],
    }


@app.post("/collect/public-presence-compact")
async def collect_public_presence_compact(req: PublicPresenceCollectRequest, _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    full_payload = await collect_public_presence(req)
    return compact_public_presence_payload(full_payload)


@app.post("/collect/public-presence")
async def collect_public_presence(req: PublicPresenceCollectRequest, _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    created_at = now_iso()
    assets = merge_assets(req)
    if not any(assets.values()):
        raise HTTPException(status_code=400, detail="Se requiere al menos un link p\u00fablico: sitio web o red social.")

    evidence = EvidenceBuilder()
    reports: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}

    # Declared input evidence, clearly separated from observed evidence.
    if req.company_name:
        evidence.add("declared_input", None, "input_parser", "company_name", req.company_name, "medium", evidence_type="declared_input")
    for platform, url in assets.items():
        if url:
            evidence.add(platform, url, "input_parser", "asset_url_declared", url, "low", limitations=["Un link declarado no prueba que el contenido haya sido le\u00eddo."], evidence_type="declared_input")

    website_result = await collect_website_static(assets.get("website"), req.max_website_pages, evidence)
    reports.extend(website_result["reports"])
    summaries["website_static"] = website_result["summary"]

    firecrawl_result = await collect_firecrawl(assets.get("website"), evidence)
    reports.extend(firecrawl_result["reports"])
    summaries["firecrawl"] = firecrawl_result["summary"]

    browserbase_result = await collect_browserbase_placeholder(assets.get("website"))
    reports.extend(browserbase_result["reports"])
    summaries["browserbase"] = browserbase_result["summary"]

    youtube_result = await collect_youtube(assets.get("youtube"), evidence)
    reports.extend(youtube_result["reports"])
    summaries["youtube"] = youtube_result["summary"]

    for platform in ["instagram", "facebook", "linkedin", "tiktok", "x"]:
        result = await collect_social_public(platform, assets.get(platform), evidence)
        reports.extend(result["reports"])
        summaries[platform] = result["summary"]

    search_result = await collect_public_search_enrichment(req.company_name, assets.get("website"), evidence)
    reports.extend(search_result["reports"])
    summaries["search_enrichment"] = search_result["summary"]

    execution = summarize_execution(reports)
    recovery = dedupe_recovery_guide(build_recovery_guide(reports))
    metrics_summary = build_metrics_summary(evidence.items, reports)
    unavailable_data = [
        {"platform": g.get("platform"), "field": g.get("field"), "reason": g.get("why_not_collected")}
        for g in recovery
        if g.get("status") in {"not_collected", "requires_owner_access"}
    ]
    requires_owner_access = [g for g in recovery if g.get("requires_client_permission")]

    temp_payload_for_analysis: Dict[str, Any] = {
        "collection_status": execution["overall_status"],
        "collector_version": APP_VERSION,
        "created_at": created_at,
        "company_name": req.company_name,
        "assets_received": assets,
        "collection_execution_report": execution,
        "collector_reports": reports,
        "evidence_registry": evidence.items,
        "metrics_summary": metrics_summary,
        "field_recovery_guide": recovery,
    }
    public_presence_score = build_public_presence_score(temp_payload_for_analysis)
    temp_payload_for_analysis["public_presence_score"] = public_presence_score
    executive_public_audit = build_executive_public_audit(temp_payload_for_analysis)

    response_payload: Dict[str, Any] = {
        "collection_status": execution["overall_status"],
        "collector_version": APP_VERSION,
        "created_at": created_at,
        "company_name": req.company_name,
        "assets_received": assets,
        "collection_depth": req.collection_depth,
        "collection_hash": "pending",
        "collection_execution_report": execution,
        "collector_reports": reports,
        "evidence_registry": evidence.items,
        "metrics_summary": metrics_summary,
        "public_presence_score": public_presence_score,
        "executive_public_audit": executive_public_audit,
        "field_recovery_guide": recovery,
        "unavailable_data": unavailable_data,
        "requires_owner_access": requires_owner_access,
        "tool_summaries": summaries,
        "txt_report": {},
        "non_analysis_guards": [
            "Este endpoint genera auditoria de presencia publica; no diagnostico de performance comercial privada.",
            "No afirmar performance, ROAS, CPA, CPL, conversi\u00f3n, ventas ni calidad de lead con este output.",
            "Los datos no recolectados deben explicarse mediante field_recovery_guide.",
        ],
    }
    response_payload["collection_hash"] = hash_payload({"assets": assets, "evidence": evidence.items, "reports": reports, "version": APP_VERSION})

    txt = build_txt_report(response_payload)
    report_id = uuid.uuid4().hex
    filename = f"public_presence_{(req.company_name or 'empresa').lower().replace(' ', '_')}_{report_id[:8]}.txt"
    TEXT_REPORTS[report_id] = {"filename": filename, "content": txt, "created_at": created_at}
    response_payload["txt_report"] = {
        "status": "generated",
        "language": "es",
        "report_id": report_id,
        "filename": filename,
        "download_url": f"{PUBLIC_BASE_URL}/deliverables/text/{report_id}.txt",
    }
    return response_payload



@app.get("/deliverables/screenshot/{screenshot_id}.png")
async def get_screenshot(screenshot_id: str) -> Response:
    item = SCREENSHOTS.get(screenshot_id)
    if not item:
        raise HTTPException(status_code=404, detail="Screenshot not found or expired")
    headers = {
        "Content-Disposition": f"inline; filename={item.get('filename', 'browser_render.png')}"
    }
    return Response(content=item["content"], media_type="image/png", headers=headers)


@app.get("/deliverables/text/{report_id}.txt")
async def get_text_report(report_id: str) -> Response:
    item = TEXT_REPORTS.get(report_id)
    if not item:
        raise HTTPException(status_code=404, detail="Text report not found or expired")
    headers = {"Content-Disposition": f"attachment; filename={item['filename']}"}
    return Response(content=item["content"], media_type="text/plain; charset=utf-8", headers=headers)


# ============================================================
# MICRO PATCH 4F.3-C/4F.3-D - Instagram profile public metrics + posts hardening
# ============================================================

from pydantic import BaseModel as _IGBaseModel, Field as _IGField
from typing import Optional as _IGOptional, Dict as _IGDict, Any as _IGAny, List as _IGList
import re as _ig_re
import statistics as _ig_statistics
from datetime import datetime as _ig_datetime, date as _ig_date, timedelta as _ig_timedelta, timezone as _ig_timezone


class InstagramProfileMetricsRequest(_IGBaseModel):
    profile_url: str = _IGField(..., description="Instagram public profile URL.")
    company_name: _IGOptional[str] = None
    max_posts: int = _IGField(20, ge=1, le=50)
    max_scan_posts: int = _IGField(120, ge=20, le=220)
    wait_ms: int = _IGField(9000, ge=1000, le=30000)
    timeout_ms: int = _IGField(120000, ge=15000, le=180000)
    full_page: bool = True
    upload_to_drive: bool = True
    drive_folder_name: _IGOptional[str] = None
    filename_prefix: _IGOptional[str] = None
    include_bio_link_expansion: bool = True
    enable_mobile_fallback: bool = True
    enable_html_url_scan: bool = True
    scroll_rounds: int = _IGField(22, ge=4, le=60)
    parse_posts: bool = True
    fast_diagnostic: bool = False


def _igpm_field_status(value: _IGAny, visible_message: str, not_visible_message: str) -> _IGDict[str, _IGAny]:
    if value is None:
        return {"value": None, "visibility": "not_visible_publicly", "message": not_visible_message}
    if isinstance(value, str) and not value.strip():
        return {"value": value, "visibility": "not_visible_publicly", "message": not_visible_message}
    if isinstance(value, list) and len(value) == 0:
        return {"value": value, "visibility": "not_visible_publicly", "message": not_visible_message}
    return {"value": value, "visibility": "visible", "message": visible_message}


def _igpm_runtime_status(message: str) -> _IGDict[str, _IGAny]:
    return {"value": None, "visibility": "not_collected_runtime", "message": message}


def _igpm_parse_compact_number(value: _IGOptional[str]) -> _IGOptional[int]:
    if value is None:
        return None
    s = str(value).strip().lower().replace("\u00a0", " ").replace(",", ".")
    if not s:
        return None
    multiplier = 1
    if "mill" in s or "millones" in s or s.endswith("m"):
        multiplier = 1000000
    elif "mil" in s or s.endswith("k"):
        multiplier = 1000
    num_match = _ig_re.search(r"(\d+(?:[.,]\d+)?)", s)
    if not num_match:
        return None
    try:
        return int(round(float(num_match.group(1).replace(",", ".")) * multiplier))
    except Exception:
        return None


def _igpm_normalize_url(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("\\/"):
        u = u.replace("\\/", "/")
    return u


def _igpm_profile_username(url: str) -> str:
    m = _ig_re.search(r"instagram\.com/([^/?#]+)/?", str(url or ""), flags=_ig_re.I)
    if not m:
        return ""
    user = m.group(1).strip()
    if user in {"p", "reel", "tv", "explore", "accounts"}:
        return ""
    return user


def _igpm_is_instagram_post_url(url: str) -> bool:
    u = str(url or "").lower()
    return ("instagram.com/p/" in u) or ("instagram.com/reel/" in u) or ("instagram.com/tv/" in u)


def _igpm_clean_post_url(url: str) -> str:
    u = _igpm_normalize_url(url)
    u = u.replace("\\/", "/")
    if u.startswith("/p/") or u.startswith("/reel/") or u.startswith("/tv/"):
        u = "https://www.instagram.com" + u
    if not u.startswith("http"):
        return ""
    u = u.split("?")[0].split("#")[0].rstrip("/") + "/"
    return u


def _igpm_is_external_link(url: str) -> bool:
    u = str(url or "").lower().strip()
    if not u:
        return False
    if u.startswith("mailto:") or u.startswith("tel:"):
        return True
    if not (u.startswith("http://") or u.startswith("https://")):
        return False
    return not any(b in u for b in [
        "instagram.com", "facebook.com", "fb.com", "meta.com", "meta.ai",
        "threads.com", "help.instagram.com", "privacycenter.instagram.com",
        "about.instagram.com", "accountscenter.instagram.com",
    ])


def _igpm_is_footer_or_platform_link(url: str, text: str = "") -> bool:
    combined = (str(url or "") + " " + str(text or "")).lower()
    markers = ["meta ai", "threads", "meta.ai", "threads.com", "about", "help", "privacy", "terms", "locations", "instagram lite", "contact uploading", "verified", "api", "jobs", "blog", "developers"]
    return any(m in combined for m in markers)


def _igpm_is_link_tree_candidate(url: str) -> bool:
    u = str(url or "").lower()
    domains = ["linktr.ee", "beacons.ai", "bio.site", "campsite.bio", "solo.to", "taplink", "lnk.bio", "linkin.bio", "msha.ke", "flow.page", "hoo.be", "wa.me", "api.whatsapp.com"]
    return any(d in u for d in domains)


def _igpm_extract_hashtags(text: str) -> _IGList[str]:
    # Extrae hashtags visibles sin rangos Unicode fragiles.
    # Evita rangos Unicode que pueden romperse por encoding/mojibake.
    raw_text = str(text or "")
    candidates = _ig_re.findall(r"#[^\s#]+", raw_text, flags=_ig_re.UNICODE)
    seen = set()
    out = []
    trailing_punctuation = '.,;:!???)]}>)"\u00e2\u20ac\u0153\u00e2\u20ac\u009d\u00e2\u20ac\u02dc\u00e2\u20ac\u2122`\u00c2\u00b4\u00e2\u20ac\u00a6'
    for tag in candidates:
        clean = tag.strip().rstrip(trailing_punctuation)
        if len(clean) <= 1:
            continue
        if any(x in clean for x in ["<", ">", "=", "http://", "https://", "&quot;"]):
            continue
        # Filtra falsos positivos tomados de CSS/HTML, por ejemplo #000000 o #FFFFFF.
        # Mantiene hashtags num\u00e9ricos leg\u00edtimos de campa\u00f1as como #2026.
        if _ig_re.fullmatch(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?", clean):
            continue
        key = clean.casefold()
        if key not in seen:
            seen.add(key)
            out.append(clean)
    return out


def _igpm_parse_iso_datetime(value: _IGOptional[str]) -> _IGOptional[str]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        _ig_datetime.fromisoformat(s.replace("Z", "+00:00"))
        return s
    except Exception:
        return s


def _igpm_date_from_iso(value: _IGOptional[str]) -> _IGOptional[_ig_date]:
    if not value:
        return None
    try:
        return _ig_datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        return None


def _igpm_parse_likes(text: str) -> _IGOptional[int]:
    t = (text or "").replace("\u00a0", " ")
    patterns = [
        r"([\d.,]+(?:\s*(?:mil|k|m|millones))?)\s+Me gusta",
        r"([\d.,]+(?:\s*(?:mil|k|m|millones))?)\s+likes",
        r"([\d.,]+(?:\s*(?:mil|k|m|millions))?)\s+likes",
        r"Le gusta a\s+.+?\s+y\s+([\d.,]+(?:\s*(?:mil|k|m|millones))?)\s+personas\s+m[a\u00e1]s",
        r"Liked by\s+.+?\s+and\s+([\d.,]+(?:\s*(?:mil|k|m|millions))?)\s+others",
        r"([\d.,]+(?:\s*(?:mil|k|m|millones))?)\s+personas\s+les\s+gusta",
    ]
    for pat in patterns:
        m = _ig_re.search(pat, t, flags=_ig_re.IGNORECASE | _ig_re.DOTALL)
        if m:
            return _igpm_parse_compact_number(m.group(1))
    return None


def _igpm_profile_counts_from_text(text: str) -> _IGDict[str, _IGOptional[int]]:
    body = (text or "").replace("\u00a0", " ").lower()
    def find(label_patterns: _IGList[str]) -> _IGOptional[int]:
        for label in label_patterns:
            for pat in [rf"([\d.,]+(?:\s*(?:mil|k|m|millones))?)\s+{label}", rf"{label}\s+([\d.,]+(?:\s*(?:mil|k|m|millones))?)"]:
                m = _ig_re.search(pat, body, flags=_ig_re.IGNORECASE)
                if m:
                    return _igpm_parse_compact_number(m.group(1))
        return None
    return {"posts_total": find(["publicaciones", "posts"]), "followers_total": find(["seguidores", "followers"]), "following_total": find(["seguidos", "siguiendo", "following"])}


def _igpm_profile_counts_status(counts: _IGDict[str, _IGOptional[int]]) -> _IGDict[str, _IGAny]:
    return {
        "posts_total": _igpm_field_status(counts.get("posts_total"), "Publicaciones totales visibles en el perfil.", "El perfil no muestra publicamente el total de publicaciones en esta vista."),
        "followers_total": _igpm_field_status(counts.get("followers_total"), "Seguidores totales visibles en el perfil.", "El perfil no muestra publicamente el total de seguidores en esta vista."),
        "following_total": _igpm_field_status(counts.get("following_total"), "Seguidos/siguiendo visibles en el perfil.", "El perfil no muestra publicamente el total de seguidos/siguiendo en esta vista."),
    }


def _igpm_get_reporting_window(today: _IGOptional[_ig_date] = None) -> _IGDict[str, str]:
    if today is None:
        today = _ig_datetime.now(_ig_timezone(_ig_timedelta(hours=-3))).date()
    if today.day <= 7:
        first_this_month = today.replace(day=1)
        end = first_this_month - _ig_timedelta(days=1)
        start = end.replace(day=1)
        mode = "previous_month_because_first_week"
    else:
        start = today.replace(day=1)
        end = today
        mode = "current_month_to_date"
    return {"mode": mode, "start_date": start.isoformat(), "end_date": end.isoformat(), "days": str((end - start).days + 1)}


def _igpm_compute_frequency(posts: _IGList[_IGDict[str, _IGAny]], window: _IGDict[str, str]) -> _IGDict[str, _IGAny]:
    start = _ig_date.fromisoformat(window["start_date"])
    end = _ig_date.fromisoformat(window["end_date"])
    days = max((end - start).days + 1, 1)
    dated = []
    for p in posts:
        d = _igpm_date_from_iso(p.get("date_iso"))
        if d and start <= d <= end:
            dated.append(d)
    dated_sorted = sorted(dated)
    intervals = []
    for i in range(1, len(dated_sorted)):
        intervals.append((dated_sorted[i] - dated_sorted[i - 1]).days)
    return {
        "window": window,
        "posts_in_window": len(dated),
        "posts_per_week": round((len(dated) / days) * 7, 2) if dated else None,
        "average_days_between_posts": round(_ig_statistics.mean(intervals), 2) if intervals else None,
        "dated_posts_used": [d.isoformat() for d in dated_sorted],
        "status": "calculated" if dated else "not_calculable",
        "message": "Frecuencia calculada con fechas visibles." if dated else "No se puede calcular frecuencia porque no hay fechas visibles suficientes en la ventana definida.",
    }


async def _igpm_inner_text(page, timeout_ms: int = 8000, limit: int = 8000) -> str:
    try:
        txt = await page.locator("body").inner_text(timeout=timeout_ms)
        return (txt or "")[:limit]
    except Exception:
        return ""


async def _igpm_meta_text(page) -> str:
    parts = []
    selectors = ['meta[property="og:description"]', 'meta[name="description"]', 'meta[property="og:title"]', 'meta[name="twitter:description"]', 'meta[property="og:url"]']
    for sel in selectors:
        try:
            value = await page.locator(sel).first.get_attribute("content", timeout=2000)
            if value:
                parts.append(value)
        except Exception:
            pass
    return "\n".join(parts)


def _igpm_extract_post_urls_from_html(html: str) -> _IGList[str]:
    h = str(html or "")
    candidates = []
    patterns = [
        r'https?:\\?/\\?/www\.instagram\.com\\?/(?:p|reel|tv)\\?/([A-Za-z0-9_-]+)\\?/',
        r'https?://www\.instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)/?',
        r'"/(?:p|reel|tv)/([A-Za-z0-9_-]+)/?"',
        r'\\u002f(?:p|reel|tv)\\u002f([A-Za-z0-9_-]+)\\u002f',
        r'\\/(?:p|reel|tv)\\/([A-Za-z0-9_-]+)\\/',
    ]
    for pat in patterns:
        for m in _ig_re.finditer(pat, h, flags=_ig_re.I):
            full = m.group(0).replace("\\/", "/").replace("\\u002f", "/").replace('"', "")
            code = m.group(1)
            if "/reel/" in full:
                candidates.append(f"https://www.instagram.com/reel/{code}/")
            elif "/tv/" in full:
                candidates.append(f"https://www.instagram.com/tv/{code}/")
            else:
                candidates.append(f"https://www.instagram.com/p/{code}/")
    normalized = h.replace("\\/", "/").replace("\\u002f", "/")
    for m in _ig_re.finditer(r'(?:https?://www\.instagram\.com)?/(p|reel|tv)/([A-Za-z0-9_-]+)/', normalized, flags=_ig_re.I):
        candidates.append(f"https://www.instagram.com/{m.group(1)}/{m.group(2)}/")
    seen = set()
    out = []
    for u in candidates:
        clean = _igpm_clean_post_url(u)
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            out.append(clean)
    return out


async def _igpm_collect_links(page) -> _IGDict[str, _IGAny]:
    try:
        raw_links = await page.locator("a[href]").evaluate_all("els => els.map(a => ({href: a.href || '', text: (a.innerText || a.textContent || '').trim()}))")
    except Exception:
        raw_links = []
    links = []
    seen = set()
    for item in raw_links:
        href = _igpm_normalize_url((item or {}).get("href", ""))
        text = ((item or {}).get("text", "") or "")[:300]
        if not href or href.lower() in seen:
            continue
        seen.add(href.lower())
        links.append({"url": href, "text": text, "is_external": _igpm_is_external_link(href) and not _igpm_is_footer_or_platform_link(href, text), "is_link_tree_candidate": _igpm_is_link_tree_candidate(href), "is_platform_footer_or_noise": _igpm_is_footer_or_platform_link(href, text)})
    external = [x for x in links if x["is_external"]]
    tree = [x for x in links if x["is_link_tree_candidate"]]
    return {
        "all_links_count": len(links),
        "external_links": external,
        "tree_candidates": tree,
        "excluded_platform_links": [x for x in links if x["is_platform_footer_or_noise"]],
        "external_links_status": _igpm_field_status(external, "Links externos publicos visibles en el perfil.", "El perfil no muestra links externos publicos de bio en esta vista."),
        "tree_candidates_status": _igpm_field_status(tree, "Se detecto un posible arbol de links/link-in-bio.", "El perfil no muestra un arbol de links publico detectable en esta vista."),
    }


async def _igpm_expand_tree_links(context, candidates: _IGList[_IGDict[str, _IGAny]], timeout_ms: int = 45000) -> _IGList[_IGDict[str, _IGAny]]:
    expanded = []
    for c in candidates[:3]:
        url = c.get("url")
        if not url:
            continue
        page = await context.new_page()
        result = {"source_url": url, "status": "failed", "page_title": None, "final_url": None, "links": [], "links_status": _igpm_runtime_status("No se pudo expandir el arbol de links por limitacion tecnica del render."), "error": None}
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(2500)
            result["page_title"] = await page.title()
            result["final_url"] = page.url
            raw_links = await page.locator("a[href]").evaluate_all("els => els.map(a => ({href: a.href || '', text: (a.innerText || a.textContent || '').trim()}))")
            seen = set()
            out = []
            for item in raw_links:
                href = _igpm_normalize_url((item or {}).get("href", ""))
                text = ((item or {}).get("text", "") or "")[:300]
                if href and href.lower() not in seen and _igpm_is_external_link(href) and not _igpm_is_footer_or_platform_link(href, text):
                    seen.add(href.lower())
                    out.append({"url": href, "text": text})
            result["links"] = out
            result["links_status"] = _igpm_field_status(out, "Links internos del arbol de links visibles.", "El arbol de links no mostro enlaces publicos verificables en esta vista.")
            result["status"] = "completed"
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            await page.close()
        expanded.append(result)
    return expanded


async def _igpm_scroll_and_collect_post_urls(page, max_scan_posts: int, wait_ms: int, scroll_rounds: int, enable_html_url_scan: bool = True) -> _IGDict[str, _IGAny]:
    seen = []
    seen_set = set()
    extraction_sources = {"a_href": 0, "html_scan": 0}

    def add_urls(urls, source):
        added = 0
        for href in urls:
            clean = _igpm_clean_post_url(href)
            if clean and _igpm_is_instagram_post_url(clean) and clean.lower() not in seen_set:
                seen_set.add(clean.lower())
                seen.append(clean)
                added += 1
        extraction_sources[source] = extraction_sources.get(source, 0) + added

    rounds_used = 0
    for i in range(scroll_rounds):
        rounds_used = i + 1
        try:
            hrefs = await page.locator("a[href]").evaluate_all("els => els.map(a => a.href || '')")
        except Exception:
            hrefs = []
        add_urls(hrefs, "a_href")
        if enable_html_url_scan:
            try:
                html = await page.content()
                html_urls = _igpm_extract_post_urls_from_html(html)
            except Exception:
                html_urls = []
            add_urls(html_urls, "html_scan")
        if len(seen) >= max_scan_posts:
            break
        try:
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(max(1800, min(wait_ms, 5500)))
        except Exception:
            break
    return {"urls": seen[:max_scan_posts], "extraction_sources": extraction_sources, "scroll_rounds_used": rounds_used}


async def _igpm_parse_post(context, url: str, timeout_ms: int, wait_ms: int) -> _IGDict[str, _IGAny]:
    page = await context.new_page()
    data = {"url": url, "type": "reel" if "/reel/" in url else ("tv" if "/tv/" in url else "post"), "date_iso": None, "date": None, "likes_count": None, "hashtags": [], "caption_text_sample": "", "parse_status": "failed", "error": None}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await page.wait_for_timeout(max(3000, min(wait_ms, 8000)))
        text = await _igpm_inner_text(page, timeout_ms=12000, limit=14000)
        meta_text = await _igpm_meta_text(page)
        try:
            html = await page.content()
        except Exception:
            html = ""
        combined_text = (text + "\n" + meta_text + "\n" + html[:8000]).strip()
        data["caption_text_sample"] = (text + "\n" + meta_text).strip()[:2500]
        data["hashtags"] = _igpm_extract_hashtags(combined_text)
        try:
            dt = await page.locator("time[datetime]").first.get_attribute("datetime", timeout=5000)
        except Exception:
            dt = None
        data["date_iso"] = _igpm_parse_iso_datetime(dt)
        d_obj = _igpm_date_from_iso(data["date_iso"])
        data["date"] = d_obj.isoformat() if d_obj else None
        data["likes_count"] = _igpm_parse_likes(combined_text)
        data["parse_status"] = "completed"
    except Exception as exc:
        data["error"] = str(exc)
    finally:
        await page.close()
    data["date_status"] = _igpm_field_status(data.get("date_iso"), "Fecha publica visible en la publicacion.", "No se pudo leer una fecha publica visible para esta publicacion.")
    data["likes_status"] = _igpm_field_status(data.get("likes_count"), "Likes publicos visibles en la publicacion.", "La publicacion no muestra publicamente el numero de likes en esta vista.")
    data["hashtags_status"] = _igpm_field_status(data.get("hashtags") or [], "Hashtags visibles en el texto de la publicacion.", "No se detectaron hashtags visibles en esta publicacion.")
    data["caption_status"] = _igpm_field_status(data.get("caption_text_sample"), "Texto/caption visible recolectado.", "No se pudo leer texto/caption visible de esta publicacion.")
    return data


def _igpm_collect_missing_data(payload: _IGDict[str, _IGAny]) -> _IGList[_IGDict[str, _IGAny]]:
    missing = []
    def add(field: str, status: _IGDict[str, _IGAny], severity: str = "medium"):
        if isinstance(status, dict) and status.get("visibility") != "visible":
            missing.append({"field": field, "visibility": status.get("visibility"), "severity": severity, "message": status.get("message")})
    for field, status in (payload.get("profile_counts_status") or {}).items():
        add(f"profile_counts.{field}", status, "high")
    links = payload.get("links") or {}
    add("links.external_links", links.get("external_links_status"), "medium")
    add("links.tree_candidates", links.get("tree_candidates_status"), "low")
    for idx, post in enumerate(payload.get("posts") or []):
        add(f"posts[{idx}].date_iso", post.get("date_status"), "high")
        add(f"posts[{idx}].likes_count", post.get("likes_status"), "medium")
        add(f"posts[{idx}].hashtags", post.get("hashtags_status"), "low")
        add(f"posts[{idx}].caption_text_sample", post.get("caption_status"), "medium")
    frequency = payload.get("frequency") or {}
    if frequency.get("status") != "calculated":
        missing.append({"field": "frequency.posts_per_week", "visibility": "not_calculable", "severity": "high", "message": frequency.get("message") or "No se pudo calcular frecuencia de publicacion."})
    summary = payload.get("metrics_summary") or {}
    if summary.get("average_likes_last_posts_visible_only") is None:
        missing.append({"field": "metrics_summary.average_likes_last_posts_visible_only", "visibility": "not_calculable", "severity": "medium", "message": "No se puede calcular promedio de likes porque Instagram no mostro likes numericos visibles en las publicaciones analizadas."})
    return missing


def _igpm_data_quality(payload: _IGDict[str, _IGAny]) -> _IGDict[str, _IGAny]:
    profile_counts_status = payload.get("profile_counts_status") or {}
    summary = payload.get("metrics_summary") or {}
    score = 0
    visible_counts = sum(1 for s in profile_counts_status.values() if isinstance(s, dict) and s.get("visibility") == "visible")
    score += min(30, visible_counts * 10)
    if payload.get("auth_render_classification", {}).get("usable_profile_visual_evidence"):
        score += 20
    returned = int(summary.get("last_posts_returned") or 0)
    requested = max(1, int(summary.get("posts_requested") or 20))
    score += min(20, int((returned / requested) * 20))
    likes_visible = int(summary.get("likes_visible_count") or 0)
    score += min(15, int((likes_visible / max(1, returned)) * 15)) if returned else 0
    dated_posts = len((payload.get("frequency") or {}).get("dated_posts_used") or [])
    score += min(15, int((dated_posts / max(1, returned)) * 15)) if returned else 0
    if score >= 80:
        grade = "strong_public_evidence"
    elif score >= 60:
        grade = "usable_with_limitations"
    elif score >= 35:
        grade = "partial_public_evidence"
    else:
        grade = "insufficient_public_evidence"
    return {"score": score, "max_score": 100, "grade": grade, "reason": "Score basado en visibilidad de perfil, cantidad de posts, likes visibles y fechas visibles."}


def _igpm_build_human_messages(payload: _IGDict[str, _IGAny]) -> _IGList[str]:
    messages = []
    counts_status = payload.get("profile_counts_status") or {}
    for key in ["posts_total", "followers_total", "following_total"]:
        status = counts_status.get(key) or {}
        if status.get("visibility") == "visible":
            messages.append(f"{key}: visible ({status.get('value')}).")
        else:
            messages.append(status.get("message") or f"{key}: no visible publicamente.")
    summary = payload.get("metrics_summary") or {}
    if summary.get("average_likes_last_posts_visible_only") is not None:
        messages.append(f"Promedio de likes visibles: {summary.get('average_likes_last_posts_visible_only')}.")
    else:
        messages.append("No se puede calcular promedio de likes porque no hay likes numericos visibles suficientes.")
    frequency = payload.get("frequency") or {}
    if frequency.get("status") == "calculated":
        messages.append(f"Frecuencia calculada: {frequency.get('posts_per_week')} publicaciones por semana en la ventana definida.")
    else:
        messages.append(frequency.get("message") or "No se pudo calcular frecuencia de publicacion.")
    return messages


def _igpm_build_text_report(payload: _IGDict[str, _IGAny]) -> str:
    lines = []
    lines.append("INSTAGRAM PROFILE PUBLIC METRICS")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"company_name: {payload.get('company_name')}")
    lines.append(f"profile_url: {payload.get('profile_url')}")
    lines.append(f"final_url: {payload.get('final_url')}")
    lines.append(f"page_title: {payload.get('page_title')}")
    lines.append(f"status: {payload.get('status')}")
    lines.append(f"classification: {payload.get('classification')}")
    lines.append("")
    lines.append("PROFILE COUNTS")
    for key, status in (payload.get("profile_counts_status") or {}).items():
        lines.append(f"- {key}: {status.get('value')} | {status.get('visibility')} | {status.get('message')}")
    lines.append("")
    lines.append("PUBLIC PROFILE INFO SAMPLE")
    lines.append((payload.get("profile_text_sample") or "")[:2200])
    lines.append("")
    lines.append("LINKS")
    links = payload.get("links") or {}
    for l in links.get("external_links", []):
        lines.append(f"- {l.get('url')} | {l.get('text')}")
    if not links.get("external_links"):
        lines.append("- El perfil no muestra links externos publicos de bio en esta vista.")
    lines.append("")
    lines.append("POST URL EXTRACTION")
    lines.append(str(payload.get("post_url_extraction") or {}))
    lines.append("")
    lines.append("LAST POSTS")
    for idx, post in enumerate(payload.get("posts", []), start=1):
        lines.append(f"{idx}. {post.get('url')}")
        lines.append(f"   type: {post.get('type')}")
        lines.append(f"   date_iso: {post.get('date_iso')} | {post.get('date_status', {}).get('message')}")
        lines.append(f"   likes_count: {post.get('likes_count')} | {post.get('likes_status', {}).get('message')}")
        lines.append(f"   hashtags: {', '.join(post.get('hashtags') or [])} | {post.get('hashtags_status', {}).get('message')}")
    lines.append("")
    lines.append("SUMMARY")
    for k, v in (payload.get("metrics_summary") or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("MISSING PUBLIC DATA")
    for item in payload.get("missing_public_data", []):
        lines.append(f"- {item.get('field')}: {item.get('message')}")
    lines.append("")
    lines.append("DATA QUALITY")
    for k, v in (payload.get("data_quality") or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("LIMITATIONS")
    for item in payload.get("limitations", []):
        lines.append(f"- {item}")
    return "\n".join(lines)


@app.get("/debug/instagram-storage-state")
async def debugInstagramStorageState():
    info = _sar_storage_state_from_env("instagram")
    return {
        "status": "completed",
        "service": "instagram-storage-state-debug",
        "version": APP_VERSION if "APP_VERSION" in globals() else "unknown",
        "storage_state": _sar_storage_state_public_info(info),
        "note": "No expone cookies, storage_state ni credenciales.",
    }


@app.post("/audit/instagram-profile-metrics")
async def auditInstagramProfileMetrics(req: InstagramProfileMetricsRequest):
    from playwright.async_api import async_playwright as _ig_async_playwright
    retrieved_at = _ig_datetime.utcnow().isoformat() + "Z"
    profile_url = str(req.profile_url)
    limitations = [
        "Solo se recolecta informacion visible en el perfil/render; no se accede a datos privados.",
        "Los likes pueden no estar visibles en todas las publicaciones; el promedio excluye likes no visibles.",
        "Fechas, likes y hashtags dependen del HTML visible que entregue Instagram en ese momento.",
        "No se resuelve CAPTCHA, checkpoint ni 2FA.",
        "No se realizan acciones de escritura: follows, likes, comments, messages ni DMs.",
    ]
    storage_state_info = _sar_storage_state_from_env("instagram")
    browser = None
    context = None
    try:
        async with _ig_async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-blink-features=AutomationControlled"])
            context_kwargs = {
                "viewport": {"width": 1365, "height": 1200},
                "locale": "es-AR",
                "timezone_id": "America/Argentina/Cordoba",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            }
            if storage_state_info.get("available") and storage_state_info.get("state") is not None:
                context_kwargs["storage_state"] = storage_state_info["state"]
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            page.set_default_timeout(req.timeout_ms)
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=req.timeout_ms)
            await page.wait_for_timeout(req.wait_ms)
            final_url = page.url
            page_title = await page.title()
            profile_body_text = await _igpm_inner_text(page, timeout_ms=12000, limit=14000)
            profile_meta_text = await _igpm_meta_text(page)
            try:
                profile_html = await page.content()
            except Exception:
                profile_html = ""
            profile_text = (profile_body_text + "\n" + profile_meta_text).strip()
            counts = _igpm_profile_counts_from_text(profile_text + "\n" + profile_html[:12000])
            profile_counts_status = _igpm_profile_counts_status(counts)
            links = await _igpm_collect_links(page)
            classification = _sar_classify_auth_state(platform="instagram", final_url=final_url, title=page_title, text=profile_text)
            class_name = classification.get("classification")
            if class_name == "authenticated_profile_visible" and not storage_state_info.get("available"):
                class_name = "public_profile_visible"
                classification["classification"] = class_name
                classification["reason"] = "Perfil visible publicamente; no hay storage_state activo, por lo tanto no se afirma sesion autenticada."
            if class_name in {"login_wall", "captcha_required", "checkpoint_required"}:
                limitations.append("Instagram no entrego perfil publico usable en este render; revisar storage_state o challenge.")
            profile_screenshot_bytes = await page.screenshot(full_page=req.full_page, type="png")
            expanded_tree_links = []
            if req.include_bio_link_expansion:
                expanded_tree_links = await _igpm_expand_tree_links(context=context, candidates=links.get("tree_candidates", []), timeout_ms=min(req.timeout_ms, 60000))
            extraction = await _igpm_scroll_and_collect_post_urls(page=page, max_scan_posts=req.max_scan_posts, wait_ms=req.wait_ms, scroll_rounds=req.scroll_rounds, enable_html_url_scan=req.enable_html_url_scan)
            post_urls = extraction.get("urls", [])
            mobile_extraction = None
            if req.enable_mobile_fallback and len(post_urls) == 0:
                mobile_context_kwargs = {
                    "viewport": {"width": 390, "height": 1200},
                    "is_mobile": True,
                    "has_touch": True,
                    "locale": "es-AR",
                    "timezone_id": "America/Argentina/Cordoba",
                    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                }
                if storage_state_info.get("available") and storage_state_info.get("state") is not None:
                    mobile_context_kwargs["storage_state"] = storage_state_info["state"]
                mobile_context = await browser.new_context(**mobile_context_kwargs)
                mobile_page = await mobile_context.new_page()
                mobile_page.set_default_timeout(req.timeout_ms)
                try:
                    await mobile_page.goto(profile_url, wait_until="domcontentloaded", timeout=req.timeout_ms)
                    await mobile_page.wait_for_timeout(req.wait_ms)
                    mobile_extraction = await _igpm_scroll_and_collect_post_urls(page=mobile_page, max_scan_posts=req.max_scan_posts, wait_ms=req.wait_ms, scroll_rounds=req.scroll_rounds, enable_html_url_scan=req.enable_html_url_scan)
                    post_urls = mobile_extraction.get("urls", []) or post_urls
                finally:
                    await mobile_context.close()
            posts = []
            window = _igpm_get_reporting_window()
            window_start = _ig_date.fromisoformat(window["start_date"])

            if getattr(req, "parse_posts", True):
                parse_source_limit = req.max_posts if getattr(req, "fast_diagnostic", False) else req.max_scan_posts
                for url in post_urls[:parse_source_limit]:
                    post = await _igpm_parse_post(context=context, url=url, timeout_ms=req.timeout_ms, wait_ms=req.wait_ms)
                    posts.append(post)
                    d = _igpm_date_from_iso(post.get("date_iso"))
                    if len(posts) >= req.max_posts and d is not None and d < window_start:
                        break
            else:
                limitations.append("parse_posts=false: solo se diagnostico perfil y URLs de posts; no se abrieron publicaciones individuales.")

            last_posts = posts[:req.max_posts]
            visible_likes = [p["likes_count"] for p in last_posts if isinstance(p.get("likes_count"), int)]
            avg_likes = round(_ig_statistics.mean(visible_likes), 2) if visible_likes else None
            frequency = _igpm_compute_frequency(posts, window)
            metrics_summary = {
                "posts_requested": req.max_posts,
                "posts_urls_found": len(post_urls),
                "posts_parsed": len(posts),
                "last_posts_returned": len(last_posts),
                "likes_visible_count": len(visible_likes),
                "likes_missing_count": len(last_posts) - len(visible_likes),
                "average_likes_last_posts_visible_only": avg_likes,
                "average_likes_status": _igpm_field_status(avg_likes, "Promedio calculado con likes numericos visibles.", "No se puede calcular promedio de likes porque Instagram no mostro likes numericos visibles en las publicaciones analizadas."),
                "publishing_frequency_window_mode": window["mode"],
                "publishing_frequency_window_start": window["start_date"],
                "publishing_frequency_window_end": window["end_date"],
                "posts_in_frequency_window": frequency["posts_in_window"],
                "posts_per_week_in_frequency_window": frequency["posts_per_week"],
                "average_days_between_posts_in_window": frequency["average_days_between_posts"],
                "frequency_status": {"visibility": "visible" if frequency["status"] == "calculated" else "not_collected_runtime", "message": frequency["message"]},
            }
            payload = {
                "collector": "instagram_profile_public_metrics",
                "version": APP_VERSION if "APP_VERSION" in globals() else "unknown",
                "status": "completed" if classification.get("usable_profile_visual_evidence") or counts.get("followers_total") else "completed_with_limitations",
                "company_name": req.company_name,
                "profile_url": profile_url,
                "username": _igpm_profile_username(profile_url),
                "final_url": final_url,
                "page_title": page_title,
                "retrieved_at": retrieved_at,
                "auth_method": "storage_state" if storage_state_info.get("available") else "public_render",
                "storage_state": _sar_storage_state_public_info(storage_state_info),
                "classification": class_name,
                "auth_render_classification": classification,
                "profile_collection_status": "completed" if counts.get("followers_total") or profile_text else "partial_or_failed",
                "posts_collection_status": "completed" if len(post_urls) > 0 else "no_post_urls_visible_in_render",
                "request_mode": {
                    "parse_posts": getattr(req, "parse_posts", True),
                    "fast_diagnostic": getattr(req, "fast_diagnostic", False),
                    "enable_mobile_fallback": req.enable_mobile_fallback,
                    "enable_html_url_scan": req.enable_html_url_scan,
                    "scroll_rounds": req.scroll_rounds,
                },
                "profile_counts": counts,
                "profile_counts_status": profile_counts_status,
                "profile_text_sample": profile_text[:5000],
                "profile_text_status": _igpm_field_status(profile_text, "Informacion publica del perfil visible.", "El perfil no muestra informacion publica de bio/texto en esta vista."),
                "links": links,
                "expanded_tree_links": expanded_tree_links,
                "post_url_extraction": {"desktop": extraction, "mobile_fallback": mobile_extraction, "strategy": ["a_href", "html_scan", "progressive_scroll", "mobile_fallback"]},
                "post_urls_found": post_urls,
                "posts": last_posts,
                "all_scanned_posts": posts,
                "metrics_summary": metrics_summary,
                "frequency": frequency,
                "visibility_report": {
                    "profile_counts_complete": all((profile_counts_status.get(k) or {}).get("visibility") == "visible" for k in ["posts_total", "followers_total", "following_total"]),
                    "bio_or_profile_text_visible": bool(profile_text.strip()),
                    "external_links_visible": len(links.get("external_links") or []) > 0,
                    "tree_links_detected": len(links.get("tree_candidates") or []) > 0,
                    "posts_found": len(post_urls),
                    "posts_returned": len(last_posts),
                    "posts_with_visible_dates": len([p for p in last_posts if p.get("date_iso")]),
                    "posts_with_visible_likes": len(visible_likes),
                    "posts_with_visible_hashtags": len([p for p in last_posts if p.get("hashtags")]),
                },
                "limitations": limitations,
            }
            payload["missing_public_data"] = _igpm_collect_missing_data(payload)
            payload["data_quality"] = _igpm_data_quality(payload)
            payload["human_readable_messages"] = _igpm_build_human_messages(payload)
            report_txt = _igpm_build_text_report(payload)
            drive_report_upload = None
            drive_screenshot_upload = None
            if req.upload_to_drive and "_drive_upload_binary" in globals():
                prefix = req.filename_prefix or "instagram_profile_metrics"
                drive_report_upload = await _drive_upload_binary(filename=f"{prefix}.txt", content=report_txt.encode("utf-8"), mime_type="text/plain; charset=utf-8", folder_name=req.drive_folder_name)
                drive_screenshot_upload = await _drive_upload_binary(filename=f"{prefix}_profile_screenshot.png", content=profile_screenshot_bytes, mime_type="image/png", folder_name=req.drive_folder_name)
            payload["drive_report_upload"] = drive_report_upload
            payload["drive_screenshot_upload"] = drive_screenshot_upload
            await context.close()
            await browser.close()
            return payload
    except Exception as exc:
        try:
            if context is not None:
                await context.close()
        except Exception:
            pass
        try:
            if browser is not None:
                await browser.close()
        except Exception:
            pass
        return {
            "collector": "instagram_profile_public_metrics",
            "version": APP_VERSION if "APP_VERSION" in globals() else "unknown",
            "status": "failed_runtime",
            "company_name": req.company_name,
            "profile_url": profile_url,
            "retrieved_at": retrieved_at,
            "reason": str(exc),
            "limitations": limitations,
            "policy": {"captcha_bypass_attempted": False, "checkpoint_bypass_attempted": False, "private_profile_access_attempted": False, "write_actions_attempted": False},
        }

# ============================================================
# MICRO PATCH 4F.3-E - Instagram posts by URL parser
# ============================================================
# ============================================================
# MICRO PATCH 4F.3-E - Instagram posts by URL parser
# ============================================================

class InstagramPostsByUrlRequest(_IGBaseModel):
    post_urls: _IGList[str] = _IGField(..., min_length=1, max_length=50)
    company_name: _IGOptional[str] = None
    profile_url: _IGOptional[str] = None
    max_posts: int = _IGField(20, ge=1, le=50)
    wait_ms: int = _IGField(2500, ge=1000, le=15000)
    timeout_ms: int = _IGField(25000, ge=10000, le=90000)
    upload_to_drive: bool = False
    drive_folder_name: _IGOptional[str] = None
    filename_prefix: _IGOptional[str] = None


def _igpbu_dedupe_urls(urls: _IGList[str], max_posts: int) -> _IGList[str]:
    out = []
    seen = set()
    for u in urls or []:
        clean = _igpm_clean_post_url(u)
        if not clean or not _igpm_is_instagram_post_url(clean):
            continue
        key = clean.lower()
        if key not in seen:
            seen.add(key)
            out.append(clean)
        if len(out) >= max_posts:
            break
    return out


def _igpbu_build_text_report(payload: _IGDict[str, _IGAny]) -> str:
    lines = []
    lines.append("INSTAGRAM POSTS BY URL PUBLIC METRICS")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"company_name: {payload.get('company_name')}")
    lines.append(f"profile_url: {payload.get('profile_url')}")
    lines.append(f"status: {payload.get('status')}")
    lines.append(f"version: {payload.get('version')}")
    lines.append(f"auth_method: {payload.get('auth_method')}")
    lines.append("")
    lines.append("SUMMARY")
    for k, v in (payload.get("metrics_summary") or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("FREQUENCY")
    for k, v in (payload.get("frequency") or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("POSTS")
    for idx, p in enumerate(payload.get("posts") or [], start=1):
        lines.append(f"{idx}. {p.get('url')}")
        lines.append(f"   type: {p.get('type')}")
        lines.append(f"   parse_status: {p.get('parse_status')}")
        lines.append(f"   date_iso: {p.get('date_iso')} | {p.get('date_status', {}).get('message')}")
        lines.append(f"   likes_count: {p.get('likes_count')} | {p.get('likes_status', {}).get('message')}")
        lines.append(f"   hashtags: {', '.join(p.get('hashtags') or [])} | {p.get('hashtags_status', {}).get('message')}")
        if p.get("error"):
            lines.append(f"   error: {p.get('error')}")
    lines.append("")
    lines.append("MISSING PUBLIC DATA")
    for item in payload.get("missing_public_data") or []:
        lines.append(f"- {item.get('field')}: {item.get('message')}")
    lines.append("")
    lines.append("LIMITATIONS")
    for item in payload.get("limitations") or []:
        lines.append(f"- {item}")
    return "\n".join(lines)


@app.post("/audit/instagram-posts-by-url")
async def auditInstagramPostsByUrl(req: InstagramPostsByUrlRequest):
    from playwright.async_api import async_playwright as _ig_async_playwright

    retrieved_at = _ig_datetime.utcnow().isoformat() + "Z"
    storage_state_info = _sar_storage_state_from_env("instagram")
    post_urls = _igpbu_dedupe_urls(req.post_urls, req.max_posts)

    limitations = [
        "Solo se abren URLs de publicaciones/reels publicas provistas por el usuario o por un paso previo de discovery.",
        "No se accede a datos privados.",
        "Los likes pueden no estar visibles; el promedio excluye likes no visibles.",
        "Fechas, likes y hashtags dependen del HTML visible que entregue Instagram en ese momento.",
        "No se resuelve CAPTCHA, checkpoint ni 2FA.",
        "No se realizan acciones de escritura: follows, likes, comments, messages ni DMs.",
    ]

    if not post_urls:
        return {
            "collector": "instagram_posts_by_url",
            "version": APP_VERSION if "APP_VERSION" in globals() else "unknown",
            "status": "failed_validation",
            "company_name": req.company_name,
            "profile_url": req.profile_url,
            "retrieved_at": retrieved_at,
            "reason": "No hay URLs validas de posts/reels/tv de Instagram.",
            "input_count": len(req.post_urls or []),
            "valid_post_urls": [],
            "policy": {
                "captcha_bypass_attempted": False,
                "checkpoint_bypass_attempted": False,
                "private_profile_access_attempted": False,
                "write_actions_attempted": False,
            },
        }

    browser = None
    context = None

    try:
        async with _ig_async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-blink-features=AutomationControlled"],
            )

            context_kwargs = {
                "viewport": {"width": 1365, "height": 1200},
                "locale": "es-AR",
                "timezone_id": "America/Argentina/Cordoba",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            }

            if storage_state_info.get("available") and storage_state_info.get("state") is not None:
                context_kwargs["storage_state"] = storage_state_info["state"]

            context = await browser.new_context(**context_kwargs)

            posts = []
            for u in post_urls:
                post = await _igpm_parse_post(
                    context=context,
                    url=u,
                    timeout_ms=req.timeout_ms,
                    wait_ms=req.wait_ms,
                )
                posts.append(post)

            visible_likes = [p["likes_count"] for p in posts if isinstance(p.get("likes_count"), int)]
            avg_likes = round(_ig_statistics.mean(visible_likes), 2) if visible_likes else None
            window = _igpm_get_reporting_window()
            frequency = _igpm_compute_frequency(posts, window)

            metrics_summary = {
                "input_urls_count": len(req.post_urls or []),
                "valid_post_urls_count": len(post_urls),
                "posts_requested": req.max_posts,
                "posts_parsed": len(posts),
                "posts_completed": len([p for p in posts if p.get("parse_status") == "completed"]),
                "posts_failed": len([p for p in posts if p.get("parse_status") != "completed"]),
                "likes_visible_count": len(visible_likes),
                "likes_missing_count": len(posts) - len(visible_likes),
                "average_likes_last_posts_visible_only": avg_likes,
                "average_likes_status": _igpm_field_status(
                    avg_likes,
                    "Promedio calculado con likes numericos visibles.",
                    "No se puede calcular promedio de likes porque Instagram no mostro likes numericos visibles en las publicaciones analizadas.",
                ),
                "publishing_frequency_window_mode": window["mode"],
                "publishing_frequency_window_start": window["start_date"],
                "publishing_frequency_window_end": window["end_date"],
                "posts_in_frequency_window": frequency["posts_in_window"],
                "posts_per_week_in_frequency_window": frequency["posts_per_week"],
                "average_days_between_posts_in_window": frequency["average_days_between_posts"],
                "frequency_status": {
                    "visibility": "visible" if frequency["status"] == "calculated" else "not_collected_runtime",
                    "message": frequency["message"],
                },
            }

            visibility_report = {
                "posts_returned": len(posts),
                "posts_with_visible_dates": len([p for p in posts if p.get("date_iso")]),
                "posts_with_visible_likes": len(visible_likes),
                "posts_with_visible_hashtags": len([p for p in posts if p.get("hashtags")]),
            }

            payload = {
                "collector": "instagram_posts_by_url",
                "version": APP_VERSION if "APP_VERSION" in globals() else "unknown",
                "status": "completed",
                "company_name": req.company_name,
                "profile_url": req.profile_url,
                "retrieved_at": retrieved_at,
                "auth_method": "storage_state" if storage_state_info.get("available") else "public_render",
                "storage_state": _sar_storage_state_public_info(storage_state_info),
                "valid_post_urls": post_urls,
                "posts": posts,
                "metrics_summary": metrics_summary,
                "frequency": frequency,
                "visibility_report": visibility_report,
                "limitations": limitations,
                "policy": {
                    "captcha_bypass_attempted": False,
                    "checkpoint_bypass_attempted": False,
                    "private_profile_access_attempted": False,
                    "write_actions_attempted": False,
                },
            }

            missing = []
            for idx, post in enumerate(posts):
                for field, status, severity in [
                    ("date_iso", post.get("date_status"), "high"),
                    ("likes_count", post.get("likes_status"), "medium"),
                    ("hashtags", post.get("hashtags_status"), "low"),
                    ("caption_text_sample", post.get("caption_status"), "medium"),
                ]:
                    if isinstance(status, dict) and status.get("visibility") != "visible":
                        missing.append({
                            "field": f"posts[{idx}].{field}",
                            "visibility": status.get("visibility"),
                            "severity": severity,
                            "message": status.get("message"),
                        })

            if frequency.get("status") != "calculated":
                missing.append({
                    "field": "frequency.posts_per_week",
                    "visibility": "not_calculable",
                    "severity": "high",
                    "message": frequency.get("message") or "No se pudo calcular frecuencia de publicacion.",
                })

            if avg_likes is None:
                missing.append({
                    "field": "metrics_summary.average_likes_last_posts_visible_only",
                    "visibility": "not_calculable",
                    "severity": "medium",
                    "message": "No se puede calcular promedio de likes porque Instagram no mostro likes numericos visibles.",
                })

            payload["missing_public_data"] = missing
            payload["human_readable_messages"] = [
                f"URLs validas analizadas: {len(post_urls)}.",
                f"Posts parseados: {len(posts)}.",
                f"Posts con fecha visible: {visibility_report['posts_with_visible_dates']}.",
                f"Posts con likes visibles: {visibility_report['posts_with_visible_likes']}.",
                f"Posts con hashtags visibles: {visibility_report['posts_with_visible_hashtags']}.",
                f"Promedio de likes visibles: {avg_likes}." if avg_likes is not None else "No se pudo calcular promedio de likes visibles.",
                f"Frecuencia: {frequency.get('posts_per_week')} publicaciones por semana." if frequency.get("status") == "calculated" else frequency.get("message"),
            ]

            drive_report_upload = None
            if req.upload_to_drive and "_drive_upload_binary" in globals():
                prefix = req.filename_prefix or "instagram_posts_by_url"
                report_txt = _igpbu_build_text_report(payload)
                drive_report_upload = await _drive_upload_binary(
                    filename=f"{prefix}.txt",
                    content=report_txt.encode("utf-8"),
                    mime_type="text/plain; charset=utf-8",
                    folder_name=req.drive_folder_name,
                )

            payload["drive_report_upload"] = drive_report_upload

            await context.close()
            await browser.close()
            return payload

    except Exception as exc:
        try:
            if context is not None:
                await context.close()
        except Exception:
            pass
        try:
            if browser is not None:
                await browser.close()
        except Exception:
            pass

        return {
            "collector": "instagram_posts_by_url",
            "version": APP_VERSION if "APP_VERSION" in globals() else "unknown",
            "status": "failed_runtime",
            "company_name": req.company_name,
            "profile_url": req.profile_url,
            "retrieved_at": retrieved_at,
            "reason": str(exc),
            "valid_post_urls": post_urls,
            "limitations": limitations,
            "policy": {
                "captcha_bypass_attempted": False,
                "checkpoint_bypass_attempted": False,
                "private_profile_access_attempted": False,
                "write_actions_attempted": False,
            },
        }

# ============================================================
# MICRO PATCH 4H.1-A - SOCIAL PUBLIC AVERAGES
# ============================================================

try:
    BaseModel
except NameError:
    from pydantic import BaseModel

class SocialPublicAveragesRequest(BaseModel):
    company_name: str | None = None
    platform: str = "instagram"
    profile_url: str | None = None
    followers_total: int | float | str | None = None
    posts: list = []
    upload_to_drive: bool = False
    drive_folder_name: str | None = None
    filename_prefix: str | None = None


def _spa_num(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    lower = s.lower().replace(" ", "")
    mult = 1.0
    if lower.endswith("k"):
        mult = 1000.0
        lower = lower[:-1]
    elif lower.endswith("m"):
        mult = 1000000.0
        lower = lower[:-1]
    lower = lower.replace(".", "").replace(",", ".")
    cleaned = "".join(ch for ch in lower if ch.isdigit() or ch in ".-")
    try:
        return float(cleaned) * mult if cleaned not in ("", "-", ".") else None
    except Exception:
        return None


def _spa_int(value):
    n = _spa_num(value)
    return int(round(n)) if n is not None else None


def _spa_avg(values, digits=2):
    nums = []
    for v in values or []:
        n = _spa_num(v)
        if n is not None:
            nums.append(n)
    if not nums:
        return None
    return round(sum(nums) / len(nums), digits)


def _spa_date(value):
    if not value:
        return None
    from datetime import datetime
    s = str(value).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt)
        except Exception:
            continue
    return None


def _spa_post_url(post):
    return str(post.get("url") or post.get("post_url") or post.get("permalink") or "")


def _spa_post_type(post):
    t = str(post.get("type") or post.get("post_type") or "").strip().lower()
    url = _spa_post_url(post).lower()
    if not t:
        if "/reel/" in url:
            t = "reel"
        elif "/p/" in url:
            t = "post"
        else:
            t = "unknown"
    return t


def _spa_post_date(post):
    for k in ("date_iso", "published_at", "created_time", "date", "timestamp"):
        dt = _spa_date(post.get(k))
        if dt is not None:
            return dt
    return None


def _spa_hashtags(post):
    raw = post.get("hashtags")
    if raw is None:
        raw = []
    if isinstance(raw, str):
        parts = [x.strip() for x in raw.replace("\n", " ").split(",")]
        if len(parts) == 1:
            parts = [x.strip() for x in raw.replace("\n", " ").split(" ")]
        tags = [x for x in parts if x.startswith("#")]
    elif isinstance(raw, list):
        tags = [str(x).strip() for x in raw if str(x).strip().startswith("#")]
    else:
        tags = []
    clean = []
    seen = set()
    for tag in tags:
        key = tag.casefold()
        if key not in seen:
            seen.add(key)
            clean.append(tag)
    return clean


def _spa_topic_from_post(post):
    tags = [t.lower() for t in _spa_hashtags(post)]
    text = str(post.get("caption") or post.get("caption_sample") or post.get("text") or "").lower()
    blob = " ".join(tags) + " " + text
    topics = []
    mapping = [
        ("navidad", ["navidad", "fiestas2025", "cajasnavide", "pan dulce", "budines"]),
        ("carnaval", ["carnaval", "fiesta"]),
        ("pascuas", ["pascuas"]),
        ("san_valentin", ["sanvalentin", "14defebrero", "amor"]),
        ("mayorista_b2b", ["mayorista", "revendedor", "emprendedores", "regalosempresariales"]),
        ("reposteria", ["reposteria", "reposter\u00eda", "mesasnavide", "bazar"]),
        ("equipo_confianza", ["trabajoenequipo", "compa\u00f1eros", "companeros", "atencionalpublico", "atenci\u00f3nalp\u00fablico"]),
        ("efemeride", ["diadel", "d\u00edadel", "diadelmate", "diadelchicle"])
    ]
    for topic, keys in mapping:
        if any(k in blob for k in keys):
            topics.append(topic)
    if not topics:
        topics.append("sin_tematica_detectada")
    return topics


def _spa_group_avg(posts, value_getter, group_getter):
    groups = {}
    for p in posts:
        v = value_getter(p)
        if v is None:
            continue
        groups.setdefault(group_getter(p), []).append(v)
    return {k: _spa_avg(v) for k, v in groups.items() if v}


def _spa_average_days_between(dates):
    if not dates or len(dates) < 2:
        return None
    ordered = sorted(dates)
    diffs = []
    for i in range(1, len(ordered)):
        try:
            diffs.append(abs((ordered[i] - ordered[i-1]).total_seconds()) / 86400.0)
        except Exception:
            pass
    return round(sum(diffs) / len(diffs), 2) if diffs else None


def _spa_posts_per_month_visible(dates):
    if not dates:
        return None
    buckets = {}
    for d in dates:
        key = f"{d.year:04d}-{d.month:02d}"
        buckets[key] = buckets.get(key, 0) + 1
    if not buckets:
        return None
    return {
        "months_detected": buckets,
        "average_posts_per_detected_month": round(sum(buckets.values()) / len(buckets), 2)
    }


def _spa_frequency_window(dates):
    if not dates:
        return {"status": "not_calculable", "reason": "No hay fechas visibles suficientes para calcular frecuencia."}
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if now.day <= 7:
        year = now.year
        month = now.month - 1
        if month == 0:
            year -= 1
            month = 12
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        end = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        mode = "previous_month"
    else:
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end = now
        mode = "current_month_to_date"
    in_window = [d for d in dates if d.tzinfo and start <= d <= end]
    if not in_window:
        return {
            "status": "not_calculable", "mode": mode,
            "window_start": start.date().isoformat(), "window_end": end.date().isoformat(),
            "posts_in_window": 0, "posts_per_week": None,
            "reason": "No hay publicaciones visibles dentro de la ventana definida."
        }
    days = max((end - start).total_seconds() / 86400.0, 1)
    weeks = max(days / 7.0, 0.14)
    return {
        "status": "calculated", "mode": mode,
        "window_start": start.date().isoformat(), "window_end": end.date().isoformat(),
        "posts_in_window": len(in_window), "posts_per_week": round(len(in_window) / weeks, 2)
    }


def _spa_build_public_averages(platform, followers_total, posts):
    platform = str(platform or "").lower().strip()
    followers = _spa_num(followers_total)
    posts = posts or []
    dates = [_spa_post_date(p) for p in posts]
    dates = [d for d in dates if d is not None]
    hashtags_by_post = [_spa_hashtags(p) for p in posts]
    content_types = [_spa_post_type(p) for p in posts]

    result = {
        "status": "partial_public_visible_metrics",
        "platform": platform,
        "total_posts_analyzed": len(posts),
        "posts_with_visible_dates": len(dates),
        "average_days_between_posts": _spa_average_days_between(dates),
        "publishing_frequency_window": _spa_frequency_window(dates),
        "posts_per_month_visible_sample": _spa_posts_per_month_visible(dates),
        "content_types_count": {t: content_types.count(t) for t in sorted(set(content_types))},
        "average_hashtags_per_post": round(sum(len(x) for x in hashtags_by_post) / len(posts), 2) if posts else None,
        "posts_with_hashtags": sum(1 for x in hashtags_by_post if x),
        "average_content_age_days": None,
        "limitations": [
            "Promedios calculados solo con datos publicos visibles.",
            "No representan alcance, reproducciones, guardados, clics, ventas ni performance real.",
            "Si una plataforma oculta una metrica, se excluye del promedio correspondiente."
        ]
    }

    if dates:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        ages = []
        for d in dates:
            try:
                ages.append(abs((now - d).total_seconds()) / 86400.0)
            except Exception:
                pass
        result["average_content_age_days"] = round(sum(ages) / len(ages), 2) if ages else None

    if platform == "instagram":
        def like_getter(p):
            n = _spa_num(p.get("likes_count"))
            return n if n is not None else _spa_num(p.get("likes"))
        likes = [like_getter(p) for p in posts if like_getter(p) is not None]
        by_type_likes = _spa_group_avg(posts, like_getter, _spa_post_type)
        by_type_hashtags = {}
        for t in sorted(set(content_types)):
            selected = [p for p in posts if _spa_post_type(p) == t]
            if selected:
                by_type_hashtags[t] = round(sum(len(_spa_hashtags(p)) for p in selected) / len(selected), 2)
        topic_values = {}
        for p in posts:
            lv = like_getter(p)
            if lv is None:
                continue
            for topic in _spa_topic_from_post(p):
                topic_values.setdefault(topic, []).append(lv)
        result.update({
            "likes_visible_count": len(likes),
            "likes_missing_count": max(len(posts) - len(likes), 0),
            "total_visible_likes": int(sum(likes)) if likes else None,
            "average_likes_visible_only": _spa_avg(likes),
            "average_likes_by_content_type": by_type_likes,
            "average_hashtags_by_content_type": by_type_hashtags,
            "average_likes_by_topic": {k: _spa_avg(v) for k, v in topic_values.items()},
            "visible_like_to_follower_ratio": round((_spa_avg(likes) / followers), 6) if likes and followers else None
        })
        sorted_liked = [p for p in posts if like_getter(p) is not None]
        sorted_liked.sort(key=lambda p: like_getter(p), reverse=True)
        result["top_posts_by_visible_likes"] = [
            {"url": _spa_post_url(p), "likes_count": _spa_int(like_getter(p)), "type": _spa_post_type(p)}
            for p in sorted_liked[:3]
        ]
        result["lowest_posts_by_visible_likes"] = [
            {"url": _spa_post_url(p), "likes_count": _spa_int(like_getter(p)), "type": _spa_post_type(p)}
            for p in list(reversed(sorted_liked[-3:]))
        ]
    elif platform == "facebook":
        reactions = [_spa_num(p.get("reactions_count")) for p in posts if _spa_num(p.get("reactions_count")) is not None]
        comments = [_spa_num(p.get("comments_count")) for p in posts if _spa_num(p.get("comments_count")) is not None]
        shares = [_spa_num(p.get("shares_count")) for p in posts if _spa_num(p.get("shares_count")) is not None]
        interactions = []
        for p in posts:
            r = _spa_num(p.get("reactions_count")) or 0
            c = _spa_num(p.get("comments_count")) or 0
            s = _spa_num(p.get("shares_count")) or 0
            if any(_spa_num(p.get(k)) is not None for k in ("reactions_count", "comments_count", "shares_count")):
                interactions.append(r + c + s)
        result.update({
            "reactions_visible_count": len(reactions),
            "comments_visible_count": len(comments),
            "shares_visible_count": len(shares),
            "average_reactions_visible_only": _spa_avg(reactions),
            "average_comments_visible_only": _spa_avg(comments),
            "average_shares_visible_only": _spa_avg(shares),
            "average_visible_interactions_per_post": _spa_avg(interactions),
            "visible_interaction_to_follower_ratio": round((_spa_avg(interactions) / followers), 6) if interactions and followers else None
        })
        if not interactions:
            result["status"] = "not_calculable"
            result["reason"] = "Facebook no expuso metricas publicas suficientes en los posts provistos."
    else:
        result["reason"] = "Plataforma generica: se calcularon solo promedios transversales disponibles."
    return result


@app.post("/audit/social-public-averages")
def auditSocialPublicAverages(request: SocialPublicAveragesRequest):
    posts = request.posts or []
    public_averages = _spa_build_public_averages(
        platform=request.platform,
        followers_total=request.followers_total,
        posts=posts
    )
    return {
        "collector": "social_public_averages",
        "version": APP_VERSION,
        "status": "completed",
        "company_name": request.company_name,
        "platform": request.platform,
        "profile_url": request.profile_url,
        "posts_received": len(posts),
        "public_averages": public_averages,
        "drive_upload": None,
        "drive_upload_status": "not_integrated_in_this_endpoint",
        "human_readable_messages": [
            "Promedios calculados solo sobre datos publicos visibles.",
            "No representan performance real sin datos nativos de la plataforma.",
            "Usar como senal parcial para priorizacion, no como verdad de negocio."
        ]
    }

# ============================================================
# MICRO PATCH 4H.1-B - INSTAGRAM POSTS BY URL COMPACT FOR ACTIONS
# ============================================================

try:
    BaseModel
except NameError:
    from pydantic import BaseModel

class InstagramPostsByUrlCompactRequest(BaseModel):
    post_urls: list
    company_name: str | None = None
    profile_url: str | None = None
    followers_total: int | float | str | None = None
    max_posts: int = 12
    wait_ms: int = 2500
    timeout_ms: int = 25000
    upload_to_drive: bool = True
    drive_folder_name: str | None = None
    filename_prefix: str | None = None
    include_posts_compact: bool = True
    max_hashtags_per_post: int = 20


def _igpuc_to_dict(obj):
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    return {}


def _igpuc_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _igpuc_hashtags(post, max_items=20):
    tags = []
    raw = _igpuc_get(post, "hashtags", [])
    if isinstance(raw, str):
        parts = [x.strip() for x in raw.replace("\n", " ").replace(";", ",").split(",")]
        if len(parts) == 1:
            parts = [x.strip() for x in raw.replace("\n", " ").split(" ")]
        tags = [x for x in parts if x.startswith("#")]
    elif isinstance(raw, list):
        tags = [str(x).strip() for x in raw if str(x).strip().startswith("#")]
    clean = []
    seen = set()
    for tag in tags:
        key = tag.casefold()
        if key not in seen:
            seen.add(key)
            clean.append(tag)
    return clean[:max_items]


def _igpuc_slim_post(post, max_hashtags=20):
    if not isinstance(post, dict):
        post = _igpuc_to_dict(post)
    url = post.get("url") or post.get("post_url") or post.get("permalink")
    typ = post.get("type") or post.get("post_type")
    if not typ and isinstance(url, str):
        if "/reel/" in url:
            typ = "reel"
        elif "/p/" in url:
            typ = "post"
    return {
        "url": url,
        "type": typ or "unknown",
        "parse_status": post.get("parse_status"),
        "date_iso": post.get("date_iso") or post.get("published_at") or post.get("created_time"),
        "likes_count": post.get("likes_count") if post.get("likes_count") is not None else post.get("likes"),
        "hashtags": _igpuc_hashtags(post, max_hashtags),
        "has_caption_sample": bool(post.get("caption_sample") or post.get("caption") or post.get("text")),
        "error": post.get("error")
    }


def _igpuc_extract_posts(full):
    if not isinstance(full, dict):
        full = _igpuc_to_dict(full)
    for key in ("posts", "posts_detail", "last_posts", "items", "post_results"):
        val = full.get(key)
        if isinstance(val, list):
            return val
    ms = full.get("metrics_summary")
    if isinstance(ms, dict):
        for key in ("posts", "last_posts", "posts_detail"):
            val = ms.get(key)
            if isinstance(val, list):
                return val
    return []


@app.post("/audit/instagram-posts-by-url-compact")
def auditInstagramPostsByUrlCompact(request: InstagramPostsByUrlCompactRequest):
    raw_urls = list(request.post_urls or [])
    urls = []
    seen = set()
    for u in raw_urls:
        s = str(u).strip()
        if not s:
            continue
        if "instagram.com/" not in s:
            continue
        if s not in seen:
            seen.add(s)
            urls.append(s)
        if len(urls) >= min(int(request.max_posts or 12), 12):
            break

    if not urls:
        return {
            "collector": "instagram_posts_by_url_compact",
            "version": APP_VERSION,
            "status": "failed_validation",
            "reason": "No valid Instagram post URLs provided.",
            "posts_received": 0
        }

    if "InstagramPostsByUrlRequest" not in globals() or "auditInstagramPostsByUrl" not in globals():
        return {
            "collector": "instagram_posts_by_url_compact",
            "version": APP_VERSION,
            "status": "failed_runtime",
            "reason": "Base endpoint auditInstagramPostsByUrl is not available.",
            "posts_received": len(urls)
        }

    base_payload = {
        "post_urls": urls,
        "company_name": request.company_name,
        "profile_url": request.profile_url,
        "max_posts": min(int(request.max_posts or 12), 12),
        "wait_ms": request.wait_ms,
        "timeout_ms": request.timeout_ms,
        "upload_to_drive": request.upload_to_drive,
        "drive_folder_name": request.drive_folder_name,
        "filename_prefix": request.filename_prefix or "instagram_posts_by_url_compact"
    }

    base_req = InstagramPostsByUrlRequest(**base_payload)
    full = auditInstagramPostsByUrl(base_req)
    full_dict = _igpuc_to_dict(full)

    posts_full = _igpuc_extract_posts(full_dict)
    posts_compact = [
        _igpuc_slim_post(p, max_hashtags=int(request.max_hashtags_per_post or 20))
        for p in posts_full
    ]

    public_averages = None
    if "_spa_build_public_averages" in globals():
        try:
            public_averages = _spa_build_public_averages(
                platform="instagram",
                followers_total=request.followers_total,
                posts=posts_compact
            )
        except Exception as exc:
            public_averages = {
                "status": "failed_runtime",
                "reason": f"public averages failed: {exc}"
            }

    metrics_summary = full_dict.get("metrics_summary") if isinstance(full_dict.get("metrics_summary"), dict) else {}
    visibility_report = full_dict.get("visibility_report") if isinstance(full_dict.get("visibility_report"), dict) else {}

    drive_keys = {}
    for k in ("drive_report_upload", "drive_upload", "report_drive_url", "report_folder_url"):
        if k in full_dict:
            drive_keys[k] = full_dict.get(k)

    return {
        "collector": "instagram_posts_by_url_compact",
        "version": APP_VERSION,
        "status": full_dict.get("status", "completed"),
        "base_collector_status": full_dict.get("status"),
        "company_name": request.company_name,
        "profile_url": request.profile_url,
        "posts_requested": len(urls),
        "posts_parsed": metrics_summary.get("posts_parsed"),
        "posts_completed": metrics_summary.get("posts_completed"),
        "posts_failed": metrics_summary.get("posts_failed"),
        "likes_visible_count": metrics_summary.get("likes_visible_count"),
        "likes_missing_count": metrics_summary.get("likes_missing_count"),
        "posts_with_visible_dates": visibility_report.get("posts_with_visible_dates"),
        "posts_with_visible_likes": visibility_report.get("posts_with_visible_likes"),
        "posts_with_visible_hashtags": visibility_report.get("posts_with_visible_hashtags"),
        "average_likes_last_posts_visible_only": metrics_summary.get("average_likes_last_posts_visible_only"),
        "frequency_status": metrics_summary.get("frequency_status"),
        "publishing_frequency_window_start": metrics_summary.get("publishing_frequency_window_start"),
        "publishing_frequency_window_end": metrics_summary.get("publishing_frequency_window_end"),
        "posts_in_frequency_window": metrics_summary.get("posts_in_frequency_window"),
        "posts_per_week_in_frequency_window": metrics_summary.get("posts_per_week_in_frequency_window"),
        "average_days_between_posts_in_window": metrics_summary.get("average_days_between_posts_in_window"),
        "public_averages": public_averages,
        "posts_compact": posts_compact if request.include_posts_compact else [],
        "drive": drive_keys,
        "human_readable_messages": [
            "Respuesta compacta para Actions.",
            "Los promedios son publicos visibles parciales.",
            "No representan alcance, views, engagement total, clics, ventas ni performance real."
        ],
        "limitations": [
            "Caption completo y HTML bruto se omiten para evitar exceder limite de respuesta de Actions.",
            "Usar Drive/report_id para evidencia completa si el endpoint base la genero.",
            "La muestra esta limitada a 12 posts en Render por estabilidad operativa."
        ]
    }

# ============================================================
# MICRO PATCH 4H.1-B.1 - INSTAGRAM POSTS COMPACT V2 ASYNC FIX
# ============================================================

def _igpuc_v2_jsonable(obj):
    import json
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "body"):
        try:
            body = obj.body
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")
            return json.loads(body)
        except Exception:
            pass
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    return {}


def _igpuc_v2_count_metrics(posts_compact):
    likes = []
    dates = 0
    hashtags = 0
    completed = 0
    failed = 0
    for p in posts_compact or []:
        status = p.get("parse_status")
        if status == "failed":
            failed += 1
        else:
            completed += 1
        if p.get("date_iso"):
            dates += 1
        if p.get("hashtags"):
            hashtags += 1
        lv = p.get("likes_count")
        if lv is not None and str(lv).strip() != "":
            try:
                likes.append(float(str(lv).replace(",", ".")))
            except Exception:
                pass
    avg_likes = round(sum(likes) / len(likes), 2) if likes else None
    return {
        "posts_completed": completed,
        "posts_failed": failed,
        "likes_visible_count": len(likes),
        "likes_missing_count": max(len(posts_compact or []) - len(likes), 0),
        "posts_with_visible_dates": dates,
        "posts_with_visible_likes": len(likes),
        "posts_with_visible_hashtags": hashtags,
        "average_likes_last_posts_visible_only": avg_likes
    }


@app.post("/audit/instagram-posts-by-url-compact-v2")
async def auditInstagramPostsByUrlCompactV2(request: InstagramPostsByUrlCompactRequest):
    import inspect

    raw_urls = list(request.post_urls or [])
    urls = []
    seen = set()
    for u in raw_urls:
        s = str(u).strip()
        if not s:
            continue
        if "instagram.com/" not in s:
            continue
        if s not in seen:
            seen.add(s)
            urls.append(s)
        if len(urls) >= min(int(request.max_posts or 12), 12):
            break

    if not urls:
        return {
            "collector": "instagram_posts_by_url_compact_v2",
            "version": APP_VERSION,
            "status": "failed_validation",
            "reason": "No valid Instagram post URLs provided.",
            "posts_received": 0
        }

    if "InstagramPostsByUrlRequest" not in globals() or "auditInstagramPostsByUrl" not in globals():
        return {
            "collector": "instagram_posts_by_url_compact_v2",
            "version": APP_VERSION,
            "status": "failed_runtime",
            "reason": "Base endpoint auditInstagramPostsByUrl is not available.",
            "posts_received": len(urls)
        }

    base_payload = {
        "post_urls": urls,
        "company_name": request.company_name,
        "profile_url": request.profile_url,
        "max_posts": min(int(request.max_posts or 12), 12),
        "wait_ms": request.wait_ms,
        "timeout_ms": request.timeout_ms,
        "upload_to_drive": request.upload_to_drive,
        "drive_folder_name": request.drive_folder_name,
        "filename_prefix": request.filename_prefix or "instagram_posts_by_url_compact_v2"
    }

    base_req = InstagramPostsByUrlRequest(**base_payload)

    try:
        base_result = auditInstagramPostsByUrl(base_req)
        if inspect.isawaitable(base_result):
            base_result = await base_result
        full_dict = _igpuc_v2_jsonable(base_result)
    except Exception as exc:
        return {
            "collector": "instagram_posts_by_url_compact_v2",
            "version": APP_VERSION,
            "status": "failed_runtime",
            "reason": f"Base endpoint call failed: {exc}",
            "posts_requested": len(urls)
        }

    posts_full = _igpuc_extract_posts(full_dict) if "_igpuc_extract_posts" in globals() else []
    posts_compact = [
        _igpuc_slim_post(p, max_hashtags=int(request.max_hashtags_per_post or 20))
        for p in posts_full
    ] if "_igpuc_slim_post" in globals() else []

    fallback_counts = _igpuc_v2_count_metrics(posts_compact)

    public_averages = None
    if "_spa_build_public_averages" in globals():
        try:
            public_averages = _spa_build_public_averages(
                platform="instagram",
                followers_total=request.followers_total,
                posts=posts_compact
            )
        except Exception as exc:
            public_averages = {
                "status": "failed_runtime",
                "reason": f"public averages failed: {exc}"
            }

    metrics_summary = full_dict.get("metrics_summary") if isinstance(full_dict.get("metrics_summary"), dict) else {}
    visibility_report = full_dict.get("visibility_report") if isinstance(full_dict.get("visibility_report"), dict) else {}

    def pick(primary, fallback_key):
        val = primary
        if val is None or val == "":
            return fallback_counts.get(fallback_key)
        return val

    drive_keys = {}
    for k in ("drive_report_upload", "drive_upload", "report_drive_url", "report_folder_url"):
        if k in full_dict:
            drive_keys[k] = full_dict.get(k)

    return {
        "collector": "instagram_posts_by_url_compact_v2",
        "version": APP_VERSION,
        "status": full_dict.get("status", "completed"),
        "base_collector_status": full_dict.get("status"),
        "company_name": request.company_name,
        "profile_url": request.profile_url,
        "posts_requested": len(urls),
        "posts_returned_compact": len(posts_compact),
        "posts_parsed": pick(metrics_summary.get("posts_parsed"), "posts_completed"),
        "posts_completed": pick(metrics_summary.get("posts_completed"), "posts_completed"),
        "posts_failed": pick(metrics_summary.get("posts_failed"), "posts_failed"),
        "likes_visible_count": pick(metrics_summary.get("likes_visible_count"), "likes_visible_count"),
        "likes_missing_count": pick(metrics_summary.get("likes_missing_count"), "likes_missing_count"),
        "posts_with_visible_dates": pick(visibility_report.get("posts_with_visible_dates"), "posts_with_visible_dates"),
        "posts_with_visible_likes": pick(visibility_report.get("posts_with_visible_likes"), "posts_with_visible_likes"),
        "posts_with_visible_hashtags": pick(visibility_report.get("posts_with_visible_hashtags"), "posts_with_visible_hashtags"),
        "average_likes_last_posts_visible_only": pick(metrics_summary.get("average_likes_last_posts_visible_only"), "average_likes_last_posts_visible_only"),
        "frequency_status": metrics_summary.get("frequency_status"),
        "publishing_frequency_window_start": metrics_summary.get("publishing_frequency_window_start"),
        "publishing_frequency_window_end": metrics_summary.get("publishing_frequency_window_end"),
        "posts_in_frequency_window": metrics_summary.get("posts_in_frequency_window"),
        "posts_per_week_in_frequency_window": metrics_summary.get("posts_per_week_in_frequency_window"),
        "average_days_between_posts_in_window": metrics_summary.get("average_days_between_posts_in_window"),
        "public_averages": public_averages,
        "posts_compact": posts_compact if request.include_posts_compact else [],
        "drive": drive_keys,
        "compact_response": True,
        "human_readable_messages": [
            "Respuesta compacta v2 para Actions.",
            "La llamada interna al endpoint base soporta funciones async/sync.",
            "Los promedios son publicos visibles parciales.",
            "No representan alcance, views, engagement total, clics, ventas ni performance real."
        ],
        "limitations": [
            "Caption completo y HTML bruto se omiten para evitar exceder limite de respuesta de Actions.",
            "Usar Drive/report_id para evidencia completa si el endpoint base la genero.",
            "La muestra esta limitada a 12 posts en Render por estabilidad operativa."
        ]
    }

# ============================================================
# MICRO PATCH 4H.2-A - REPORT PACKAGE BUILDER + DRIVE DOCS
# ============================================================

try:
    BaseModel
except NameError:
    from pydantic import BaseModel

from typing import Any, Dict, Optional, List
import os as _rpb_os
import re as _rpb_re
import json as _rpb_json
import html as _rpb_html
import uuid as _rpb_uuid
import base64 as _rpb_base64
import mimetypes as _rpb_mimetypes
from pathlib import Path as _rpb_Path
from datetime import datetime as _rpb_datetime, timezone as _rpb_timezone

try:
    from fastapi.responses import HTMLResponse as _rpb_HTMLResponse, FileResponse as _rpb_FileResponse, JSONResponse as _rpb_JSONResponse
except Exception:
    _rpb_HTMLResponse = None
    _rpb_FileResponse = None
    _rpb_JSONResponse = None


class ReportPackageRequest(BaseModel):
    company_name: str
    report_title: str = "Auditoria Publica Integral"
    client_type: Optional[str] = None
    markdown_report: str
    executive_summary_markdown: Optional[str] = None
    evidence_payload: Dict[str, Any] = {}
    social_metrics: Dict[str, Any] = {}
    drive_folder_name: Optional[str] = None
    documentation_folder_name: str = "Documentaci\u00f3n"
    technical_folder_name: str = "T\u00e9cnico"
    generate_interactive_html: bool = True
    generate_full_pdf: bool = True
    generate_executive_pdf: bool = True
    upload_to_drive: bool = True
    public_sharing: bool = True
    filename_prefix: Optional[str] = None


class ReportPackageRegenerateRequest(BaseModel):
    company_name: str
    report_title: str = "Auditoria Publica Integral"
    markdown_report: str
    executive_summary_markdown: Optional[str] = None
    evidence_payload: Dict[str, Any] = {}
    social_metrics: Dict[str, Any] = {}
    drive_folder_name: Optional[str] = None
    documentation_folder_name: str = "Documentaci\u00f3n"
    technical_folder_name: str = "T\u00e9cnico"
    regenerate_interactive_html: bool = True
    regenerate_full_pdf: bool = True
    regenerate_executive_pdf: bool = True
    upload_to_drive: bool = True
    public_sharing: bool = True
    filename_prefix: Optional[str] = None


_RPB_ROOT = _rpb_Path(_rpb_os.getenv("REPORT_PACKAGE_ROOT", "/tmp/marketing_audit_report_packages"))
_RPB_ROOT.mkdir(parents=True, exist_ok=True)


def _rpb_now_iso():
    return _rpb_datetime.now(_rpb_timezone.utc).isoformat()


def _rpb_public_base_url():
    return (_rpb_os.getenv("PUBLIC_BASE_URL") or _rpb_os.getenv("RENDER_EXTERNAL_URL") or "https://marketing-audit-api.onrender.com").rstrip("/")


def _rpb_slug(value: str) -> str:
    value = (value or "reporte").lower()
    for a, b in {"\u00e1":"a","\u00e9":"e","\u00ed":"i","\u00f3":"o","\u00fa":"u","\u00f1":"n","\u00fc":"u"}.items():
        value = value.replace(a, b)
    value = _rpb_re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return (value or "reporte")[:80]


def _rpb_report_id(company_name: str) -> str:
    return f"{_rpb_slug(company_name)}_{_rpb_datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{_rpb_uuid.uuid4().hex[:8]}"


def _rpb_escape(value: Any) -> str:
    return _rpb_html.escape("" if value is None else str(value), quote=True)


def _rpb_markdown_to_basic_html(md: str) -> str:
    lines = (md or "").splitlines()
    out = []
    in_ul = False
    in_table = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    def close_table():
        nonlocal in_table
        if in_table:
            out.append("</tbody></table></div>")
            in_table = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_ul()
            close_table()
            continue
        if line.startswith("|") and line.endswith("|"):
            close_ul()
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if not in_table:
                out.append('<div class="table-wrap"><table><tbody>')
                in_table = True
            out.append("<tr>" + "".join(f"<td>{_rpb_escape(c)}</td>" for c in cells) + "</tr>")
            continue
        close_table()
        if line.startswith("### "):
            close_ul()
            out.append(f"<h3>{_rpb_escape(line[4:])}</h3>")
        elif line.startswith("## "):
            close_ul()
            out.append(f"<h2>{_rpb_escape(line[3:])}</h2>")
        elif line.startswith("# "):
            close_ul()
            out.append(f"<h1>{_rpb_escape(line[2:])}</h1>")
        elif _rpb_re.match(r"^\s*[-*]\s+", line):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = _rpb_re.sub(r"^\s*[-*]\s+", "", line)
            out.append(f"<li>{_rpb_escape(item)}</li>")
        else:
            close_ul()
            text = _rpb_escape(line)
            text = _rpb_re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
            out.append(f"<p>{text}</p>")
    close_ul()
    close_table()
    return "\n".join(out)


def _rpb_sections_from_markdown(md: str) -> List[Dict[str, str]]:
    sections = []
    title = "Inicio"
    buf = []
    for line in (md or "").splitlines():
        if line.startswith("## "):
            if buf:
                sections.append({"title": title, "markdown": "\n".join(buf).strip()})
            title = line[3:].strip()
            buf = [line]
        else:
            buf.append(line)
    if buf:
        sections.append({"title": title, "markdown": "\n".join(buf).strip()})
    return sections


def _rpb_build_interactive_html(req: ReportPackageRequest, report_id: str, created_at: str) -> str:
    sections = _rpb_sections_from_markdown(req.markdown_report)
    nav = []
    panels = []
    for i, sec in enumerate(sections):
        sid = f"sec_{i}"
        active = "active" if i == 0 else ""
        nav.append(f"<button class='tab {active}' data-target='{sid}'>{_rpb_escape(sec['title'])}</button>")
        panels.append(f"<section id='{sid}' class='panel {active}'>{_rpb_markdown_to_basic_html(sec['markdown'])}</section>")
    evidence = _rpb_escape(_rpb_json.dumps(req.evidence_payload or {}, ensure_ascii=False, indent=2))
    metrics = _rpb_escape(_rpb_json.dumps(req.social_metrics or {}, ensure_ascii=False, indent=2))
    css = ":root{--bg:#020617;--card:#0f172a;--line:#334155;--text:#e5e7eb;--muted:#94a3b8;--acc:#38bdf8}*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text)}header{padding:28px;background:#0f172a;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}h1{margin:0 0 8px;font-size:28px}.meta{color:var(--muted);font-size:13px;display:flex;gap:14px;flex-wrap:wrap}.layout{display:grid;grid-template-columns:290px 1fr}nav{border-right:1px solid var(--line);padding:18px;background:#030712;position:sticky;top:94px;height:calc(100vh - 94px);overflow:auto}.tab{display:block;width:100%;text-align:left;margin:0 0 8px;padding:11px 12px;background:#0f172a;color:var(--text);border:1px solid var(--line);border-radius:12px;cursor:pointer}.tab.active,.tab:hover{border-color:var(--acc);background:#082f49}main{padding:24px;max-width:1320px}.panel{display:none;background:#0f172a;border:1px solid var(--line);border-radius:18px;padding:24px;box-shadow:0 12px 40px #0006}.panel.active{display:block}h2{border-bottom:1px solid var(--line);padding-bottom:8px}h3{color:#bae6fd}p,li{line-height:1.55}.table-wrap{overflow:auto;margin:14px 0;border:1px solid var(--line);border-radius:12px}table{border-collapse:collapse;width:100%;min-width:760px}td,th{border-bottom:1px solid var(--line);padding:10px;vertical-align:top}tr:first-child td{font-weight:700;color:#e0f2fe;background:#0b1220}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:18px 0}.card{background:#0b1220;border:1px solid var(--line);border-radius:14px;padding:14px}details{margin:14px 0;border:1px solid var(--line);border-radius:12px;padding:12px;background:#0b1220}summary{cursor:pointer;color:#bae6fd;font-weight:700}pre{white-space:pre-wrap;overflow:auto;max-height:480px;background:#020617;border:1px solid var(--line);border-radius:12px;padding:12px}@media(max-width:900px){.layout{grid-template-columns:1fr}nav{position:relative;top:0;height:auto}}"
    js = "document.querySelectorAll('.tab').forEach(function(btn){btn.addEventListener('click',function(){document.querySelectorAll('.tab').forEach(function(b){b.classList.remove('active')});document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active')});btn.classList.add('active');var t=document.getElementById(btn.dataset.target);if(t){t.classList.add('active')}})})"
    return "\n".join([
        "<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>{_rpb_escape(req.report_title)} - {_rpb_escape(req.company_name)}</title><style>{css}</style></head><body>",
        "<header>",
        f"<h1>{_rpb_escape(req.report_title)}</h1>",
        f"<div class='meta'><span>Cliente: <strong>{_rpb_escape(req.company_name)}</strong></span><span>Report ID: {report_id}</span><span>Creado: {created_at}</span><span>Tipo: {_rpb_escape(req.client_type or 'auditoria_publica')}</span></div>",
        "</header><div class='layout'><nav>",
        "".join(nav),
        "</nav><main>",
        "<div class='cards'><div class='card'><strong>HTML interactivo</strong><p>Auditor\u00eda completa navegable.</p></div><div class='card'><strong>PDF completo</strong><p>Mismo contenido, fijo.</p></div><div class='card'><strong>PDF ejecutivo</strong><p>Resumen para due\u00f1os.</p></div></div>",
        "".join(panels),
        f"<section class='panel active' style='display:block;margin-top:18px'><h2>Anexos t\u00e9cnicos</h2><details><summary>Evidencia t\u00e9cnica JSON</summary><pre>{evidence}</pre></details><details><summary>M\u00e9tricas sociales JSON</summary><pre>{metrics}</pre></details></section>",
        "</main></div><footer style='padding:24px;color:#94a3b8'>Generado por Marketing Auditor. M\u00e9tricas p\u00fablicas parciales, no performance interna.</footer>",
        f"<script>{js}</script></body></html>"
    ])


def _rpb_extract_executive_md(full_md: str) -> str:
    keys = ["resumen ejecutivo", "sem\u00e1foro", "semaforo", "m\u00e9tricas p\u00fablicas", "metricas publicas", "plan 30", "pr\u00f3ximos pasos", "proximos pasos", "decisi\u00f3n", "decision"]
    selected = []
    for sec in _rpb_sections_from_markdown(full_md):
        if any(k in sec["title"].lower() for k in keys):
            selected.append(sec["markdown"])
    return "\n\n".join(selected[:6]) if selected else "\n".join((full_md or "").splitlines()[:120])


def _rpb_parse_table(lines: List[str], start: int):
    rows = []
    i = start
    while i < len(lines):
        line = lines[i].strip()
        if not (line.startswith("|") and line.endswith("|")):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not all(set(c) <= set("-: ") for c in cells):
            rows.append(cells)
        i += 1
    return rows, i


def _rpb_markdown_to_pdf(path: _rpb_Path, title: str, md: str, company_name: str, executive: bool = False):
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except Exception as exc:
        raise RuntimeError(f"reportlab unavailable: {exc}")
    page_size = A4 if executive else landscape(A4)
    doc = SimpleDocTemplate(str(path), pagesize=page_size, rightMargin=1.2*cm, leftMargin=1.2*cm, topMargin=1.2*cm, bottomMargin=1.2*cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SmallBodyRPB", parent=styles["BodyText"], fontSize=8 if not executive else 9, leading=10 if not executive else 12))
    styles.add(ParagraphStyle(name="TinyRPB", parent=styles["BodyText"], fontSize=7, leading=9))
    story = [Paragraph(_rpb_escape(title), styles["Heading1"]), Paragraph(f"Cliente: {_rpb_escape(company_name)}", styles["SmallBodyRPB"]), Paragraph(f"Generado: {_rpb_now_iso()}", styles["TinyRPB"]), Spacer(1, 10)]
    lines = (md or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            story.append(Spacer(1, 4)); i += 1; continue
        if line.startswith("|") and line.endswith("|"):
            rows, nxt = _rpb_parse_table(lines, i)
            if rows:
                max_cols = max(len(r) for r in rows)
                norm = []
                for r in rows:
                    rr = r + [""] * (max_cols - len(r))
                    norm.append([Paragraph(_rpb_escape(c), styles["TinyRPB"]) for c in rr])
                usable = page_size[0] - 2.4*cm
                tbl = Table(norm, colWidths=[max(2.2*cm, usable / max_cols)] * max_cols, repeatRows=1)
                tbl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0f172a")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#cbd5e1")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
                story.append(tbl); story.append(Spacer(1, 8)); i = nxt; continue
        if line.startswith("# "):
            story.append(Paragraph(_rpb_escape(line[2:]), styles["Heading1"]))
        elif line.startswith("## "):
            story.append(Paragraph(_rpb_escape(line[3:]), styles["Heading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(_rpb_escape(line[4:]), styles["Heading3"]))
        else:
            story.append(Paragraph(_rpb_escape(line), styles["SmallBodyRPB"]))
        i += 1
    doc.build(story)


def _rpb_service_account_info():
    keys = ["GOOGLE_SERVICE_ACCOUNT_JSON","GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON","GDRIVE_SERVICE_ACCOUNT_JSON","DRIVE_SERVICE_ACCOUNT_JSON","GOOGLE_CREDENTIALS_JSON","GOOGLE_APPLICATION_CREDENTIALS_JSON"]
    for key in keys:
        val = _rpb_os.getenv(key)
        if not val: continue
        try: return _rpb_json.loads(val)
        except Exception: pass
        try: return _rpb_json.loads(_rpb_base64.b64decode(val).decode("utf-8"))
        except Exception: pass
    p = _rpb_os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if p and _rpb_Path(p).exists():
        return _rpb_json.loads(_rpb_Path(p).read_text(encoding="utf-8"))
    return None


def _rpb_drive_parent_id():
    for key in ["GOOGLE_DRIVE_PARENT_FOLDER_ID","DRIVE_PARENT_FOLDER_ID","GOOGLE_DRIVE_FOLDER_ID","DRIVE_FOLDER_ID","GDRIVE_FOLDER_ID"]:
        val = _rpb_os.getenv(key)
        if val: return val.strip()
    return None


def _rpb_drive_headers():
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except Exception as exc:
        raise RuntimeError(f"google-auth unavailable: {exc}")
    info = _rpb_service_account_info()
    if not info:
        raise RuntimeError("No Google service account JSON found in environment aliases.")
    creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive"])
    creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}


def _rpb_drive_find_or_create_folder(name: str, parent_id: Optional[str], public_sharing: bool = True):
    import requests
    headers = _rpb_drive_headers()
    safe = (name or "").replace("\\", "\\\\").replace("'", "\\'")
    q = f"mimeType='application/vnd.google-apps.folder' and trashed=false and name='{safe}'"
    if parent_id: q += f" and '{parent_id}' in parents"
    params = {"q": q, "fields": "files(id,name,webViewLink)", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
    r = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params=params, timeout=60); r.raise_for_status()
    files = r.json().get("files") or []
    if files: return files[0]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id: meta["parents"] = [parent_id]
    r = requests.post("https://www.googleapis.com/drive/v3/files", headers={**headers, "Content-Type":"application/json"}, params={"fields":"id,name,webViewLink","supportsAllDrives":"true"}, json=meta, timeout=60); r.raise_for_status()
    folder = r.json()
    if public_sharing:
        try:
            requests.post(f"https://www.googleapis.com/drive/v3/files/{folder['id']}/permissions", headers={**headers, "Content-Type":"application/json"}, params={"supportsAllDrives":"true"}, json={"role":"reader","type":"anyone"}, timeout=60)
        except Exception: pass
    return folder


def _rpb_drive_upload_file(path: _rpb_Path, folder_id: str, public_sharing: bool = True):
    import requests
    headers = _rpb_drive_headers()
    mime = _rpb_mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    boundary = "rpb_" + _rpb_uuid.uuid4().hex
    meta = _rpb_json.dumps({"name": path.name, "parents": [folder_id]}).encode("utf-8")
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n").encode("utf-8") + meta + (f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode("utf-8") + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    r = requests.post("https://www.googleapis.com/upload/drive/v3/files", headers={**headers, "Content-Type": f"multipart/related; boundary={boundary}"}, params={"uploadType":"multipart","fields":"id,name,webViewLink,webContentLink","supportsAllDrives":"true"}, data=body, timeout=180); r.raise_for_status()
    info = r.json()
    if public_sharing:
        try:
            requests.post(f"https://www.googleapis.com/drive/v3/files/{info['id']}/permissions", headers={**headers, "Content-Type":"application/json"}, params={"supportsAllDrives":"true"}, json={"role":"reader","type":"anyone"}, timeout=60)
        except Exception as exc:
            info["permission_warning"] = str(exc)
    return info


def _rpb_build_package(req: ReportPackageRequest):
    created_at = _rpb_now_iso()
    report_id = _rpb_report_id(req.company_name)
    prefix = _rpb_slug(req.filename_prefix or req.company_name)
    workdir = _RPB_ROOT / report_id
    techdir = workdir / "tecnico"
    techdir.mkdir(parents=True, exist_ok=True)
    files = {}
    errors = []
    md_path = techdir / f"04_{prefix}_reporte_fuente.md"
    json_path = techdir / f"05_{prefix}_evidencia_tecnica.json"
    md_path.write_text(req.markdown_report or "", encoding="utf-8")
    json_path.write_text(_rpb_json.dumps({"report_id":report_id,"company_name":req.company_name,"report_title":req.report_title,"created_at":created_at,"evidence_payload":req.evidence_payload or {},"social_metrics":req.social_metrics or {}}, ensure_ascii=False, indent=2), encoding="utf-8")
    files["markdown_source"] = {"status":"created","path":str(md_path)}
    files["evidence_json"] = {"status":"created","path":str(json_path)}
    html_path = workdir / f"01_{prefix}_auditoria_interactiva_completa.html"
    full_pdf_path = workdir / f"02_{prefix}_auditoria_completa.pdf"
    exec_pdf_path = workdir / f"03_{prefix}_resumen_ejecutivo_duenos.pdf"
    if req.generate_interactive_html:
        try:
            html_path.write_text(_rpb_build_interactive_html(req, report_id, created_at), encoding="utf-8")
            files["interactive_html"] = {"status":"created","path":str(html_path)}
        except Exception as exc:
            files["interactive_html"] = {"status":"failed","reason":str(exc),"regenerable":True}; errors.append(f"interactive_html failed: {exc}")
    if req.generate_full_pdf:
        try:
            _rpb_markdown_to_pdf(full_pdf_path, f"{req.report_title} - Completa", req.markdown_report, req.company_name, executive=False)
            files["full_pdf"] = {"status":"created","path":str(full_pdf_path)}
        except Exception as exc:
            files["full_pdf"] = {"status":"failed","reason":str(exc),"regenerable":True}; errors.append(f"full_pdf failed: {exc}")
    if req.generate_executive_pdf:
        try:
            _rpb_markdown_to_pdf(exec_pdf_path, f"{req.report_title} - Resumen Ejecutivo", req.executive_summary_markdown or _rpb_extract_executive_md(req.markdown_report), req.company_name, executive=True)
            files["executive_pdf"] = {"status":"created","path":str(exec_pdf_path)}
        except Exception as exc:
            files["executive_pdf"] = {"status":"failed","reason":str(exc),"regenerable":True}; errors.append(f"executive_pdf failed: {exc}")
    base = _rpb_public_base_url()
    local_urls = {"interactive_html_url":f"{base}/deliverables/report-package/{report_id}/html","full_pdf_url":f"{base}/deliverables/report-package/{report_id}/pdf-full","executive_pdf_url":f"{base}/deliverables/report-package/{report_id}/pdf-executive","markdown_source_url":f"{base}/deliverables/report-package/{report_id}/md","evidence_json_url":f"{base}/deliverables/report-package/{report_id}/json"}
    drive = {"requested":bool(req.upload_to_drive),"status":"not_requested","parent_folder_name":req.drive_folder_name,"documentation_folder_name":req.documentation_folder_name,"technical_folder_name":req.technical_folder_name,"files":{}}
    if req.upload_to_drive:
        try:
            parent_name = req.drive_folder_name or f"{req.company_name} - Auditoria Publica Integral - {_rpb_datetime.utcnow().strftime('%Y-%m-%d')}"
            parent = _rpb_drive_find_or_create_folder(parent_name, _rpb_drive_parent_id(), req.public_sharing)
            doc = _rpb_drive_find_or_create_folder(req.documentation_folder_name or "Documentaci\u00f3n", parent.get("id"), req.public_sharing)
            tech = _rpb_drive_find_or_create_folder(req.technical_folder_name or "T\u00e9cnico", doc.get("id"), req.public_sharing)
            drive.update({"status":"uploading","parent_folder_id":parent.get("id"),"parent_folder_url":parent.get("webViewLink"),"documentation_folder_id":doc.get("id"),"documentation_folder_url":doc.get("webViewLink"),"technical_folder_id":tech.get("id"),"technical_folder_url":tech.get("webViewLink")})
            upload_plan = {"interactive_html":(html_path,doc.get("id")),"full_pdf":(full_pdf_path,doc.get("id")),"executive_pdf":(exec_pdf_path,doc.get("id")),"markdown_source":(md_path,tech.get("id")),"evidence_json":(json_path,tech.get("id"))}
            for key, (p, folder_id) in upload_plan.items():
                if p.exists() and files.get(key, {}).get("status") == "created":
                    try:
                        up = _rpb_drive_upload_file(p, folder_id, req.public_sharing)
                        drive["files"][key] = {"status":"uploaded","drive_file_id":up.get("id"),"drive_file_name":up.get("name"),"drive_url":up.get("webViewLink"),"download_url":up.get("webContentLink")}
                        files[key]["drive_url"] = up.get("webViewLink")
                        files[key]["drive_file_id"] = up.get("id")
                    except Exception as exc:
                        drive["files"][key] = {"status":"failed","reason":str(exc),"regenerable":True}; errors.append(f"drive upload {key} failed: {exc}")
            drive["status"] = "partial_failed" if any(v.get("status") == "failed" for v in drive["files"].values()) else "completed"
        except Exception as exc:
            drive["status"] = "failed"; drive["reason"] = str(exc); errors.append(f"drive setup failed: {exc}")
    return {"collector":"report_package_builder","version":APP_VERSION,"status":"completed" if not errors else "partial_completed","report_id":report_id,"company_name":req.company_name,"report_title":req.report_title,"created_at":created_at,"documentation_folder_name":req.documentation_folder_name,"technical_folder_name":req.technical_folder_name,"local_urls":local_urls,"files":files,"drive":drive,"errors":errors,"regeneration_available":True,"notes":["HTML interactivo completo y PDF completo comparten el mismo markdown_source.","PDF completo contiene la misma auditoria en formato fijo/no interactivo.","PDF ejecutivo es un documento separado para due\u00f1os/gerencia.","JSON tecnico y MD fuente sirven para trazabilidad y regeneracion."]}


@app.post("/deliverables/report-package")
def createReportPackage(request: ReportPackageRequest):
    return _rpb_build_package(request)


@app.post("/deliverables/report-package/regenerate")
def regenerateReportPackage(request: ReportPackageRegenerateRequest):
    req = ReportPackageRequest(company_name=request.company_name, report_title=request.report_title, markdown_report=request.markdown_report, executive_summary_markdown=request.executive_summary_markdown, evidence_payload=request.evidence_payload, social_metrics=request.social_metrics, drive_folder_name=request.drive_folder_name, documentation_folder_name=request.documentation_folder_name, technical_folder_name=request.technical_folder_name, generate_interactive_html=request.regenerate_interactive_html, generate_full_pdf=request.regenerate_full_pdf, generate_executive_pdf=request.regenerate_executive_pdf, upload_to_drive=request.upload_to_drive, public_sharing=request.public_sharing, filename_prefix=request.filename_prefix)
    return _rpb_build_package(req)


@app.get("/deliverables/report-package/{report_id}/html")
def getReportPackageHtml(report_id: str):
    matches = list((_RPB_ROOT / report_id).glob("01_*_auditoria_interactiva_completa.html"))
    if not matches:
        return _rpb_JSONResponse({"status":"not_found","report_id":report_id}, status_code=404) if _rpb_JSONResponse else {"status":"not_found","report_id":report_id}
    return _rpb_HTMLResponse(matches[0].read_text(encoding="utf-8")) if _rpb_HTMLResponse else matches[0].read_text(encoding="utf-8")


@app.get("/deliverables/report-package/{report_id}/pdf-full")
def getReportPackageFullPdf(report_id: str):
    matches = list((_RPB_ROOT / report_id).glob("02_*_auditoria_completa.pdf"))
    if not matches:
        return _rpb_JSONResponse({"status":"not_found","report_id":report_id}, status_code=404) if _rpb_JSONResponse else {"status":"not_found","report_id":report_id}
    return _rpb_FileResponse(str(matches[0]), media_type="application/pdf", filename=matches[0].name) if _rpb_FileResponse else {"status":"available","path":str(matches[0])}


@app.get("/deliverables/report-package/{report_id}/pdf-executive")
def getReportPackageExecutivePdf(report_id: str):
    matches = list((_RPB_ROOT / report_id).glob("03_*_resumen_ejecutivo_duenos.pdf"))
    if not matches:
        return _rpb_JSONResponse({"status":"not_found","report_id":report_id}, status_code=404) if _rpb_JSONResponse else {"status":"not_found","report_id":report_id}
    return _rpb_FileResponse(str(matches[0]), media_type="application/pdf", filename=matches[0].name) if _rpb_FileResponse else {"status":"available","path":str(matches[0])}


@app.get("/deliverables/report-package/{report_id}/md")
def getReportPackageMarkdownSource(report_id: str):
    matches = list((_RPB_ROOT / report_id / "tecnico").glob("04_*_reporte_fuente.md"))
    if not matches:
        return _rpb_JSONResponse({"status":"not_found","report_id":report_id}, status_code=404) if _rpb_JSONResponse else {"status":"not_found","report_id":report_id}
    return _rpb_FileResponse(str(matches[0]), media_type="text/markdown", filename=matches[0].name) if _rpb_FileResponse else matches[0].read_text(encoding="utf-8")


@app.get("/deliverables/report-package/{report_id}/json")
def getReportPackageEvidenceJson(report_id: str):
    matches = list((_RPB_ROOT / report_id / "tecnico").glob("05_*_evidencia_tecnica.json"))
    if not matches:
        return _rpb_JSONResponse({"status":"not_found","report_id":report_id}, status_code=404) if _rpb_JSONResponse else {"status":"not_found","report_id":report_id}
    return _rpb_FileResponse(str(matches[0]), media_type="application/json", filename=matches[0].name) if _rpb_FileResponse else _rpb_json.loads(matches[0].read_text(encoding="utf-8"))

# ============================================================
# MICRO PATCH 4H.2-B - REPORT PACKAGE DRIVE VIA EXISTING WEBAPP
# ============================================================

def _rpb_model_copy_no_drive(req):
    try:
        return req.model_copy(update={"upload_to_drive": False})
    except Exception:
        try:
            return req.copy(update={"upload_to_drive": False})
        except Exception:
            data = req.dict() if hasattr(req, "dict") else dict(req)
            data["upload_to_drive"] = False
            return ReportPackageRequest(**data)


def _rpb_folder_path(*parts):
    clean = []
    for p in parts:
        s = str(p or "").strip().strip("/").strip("\\")
        if s:
            clean.append(s)
    return "/".join(clean)


async def _rpb_upload_package_with_existing_drive(req, package_result):
    if "_drive_upload_binary" not in globals():
        return {
            "requested": bool(getattr(req, "upload_to_drive", False)),
            "status": "failed",
            "reason": "_drive_upload_binary not available",
            "integration": "existing_drive_webapp"
        }

    parent_folder = getattr(req, "drive_folder_name", None) or f"{getattr(req, 'company_name', 'Cliente')} - Auditoria Publica Integral - {_rpb_datetime.utcnow().strftime('%Y-%m-%d')}"
    documentation_name = getattr(req, "documentation_folder_name", None) or "Documentaci\u00f3n"
    technical_name = getattr(req, "technical_folder_name", None) or "T\u00e9cnico"

    documentation_folder = _rpb_folder_path(parent_folder, documentation_name)
    technical_folder = _rpb_folder_path(parent_folder, documentation_name, technical_name)

    files = package_result.get("files") or {}

    plan = {
        "interactive_html": ("text/html; charset=utf-8", documentation_folder),
        "full_pdf": ("application/pdf", documentation_folder),
        "executive_pdf": ("application/pdf", documentation_folder),
        "markdown_source": ("text/markdown; charset=utf-8", technical_folder),
        "evidence_json": ("application/json; charset=utf-8", technical_folder),
    }

    drive = {
        "requested": True,
        "status": "uploading",
        "integration": "existing_drive_webapp",
        "parent_folder_name": parent_folder,
        "documentation_folder_name": documentation_name,
        "technical_folder_name": technical_name,
        "documentation_folder_path": documentation_folder,
        "technical_folder_path": technical_folder,
        "files": {}
    }

    errors = []

    for key, tuple_value in plan.items():
        mime_type, folder_name = tuple_value
        item = files.get(key) or {}
        path_value = item.get("path")
        if not path_value:
            drive["files"][key] = {"status": "skipped", "reason": "file path missing"}
            continue

        try:
            p = _rpb_Path(path_value)
            if not p.exists():
                drive["files"][key] = {"status": "failed", "reason": f"file not found: {path_value}", "regenerable": True}
                errors.append(f"{key}: file not found")
                continue

            upload = await _drive_upload_binary(
                filename=p.name,
                content=p.read_bytes(),
                mime_type=mime_type,
                folder_name=folder_name
            )

            file_status = upload.get("status") or upload.get("drive_status") or "unknown"
            drive_url = upload.get("drive_url") or upload.get("file_url") or upload.get("webViewLink")
            folder_url = upload.get("drive_folder_url") or upload.get("folder_url")

            drive["files"][key] = {
                "status": file_status,
                "drive_url": drive_url,
                "folder_url": folder_url,
                "raw_upload_status": upload
            }

            if key in files:
                files[key]["drive_url"] = drive_url
                files[key]["drive_folder_url"] = folder_url
                files[key]["drive_upload_status"] = file_status

            if str(file_status).lower() not in ("completed", "uploaded", "ok", "success"):
                errors.append(f"{key}: upload status {file_status}")

        except Exception as exc:
            drive["files"][key] = {"status": "failed", "reason": str(exc), "regenerable": True}
            errors.append(f"{key}: {exc}")

    uploaded_ok = [
        k for k, v in drive["files"].items()
        if str(v.get("status")).lower() in ("completed", "uploaded", "ok", "success")
    ]
    failed = [
        k for k, v in drive["files"].items()
        if str(v.get("status")).lower() not in ("completed", "uploaded", "ok", "success")
    ]

    drive["uploaded_count"] = len(uploaded_ok)
    drive["failed_count"] = len(failed)
    drive["status"] = "completed" if len(uploaded_ok) == 5 and not errors else ("partial_failed" if uploaded_ok else "failed")
    if errors:
        drive["errors"] = errors

    return drive


@app.post("/deliverables/report-package-v2")
async def createReportPackageV2(request: ReportPackageRequest):
    local_req = _rpb_model_copy_no_drive(request)
    result = _rpb_build_package(local_req)
    result["collector"] = "report_package_builder_v2"
    result["version"] = APP_VERSION
    result["drive"] = {
        "requested": bool(request.upload_to_drive),
        "status": "not_requested",
        "integration": "existing_drive_webapp"
    }

    if request.upload_to_drive:
        drive = await _rpb_upload_package_with_existing_drive(request, result)
        result["drive"] = drive
        if drive.get("status") != "completed":
            result["status"] = "partial_completed"
            existing_errors = result.get("errors") or []
            for err in drive.get("errors") or []:
                existing_errors.append(f"drive_webapp upload: {err}")
            result["errors"] = existing_errors

    notes = result.get("notes") or []
    notes.append("4H.2-B: Drive upload uses existing DRIVE_UPLOAD_WEBAPP_URL/DRIVE_UPLOAD_SECRET integration.")
    notes.append("Documentation folder is requested as parent/Documentaci\u00f3n and technical files as parent/Documentaci\u00f3n/T\u00e9cnico.")
    result["notes"] = notes
    return result


@app.post("/deliverables/report-package/regenerate-v2")
async def regenerateReportPackageV2(request: ReportPackageRegenerateRequest):
    req = ReportPackageRequest(
        company_name=request.company_name,
        report_title=request.report_title,
        markdown_report=request.markdown_report,
        executive_summary_markdown=request.executive_summary_markdown,
        evidence_payload=request.evidence_payload,
        social_metrics=request.social_metrics,
        drive_folder_name=request.drive_folder_name,
        documentation_folder_name=request.documentation_folder_name,
        technical_folder_name=request.technical_folder_name,
        generate_interactive_html=request.regenerate_interactive_html,
        generate_full_pdf=request.regenerate_full_pdf,
        generate_executive_pdf=request.regenerate_executive_pdf,
        upload_to_drive=request.upload_to_drive,
        public_sharing=request.public_sharing,
        filename_prefix=request.filename_prefix
    )
    return await createReportPackageV2(req)

# ============================================================
# MICRO PATCH 4H.2-D - SPANISH ENCODING + BETTER PDF
# ============================================================

import unicodedata as _rpv3_unicodedata


def _rpv3_mojibake_score(text: str) -> int:
    if not isinstance(text, str):
        return 0
    markers = ["\u00c3\u0192", "\u00c3\u201a", "\u00c3\u00a2\u00e2\u201a\u00ac", "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u201e\u00a2", "\u00c3\u00a2\u00e2\u201a\u00ac\u00c5\u201c", "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u009d", "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u0153", "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u009d", "\u00c3\u00b0\u00c5\u00b8", "\u00ef\u00bf\u00bd"]
    return sum(text.count(m) for m in markers)


def _rpv3_fix_text(value):
    if not isinstance(value, str):
        return value
    text = value
    manual = {
        "\u00c3\u0192?":"?", "\u00c3\u0192\u00c2\u00a9":"?", "\u00c3\u0192\u00c2\u00ad":"?", "\u00c3\u0192\u00c2\u00b3":"?", "\u00c3\u0192\u00c2\u00ba":"?",
        "\u00c3\u0192\u00c2\u0081":"?", "\u00c3\u0192\u00e2\u20ac\u00b0":"\u00c3\u2030", "\u00c3\u0192\u00c2\u008d":"?", "\u00c3\u0192\u00e2\u20ac\u0153":"\u00c3\u201c", "\u00c3\u0192\u00c5\u00a1":"\u00c3\u0161",
        "\u00c3\u0192\u00c2\u00b1":"?", "\u00c3\u0192\u00e2\u20ac\u02dc":"\u00c3\u2018", "\u00c3\u0192\u00c2\u00bc":"?", "\u00c3\u0192\u00c5\u201c":"\u00c3\u0153",
        "\u00c3\u201a?":"?", "\u00c3\u201a?":"?", "\u00c3\u201a\u00c2\u00b0":"\u00c2\u00b0", "\u00c3\u201a\u00c2\u00ba":"\u00c2\u00ba", "\u00c3\u201a\u00c2\u00aa":"\u00c2\u00aa",
        "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u0153":"-", "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u009d":"-", "\u00c3\u00a2\u00e2\u201a\u00ac\u00cb\u0153":"'", "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u201e\u00a2":"'", "\u00c3\u00a2\u00e2\u201a\u00ac\u00c5\u201c":"\"", "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u009d":"\"",
        "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a6":"...", "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a2":"-", "\u00c3\u201a\u00c2\u00b7":"-",
        "\u00c3\u0192\u00c2\u0192\u00c3\u201a?":"?", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00a9":"?", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00ad":"?", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00b3":"?", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00ba":"?",
        "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00b1":"?", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00bc":"?", "\u00c3\u0192\u00c2\u0192\u00c3\u00a2\u00e2\u201a\u00ac\u00cb\u0153":"\u00c3\u2018",
        "Documentaci\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00b3n":"Documentaci?n", "T\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00a9cnico":"T?cnico",
        "Auditor\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00ada":"Auditor?a", "P\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00bablica":"P?blica", "M\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00a9tricas":"M?tricas",
        "due\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00b1os":"due?os", "acci\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00b3n":"acci?n", "decisi\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00b3n":"decisi?n"
    }
    for _ in range(4):
        before = text
        for bad, good in manual.items():
            text = text.replace(bad, good)
        if _rpv3_mojibake_score(text) > 0:
            try:
                candidate = text.encode("latin1", errors="strict").decode("utf-8", errors="strict")
                if _rpv3_mojibake_score(candidate) < _rpv3_mojibake_score(text):
                    text = candidate
            except Exception:
                pass
        if text == before:
            break
    replacements = {
        "\u00f0\u0178\u203a\u2019":"carrito", "\u00e2\u008f\u00b0":"horario", "\u00e2\u0153\u2026":"OK", "\u00e2\u009d\u0152":"NO", "\u00e2\u0161\u00a0\u00ef\u00b8\u008f":"ALERTA",
        "\u00e2\u0161\u00a0":"ALERTA", "\u00f0\u0178\u201c\u0152":"Nota", "\u00f0\u0178\u201c\u0160":"M?tricas", "\u00f0\u0178\u201d\u00a5":"Prioridad", "\u00f0\u0178\u0161\u20ac":"Escalar", "\u00f0\u0178\u2019\u00a1":"Idea"
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = _rpv3_unicodedata.normalize("NFC", text)
    return "".join(ch for ch in text if ch in ("\n", "\t") or ord(ch) >= 32)


def _rpv3_fix_obj(obj):
    if isinstance(obj, str):
        return _rpv3_fix_text(obj)
    if isinstance(obj, list):
        return [_rpv3_fix_obj(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_rpv3_fix_obj(x) for x in obj)
    if isinstance(obj, dict):
        return {_rpv3_fix_text(k) if isinstance(k, str) else k: _rpv3_fix_obj(v) for k, v in obj.items()}
    return obj


def _rpv3_clean_report_request(req, upload_to_drive=None):
    try:
        data = req.model_dump()
    except Exception:
        data = req.dict() if hasattr(req, "dict") else dict(req)
    data = _rpv3_fix_obj(data)
    data["documentation_folder_name"] = "Documentacion"
    data["technical_folder_name"] = "Tecnico"
    if upload_to_drive is not None:
        data["upload_to_drive"] = bool(upload_to_drive)
    return ReportPackageRequest(**data)


def _rpv3_pdf_safe(text):
    text = _rpv3_fix_text(text or "")
    return text.replace("\u00e2\u2020\u2019", "->").replace("\u00e2\u20ac\u201c", "-").replace("\u00e2\u20ac\u201d", "-")


def _rpv3_table_rows(lines, start):
    rows = []
    i = start
    while i < len(lines):
        line = lines[i].strip()
        if not (line.startswith("|") and line.endswith("|")):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not all(set(c) <= set("-: ") for c in cells):
            rows.append(cells)
        i += 1
    return rows, i


def _rpv3_markdown_to_pdf(path: _rpb_Path, title: str, md: str, company_name: str, executive: bool = False):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    except Exception as exc:
        raise RuntimeError(f"reportlab unavailable: {exc}")

    title = _rpv3_pdf_safe(title)
    company_name = _rpv3_pdf_safe(company_name)
    md = _rpv3_pdf_safe(md)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=1.35*cm,
        leftMargin=1.35*cm,
        topMargin=1.45*cm,
        bottomMargin=1.35*cm
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitleV3", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=30, textColor=colors.HexColor("#0f172a"), spaceAfter=18))
    styles.add(ParagraphStyle(name="CoverSubV3", parent=styles["BodyText"], fontName="Helvetica", fontSize=11, leading=15, textColor=colors.HexColor("#334155"), spaceAfter=6))
    styles.add(ParagraphStyle(name="H1V3", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=15 if not executive else 16, leading=20, textColor=colors.HexColor("#0f172a"), spaceBefore=12, spaceAfter=8))
    styles.add(ParagraphStyle(name="H2V3", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=colors.HexColor("#075985"), spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="H3V3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10.8, leading=14, textColor=colors.HexColor("#334155"), spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle(name="BodyV3", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.7 if not executive else 9.5, leading=12 if not executive else 13, textColor=colors.HexColor("#111827"), spaceAfter=4))
    styles.add(ParagraphStyle(name="SmallV3", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.1, leading=9.2, textColor=colors.HexColor("#111827")))

    story = []
    story.append(Spacer(1, 2.0*cm))
    story.append(Paragraph(_rpb_html.escape(title), styles["CoverTitleV3"]))
    story.append(Paragraph(f"Cliente: <b>{_rpb_html.escape(company_name)}</b>", styles["CoverSubV3"]))
    story.append(Paragraph(f"Tipo de documento: {'Resumen ejecutivo' if executive else 'Auditor\u00eda completa'}", styles["CoverSubV3"]))
    story.append(Paragraph(f"Generado: {_rpb_now_iso()}", styles["CoverSubV3"]))
    story.append(Spacer(1, 1.0*cm))
    story.append(Paragraph("Nota metodol\u00f3gica: este documento usa evidencia p\u00fablica visible. No representa m\u00e9tricas privadas ni performance interna sin accesos del cliente.", styles["BodyV3"]))
    story.append(PageBreak())

    sections = _rpb_sections_from_markdown(md)
    if sections:
        story.append(Paragraph("\u00cdndice", styles["H1V3"]))
        for idx, sec in enumerate(sections, start=1):
            story.append(Paragraph(f"{idx}. {_rpb_html.escape(_rpv3_pdf_safe(sec.get('title') or 'Secci\u00f3n'))}", styles["BodyV3"]))
        story.append(PageBreak())

    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = _rpv3_pdf_safe(lines[i].rstrip())
        if not line.strip():
            story.append(Spacer(1, 3))
            i += 1
            continue

        if line.startswith("|") and line.endswith("|"):
            rows, next_i = _rpv3_table_rows(lines, i)
            if rows:
                max_cols = max(len(r) for r in rows)
                norm = []
                for r in rows:
                    rr = r + [""] * (max_cols - len(r))
                    norm.append([Paragraph(_rpb_html.escape(_rpv3_pdf_safe(c)), styles["SmallV3"]) for c in rr])
                usable_width = A4[0] - 2.7*cm
                col_widths = [usable_width / max_cols] * max_cols
                tbl = Table(norm, colWidths=col_widths, repeatRows=1, splitByRow=1)
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 8))
                i = next_i
                continue

        escaped = _rpb_html.escape(line)
        escaped = _rpb_re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        if line.startswith("# "):
            story.append(Paragraph(_rpb_html.escape(line[2:]), styles["H1V3"]))
        elif line.startswith("## "):
            story.append(Paragraph(_rpb_html.escape(line[3:]), styles["H1V3"]))
        elif line.startswith("### "):
            story.append(Paragraph(_rpb_html.escape(line[4:]), styles["H2V3"]))
        elif _rpb_re.match(r"^\s*[-*]\s+", line):
            item = _rpb_re.sub(r"^\s*[-*]\s+", "- ", line)
            story.append(Paragraph(_rpb_html.escape(item), styles["BodyV3"]))
        else:
            story.append(Paragraph(escaped, styles["BodyV3"]))
        i += 1

    def _footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(1.35*cm, 0.75*cm, _rpv3_pdf_safe(f"{company_name} - {title}")[:95])
        canvas.drawRightString(A4[0] - 1.35*cm, 0.75*cm, f"P\u00e1gina {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


def _rpv3_extract_executive_md(full_md: str) -> str:
    full_md = _rpv3_fix_text(full_md or "")
    selected = _rpb_extract_executive_md(full_md)
    if len(selected.strip()) < 600:
        selected = "\n".join(full_md.splitlines()[:160])
    return selected


def _rpv3_build_html(req, report_id, created_at):
    req.markdown_report = _rpv3_fix_text(req.markdown_report or "")
    req.company_name = _rpv3_fix_text(req.company_name or "")
    req.report_title = _rpv3_fix_text(req.report_title or "")
    html = _rpb_build_interactive_html(req, report_id, created_at)
    html = _rpv3_fix_text(html)
    if '<meta charset="utf-8">' not in html.lower():
        html = html.replace("<head>", "<head>\n<meta charset=\"utf-8\">", 1)
    return html


@app.post("/deliverables/report-package-v3")
async def createReportPackageV3(request: ReportPackageRequest):
    clean_req = _rpv3_clean_report_request(request, upload_to_drive=request.upload_to_drive)
    local_req = _rpv3_clean_report_request(clean_req, upload_to_drive=False)

    old_pdf = globals().get("_rpb_markdown_to_pdf")
    old_html = globals().get("_rpb_build_interactive_html")
    globals()["_rpb_markdown_to_pdf"] = _rpv3_markdown_to_pdf
    globals()["_rpb_build_interactive_html"] = _rpv3_build_html
    try:
        result = _rpb_build_package(local_req)
    finally:
        if old_pdf:
            globals()["_rpb_markdown_to_pdf"] = old_pdf
        if old_html:
            globals()["_rpb_build_interactive_html"] = old_html

    result["collector"] = "report_package_builder_v3"
    result["version"] = APP_VERSION
    result["documentation_folder_name"] = "Documentacion"
    result["technical_folder_name"] = "Tecnico"
    result["notes"] = (result.get("notes") or []) + [
        "4H.2-D: contenido espa\u00f1ol normalizado a UTF-8/NFC y correcci\u00f3n b\u00e1sica de mojibake.",
        "PDF completo mejorado: portada, \u00edndice, estilos, tablas legibles y pie de p\u00e1gina.",
        "Carpetas Drive ASCII seguras: Documentacion/Tecnico."
    ]

    if clean_req.upload_to_drive:
        drive = await _rpb_upload_package_with_existing_drive(clean_req, result)
        result["drive"] = drive
        if drive.get("status") != "completed":
            result["status"] = "partial_completed"
            errors = result.get("errors") or []
            for err in drive.get("errors") or []:
                errors.append(f"drive_webapp upload: {err}")
            result["errors"] = errors

    return result


@app.post("/deliverables/report-package/regenerate-v3")
async def regenerateReportPackageV3(request: ReportPackageRegenerateRequest):
    req = ReportPackageRequest(
        company_name=request.company_name,
        report_title=request.report_title,
        markdown_report=request.markdown_report,
        executive_summary_markdown=request.executive_summary_markdown,
        evidence_payload=request.evidence_payload,
        social_metrics=request.social_metrics,
        drive_folder_name=request.drive_folder_name,
        documentation_folder_name="Documentacion",
        technical_folder_name="Tecnico",
        generate_interactive_html=request.regenerate_interactive_html,
        generate_full_pdf=request.regenerate_full_pdf,
        generate_executive_pdf=request.regenerate_executive_pdf,
        upload_to_drive=request.upload_to_drive,
        public_sharing=request.public_sharing,
        filename_prefix=request.filename_prefix
    )
    return await createReportPackageV3(req)

# ============================================================
# HOTFIX 4H.2-E - SAFE HTML BUILDER + REPORT PACKAGE V4
# ============================================================

def _rpv4_inline_md(text):
    text = _rpv3_fix_text("" if text is None else str(text))
    text = _rpb_html.escape(text, quote=True)
    text = _rpb_re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = _rpb_re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def _rpv4_markdown_to_basic_html(md):
    lines = (_rpv3_fix_text(md or "")).splitlines()
    out = []
    in_ul = False
    in_ol = False
    in_table = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def close_table():
        nonlocal in_table
        if in_table:
            out.append("</tbody></table></div>")
            in_table = False

    for raw_line in lines:
        line = raw_line.rstrip()

        if not line.strip():
            close_lists()
            close_table()
            out.append("<div class=\"space\"></div>")
            continue

        if line.startswith("|") and line.endswith("|"):
            close_lists()
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if not in_table:
                out.append('<div class="table-wrap"><table><tbody>')
                in_table = True
            out.append("<tr>" + "".join("<td>" + _rpv4_inline_md(c) + "</td>" for c in cells) + "</tr>")
            continue
        else:
            close_table()

        if line.startswith("### "):
            close_lists()
            out.append("<h3>" + _rpv4_inline_md(line[4:]) + "</h3>")
        elif line.startswith("## "):
            close_lists()
            out.append("<h2>" + _rpv4_inline_md(line[3:]) + "</h2>")
        elif line.startswith("# "):
            close_lists()
            out.append("<h1>" + _rpv4_inline_md(line[2:]) + "</h1>")
        elif _rpb_re.match(r"^\s*[-*]\s+", line):
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            item = _rpb_re.sub(r"^\s*[-*]\s+", "", line)
            out.append("<li>" + _rpv4_inline_md(item) + "</li>")
        elif _rpb_re.match(r"^\s*\d+\.\s+", line):
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            item = _rpb_re.sub(r"^\s*\d+\.\s+", "", line)
            out.append("<li>" + _rpv4_inline_md(item) + "</li>")
        else:
            close_lists()
            out.append("<p>" + _rpv4_inline_md(line) + "</p>")

    close_lists()
    close_table()
    return "\n".join(out)


def _rpv4_sections_from_markdown(md):
    md = _rpv3_fix_text(md or "")
    sections = []
    current_title = "Resumen"
    current_lines = []
    for line in md.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append({"title": current_title, "markdown": "\n".join(current_lines).strip()})
            current_title = line[3:].strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append({"title": current_title, "markdown": "\n".join(current_lines).strip()})
    return sections or [{"title": "Reporte", "markdown": md}]


def _rpv4_build_interactive_html(req, report_id, created_at):
    title = _rpv3_fix_text(req.report_title)
    company = _rpv3_fix_text(req.company_name)
    md = _rpv3_fix_text(req.markdown_report or "")
    sections = _rpv4_sections_from_markdown(md)

    nav_parts = []
    panel_parts = []

    for idx, sec in enumerate(sections):
        sid = "sec_" + str(idx)
        active = "active" if idx == 0 else ""
        sec_title = _rpv3_fix_text(sec.get("title") or ("Secci\u00f3n " + str(idx + 1)))
        nav_parts.append('<button class="tab ' + active + '" data-target="' + sid + '">' + _rpb_html.escape(sec_title, quote=True) + '</button>')
        panel_parts.append('<section id="' + sid + '" class="panel ' + active + '">' + _rpv4_markdown_to_basic_html(sec.get("markdown") or "") + '</section>')

    evidence_json = _rpb_html.escape(_rpb_json.dumps(_rpv3_fix_obj(req.evidence_payload or {}), ensure_ascii=False, indent=2), quote=True)
    metrics_json = _rpb_html.escape(_rpb_json.dumps(_rpv3_fix_obj(req.social_metrics or {}), ensure_ascii=False, indent=2), quote=True)

    head = [
        "<!doctype html>",
        '<html lang="es">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>" + _rpb_html.escape(title, quote=True) + " - " + _rpb_html.escape(company, quote=True) + "</title>",
        "<style>",
        ":root{--bg:#f8fafc;--ink:#0f172a;--muted:#64748b;--line:#cbd5e1;--primary:#0f172a;--accent:#0369a1;--soft:#e0f2fe;--card:#ffffff;}",
        "*{box-sizing:border-box;}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--ink);}",
        "header{padding:28px 32px;background:linear-gradient(135deg,#0f172a,#1e293b);color:white;position:sticky;top:0;z-index:5;box-shadow:0 4px 20px rgba(15,23,42,.22);}",
        "h1{margin:0 0 8px;font-size:30px;letter-spacing:-.02em}.meta{color:#cbd5e1;font-size:13px;display:flex;gap:14px;flex-wrap:wrap;}",
        ".layout{display:grid;grid-template-columns:300px 1fr;min-height:calc(100vh - 98px);}nav{border-right:1px solid var(--line);padding:18px;background:#fff;position:sticky;top:98px;height:calc(100vh - 98px);overflow:auto;}",
        ".tab{display:block;width:100%;text-align:left;margin:0 0 8px;padding:11px 12px;background:#f8fafc;color:var(--ink);border:1px solid var(--line);border-radius:12px;cursor:pointer;font-weight:600;}",
        ".tab.active,.tab:hover{border-color:var(--accent);background:var(--soft);}main{padding:24px;max-width:1360px;}",
        ".panel{display:none;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:26px;box-shadow:0 10px 30px rgba(15,23,42,.08);}.panel.active{display:block;}",
        "h2{color:var(--primary);margin-top:8px;border-bottom:2px solid var(--soft);padding-bottom:8px;}h3{color:var(--accent);margin-top:24px;}p,li{line-height:1.58}.space{height:8px;}",
        ".table-wrap{overflow:auto;margin:14px 0;border:1px solid var(--line);border-radius:12px;}table{border-collapse:collapse;width:100%;min-width:760px;font-size:14px;}td,th{border-bottom:1px solid var(--line);padding:10px;vertical-align:top;}tr:first-child td{font-weight:700;color:white;background:var(--primary);}",
        ".badge{display:inline-block;padding:4px 9px;border:1px solid var(--line);border-radius:999px;color:var(--accent);background:var(--soft);font-weight:700;}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:18px 0;}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px;box-shadow:0 6px 16px rgba(15,23,42,.06);}",
        "details{margin:14px 0;border:1px solid var(--line);border-radius:12px;padding:12px;background:#f8fafc;}summary{cursor:pointer;color:var(--accent);font-weight:700;}pre{white-space:pre-wrap;overflow:auto;max-height:480px;background:#0f172a;border-radius:12px;padding:12px;color:#e2e8f0;}footer{color:var(--muted);font-size:12px;padding:24px;text-align:center;}@media(max-width:900px){.layout{grid-template-columns:1fr;}nav{position:relative;top:0;height:auto;}}",
        "</style>",
        "</head>",
        "<body>",
        "<header>",
        "<h1>" + _rpb_html.escape(title, quote=True) + "</h1>",
        '<div class="meta"><span>Cliente: <strong>' + _rpb_html.escape(company, quote=True) + "</strong></span><span>Report ID: " + _rpb_html.escape(report_id, quote=True) + "</span><span>Creado: " + _rpb_html.escape(created_at, quote=True) + "</span><span>Tipo: " + _rpb_html.escape(_rpv3_fix_text(req.client_type or "auditor\u00eda p\u00fablica"), quote=True) + "</span></div>",
        "</header>",
        '<div class="layout">',
        "<nav>" + "".join(nav_parts) + "</nav>",
        "<main>",
        '<div class="cards"><div class="card"><span class="badge">Informe completo</span><p>Auditor\u00eda p\u00fablica integral con evidencia, diagn\u00f3stico y plan de acci\u00f3n.</p></div><div class="card"><span class="badge">Versi\u00f3n PDF</span><p>El PDF completo conserva el mismo contenido, sin interacci\u00f3n.</p></div><div class="card"><span class="badge">Resumen ejecutivo</span><p>Documento separado para due\u00f1os y gerencia.</p></div></div>',
        "".join(panel_parts),
        '<section class="panel active" style="display:block;margin-top:18px;"><h2>Anexos t\u00e9cnicos</h2><details><summary>Evidencia t\u00e9cnica JSON</summary><pre>' + evidence_json + '</pre></details><details><summary>M\u00e9tricas sociales JSON</summary><pre>' + metrics_json + '</pre></details></section>',
        "</main></div>",
        "<footer>Generado por Marketing Auditor. Las m\u00e9tricas p\u00fablicas son parciales y no representan performance interna.</footer>",
        "<script>document.querySelectorAll('.tab').forEach(function(btn){btn.addEventListener('click',function(){document.querySelectorAll('.tab').forEach(function(b){b.classList.remove('active');});document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active');});btn.classList.add('active');var target=document.getElementById(btn.dataset.target);if(target)target.classList.add('active');});});</script>",
        "</body></html>"
    ]
    return "\n".join(head)


def _rpv4_build_package(req):
    req = _rpv3_request_clean_copy(req)
    created_at = _rpb_now_iso()
    report_id = _rpb_report_id(req.company_name)
    prefix = _rpb_slug(req.filename_prefix or req.company_name)
    workdir = _RPB_ROOT / report_id
    workdir.mkdir(parents=True, exist_ok=True)

    technical_dir = workdir / "tecnico"
    technical_dir.mkdir(exist_ok=True)

    files = {}
    errors = []

    markdown_report = _rpv3_fix_text(req.markdown_report or "")
    evidence_payload = _rpv3_fix_obj(req.evidence_payload or {})
    social_metrics = _rpv3_fix_obj(req.social_metrics or {})

    md_path = technical_dir / f"04_{prefix}_reporte_fuente.md"
    json_path = technical_dir / f"05_{prefix}_evidencia_tecnica.json"

    md_path.write_text(markdown_report, encoding="utf-8")
    json_payload = {
        "report_id": report_id,
        "company_name": _rpv3_fix_text(req.company_name),
        "report_title": _rpv3_fix_text(req.report_title),
        "client_type": _rpv3_fix_text(req.client_type),
        "created_at": created_at,
        "evidence_payload": evidence_payload,
        "social_metrics": social_metrics,
        "encoding_policy": "utf8_nfc_mojibake_fixed",
        "folder_policy": "ascii_safe_drive_folder_names",
        "html_policy": "safe_non_recursive_renderer_v4"
    }
    json_path.write_text(_rpb_json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    files["markdown_source"] = {"status": "created", "path": str(md_path)}
    files["evidence_json"] = {"status": "created", "path": str(json_path)}

    html_path = workdir / f"01_{prefix}_auditoria_interactiva_completa.html"
    full_pdf_path = workdir / f"02_{prefix}_auditoria_completa.pdf"
    executive_pdf_path = workdir / f"03_{prefix}_resumen_ejecutivo_duenos.pdf"

    if req.generate_interactive_html:
        try:
            html = _rpv4_build_interactive_html(req, report_id, created_at)
            html_path.write_text(html, encoding="utf-8")
            files["interactive_html"] = {"status": "created", "path": str(html_path)}
        except Exception as exc:
            files["interactive_html"] = {"status": "failed", "reason": str(exc), "regenerable": True}
            errors.append(f"interactive_html failed: {exc}")

    if req.generate_full_pdf:
        try:
            _rpv3_markdown_to_pdf(full_pdf_path, f"{req.report_title} - Completa", markdown_report, req.company_name, executive=False)
            files["full_pdf"] = {"status": "created", "path": str(full_pdf_path)}
        except Exception as exc:
            files["full_pdf"] = {"status": "failed", "reason": str(exc), "regenerable": True}
            errors.append(f"full_pdf failed: {exc}")

    if req.generate_executive_pdf:
        try:
            exec_md = _rpv4_executive_md_4h3c(markdown_report, req.executive_summary_markdown)
            _rpv3_markdown_to_pdf(executive_pdf_path, f"{req.report_title} - Resumen Ejecutivo", exec_md, req.company_name, executive=True)
            files["executive_pdf"] = {"status": "created", "path": str(executive_pdf_path)}
        except Exception as exc:
            files["executive_pdf"] = {"status": "failed", "reason": str(exc), "regenerable": True}
            errors.append(f"executive_pdf failed: {exc}")

    base = _rpb_public_base_url()
    local_urls = {
        "interactive_html_url": f"{base}/deliverables/report-package/{report_id}/html",
        "full_pdf_url": f"{base}/deliverables/report-package/{report_id}/pdf-full",
        "executive_pdf_url": f"{base}/deliverables/report-package/{report_id}/pdf-executive",
        "markdown_source_url": f"{base}/deliverables/report-package/{report_id}/md",
        "evidence_json_url": f"{base}/deliverables/report-package/{report_id}/json"
    }

    return {
        "collector": "report_package_builder_v4",
        "version": APP_VERSION,
        "status": "completed" if not errors else "partial_completed",
        "report_id": report_id,
        "company_name": _rpv3_fix_text(req.company_name),
        "report_title": _rpv3_fix_text(req.report_title),
        "created_at": created_at,
        "documentation_folder_name": req.documentation_folder_name,
        "technical_folder_name": req.technical_folder_name,
        "local_urls": local_urls,
        "files": files,
        "drive": {
            "requested": bool(req.upload_to_drive),
            "status": "not_requested",
            "integration": "existing_drive_webapp"
        },
        "errors": errors,
        "regeneration_available": True,
        "notes": [
            "4H.2-E: HTML usa renderer independiente no recursivo.",
            "PDF completo y ejecutivo se mantienen desde el renderer mejorado v3.",
            "Contenido espa\u00f1ol normalizado y carpetas Drive ASCII seguras."
        ]
    }


@app.post("/deliverables/report-package-v4")
async def createReportPackageV4(request: ReportPackageRequest):
    clean_req = _rpv3_request_clean_copy(request)
    local_req = _rpb_model_copy_no_drive(clean_req)
    result = _rpv4_build_package(local_req)
    result["version"] = APP_VERSION

    if clean_req.upload_to_drive:
        drive = await _rpb_upload_package_with_existing_drive(clean_req, result)
        result["drive"] = drive
        if drive.get("status") != "completed":
            result["status"] = "partial_completed"
            existing_errors = result.get("errors") or []
            for err in drive.get("errors") or []:
                existing_errors.append(f"drive_webapp upload: {err}")
            result["errors"] = existing_errors

    return result


@app.post("/deliverables/report-package/regenerate-v4")
async def regenerateReportPackageV4(request: ReportPackageRegenerateRequest):
    req = ReportPackageRequest(
        company_name=request.company_name,
        report_title=request.report_title,
        markdown_report=request.markdown_report,
        executive_summary_markdown=request.executive_summary_markdown,
        evidence_payload=request.evidence_payload,
        social_metrics=request.social_metrics,
        drive_folder_name=request.drive_folder_name,
        documentation_folder_name="Documentacion",
        technical_folder_name="Tecnico",
        generate_interactive_html=request.regenerate_interactive_html,
        generate_full_pdf=request.regenerate_full_pdf,
        generate_executive_pdf=request.regenerate_executive_pdf,
        upload_to_drive=request.upload_to_drive,
        public_sharing=request.public_sharing,
        filename_prefix=request.filename_prefix
    )
    return await createReportPackageV4(req)

# ============================================================
# HOTFIX 4H.2-F - V4 COMPATIBILITY HELPERS
# ============================================================

def _rpv3_fix_text(value):
    if not isinstance(value, str):
        return value
    text = value
    replacements = {
        "\u00c3\u0192?": "?", "\u00c3\u0192\u00c2\u00a9": "?", "\u00c3\u0192\u00c2\u00ad": "?", "\u00c3\u0192\u00c2\u00b3": "?", "\u00c3\u0192\u00c2\u00ba": "?",
        "\u00c3\u0192\u00c2\u0081": "?", "\u00c3\u0192\u00e2\u20ac\u00b0": "\u00c3\u2030", "\u00c3\u0192\u00c2\u008d": "?", "\u00c3\u0192\u00e2\u20ac\u0153": "\u00c3\u201c", "\u00c3\u0192\u00c5\u00a1": "\u00c3\u0161",
        "\u00c3\u0192\u00c2\u00b1": "?", "\u00c3\u0192\u00e2\u20ac\u02dc": "\u00c3\u2018", "\u00c3\u0192\u00c2\u00bc": "?", "\u00c3\u0192\u00c5\u201c": "\u00c3\u0153",
        "\u00c3\u201a?": "?", "\u00c3\u201a?": "?", "\u00c3\u201a\u00c2\u00b0": "\u00c2\u00b0",
        "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u0153": "-", "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u009d": "-", "\u00c3\u00a2\u00e2\u201a\u00ac\u00cb\u0153": "'", "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u201e\u00a2": "'", "\u00c3\u00a2\u00e2\u201a\u00ac\u00c5\u201c": '"', "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u009d": '"',
        "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a6": "...", "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a2": "-",
        "\u00c3\u0192\u00c2\u0192\u00c3\u201a?": "?", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00a9": "?", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00ad": "?", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00b3": "?", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00ba": "?",
        "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00b1": "?", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00bc": "?",
        "Documentaci\u00c3\u0192\u00c2\u00b3n": "Documentaci?n", "T\u00c3\u0192\u00c2\u00a9cnico": "T?cnico",
        "Auditor\u00c3\u0192\u00c2\u00ada": "Auditor?a", "P\u00c3\u0192\u00c2\u00bablica": "P?blica", "M\u00c3\u0192\u00c2\u00a9tricas": "M?tricas", "due\u00c3\u0192\u00c2\u00b1os": "due?os"
    }
    for _ in range(3):
        before = text
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        if text == before:
            break
    symbol_replacements = {
        "\u00f0\u0178\u203a\u2019": "carrito", "\u00e2\u008f\u00b0": "horario", "\u00e2\u0153\u2026": "OK", "\u00e2\u009d\u0152": "NO",
        "\u00e2\u0161\u00a0\u00ef\u00b8\u008f": "ALERTA", "\u00e2\u0161\u00a0": "ALERTA", "\u00f0\u0178\u201c\u0152": "Nota", "\u00f0\u0178\u201c\u0160": "M?tricas",
        "\u00f0\u0178\u201d\u00a5": "Prioridad", "\u00f0\u0178\u0161\u20ac": "Escalar", "\u00f0\u0178\u2019\u00a1": "Idea"
    }
    for bad, good in symbol_replacements.items():
        text = text.replace(bad, good)
    return text


def _rpv3_fix_obj(obj):
    if isinstance(obj, str):
        return _rpv3_fix_text(obj)
    if isinstance(obj, list):
        return [_rpv3_fix_obj(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_rpv3_fix_obj(x) for x in obj)
    if isinstance(obj, dict):
        fixed = {}
        for k, v in obj.items():
            fixed_key = _rpv3_fix_text(k) if isinstance(k, str) else k
            fixed[fixed_key] = _rpv3_fix_obj(v)
        return fixed
    return obj


def _rpv3_request_clean_copy(req):
    try:
        data = req.model_dump()
    except Exception:
        try:
            data = req.dict()
        except Exception:
            data = dict(req)

    data = _rpv3_fix_obj(data)
    data["documentation_folder_name"] = "Documentacion"
    data["technical_folder_name"] = "Tecnico"

    return ReportPackageRequest(**data)


def _rpv3_extract_executive_md(full_md):
    full_md = _rpv3_fix_text(full_md or "")
    try:
        return _rpb_extract_executive_md(full_md)
    except Exception:
        return "\n".join(full_md.splitlines()[:160])


def _rpv3_markdown_to_pdf(path, title, md, company_name, executive=False):
    title = _rpv3_fix_text(title)
    md = _rpv3_fix_text(md or "")
    company_name = _rpv3_fix_text(company_name)
    return _rpb_markdown_to_pdf(path, title, md, company_name, executive=executive)

# ============================================================
# MICRO PATCH 4H.3-A - AUDIT RUN STATE / COLLECTION VISIBILITY
# ============================================================

from datetime import datetime as _ars_datetime, timezone as _ars_timezone
from uuid import uuid4 as _ars_uuid4
from pydantic import BaseModel as _ARSBaseModel


_AUDIT_RUN_STATE_STORE = {}


_AUDIT_DEFAULT_MODULES = [
    {
        "module": "api_status",
        "label": "Estado backend",
        "category": "system",
        "endpoint": "GET /api/status",
        "required_for": ["complete_audit", "partial_audit"],
        "blocking_if_failed": True,
    },
    {
        "module": "collector_config",
        "label": "Configuraci\u00f3n collectors",
        "category": "system",
        "endpoint": "GET /debug/collector-config",
        "required_for": ["complete_audit"],
        "blocking_if_failed": False,
    },
    {
        "module": "public_presence_compact",
        "label": "Presencia p\u00fablica compacta",
        "category": "public_presence",
        "endpoint": "POST /collect/public-presence-compact",
        "required_for": ["complete_audit", "partial_audit"],
        "blocking_if_failed": False,
    },
    {
        "module": "text_report",
        "label": "TXT fuente de presencia p\u00fablica",
        "category": "public_presence",
        "endpoint": "GET /deliverables/text/{report_id}.txt",
        "required_for": ["complete_audit"],
        "blocking_if_failed": False,
    },
    {
        "module": "visual_site",
        "label": "Auditor\u00eda visual del sitio",
        "category": "website",
        "endpoint": "POST /audit/visual-site",
        "required_for": ["complete_audit"],
        "blocking_if_failed": False,
    },
    {
        "module": "instagram_profile_metrics",
        "label": "Instagram perfil p\u00fablico",
        "category": "instagram",
        "endpoint": "POST /audit/instagram-profile-metrics",
        "required_for": ["complete_audit", "partial_audit"],
        "blocking_if_failed": False,
    },
    {
        "module": "instagram_posts_compact_v2",
        "label": "Instagram publicaciones compactas",
        "category": "instagram",
        "endpoint": "POST /audit/instagram-posts-by-url-compact-v2",
        "required_for": ["complete_audit"],
        "blocking_if_failed": False,
    },
    {
        "module": "social_public_averages_instagram",
        "label": "Promedios p\u00fablicos visibles de Instagram",
        "category": "instagram",
        "endpoint": "POST /audit/social-public-averages",
        "required_for": ["complete_audit"],
        "blocking_if_failed": False,
    },
    {
        "module": "facebook_public",
        "label": "Facebook p\u00fablico",
        "category": "facebook",
        "endpoint": "POST /audit/social-public",
        "required_for": ["complete_audit"],
        "blocking_if_failed": False,
    },
    {
        "module": "linkedin_public",
        "label": "LinkedIn p\u00fablico",
        "category": "linkedin",
        "endpoint": "POST /audit/social-public",
        "required_for": ["complete_audit"],
        "blocking_if_failed": False,
    },
    {
        "module": "marketplace_manual_evidence",
        "label": "Marketplace / Mercado Libre evidencia",
        "category": "marketplace",
        "endpoint": "manual_or_external_evidence",
        "required_for": ["complete_audit"],
        "blocking_if_failed": False,
    },
    {
        "module": "tracking_internal_access",
        "label": "Tracking / accesos internos",
        "category": "internal_access",
        "endpoint": "owner_access_required",
        "required_for": ["complete_audit"],
        "blocking_if_failed": False,
        "default_status": "requires_access",
    },
    {
        "module": "report_package_v4",
        "label": "Paquete documental final",
        "category": "deliverables",
        "endpoint": "POST /deliverables/report-package-v4",
        "required_for": ["deliverable"],
        "blocking_if_failed": False,
    },
]


_AUDIT_VALID_STATUSES = {
    "pending",
    "running",
    "completed",
    "partial",
    "failed",
    "skipped",
    "requires_access",
    "not_available",
    "not_calculable",
}


class AuditRunStartRequest(_ARSBaseModel):
    company_name: str | None = None
    assets: dict | None = None
    required_modules: list[str] | None = None
    notes: list[str] | None = None


class AuditRunModuleUpdateRequest(_ARSBaseModel):
    run_id: str
    module: str
    status: str
    endpoint: str | None = None
    evidence: dict | None = None
    limitations: list[str] | None = None
    drive_urls: dict | None = None
    next_action: str | None = None
    confidence: str | None = None


class AuditRunBulkUpdateRequest(_ARSBaseModel):
    run_id: str
    updates: list[AuditRunModuleUpdateRequest]


class AuditRunReadinessRequest(_ARSBaseModel):
    run_id: str


def _ars_now():
    return _ars_datetime.now(_ars_timezone.utc).isoformat()


def _ars_slug(value):
    text = str(value or "audit").strip().lower()
    out = []
    for ch in text:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "audit"


def _ars_initial_modules(required_modules=None):
    wanted = set(required_modules or [])
    modules = {}
    for item in _AUDIT_DEFAULT_MODULES:
        module_name = item["module"]
        status = item.get("default_status") or "pending"
        if wanted and module_name not in wanted and "system" not in item.get("category", ""):
            status = "skipped"
        modules[module_name] = {
            "module": module_name,
            "label": item.get("label"),
            "category": item.get("category"),
            "endpoint": item.get("endpoint"),
            "status": status,
            "required_for": item.get("required_for", []),
            "blocking_if_failed": bool(item.get("blocking_if_failed", False)),
            "evidence": {},
            "limitations": [],
            "drive_urls": {},
            "next_action": None,
            "confidence": None,
            "updated_at": None,
        }
    return modules


def _ars_compute_readiness(run):
    modules = run.get("modules", {})

    completed_like = {"completed", "partial"}
    evidence_modules = [
        "public_presence_compact",
        "visual_site",
        "instagram_profile_metrics",
        "instagram_posts_compact_v2",
        "social_public_averages_instagram",
        "facebook_public",
        "linkedin_public",
        "marketplace_manual_evidence",
    ]

    system_blockers = []
    for name, mod in modules.items():
        if mod.get("blocking_if_failed") and mod.get("status") in ("failed", "not_available"):
            system_blockers.append(name)

    collected_evidence = [
        name for name in evidence_modules
        if modules.get(name, {}).get("status") in completed_like
    ]

    failed_modules = [
        name for name, mod in modules.items()
        if mod.get("status") == "failed"
    ]

    pending_modules = [
        name for name, mod in modules.items()
        if mod.get("status") in ("pending", "running")
    ]

    requires_access_modules = [
        name for name, mod in modules.items()
        if mod.get("status") == "requires_access"
    ]

    instagram_profile_ok = modules.get("instagram_profile_metrics", {}).get("status") in completed_like
    instagram_posts_ok = modules.get("instagram_posts_compact_v2", {}).get("status") in completed_like
    instagram_averages_ok = modules.get("social_public_averages_instagram", {}).get("status") in completed_like

    social_state = "not_started"
    if instagram_profile_ok and instagram_posts_ok and instagram_averages_ok:
        social_state = "instagram_public_metrics_ready"
    elif instagram_profile_ok and not instagram_posts_ok:
        social_state = "instagram_profile_ready_posts_pending"
    elif instagram_profile_ok and instagram_posts_ok and not instagram_averages_ok:
        social_state = "instagram_posts_ready_averages_pending"
    elif any(modules.get(x, {}).get("status") == "failed" for x in ["instagram_profile_metrics", "instagram_posts_compact_v2", "social_public_averages_instagram"]):
        social_state = "instagram_partial_or_failed"

    if system_blockers:
        readiness = "blocked"
        can_generate = False
        reason = "Hay bloqueadores t\u00e9cnicos del sistema."
    elif len(collected_evidence) >= 3:
        readiness = "ready_for_complete_or_strong_partial_report"
        can_generate = True
        reason = "Hay suficiente evidencia p\u00fablica recolectada para generar auditor\u00eda con limitaciones declaradas."
    elif len(collected_evidence) >= 1:
        readiness = "ready_for_partial_report"
        can_generate = True
        reason = "Hay evidencia p\u00fablica m\u00ednima; el reporte debe marcar limitaciones y m\u00f3dulos pendientes."
    else:
        readiness = "not_ready"
        can_generate = False
        reason = "No hay evidencia p\u00fablica suficiente para generar una auditor\u00eda defendible."

    next_actions = []
    priority_order = [
        "api_status",
        "collector_config",
        "public_presence_compact",
        "text_report",
        "visual_site",
        "instagram_profile_metrics",
        "instagram_posts_compact_v2",
        "social_public_averages_instagram",
        "facebook_public",
        "linkedin_public",
        "marketplace_manual_evidence",
        "report_package_v4",
    ]

    for name in priority_order:
        mod = modules.get(name)
        if not mod:
            continue
        if mod.get("status") in ("pending", "running", "failed"):
            next_actions.append({
                "module": name,
                "status": mod.get("status"),
                "endpoint": mod.get("endpoint"),
                "action": mod.get("next_action") or f"Ejecutar o corregir {mod.get('label')}",
            })

    return {
        "readiness": readiness,
        "can_generate_report": can_generate,
        "reason": reason,
        "social_collection_state": social_state,
        "completed_or_partial_modules": collected_evidence,
        "failed_modules": failed_modules,
        "pending_modules": pending_modules,
        "requires_access_modules": requires_access_modules,
        "system_blockers": system_blockers,
        "next_actions": next_actions[:8],
        "guardrail": "Si can_generate_report=true pero hay m\u00f3dulos pending/failed/requires_access, el informe final debe marcar esos puntos como limitaciones y no inventar m\u00e9tricas privadas.",
    }


def _ars_public_run(run):
    readiness = _ars_compute_readiness(run)
    summary = {
        "total_modules": len(run.get("modules", {})),
        "completed": len([m for m in run.get("modules", {}).values() if m.get("status") == "completed"]),
        "partial": len([m for m in run.get("modules", {}).values() if m.get("status") == "partial"]),
        "failed": len([m for m in run.get("modules", {}).values() if m.get("status") == "failed"]),
        "pending": len([m for m in run.get("modules", {}).values() if m.get("status") == "pending"]),
        "running": len([m for m in run.get("modules", {}).values() if m.get("status") == "running"]),
        "requires_access": len([m for m in run.get("modules", {}).values() if m.get("status") == "requires_access"]),
        "skipped": len([m for m in run.get("modules", {}).values() if m.get("status") == "skipped"]),
    }
    return {
        **run,
        "summary": summary,
        "readiness": readiness,
    }


@app.post("/audit/run-state/start")
async def startAuditRunState(request: AuditRunStartRequest):
    run_id = f"{_ars_slug(request.company_name)}_{_ars_datetime.now(_ars_timezone.utc).strftime('%Y%m%d_%H%M%S')}_{str(_ars_uuid4())[:8]}"
    run = {
        "run_id": run_id,
        "company_name": request.company_name,
        "assets": request.assets or {},
        "status": "running",
        "created_at": _ars_now(),
        "updated_at": _ars_now(),
        "notes": request.notes or [],
        "modules": _ars_initial_modules(request.required_modules),
    }
    _AUDIT_RUN_STATE_STORE[run_id] = run
    return _ars_public_run(run)


@app.post("/audit/run-state/update")
async def updateAuditRunState(request: AuditRunModuleUpdateRequest):
    run = _AUDIT_RUN_STATE_STORE.get(request.run_id)
    if not run:
        return {
            "status": "not_found",
            "reason": "run_id not found",
            "run_id": request.run_id,
        }

    status = (request.status or "").strip().lower()
    if status not in _AUDIT_VALID_STATUSES:
        return {
            "status": "invalid_status",
            "valid_statuses": sorted(list(_AUDIT_VALID_STATUSES)),
            "received": request.status,
        }

    modules = run.setdefault("modules", {})
    mod = modules.get(request.module) or {
        "module": request.module,
        "label": request.module,
        "category": "custom",
        "endpoint": request.endpoint,
        "required_for": [],
        "blocking_if_failed": False,
        "evidence": {},
        "limitations": [],
        "drive_urls": {},
    }

    mod["status"] = status
    if request.endpoint:
        mod["endpoint"] = request.endpoint
    if request.evidence is not None:
        mod["evidence"] = request.evidence
    if request.limitations is not None:
        mod["limitations"] = request.limitations
    if request.drive_urls is not None:
        mod["drive_urls"] = request.drive_urls
    if request.next_action is not None:
        mod["next_action"] = request.next_action
    if request.confidence is not None:
        mod["confidence"] = request.confidence

    mod["updated_at"] = _ars_now()
    modules[request.module] = mod
    run["updated_at"] = _ars_now()

    if request.module == "report_package_v4" and status == "completed":
        run["status"] = "completed"

    return _ars_public_run(run)


@app.post("/audit/run-state/bulk-update")
async def bulkUpdateAuditRunState(request: AuditRunBulkUpdateRequest):
    results = []
    for update in request.updates:
        update.run_id = request.run_id
        results.append(await updateAuditRunState(update))
    run = _AUDIT_RUN_STATE_STORE.get(request.run_id)
    if not run:
        return {"status": "not_found", "run_id": request.run_id}
    return _ars_public_run(run)


@app.get("/audit/run-state/{run_id}")
async def getAuditRunState(run_id: str):
    run = _AUDIT_RUN_STATE_STORE.get(run_id)
    if not run:
        return {
            "status": "not_found",
            "run_id": run_id,
            "reason": "No audit run state exists for this run_id.",
        }
    return _ars_public_run(run)


@app.post("/audit/run-state/readiness")
async def getAuditRunReadiness(request: AuditRunReadinessRequest):
    run = _AUDIT_RUN_STATE_STORE.get(request.run_id)
    if not run:
        return {
            "status": "not_found",
            "run_id": request.run_id,
            "reason": "No audit run state exists for this run_id.",
        }
    return {
        "run_id": request.run_id,
        "company_name": run.get("company_name"),
        "status": run.get("status"),
        "updated_at": run.get("updated_at"),
        "readiness": _ars_compute_readiness(run),
        "summary": _ars_public_run(run).get("summary"),
    }

# ============================================================
# HOTFIX 4H.3-B - PDF TABLE CONTRAST
# ============================================================

def _rpv3_pdf_inline_4h3b(text):
    text = _rpv3_fix_text("" if text is None else str(text))
    text = _rpb_html.escape(text, quote=True)
    text = _rpb_re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = _rpb_re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    return text


def _rpv3_markdown_to_pdf(path, title, md, company_name, executive=False):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    except Exception as exc:
        raise RuntimeError(f"reportlab unavailable: {exc}")

    title = _rpv3_fix_text(title)
    company_name = _rpv3_fix_text(company_name)
    md = _rpv3_fix_text(md or "")

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=1.25 * cm,
        leftMargin=1.25 * cm,
        topMargin=1.35 * cm,
        bottomMargin=1.25 * cm
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="CoverTitle4H3B",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=27,
        textColor=colors.HexColor("#111827"),
        spaceAfter=18
    ))

    styles.add(ParagraphStyle(
        name="CoverSub4H3B",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#111827"),
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        name="H1_4H3B",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15 if not executive else 16,
        leading=19,
        textColor=colors.HexColor("#111827"),
        spaceBefore=12,
        spaceAfter=8
    ))

    styles.add(ParagraphStyle(
        name="H2_4H3B",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#075985"),
        spaceBefore=10,
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        name="H3_4H3B",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceBefore=8,
        spaceAfter=4
    ))

    styles.add(ParagraphStyle(
        name="Body4H3B",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.4 if not executive else 9.4,
        leading=11.4 if not executive else 12.8,
        textColor=colors.HexColor("#111827"),
        spaceAfter=4
    ))

    styles.add(ParagraphStyle(
        name="Small4H3B",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=6.7,
        leading=8.6,
        textColor=colors.HexColor("#111827")
    ))

    styles.add(ParagraphStyle(
        name="SmallHeader4H3B",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=6.8,
        leading=8.8,
        textColor=colors.white
    ))

    story = []

    story.append(Spacer(1, 1.8 * cm))
    story.append(Paragraph(_rpv3_pdf_inline_4h3b(title), styles["CoverTitle4H3B"]))
    story.append(Paragraph("Cliente: <b>" + _rpb_html.escape(company_name, quote=True) + "</b>", styles["CoverSub4H3B"]))
    story.append(Paragraph("Tipo de documento: " + ("Resumen ejecutivo" if executive else "Auditor\u00eda completa"), styles["CoverSub4H3B"]))
    story.append(Paragraph("Generado: " + _rpb_html.escape(_rpb_now_iso(), quote=True), styles["CoverSub4H3B"]))
    story.append(Spacer(1, 0.7 * cm))
    story.append(Paragraph(
        "Nota metodol\u00f3gica: este documento usa evidencia p\u00fablica visible y separa hechos, inferencias razonadas y datos que requieren acceso interno.",
        styles["Body4H3B"]
    ))
    story.append(PageBreak())

    try:
        sections = _rpb_sections_from_markdown(md)
    except Exception:
        sections = []

    if sections:
        story.append(Paragraph("\u00cdndice", styles["H1_4H3B"]))
        for idx, sec in enumerate(sections, start=1):
            story.append(Paragraph(str(idx) + ". " + _rpv3_pdf_inline_4h3b(sec.get("title") or "Secci\u00f3n"), styles["Body4H3B"]))
        story.append(PageBreak())

    lines = md.splitlines()
    i = 0

    def read_table(start_index):
        rows = []
        j = start_index
        while j < len(lines):
            ln = lines[j].strip()
            if not (ln.startswith("|") and ln.endswith("|")):
                break
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
            j += 1
        return rows, j

    while i < len(lines):
        line = lines[i].rstrip()
        clean = _rpv3_fix_text(line)

        if not clean.strip():
            story.append(Spacer(1, 3))
            i += 1
            continue

        if clean.startswith("|") and clean.endswith("|"):
            rows, next_i = read_table(i)
            if rows:
                max_cols = max(len(r) for r in rows)
                normalized = []
                for ridx, r in enumerate(rows):
                    rr = r + [""] * (max_cols - len(r))
                    row_style = styles["SmallHeader4H3B"] if ridx == 0 else styles["Small4H3B"]
                    normalized.append([Paragraph(_rpv3_pdf_inline_4h3b(c), row_style) for c in rr])

                usable_width = A4[0] - 2.5 * cm
                col_widths = [usable_width / max_cols] * max_cols

                tbl = Table(normalized, colWidths=col_widths, repeatRows=1, splitByRow=1)
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 8))
                i = next_i
                continue

        if clean.startswith("# "):
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean[2:]), styles["H1_4H3B"]))
        elif clean.startswith("## "):
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean[3:]), styles["H1_4H3B"]))
        elif clean.startswith("### "):
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean[4:]), styles["H2_4H3B"]))
        elif clean.startswith("#### "):
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean[5:]), styles["H3_4H3B"]))
        elif _rpb_re.match(r"^\s*[-*]\s+", clean):
            item = _rpb_re.sub(r"^\s*[-*]\s+", "- ", clean)
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(item), styles["Body4H3B"]))
        elif _rpb_re.match(r"^\s*\d+\.\s+", clean):
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean), styles["Body4H3B"]))
        elif clean.strip() == "---":
            story.append(Spacer(1, 8))
        else:
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean), styles["Body4H3B"]))

        i += 1

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(1.25 * cm, 0.65 * cm, _rpv3_fix_text(company_name + " - " + title)[:120])
        canvas.drawRightString(A4[0] - 1.25 * cm, 0.65 * cm, "P\u00e1gina " + str(doc_obj.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)

# ============================================================
# HOTFIX 4H.3-C - HTML ENCODING + EXECUTIVE SUMMARY
# ============================================================

def _rpv3_fix_text(value):
    if not isinstance(value, str):
        return value
    text = value
    replacements = {
        "\u00c3\u00a1": "\u00e1", "\u00c3\u00a9": "\u00e9", "\u00c3\u00ad": "\u00ed", "\u00c3\u00b3": "\u00f3", "\u00c3\u00ba": "\u00fa",
        "\u00c3\u00b1": "\u00f1", "\u00c3\u0091": "\u00d1", "\u00c3\u00bc": "\u00fc", "\u00c3\u009c": "\u00dc",
        "\u00c2\u00bf": "\u00bf", "\u00c2\u00a1": "\u00a1", "\u00c2\u00b0": "\u00b0",
        "\u00e2\u0080\u0093": "-", "\u00e2\u0080\u0094": "-", "\u00e2\u0080\u0098": "'", "\u00e2\u0080\u0099": "'",
        "\u00e2\u0080\u009c": '"', "\u00e2\u0080\u009d": '"', "\u00e2\u0080\u00a6": "...", "\u00e2\u0080\u00a2": "-",
        "Auditor\u00c3\u00ada": "Auditor\u00eda",
        "auditor\u00c3\u00ada": "auditor\u00eda",
        "p\u00c3\u00bablica": "p\u00fablica",
        "P\u00c3\u00bablica": "P\u00fablica",
        "M\u00c3\u00a9tricas": "M\u00e9tricas",
        "m\u00c3\u00a9tricas": "m\u00e9tricas",
        "t\u00c3\u00a9cnicos": "t\u00e9cnicos",
        "t\u00c3\u00a9cnica": "t\u00e9cnica",
        "due\u00c3\u00b1os": "due\u00f1os",
        "Versi\u00c3\u00b3n": "Versi\u00f3n",
        "interacci\u00c3\u00b3n": "interacci\u00f3n",
        "diagn\u00c3\u00b3stico": "diagn\u00f3stico",
        "acci\u00c3\u00b3n": "acci\u00f3n",
        "Documentaci\u00c3\u00b3n": "Documentaci\u00f3n",
        "T\u00c3\u00a9cnico": "T\u00e9cnico",
    }
    for _ in range(5):
        before = text
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        if text == before:
            break
    return text


def _rpv3_fix_obj(obj):
    if isinstance(obj, str):
        return _rpv3_fix_text(obj)
    if isinstance(obj, list):
        return [_rpv3_fix_obj(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_rpv3_fix_obj(x) for x in obj)
    if isinstance(obj, dict):
        return {(_rpv3_fix_text(k) if isinstance(k, str) else k): _rpv3_fix_obj(v) for k, v in obj.items()}
    return obj


def _rpv4_section_by_title_4h3c(full_md, needles):
    full_md = _rpv3_fix_text(full_md or "")
    sections = _rpv4_sections_from_markdown(full_md)
    for sec in sections:
        title = _rpv3_fix_text(sec.get("title") or "").lower()
        if any(n.lower() in title for n in needles):
            return _rpv3_fix_text(sec.get("markdown") or "").strip()
    return ""


def _rpv4_take_lines_4h3c(text, max_lines=55):
    lines = [ln for ln in (_rpv3_fix_text(text or "")).splitlines() if ln.strip()]
    return "\n".join(lines[:max_lines]).strip()


def _rpv4_executive_md_4h3c(full_md, provided=None):
    provided = _rpv3_fix_text(provided or "").strip()
    if len(provided) >= 1200 and ("##" in provided or "|" in provided):
        return provided

    full_md = _rpv3_fix_text(full_md or "")
    resumen = _rpv4_section_by_title_4h3c(full_md, ["resumen ejecutivo"])
    estado = _rpv4_section_by_title_4h3c(full_md, ["estado de recoleccion", "estado de recolecci\u00f3n"])
    evidencia = _rpv4_section_by_title_4h3c(full_md, ["evidencia publica", "evidencia p\u00fablica"])
    semaforo = _rpv4_section_by_title_4h3c(full_md, ["semaforo", "sem\u00e1foro"])
    metricas = _rpv4_section_by_title_4h3c(full_md, ["metricas publicas", "m\u00e9tricas p\u00fablicas"])
    lectura = _rpv4_section_by_title_4h3c(full_md, ["lectura ejecutiva"])
    proximos = _rpv4_section_by_title_4h3c(full_md, ["proximos pasos", "pr\u00f3ximos pasos"])

    parts = [
        "## Resumen ejecutivo ampliado",
        _rpv4_take_lines_4h3c(resumen or provided or full_md, 38),
        "## Datos p\u00fablicos relevantes",
        _rpv4_take_lines_4h3c(evidencia, 32),
        "## Estado de recolecci\u00f3n y limitaciones",
        _rpv4_take_lines_4h3c(estado, 34),
        "## Sem\u00e1foro de prioridades",
        _rpv4_take_lines_4h3c(semaforo, 36),
        "## M\u00e9tricas p\u00fablicas de redes",
        _rpv4_take_lines_4h3c(metricas, 34),
        "## Lectura para due\u00f1os",
        _rpv4_take_lines_4h3c(lectura, 18),
        "## Pr\u00f3ximos pasos",
        _rpv4_take_lines_4h3c(proximos, 20),
    ]
    return _rpv3_fix_text("\n\n".join([p for p in parts if p and p.strip()]))


def _rpv4_build_interactive_html(req, report_id, created_at):
    title = _rpv3_fix_text(req.report_title)
    company = _rpv3_fix_text(req.company_name)
    md = _rpv3_fix_text(req.markdown_report or "")
    sections = _rpv4_sections_from_markdown(md)

    nav_parts = []
    panel_parts = []
    for idx, sec in enumerate(sections):
        sid = "sec_" + str(idx)
        active = "active" if idx == 0 else ""
        sec_title = _rpv3_fix_text(sec.get("title") or ("Seccion " + str(idx + 1)))
        nav_parts.append('<button class="tab ' + active + '" data-target="' + sid + '">' + _rpb_html.escape(sec_title, quote=True) + '</button>')
        panel_parts.append('<section id="' + sid + '" class="panel ' + active + '">' + _rpv4_markdown_to_basic_html(_rpv3_fix_text(sec.get("markdown") or "")) + '</section>')

    evidence_json = _rpb_html.escape(_rpb_json.dumps(_rpv3_fix_obj(req.evidence_payload or {}), ensure_ascii=False, indent=2), quote=True)
    metrics_json = _rpb_html.escape(_rpb_json.dumps(_rpv3_fix_obj(req.social_metrics or {}), ensure_ascii=False, indent=2), quote=True)

    head = [
        "<!doctype html>", '<html lang="es">', "<head>", '<meta charset="utf-8">',
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>" + _rpb_html.escape(title, quote=True) + " - " + _rpb_html.escape(company, quote=True) + "</title>",
        "<style>",
        ":root{--bg:#f8fafc;--ink:#0f172a;--muted:#64748b;--line:#cbd5e1;--primary:#0f172a;--accent:#0369a1;--soft:#e0f2fe;--card:#ffffff;}",
        "*{box-sizing:border-box;}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--ink);}",
        "header{padding:28px 32px;background:linear-gradient(135deg,#0f172a,#1e293b);color:white;position:sticky;top:0;z-index:5;box-shadow:0 4px 20px rgba(15,23,42,.22);}",
        "h1{margin:0 0 8px;font-size:30px;letter-spacing:-.02em}.meta{color:#e2e8f0;font-size:13px;display:flex;gap:14px;flex-wrap:wrap;}",
        ".layout{display:grid;grid-template-columns:300px 1fr;min-height:calc(100vh - 98px);}nav{border-right:1px solid var(--line);padding:18px;background:#fff;position:sticky;top:98px;height:calc(100vh - 98px);overflow:auto;}",
        ".tab{display:block;width:100%;text-align:left;margin:0 0 8px;padding:11px 12px;background:#f8fafc;color:var(--ink);border:1px solid var(--line);border-radius:12px;cursor:pointer;font-weight:700;}",
        ".tab.active,.tab:hover{border-color:var(--accent);background:var(--soft);}main{padding:24px;max-width:1360px;}",
        ".panel{display:none;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:26px;box-shadow:0 10px 30px rgba(15,23,42,.08);}.panel.active{display:block;}",
        "h2{color:var(--primary);margin-top:8px;border-bottom:2px solid var(--soft);padding-bottom:8px;}h3{color:var(--accent);margin-top:24px;}p,li{line-height:1.58}.space{height:8px;}",
        ".table-wrap{overflow:auto;margin:14px 0;border:1px solid var(--line);border-radius:12px;}table{border-collapse:collapse;width:100%;min-width:760px;font-size:14px;}td,th{border-bottom:1px solid var(--line);padding:10px;vertical-align:top;}tr:first-child td{font-weight:700;color:white;background:var(--primary);}",
        ".badge{display:inline-block;padding:4px 9px;border:1px solid var(--line);border-radius:999px;color:var(--accent);background:var(--soft);font-weight:700;}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:18px 0;}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px;box-shadow:0 6px 16px rgba(15,23,42,.06);}",
        "details{margin:14px 0;border:1px solid var(--line);border-radius:12px;padding:12px;background:#f8fafc;}summary{cursor:pointer;color:var(--accent);font-weight:700;}pre{white-space:pre-wrap;overflow:auto;max-height:480px;background:#0f172a;border-radius:12px;padding:12px;color:#e2e8f0;}footer{color:var(--muted);font-size:12px;padding:24px;text-align:center;}@media(max-width:900px){.layout{grid-template-columns:1fr;}nav{position:relative;top:0;height:auto;}}",
        "</style>", "</head>", "<body>", "<header>",
        "<h1>" + _rpb_html.escape(title, quote=True) + "</h1>",
        '<div class="meta"><span>Cliente: <strong>' + _rpb_html.escape(company, quote=True) + "</strong></span><span>Report ID: " + _rpb_html.escape(report_id, quote=True) + "</span><span>Creado: " + _rpb_html.escape(created_at, quote=True) + "</span><span>Tipo: " + _rpb_html.escape(_rpv3_fix_text(req.client_type or "auditoria publica"), quote=True) + "</span></div>",
        "</header>", '<div class="layout">', "<nav>" + "".join(nav_parts) + "</nav>", "<main>",
        '<div class="cards"><div class="card"><span class="badge">Informe completo</span><p>Auditor&iacute;a p&uacute;blica integral con evidencia, diagn&oacute;stico y plan de acci&oacute;n.</p></div><div class="card"><span class="badge">Versi&oacute;n PDF</span><p>El PDF completo conserva el mismo contenido, sin interacci&oacute;n.</p></div><div class="card"><span class="badge">Resumen ejecutivo</span><p>Documento separado para due&ntilde;os y gerencia.</p></div></div>',
        "".join(panel_parts),
        '<section class="panel active" style="display:block;margin-top:18px;"><h2>Anexos t&eacute;cnicos</h2><details><summary>Evidencia t&eacute;cnica JSON</summary><pre>' + evidence_json + '</pre></details><details><summary>M&eacute;tricas sociales JSON</summary><pre>' + metrics_json + '</pre></details></section>',
        "</main></div>",
        "<footer>Generado por Marketing Auditor. Las m&eacute;tricas p&uacute;blicas son parciales y no representan performance interna.</footer>",
        "<script>document.querySelectorAll('.tab').forEach(function(btn){btn.addEventListener('click',function(){document.querySelectorAll('.tab').forEach(function(b){b.classList.remove('active');});document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active');});btn.classList.add('active');var target=document.getElementById(btn.dataset.target);if(target)target.classList.add('active');});});</script>",
        "</body></html>"
    ]
    return _rpv3_fix_text("\n".join(head))



# ============================================================
# HOTFIX 4H.3-D - REPORT QUALITY GATE + CLEAN PDF/HTML OUTPUT
# ============================================================


import unicodedata as _rpv4_unicodedata
import re as _rpv4_re

_RPV4_MIN_FULL_WORDS_4H3D = 3800
_RPV4_MIN_FULL_SECTIONS_4H3D = 16
_RPV4_MIN_FULL_TABLES_4H3D = 8
_RPV4_MIN_EXEC_WORDS_4H3D = 950
_RPV4_MIN_EXEC_SECTIONS_4H3D = 5

_RPV4_REQUIRED_SECTIONS_4H3D = [
    ("resumen ejecutivo", ["resumen ejecutivo"]),
    ("estado de recoleccion", ["estado de recoleccion"]),
    ("evidencia publica recolectada", ["evidencia publica recolectada", "evidencia publica"]),
    ("semaforo ejecutivo", ["semaforo ejecutivo", "semaforo"]),
    ("metricas publicas agregadas de redes", ["metricas publicas agregadas de redes", "metricas publicas de redes", "metricas publicas"]),
    ("diagnostico duro", ["diagnostico duro", "diagnostico"]),
    ("analisis por canal", ["analisis por canal"]),
    ("matriz impacto/esfuerzo", ["matriz impacto/esfuerzo", "matriz de impacto", "impacto/esfuerzo"]),
    ("tracking checklist operativo", ["tracking checklist operativo", "lista de verificacion operativa de medicion", "lista de verificacion de medicion"]),
    ("arquitectura sugerida de campanas", ["arquitectura sugerida de campanas", "arquitectura de campanas"]),
    ("plan 30/60/90", ["plan 30/60/90", "30/60/90"]),
    ("preguntas para el cliente", ["preguntas para el cliente"]),
    ("datos internos necesarios", ["datos internos necesarios"]),
    ("lectura ejecutiva para reunion", ["lectura ejecutiva para reunion", "lectura ejecutiva"]),
    ("proximos pasos concretos", ["proximos pasos concretos", "proximos pasos"]),
    ("fiabilidad de metricas y evidencia", ["fiabilidad de metricas y evidencia", "fiabilidad"]),
]

_RPV4_MOJIBAKE_REPLACEMENTS_4H3D = {
    "?": "\u00e1", "?": "\u00e9", "?": "\u00ed", "?": "\u00f3", "?": "\u00fa",
    "?": "\u00c1", "\u00c3\u2030": "\u00c9", "?": "\u00cd", "\u00c3\u201c": "\u00d3", "\u00c3\u0161": "\u00da",
    "?": "\u00f1", "\u00c3\u2018": "\u00d1", "?": "\u00fc", "\u00c3\u0153": "\u00dc",
    "?": "\u00bf", "?": "\u00a1", "\u00c2\u00b0": "\u00b0", "\u00c2\u00ba": "\u00ba", "\u00c2\u00aa": "\u00aa",
    "\u00e2\u20ac\u201c": "-", "\u00e2\u20ac\u201d": "-", "\u00e2\u20ac\u02dc": "'", "\u00e2\u20ac\u2122": "'", "\u00e2\u20ac\u0153": '"', "\u00e2\u20ac\u009d": '"',
    "\u00e2\u20ac\u00a6": "...", "\u00e2\u20ac\u00a2": "-", "\u00e2\u2020\u2019": "->", "\u00e2\u20ac": '"',
    "\u00c3\u0192?": "\u00e1", "\u00c3\u0192\u00c2\u00a9": "\u00e9", "\u00c3\u0192\u00c2\u00ad": "\u00ed", "\u00c3\u0192\u00c2\u00b3": "\u00f3", "\u00c3\u0192\u00c2\u00ba": "\u00fa",
    "\u00c3\u0192\u00c2\u0081": "\u00c1", "\u00c3\u0192\u00e2\u20ac\u00b0": "\u00c9", "\u00c3\u0192\u00c2\u008d": "\u00cd", "\u00c3\u0192\u00e2\u20ac\u0153": "\u00d3", "\u00c3\u0192\u00c5\u00a1": "\u00da",
    "\u00c3\u0192\u00c2\u00b1": "\u00f1", "\u00c3\u0192\u00e2\u20ac\u02dc": "\u00d1", "\u00c3\u0192\u00c2\u00bc": "\u00fc", "\u00c3\u0192\u00c5\u201c": "\u00dc",
    "\u00c3\u201a?": "\u00bf", "\u00c3\u201a?": "\u00a1", "\u00c3\u201a\u00c2\u00b0": "\u00b0", "\u00c3\u201a\u00c2\u00ba": "\u00ba", "\u00c3\u201a\u00c2\u00aa": "\u00aa",
    "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u0153": "-", "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u009d": "-", "\u00c3\u00a2\u00e2\u201a\u00ac\u00cb\u0153": "'", "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u201e\u00a2": "'",
    "\u00c3\u00a2\u00e2\u201a\u00ac\u00c5\u201c": '"', "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u009d": '"', "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a6": "...", "\u00c3\u00a2\u00e2\u201a\u00ac\u00c2\u00a2": "-",
    "\u00c3\u0192\u00c2\u0192\u00c3\u201a?": "\u00e1", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00a9": "\u00e9", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00ad": "\u00ed", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00b3": "\u00f3", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00ba": "\u00fa",
    "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00b1": "\u00f1", "\u00c3\u0192\u00c2\u0192\u00c3\u201a\u00c2\u00bc": "\u00fc",
    "Auditor\u00c3a": "Auditor\u00eda", "auditor\u00c3a": "auditor\u00eda",
    "Auditor?a": "Auditor\u00eda", "auditor?a": "auditor\u00eda",
    "p?blica": "p\u00fablica", "P?blica": "P\u00fablica",
    "m?tricas": "m\u00e9tricas", "M?tricas": "M\u00e9tricas",
    "diagn?stico": "diagn\u00f3stico", "acci?n": "acci\u00f3n",
    "recolecci?n": "recolecci\u00f3n", "Pr?ximos": "Pr\u00f3ximos", "pr?ximos": "pr\u00f3ximos",
    "Sem?foro": "Sem\u00e1foro", "sem?foro": "sem\u00e1foro",
    "?ndice": "\u00cdndice", "\u00c3\u25a0ndice": "\u00cdndice", "\u00c3ndice": "\u00cdndice",
    "P?gina": "P\u00e1gina", "p?gina": "p\u00e1gina",
    "Secci?n": "Secci\u00f3n", "secci?n": "secci\u00f3n",
    "T?cnico": "T\u00e9cnico", "t?cnico": "t\u00e9cnico",
    "due?os": "due\u00f1os", "Due?os": "Due\u00f1os",
    "ma?ana": "ma\u00f1ana", "a?o": "a\u00f1o", "a?os": "a\u00f1os",
    "Espa?ol": "Espa\u00f1ol", "espa?ol": "espa\u00f1ol",
    "Informaci?n": "Informaci\u00f3n", "informaci?n": "informaci\u00f3n",
    "Documentaci?n": "Documentaci\u00f3n", "documentaci?n": "documentaci\u00f3n",
    "Versi?n": "Versi\u00f3n", "versi?n": "versi\u00f3n",
    "interacci?n": "interacci\u00f3n", "decisi?n": "decisi\u00f3n",
    "\u00f0\u0178\u203a\u2019": "carrito", "\u00e2\u008f\u00b0": "horario", "\u00e2\u0153\u2026": "OK", "\u00e2\u009d\u0152": "NO",
    "\u00e2\u0161\u00a0\u00ef\u00b8\u008f": "ALERTA", "\u00e2\u0161\u00a0": "ALERTA", "\u00f0\u0178\u201c\u0152": "Nota", "\u00f0\u0178\u201c\u0160": "M\u00e9tricas",
    "\u00f0\u0178\u201d\u00a5": "Prioridad", "\u00f0\u0178\u0161\u20ac": "Escalar", "\u00f0\u0178\u2019\u00a1": "Idea",
    "\ufeff": "",
}

_RPV4_VISIBLE_TERM_REPLACEMENTS_4H3D = [
    (r"\bActions\b", "Acciones"),
    (r"\bAction\b", "Acci\u00f3n"),
    (r"\baction\b", "acci\u00f3n"),
    (r"\bendpoint\b", "punto de conexi\u00f3n"),
    (r"\bendpoints\b", "puntos de conexi\u00f3n"),
    (r"\bstatus\b", "estado"),
    (r"\bscore\b", "puntuaci\u00f3n"),
    (r"\btracking\b", "medici\u00f3n"),
    (r"\bTracking\b", "Medici\u00f3n"),
    (r"\bcollector\b", "recolector"),
    (r"\bcollectors\b", "recolectores"),
    (r"\bCollector\b", "Recolector"),
    (r"\bCollectors\b", "Recolectores"),
    (r"\brun-state\b", "estado de ejecuci\u00f3n"),
    (r"\breadiness\b", "preparaci\u00f3n"),
    (r"\bpublic\b", "p\u00fablico"),
    (r"\bPublic\b", "P\u00fablico"),
    (r"\bwebsite\b", "sitio web"),
    (r"\bWebsite\b", "Sitio web"),
    (r"\bprofile\b", "perfil"),
    (r"\bProfile\b", "Perfil"),
    (r"\bposts\b", "publicaciones"),
    (r"\bPosts\b", "Publicaciones"),
    (r"\bpost\b", "publicaci\u00f3n"),
    (r"\bPost\b", "Publicaci\u00f3n"),
    (r"\bengagement\b", "interacci\u00f3n"),
    (r"\bEngagement\b", "Interacci\u00f3n"),
    (r"\binsights\b", "m\u00e9tricas internas"),
    (r"\bInsights\b", "M\u00e9tricas internas"),
    (r"\breach\b", "alcance"),
    (r"\bReach\b", "Alcance"),
    (r"\bimpressions\b", "impresiones"),
    (r"\bImpressions\b", "Impresiones"),
    (r"\bclicks\b", "clics"),
    (r"\bClicks\b", "Clics"),
    (r"\bviews\b", "visualizaciones"),
    (r"\bViews\b", "Visualizaciones"),
    (r"\bfollowers\b", "seguidores"),
    (r"\bFollowers\b", "Seguidores"),
    (r"\bfollowing\b", "seguidos"),
    (r"\bFollowing\b", "Seguidos"),
    (r"\blikes\b", "me gusta"),
    (r"\bLikes\b", "Me gusta"),
    (r"\bcomments\b", "comentarios"),
    (r"\bComments\b", "Comentarios"),
    (r"\bshares\b", "compartidos"),
    (r"\bShares\b", "Compartidos"),
    (r"\bleads\b", "contactos comerciales"),
    (r"\bLeads\b", "Contactos comerciales"),
    (r"\brevenue\b", "ingresos"),
    (r"\bRevenue\b", "Ingresos"),
    (r"\bperformance\b", "rendimiento"),
    (r"\bPerformance\b", "Rendimiento"),
    (r"\bfooter\b", "pie de p\u00e1gina"),
    (r"\bheader\b", "encabezado"),
    (r"\bquality gate\b", "control de calidad"),
    (r"\bQuality gate\b", "Control de calidad"),
    (r"\bmarkdown\b", "fuente en Markdown"),
    (r"\bMarkdown\b", "Markdown fuente"),
    (r"\bJSON t\u00e9cnico\b", "JSON t\u00e9cnico"),
    (r"\bReport ID\b", "ID del informe"),
]

def _rpv4_strip_accents_4h3d(value):
    value = _rpv3_fix_text(value or "")
    value = _rpv4_unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if _rpv4_unicodedata.category(ch) != "Mn")
    return value.lower().strip()


def _rpv3_fix_text(value):
    if not isinstance(value, str):
        return value

    text = value
    for _ in range(6):
        before = text
        for bad, good in _RPV4_MOJIBAKE_REPLACEMENTS_4H3D.items():
            text = text.replace(bad, good)

        if any(marker in text for marker in ("\u00c3", "\u00c2", "\u00e2", "\u00f0\u0178", "\u00ef\u00bf\u00bd")):
            try:
                candidate = text.encode("latin1", errors="strict").decode("utf-8", errors="strict")
                if sum(candidate.count(m) for m in ("\u00c3", "\u00c2", "\u00e2", "\u00f0\u0178", "\u00ef\u00bf\u00bd")) < sum(text.count(m) for m in ("\u00c3", "\u00c2", "\u00e2", "\u00f0\u0178", "\u00ef\u00bf\u00bd")):
                    text = candidate
            except Exception:
                pass

        if text == before:
            break

    text = text.replace("\uFFFD", "")
    text = _rpv4_unicodedata.normalize("NFC", text)
    return "".join(ch for ch in text if ch in ("\n", "\t") or ord(ch) >= 32)


def _rpv4_localize_visible_terms_4h3d(value):
    text = _rpv3_fix_text(value or "")
    out_lines = []

    for line in text.splitlines():
        # No tocar URLs puras para no romper links.
        stripped = line.strip()
        if stripped.startswith(("http://", "https://")):
            out_lines.append(line)
            continue

        clean = line
        for pattern, replacement in _RPV4_VISIBLE_TERM_REPLACEMENTS_4H3D:
            clean = _rpv4_re.sub(pattern, replacement, clean)
        out_lines.append(clean)

    return _rpv3_fix_text("\n".join(out_lines))


def _rpv4_fix_obj_mojibake_only_4h3d(obj):
    if isinstance(obj, str):
        return _rpv3_fix_text(obj)
    if isinstance(obj, list):
        return [_rpv4_fix_obj_mojibake_only_4h3d(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_rpv4_fix_obj_mojibake_only_4h3d(x) for x in obj)
    if isinstance(obj, dict):
        return {(_rpv3_fix_text(k) if isinstance(k, str) else k): _rpv4_fix_obj_mojibake_only_4h3d(v) for k, v in obj.items()}
    return obj


def _rpv3_fix_obj(obj):
    return _rpv4_fix_obj_mojibake_only_4h3d(obj)


def _rpv3_request_clean_copy(req):
    try:
        data = req.model_dump()
    except Exception:
        try:
            data = req.dict()
        except Exception:
            data = dict(req)

    data = _rpv4_fix_obj_mojibake_only_4h3d(data)
    data["documentation_folder_name"] = "Documentacion"
    data["technical_folder_name"] = "Tecnico"

    if "markdown_report" in data:
        data["markdown_report"] = _rpv4_prepare_report_markdown_4h3d(data.get("markdown_report") or "")
    if "executive_summary_markdown" in data and data.get("executive_summary_markdown"):
        data["executive_summary_markdown"] = _rpv4_localize_visible_terms_4h3d(data.get("executive_summary_markdown") or "")

    return ReportPackageRequest(**data)


def _rpv4_prepare_report_markdown_4h3d(md):
    md = _rpv3_fix_text(md or "")
    md = _rpv4_localize_visible_terms_4h3d(md)
    md = _rpv4_re.sub(r"\n{4,}", "\n\n\n", md)
    md = _rpv4_re.sub(r"[ \t]+\n", "\n", md)
    return md.strip() + "\n"


def _rpv4_word_count_4h3d(md):
    return len(_rpv4_re.findall(r"[A-Za-z\u00c1\u00c9\u00cd\u00d3\u00da\u00dc\u00d1\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc\u00f10-9]+(?:[-'][A-Za-z\u00c1\u00c9\u00cd\u00d3\u00da\u00dc\u00d1\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc\u00f10-9]+)?", md or ""))


def _rpv4_table_count_4h3d(md):
    count = 0
    in_table = False
    for line in (md or "").splitlines():
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2
        if is_table_line and not in_table:
            count += 1
            in_table = True
        elif not is_table_line:
            in_table = False
    return count


def _rpv4_section_titles_4h3d(md):
    titles = []
    for line in (md or "").splitlines():
        if line.startswith("## "):
            titles.append(line[3:].strip())
        elif line.startswith("# ") and not titles:
            titles.append(line[2:].strip())
    return titles


def _rpv4_missing_required_sections_4h3d(md):
    titles = [_rpv4_strip_accents_4h3d(t) for t in _rpv4_section_titles_4h3d(md)]
    missing = []
    for canonical, aliases in _RPV4_REQUIRED_SECTIONS_4H3D:
        found = False
        for title in titles:
            if any(alias in title for alias in aliases):
                found = True
                break
        if not found:
            missing.append(canonical)
    return missing


def _rpv4_assess_full_report_quality_4h3d(md):
    md = _rpv4_prepare_report_markdown_4h3d(md)
    word_count = _rpv4_word_count_4h3d(md)
    section_count = len([t for t in _rpv4_section_titles_4h3d(md) if t.strip()])
    table_count = _rpv4_table_count_4h3d(md)
    missing_sections = _rpv4_missing_required_sections_4h3d(md)

    failures = []
    if word_count < _RPV4_MIN_FULL_WORDS_4H3D:
        failures.append("word_count")
    if section_count < _RPV4_MIN_FULL_SECTIONS_4H3D:
        failures.append("section_count")
    if table_count < _RPV4_MIN_FULL_TABLES_4H3D:
        failures.append("table_count")
    if missing_sections:
        failures.append("required_sections")

    return {
        "status": "passed" if not failures else "failed",
        "word_count": word_count,
        "min_word_count": _RPV4_MIN_FULL_WORDS_4H3D,
        "section_count": section_count,
        "min_section_count": _RPV4_MIN_FULL_SECTIONS_4H3D,
        "table_count": table_count,
        "min_table_count": _RPV4_MIN_FULL_TABLES_4H3D,
        "missing_required_sections": missing_sections,
        "failures": failures,
    }


def _rpv4_assess_executive_quality_4h3d(md):
    md = _rpv4_prepare_report_markdown_4h3d(md)
    word_count = _rpv4_word_count_4h3d(md)
    section_count = len([t for t in _rpv4_section_titles_4h3d(md) if t.strip()])
    failures = []
    if word_count < _RPV4_MIN_EXEC_WORDS_4H3D:
        failures.append("word_count")
    if section_count < _RPV4_MIN_EXEC_SECTIONS_4H3D:
        failures.append("section_count")
    return {
        "status": "passed" if not failures else "failed",
        "word_count": word_count,
        "min_word_count": _RPV4_MIN_EXEC_WORDS_4H3D,
        "section_count": section_count,
        "min_section_count": _RPV4_MIN_EXEC_SECTIONS_4H3D,
        "failures": failures,
    }


def _rpv4_section_by_title_4h3d(full_md, needles):
    full_md = _rpv4_prepare_report_markdown_4h3d(full_md or "")
    sections = _rpv4_sections_from_markdown(full_md)
    clean_needles = [_rpv4_strip_accents_4h3d(n) for n in needles]
    for sec in sections:
        title = _rpv4_strip_accents_4h3d(sec.get("title") or "")
        if any(n in title for n in clean_needles):
            return _rpv4_prepare_report_markdown_4h3d(sec.get("markdown") or "").strip()
    return ""


def _rpv4_trim_section_4h3d(text, max_words=220):
    text = _rpv4_prepare_report_markdown_4h3d(text or "")
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).strip() + "..."


def _rpv4_executive_md_4h3c(full_md, provided=None):
    full_md = _rpv4_prepare_report_markdown_4h3d(full_md or "")
    provided = _rpv4_prepare_report_markdown_4h3d(provided or "").strip()

    if provided and _rpv4_word_count_4h3d(provided) >= _RPV4_MIN_EXEC_WORDS_4H3D and len(_rpv4_section_titles_4h3d(provided)) >= _RPV4_MIN_EXEC_SECTIONS_4H3D:
        return provided

    resumen = _rpv4_section_by_title_4h3d(full_md, ["resumen ejecutivo"])
    estado = _rpv4_section_by_title_4h3d(full_md, ["estado de recoleccion"])
    evidencia = _rpv4_section_by_title_4h3d(full_md, ["evidencia publica recolectada", "evidencia publica"])
    semaforo = _rpv4_section_by_title_4h3d(full_md, ["semaforo ejecutivo", "semaforo"])
    metricas = _rpv4_section_by_title_4h3d(full_md, ["metricas publicas agregadas de redes", "metricas publicas"])
    diagnostico = _rpv4_section_by_title_4h3d(full_md, ["diagnostico duro", "diagnostico"])
    matriz = _rpv4_section_by_title_4h3d(full_md, ["matriz impacto/esfuerzo", "matriz de impacto"])
    lectura = _rpv4_section_by_title_4h3d(full_md, ["lectura ejecutiva para reunion", "lectura ejecutiva"])
    proximos = _rpv4_section_by_title_4h3d(full_md, ["proximos pasos concretos", "proximos pasos"])
    fiabilidad = _rpv4_section_by_title_4h3d(full_md, ["fiabilidad de metricas y evidencia", "fiabilidad"])
    internos = _rpv4_section_by_title_4h3d(full_md, ["datos internos necesarios"])

    parts = [
        "# Resumen ejecutivo para due\u00f1os y gerencia",
        "Este resumen usa la misma evidencia del informe completo. No agrega datos privados ni afirma ventas, ROAS, CPA, margen, tr\u00e1fico real, conversiones reales, alcance real, clics o ingresos sin acceso interno validado.",
        "## Diagn\u00f3stico general",
        _rpv4_trim_section_4h3d(resumen or diagnostico or provided or full_md, 260),
        "## Evidencia p\u00fablica relevante",
        _rpv4_trim_section_4h3d((evidencia + "\n\n" + metricas).strip(), 260),
        "## Estado de recolecci\u00f3n y l\u00edmites",
        _rpv4_trim_section_4h3d((estado + "\n\n" + fiabilidad).strip(), 230),
        "## Prioridades para decisi\u00f3n",
        _rpv4_trim_section_4h3d((semaforo + "\n\n" + matriz).strip(), 260),
        "## Datos internos necesarios",
        _rpv4_trim_section_4h3d(internos, 180),
        "## Pr\u00f3ximos pasos para reuni\u00f3n",
        _rpv4_trim_section_4h3d((lectura + "\n\n" + proximos).strip(), 240),
    ]

    exec_md = _rpv4_prepare_report_markdown_4h3d("\n\n".join([p for p in parts if p and p.strip()]))

    if _rpv4_word_count_4h3d(exec_md) < _RPV4_MIN_EXEC_WORDS_4H3D:
        filler = []
        for sec in _rpv4_sections_from_markdown(full_md):
            title = sec.get("title") or ""
            body = sec.get("markdown") or ""
            if title and body and title not in exec_md:
                filler.append("### Apoyo ejecutivo: " + title)
                filler.append(_rpv4_trim_section_4h3d(body, 120))
            if _rpv4_word_count_4h3d(exec_md + "\n\n" + "\n\n".join(filler)) >= _RPV4_MIN_EXEC_WORDS_4H3D:
                break
        if filler:
            exec_md = _rpv4_prepare_report_markdown_4h3d(exec_md + "\n\n" + "\n\n".join(filler))

    return exec_md


def _rpv3_pdf_inline_4h3b(text):
    text = _rpv3_fix_text(text or "")
    text = text.replace("**", "")
    text = _rpb_html.escape(text, quote=True)
    text = _rpv4_re.sub(r"`([^`]+)`", r"<font name='Helvetica-Bold'>\1</font>", text)
    return text


def _rpv3_pdf_safe(text):
    return _rpv3_fix_text(text or "").replace("\u2192", "->").replace("\u2013", "-").replace("\u2014", "-")


def _rpv4_read_markdown_table_4h3d(lines, start_index):
    rows = []
    j = start_index
    while j < len(lines):
        ln = lines[j].strip()
        if not (ln.startswith("|") and ln.endswith("|") and ln.count("|") >= 2):
            break
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if not all(set(c) <= set("-: ") for c in cells):
            rows.append(cells)
        j += 1
    return rows, j


def _rpv3_markdown_to_pdf(path, title, md, company_name, executive=False):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    except Exception as exc:
        raise RuntimeError("reportlab no est\u00e1 instalado. Agregar reportlab a requirements.txt") from exc

    title = _rpv3_pdf_safe(title)
    company_name = _rpv3_pdf_safe(company_name)
    md = _rpv4_prepare_report_markdown_4h3d(md or "")

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=1.35 * cm,
        leftMargin=1.35 * cm,
        topMargin=1.25 * cm,
        bottomMargin=1.15 * cm,
        title=title,
        author="Marketing Auditor",
        subject=company_name,
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="CoverTitle4H3D",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22 if not executive else 18,
        leading=27 if not executive else 23,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=16,
    ))
    styles.add(ParagraphStyle(
        name="CoverSub4H3D",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="H1_4H3D",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15 if not executive else 14.5,
        leading=19,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=11,
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="H2_4H3D",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12.2,
        leading=15.5,
        textColor=colors.HexColor("#075985"),
        spaceBefore=9,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="H3_4H3D",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13.5,
        textColor=colors.HexColor("#334155"),
        spaceBefore=7,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Body4H3D",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.8 if not executive else 9.2,
        leading=12.0 if not executive else 12.7,
        textColor=colors.HexColor("#111827"),
        spaceAfter=4.2,
    ))
    styles.add(ParagraphStyle(
        name="Small4H3D",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=6.8,
        leading=8.8,
        textColor=colors.HexColor("#111827"),
    ))
    styles.add(ParagraphStyle(
        name="SmallHeader4H3D",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=6.9,
        leading=8.9,
        textColor=colors.white,
    ))

    story = []

    if executive:
        story.append(Paragraph(_rpv3_pdf_inline_4h3b(title), styles["CoverTitle4H3D"]))
        story.append(Paragraph("Cliente: <b>" + _rpb_html.escape(company_name, quote=True) + "</b>", styles["CoverSub4H3D"]))
        story.append(Paragraph("Documento ejecutivo basado en evidencia p\u00fablica visible. No incluye m\u00e9tricas privadas sin acceso interno.", styles["CoverSub4H3D"]))
        story.append(Spacer(1, 8))
    else:
        story.append(Spacer(1, 1.25 * cm))
        story.append(Paragraph(_rpv3_pdf_inline_4h3b(title), styles["CoverTitle4H3D"]))
        story.append(Paragraph("Cliente: <b>" + _rpb_html.escape(company_name, quote=True) + "</b>", styles["CoverSub4H3D"]))
        story.append(Paragraph("Tipo de documento: Auditor\u00eda completa", styles["CoverSub4H3D"]))
        story.append(Paragraph("Generado: " + _rpb_html.escape(_rpb_now_iso(), quote=True), styles["CoverSub4H3D"]))
        story.append(Spacer(1, 0.45 * cm))
        story.append(Paragraph(
            "Nota metodol\u00f3gica: este documento usa evidencia p\u00fablica visible y separa hechos, inferencias razonadas y datos que requieren acceso interno.",
            styles["Body4H3D"]
        ))
        story.append(PageBreak())

        try:
            sections = _rpb_sections_from_markdown(md)
        except Exception:
            sections = []

        if sections and len(sections) >= 4:
            story.append(Paragraph("\u00cdndice", styles["H1_4H3D"]))
            for idx, sec in enumerate(sections, start=1):
                story.append(Paragraph(str(idx) + ". " + _rpv3_pdf_inline_4h3b(sec.get("title") or "Secci\u00f3n"), styles["Body4H3D"]))
            story.append(PageBreak())

    lines = md.splitlines()
    i = 0
    blank_added = False

    while i < len(lines):
        raw = lines[i].rstrip()
        clean = _rpv3_fix_text(raw).strip()

        if not clean:
            if not blank_added:
                story.append(Spacer(1, 2.5))
                blank_added = True
            i += 1
            continue

        blank_added = False

        if clean.startswith("|") and clean.endswith("|"):
            rows, next_i = _rpv4_read_markdown_table_4h3d(lines, i)
            if rows:
                max_cols = max(len(r) for r in rows)
                normalized = []
                for ridx, r in enumerate(rows):
                    rr = r + [""] * (max_cols - len(r))
                    row_style = styles["SmallHeader4H3D"] if ridx == 0 else styles["Small4H3D"]
                    normalized.append([Paragraph(_rpv3_pdf_inline_4h3b(c), row_style) for c in rr])

                usable_width = A4[0] - 2.7 * cm
                col_widths = [usable_width / max_cols] * max_cols

                tbl = Table(normalized, colWidths=col_widths, repeatRows=1, splitByRow=1)
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 7))
                i = next_i
                continue

        if clean.startswith("# "):
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean[2:]), styles["H1_4H3D"]))
        elif clean.startswith("## "):
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean[3:]), styles["H1_4H3D"]))
        elif clean.startswith("### "):
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean[4:]), styles["H2_4H3D"]))
        elif clean.startswith("#### "):
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean[5:]), styles["H3_4H3D"]))
        elif _rpb_re.match(r"^\s*[-*]\s+", clean):
            item = _rpb_re.sub(r"^\s*[-*]\s+", "\u2022 ", clean)
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(item), styles["Body4H3D"]))
        elif _rpb_re.match(r"^\s*\d+\.\s+", clean):
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean), styles["Body4H3D"]))
        elif clean == "---":
            story.append(Spacer(1, 7))
        else:
            story.append(Paragraph(_rpv3_pdf_inline_4h3b(clean), styles["Body4H3D"]))

        i += 1

    if not story:
        raise RuntimeError("No hay contenido suficiente para generar PDF.")

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(1.25 * cm, 0.65 * cm, _rpv3_fix_text(company_name + " - " + title)[:118])
        canvas.drawRightString(A4[0] - 1.25 * cm, 0.65 * cm, "P\u00e1gina " + str(doc_obj.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def _rpv4_build_interactive_html(req, report_id, created_at):
    title = _rpv3_fix_text(req.report_title)
    company = _rpv3_fix_text(req.company_name)
    md = _rpv4_prepare_report_markdown_4h3d(req.markdown_report or "")
    sections = _rpv4_sections_from_markdown(md)

    nav_parts = []
    panel_parts = []
    for idx, sec in enumerate(sections):
        sid = "sec_" + str(idx)
        active = "active" if idx == 0 else ""
        sec_title = _rpv3_fix_text(sec.get("title") or ("Secci\u00f3n " + str(idx + 1)))
        nav_parts.append('<button class="tab ' + active + '" data-target="' + sid + '">' + _rpb_html.escape(sec_title, quote=True) + '</button>')
        panel_parts.append('<section id="' + sid + '" class="panel ' + active + '">' + _rpv4_markdown_to_basic_html(_rpv4_prepare_report_markdown_4h3d(sec.get("markdown") or "")) + '</section>')

    evidence_json = _rpb_html.escape(_rpb_json.dumps(_rpv4_fix_obj_mojibake_only_4h3d(req.evidence_payload or {}), ensure_ascii=False, indent=2), quote=True)
    metrics_json = _rpb_html.escape(_rpb_json.dumps(_rpv4_fix_obj_mojibake_only_4h3d(req.social_metrics or {}), ensure_ascii=False, indent=2), quote=True)

    head = [
        "<!doctype html>", '<html lang="es">', "<head>", '<meta charset="utf-8">',
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>" + _rpb_html.escape(title, quote=True) + " - " + _rpb_html.escape(company, quote=True) + "</title>",
        "<style>",
        ":root{--bg:#f8fafc;--ink:#0f172a;--muted:#64748b;--line:#cbd5e1;--primary:#0f172a;--accent:#0369a1;--soft:#e0f2fe;--card:#ffffff;}",
        "*{box-sizing:border-box;}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--ink);}",
        "header{padding:30px 34px;background:linear-gradient(135deg,#0f172a,#1e293b);color:white;position:sticky;top:0;z-index:5;box-shadow:0 4px 20px rgba(15,23,42,.22);}",
        "h1{margin:0 0 8px;font-size:30px;letter-spacing:-.02em}.meta{color:#e2e8f0;font-size:13px;display:flex;gap:14px;flex-wrap:wrap;}",
        ".layout{display:grid;grid-template-columns:310px 1fr;min-height:calc(100vh - 100px);}nav{border-right:1px solid var(--line);padding:18px;background:#fff;position:sticky;top:100px;height:calc(100vh - 100px);overflow:auto;}",
        ".tab{display:block;width:100%;text-align:left;margin:0 0 8px;padding:11px 12px;background:#f8fafc;color:var(--ink);border:1px solid var(--line);border-radius:12px;cursor:pointer;font-weight:700;}",
        ".tab.active,.tab:hover{border-color:var(--accent);background:var(--soft);}main{padding:26px;max-width:1360px;}",
        ".panel{display:none;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:28px;box-shadow:0 10px 30px rgba(15,23,42,.08);}.panel.active{display:block;}",
        "h2{color:var(--primary);margin-top:8px;border-bottom:2px solid var(--soft);padding-bottom:8px;}h3{color:var(--accent);margin-top:24px;}p,li{line-height:1.62}.space{height:8px;}",
        ".table-wrap{overflow:auto;margin:16px 0;border:1px solid var(--line);border-radius:12px;}table{border-collapse:collapse;width:100%;min-width:760px;font-size:14px;}td,th{border-bottom:1px solid var(--line);padding:10px;vertical-align:top;}tr:first-child td{font-weight:700;color:white;background:var(--primary);}",
        ".badge{display:inline-block;padding:4px 9px;border:1px solid var(--line);border-radius:999px;color:var(--accent);background:var(--soft);font-weight:700;}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0;}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px;box-shadow:0 6px 16px rgba(15,23,42,.06);}",
        "details{margin:14px 0;border:1px solid var(--line);border-radius:12px;padding:12px;background:#f8fafc;}summary{cursor:pointer;color:var(--accent);font-weight:700;}pre{white-space:pre-wrap;overflow:auto;max-height:480px;background:#0f172a;border-radius:12px;padding:12px;color:#e2e8f0;}footer{color:var(--muted);font-size:12px;padding:24px;text-align:center;}@media(max-width:900px){.layout{grid-template-columns:1fr;}nav{position:relative;top:0;height:auto;}}",
        "</style>", "</head>", "<body>", "<header>",
        "<h1>" + _rpb_html.escape(title, quote=True) + "</h1>",
        '<div class="meta"><span>Cliente: <strong>' + _rpb_html.escape(company, quote=True) + "</strong></span><span>ID del informe: " + _rpb_html.escape(report_id, quote=True) + "</span><span>Creado: " + _rpb_html.escape(created_at, quote=True) + "</span><span>Tipo: " + _rpb_html.escape(_rpv3_fix_text(req.client_type or "auditor\u00eda p\u00fablica"), quote=True) + "</span></div>",
        "</header>", '<div class="layout">', "<nav>" + "".join(nav_parts) + "</nav>", "<main>",
        '<div class="cards"><div class="card"><span class="badge">Informe completo</span><p>Auditor\u00eda p\u00fablica integral con evidencia, diagn\u00f3stico y plan de acci\u00f3n.</p></div><div class="card"><span class="badge">Versi\u00f3n PDF</span><p>El PDF completo conserva el mismo contenido, sin interacci\u00f3n.</p></div><div class="card"><span class="badge">Resumen ejecutivo</span><p>Documento separado para due\u00f1os y gerencia.</p></div></div>',
        "".join(panel_parts),
        '<section class="panel active" style="display:block;margin-top:18px;"><h2>Anexos t\u00e9cnicos</h2><details><summary>Evidencia t\u00e9cnica JSON</summary><pre>' + evidence_json + '</pre></details><details><summary>M\u00e9tricas sociales JSON</summary><pre>' + metrics_json + '</pre></details></section>',
        "</main></div>",
        "<footer>Generado por Marketing Auditor. Las m\u00e9tricas p\u00fablicas son parciales y no representan rendimiento interno.</footer>",
        "<script>document.querySelectorAll('.tab').forEach(function(btn){btn.addEventListener('click',function(){document.querySelectorAll('.tab').forEach(function(b){b.classList.remove('active');});document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active');});btn.classList.add('active');var target=document.getElementById(btn.dataset.target);if(target)target.classList.add('active');});});</script>",
        "</body></html>"
    ]
    return _rpv3_fix_text("\n".join(head))


def _rpv4_model_copy_clean_4h3d(req, markdown_report=None, executive_summary_markdown=None, upload_to_drive=None):
    try:
        data = req.model_dump()
    except Exception:
        try:
            data = req.dict()
        except Exception:
            data = dict(req)

    data = _rpv4_fix_obj_mojibake_only_4h3d(data)
    if markdown_report is not None:
        data["markdown_report"] = markdown_report
    if executive_summary_markdown is not None:
        data["executive_summary_markdown"] = executive_summary_markdown
    if upload_to_drive is not None:
        data["upload_to_drive"] = bool(upload_to_drive)
    data["documentation_folder_name"] = "Documentacion"
    data["technical_folder_name"] = "Tecnico"
    return ReportPackageRequest(**data)


def _rpv4_quality_gate_response_4h3d(req, quality_gate):
    created_at = _rpb_now_iso()
    report_id = _rpb_report_id(getattr(req, "company_name", "cliente"))
    base = _rpb_public_base_url()
    return {
        "collector": "report_package_builder_v4",
        "version": APP_VERSION,
        "status": "needs_more_content",
        "reason": "El informe completo no cumple el est\u00e1ndar m\u00ednimo de profundidad para generar entregables.",
        "report_id": report_id,
        "company_name": _rpv3_fix_text(getattr(req, "company_name", "")),
        "report_title": _rpv3_fix_text(getattr(req, "report_title", "")),
        "created_at": created_at,
        "quality_gate": quality_gate,
        "local_urls": {
            "interactive_html_url": f"{base}/deliverables/report-package/{report_id}/html",
            "full_pdf_url": f"{base}/deliverables/report-package/{report_id}/pdf-full",
            "executive_pdf_url": f"{base}/deliverables/report-package/{report_id}/pdf-executive",
            "markdown_source_url": f"{base}/deliverables/report-package/{report_id}/md",
            "evidence_json_url": f"{base}/deliverables/report-package/{report_id}/json",
        },
        "files": {},
        "drive": {
            "requested": bool(getattr(req, "upload_to_drive", False)),
            "status": "not_requested",
            "integration": "existing_drive_webapp",
        },
        "errors": [],
        "regeneration_available": False,
        "notes": [
            "No se gener\u00f3 HTML/PDF porque el contenido era demasiado corto o incompleto.",
            "Para corregirlo, ampliar el Markdown completo hasta cumplir word_count, section_count, table_count y secciones obligatorias.",
            "El backend bloquea entregables cortos para evitar PDFs pobres, p\u00e1ginas vac\u00edas o res\u00famenes ejecutivos de una sola p\u00e1gina real."
        ]
    }


def _rpv4_build_package(req):
    req = _rpv3_request_clean_copy(req)
    created_at = _rpb_now_iso()
    report_id = _rpb_report_id(req.company_name)
    prefix = _rpb_slug(req.filename_prefix or req.company_name)
    workdir = _RPB_ROOT / report_id
    workdir.mkdir(parents=True, exist_ok=True)

    technical_dir = workdir / "tecnico"
    technical_dir.mkdir(exist_ok=True)

    files = {}
    errors = []

    markdown_report = _rpv4_prepare_report_markdown_4h3d(req.markdown_report or "")
    full_quality = _rpv4_assess_full_report_quality_4h3d(markdown_report)
    if full_quality.get("status") != "passed":
        return _rpv4_quality_gate_response_4h3d(req, full_quality)

    exec_md = _rpv4_executive_md_4h3c(markdown_report, req.executive_summary_markdown)
    exec_quality = _rpv4_assess_executive_quality_4h3d(exec_md)
    if exec_quality.get("status") != "passed":
        quality = dict(full_quality)
        quality["executive_quality_gate"] = exec_quality
        return _rpv4_quality_gate_response_4h3d(req, quality)

    req = _rpv4_model_copy_clean_4h3d(req, markdown_report=markdown_report, executive_summary_markdown=exec_md, upload_to_drive=False)

    evidence_payload = _rpv4_fix_obj_mojibake_only_4h3d(req.evidence_payload or {})
    social_metrics = _rpv4_fix_obj_mojibake_only_4h3d(req.social_metrics or {})

    md_path = technical_dir / f"04_{prefix}_reporte_fuente.md"
    json_path = technical_dir / f"05_{prefix}_evidencia_tecnica.json"

    md_path.write_text(markdown_report, encoding="utf-8")
    json_payload = {
        "report_id": report_id,
        "company_name": _rpv3_fix_text(req.company_name),
        "report_title": _rpv3_fix_text(req.report_title),
        "client_type": _rpv3_fix_text(req.client_type),
        "created_at": created_at,
        "quality_gate": {
            "full_report": full_quality,
            "executive_report": exec_quality,
            "empty_page_policy": "executive_without_cover_or_index_pagebreaks",
            "encoding_policy": "utf8_nfc_mojibake_fixed_all_visible_renderers",
            "language_policy": "visible_output_spanish_first",
        },
        "evidence_payload": evidence_payload,
        "social_metrics": social_metrics,
    }
    json_path.write_text(_rpb_json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    files["markdown_source"] = {"status": "created", "path": str(md_path)}
    files["evidence_json"] = {"status": "created", "path": str(json_path)}

    html_path = workdir / f"01_{prefix}_auditoria_interactiva_completa.html"
    full_pdf_path = workdir / f"02_{prefix}_auditoria_completa.pdf"
    executive_pdf_path = workdir / f"03_{prefix}_resumen_ejecutivo_duenos.pdf"

    if req.generate_interactive_html:
        try:
            html_doc = _rpv4_build_interactive_html(req, report_id, created_at)
            html_path.write_text(html_doc, encoding="utf-8")
            files["interactive_html"] = {"status": "created", "path": str(html_path)}
        except Exception as exc:
            files["interactive_html"] = {"status": "failed", "reason": str(exc), "regenerable": True}
            errors.append(f"interactive_html failed: {exc}")

    if req.generate_full_pdf:
        try:
            _rpv3_markdown_to_pdf(full_pdf_path, f"{req.report_title} - Completa", markdown_report, req.company_name, executive=False)
            files["full_pdf"] = {"status": "created", "path": str(full_pdf_path)}
        except Exception as exc:
            files["full_pdf"] = {"status": "failed", "reason": str(exc), "regenerable": True}
            errors.append(f"full_pdf failed: {exc}")

    if req.generate_executive_pdf:
        try:
            _rpv3_markdown_to_pdf(executive_pdf_path, f"{req.report_title} - Resumen ejecutivo", exec_md, req.company_name, executive=True)
            files["executive_pdf"] = {"status": "created", "path": str(executive_pdf_path)}
        except Exception as exc:
            files["executive_pdf"] = {"status": "failed", "reason": str(exc), "regenerable": True}
            errors.append(f"executive_pdf failed: {exc}")

    base = _rpb_public_base_url()
    local_urls = {
        "interactive_html_url": f"{base}/deliverables/report-package/{report_id}/html",
        "full_pdf_url": f"{base}/deliverables/report-package/{report_id}/pdf-full",
        "executive_pdf_url": f"{base}/deliverables/report-package/{report_id}/pdf-executive",
        "markdown_source_url": f"{base}/deliverables/report-package/{report_id}/md",
        "evidence_json_url": f"{base}/deliverables/report-package/{report_id}/json",
    }

    return {
        "collector": "report_package_builder_v4",
        "version": APP_VERSION,
        "status": "completed" if not errors else "partial_completed",
        "report_id": report_id,
        "company_name": _rpv3_fix_text(req.company_name),
        "report_title": _rpv3_fix_text(req.report_title),
        "created_at": created_at,
        "documentation_folder_name": "Documentacion",
        "technical_folder_name": "Tecnico",
        "local_urls": local_urls,
        "files": files,
        "drive": {
            "requested": bool(req.upload_to_drive),
            "status": "not_requested",
            "integration": "existing_drive_webapp",
        },
        "quality_gate": {
            "full_report": full_quality,
            "executive_report": exec_quality,
        },
        "errors": errors,
        "regeneration_available": True,
        "notes": [
            "4H.3-D: quality gate bloquea informes completos cortos o incompletos.",
            "4H.3-D: PDF ejecutivo no genera portada ni \u00edndice separados; empieza con contenido real.",
            "4H.3-D: renderer PDF y HTML aplican limpieza de mojibake y salida visible en espa\u00f1ol.",
            "4H.3-D: se limita el espaciado vac\u00edo para evitar hojas al vicio."
        ]
    }


_rpb_upload_package_with_existing_drive_previous_4h3d = _rpb_upload_package_with_existing_drive

async def _rpb_upload_package_with_existing_drive(req, package_result):
    if (package_result or {}).get("status") == "needs_more_content":
        return {
            "requested": bool(getattr(req, "upload_to_drive", False)),
            "status": "completed",
            "skipped": True,
            "reason": "quality_gate_failed_no_files_generated",
            "integration": "existing_drive_webapp",
            "uploaded_count": 0,
            "failed_count": 0,
            "files": {},
        }
    return await _rpb_upload_package_with_existing_drive_previous_4h3d(req, package_result)

# ============================================================
# END HOTFIX 4H.3-D
# ============================================================


# HOTFIX 4H.3-G: report quality gate + safe PDF rendering verification marker.

# HOTFIX 4H.3-I: mojibake cleanup without blocking prompt.

# HOTFIX 4H.3-J: ASCII-safe source encoding guard.

# HOTFIX 4H.3-O: removed duplicate APP_VERSION override.
