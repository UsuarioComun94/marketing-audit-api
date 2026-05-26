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

APP_VERSION = "public-presence-collector-mvp-0.8.2"
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
    "missing_input": "No se recibió un link para esta fuente.",
    "missing_api_key": "La herramienta necesaria no está configurada en el backend mediante variable de entorno.",
    "blocked_by_platform": "La plataforma limitó la lectura pública, requirió login o bloqueó el acceso automatizado.",
    "not_publicly_available": "El dato no está disponible públicamente de forma confiable.",
    "requires_owner_access": "Este dato requiere autorización del propietario de la cuenta o acceso del cliente.",
    "robots_disallowed": "El archivo robots.txt no permite recolectar esta URL con el user-agent actual.",
    "http_error": "La URL respondió con error HTTP.",
    "timeout": "La solicitud agotó el tiempo de espera.",
    "parse_error": "Se pudo descargar contenido, pero no se pudo interpretar de forma confiable.",
    "js_render_required": "El contenido parece depender de JavaScript/renderizado dinámico.",
    "rate_limited": "La plataforma o API limitó la cantidad de solicitudes.",
    "unsupported_platform": "La plataforma no está soportada por este MVP.",
    "collector_not_implemented": "El collector está reconocido, pero todavía no está implementado en esta versión mínima.",
    "insufficient_public_data": "La fuente pública entregó información insuficiente para ese campo.",
    "private_metric": "Es una métrica privada de performance; no puede obtenerse desde links públicos.",
    "all_search_providers_failed": "Todos los proveedores de búsqueda configurados fallaron o no devolvieron resultados útiles.",
    "no_search_results": "La búsqueda pública no devolvió resultados útiles con los proveedores configurados.",
}

HOW_TO_COLLECT_ES = {
    "website": {
        "generic": [
            "Verificar que la URL sea pública y correcta.",
            "Probar lectura con Firecrawl si el HTML público viene pobre.",
            "Usar Browserbase/Playwright si el contenido depende de JavaScript.",
            "Pedir al cliente la landing exacta si la página pública no contiene la información comercial.",
        ]
    },
    "instagram": {
        "generic": [
            "Solicitar link correcto del perfil público.",
            "Si se requieren métricas reales, conectar cuenta profesional mediante Meta/Instagram API con autorización del cliente.",
            "Como alternativa operativa, pedir captura o export manual desde Meta Business Suite con fecha de captura.",
        ]
    },
    "facebook": {
        "generic": [
            "Solicitar link correcto de la página pública.",
            "Para insights reales, el cliente debe autorizar Meta/Facebook Page mediante permisos de página.",
            "Como alternativa, pedir capturas o export manual desde Meta Business Suite.",
        ]
    },
    "linkedin": {
        "generic": [
            "Solicitar URL correcta de página de empresa o perfil.",
            "Para estadísticas reales, el cliente debe autorizar LinkedIn API/OAuth o entregar export/capturas.",
            "LinkedIn limita mucha información pública sin login; registrar la limitación si no expone posts o métricas.",
        ]
    },
    "youtube": {
        "generic": [
            "Verificar que el link corresponda a un canal, handle o video público.",
            "Configurar YOUTUBE_API_KEY si falta la clave.",
            "Si el conteo de suscriptores está oculto por el canal, marcarlo como no público.",
        ]
    },
    "tiktok": {
        "generic": [
            "Solicitar link correcto del perfil público.",
            "Si la plataforma oculta métricas, pedir captura manual del perfil y contenidos recientes.",
            "Para métricas internas reales, se requiere acceso del cliente o export de la plataforma.",
        ]
    },
    "x": {
        "generic": [
            "Solicitar link correcto del perfil público.",
            "Si las métricas no son visibles, marcar como no disponible públicamente.",
            "Para datos estructurados, usar API de X si existe acceso y condiciones habilitadas.",
        ]
    },
    "search": {
        "generic": [
            "Configurar TAVILY_API_KEY y SERPER_API_KEY para búsqueda pública con fallback.",
            "Si un proveedor responde 429, esperar reset de cuota o usar fallback.",
            "Usar Firecrawl después de la búsqueda para extraer contenido real de URLs encontradas.",
            "No tratar snippets de SERP como evidencia definitiva; usarlos para descubrir fuentes.",
        ]
    },
}

app = FastAPI(
    title="Marketing Auditor - Public Presence Collector MVP",
    version=APP_VERSION,
    description=(
        "MVP de recolección pasiva/semi-pasiva de presencia pública. "
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
    url: Optional[str] = Field(default=None, description="URL pública del sitio.")
    website: Optional[str] = Field(default=None, description="Alias de url.")
    company_name: Optional[str] = None
    max_internal_pages: int = Field(default=3, ge=0, le=5)
    viewports: List[str] = Field(default_factory=lambda: ["desktop", "mobile"])
    wait_ms: int = Field(default=1500, ge=0, le=8000)
    timeout_ms: int = Field(default=45000, ge=5000, le=90000)
    full_page: bool = Field(default=True, description="Capturar página completa.")


class SearchProviderDebugRequest(BaseModel):
    query: str = Field(..., min_length=2, description="Consulta pública a ejecutar.")
    max_results: int = Field(default=8, ge=1, le=10)
    gl: str = Field(default="ar", min_length=2, max_length=5, description="País para Serper/Google, por ejemplo ar o us.")
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
    return text[: limit - 1].rstrip() + "…"


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
        "blog_or_news": any(k in both for k in ["blog", "noticias", "news", "artículo", "articulos", "podcast", "newsletter"]),
        "testimonials_or_clients": any(k in both for k in ["testimonio", "testimonios", "clientes", "casos", "reseñas", "reviews", "logos", "empresas que confían", "confían en"]),
        "services_or_products": any(k in both for k in ["servicio", "servicios", "producto", "productos", "soluciones", "plans", "planes", "consultoría", "consultoria"]),
        "website_claims": any(k in both for k in ["años de experiencia", "clientes satisfechos", "tasa de éxito", "premios", "líder", "lider", "garantía", "garantia", "%", "casos de éxito"]),
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
                    "label_es": f"Datos públicos de {platform}",
                    "status": "not_collected",
                    "why_not_collected": "No se recibió un link para esta fuente.",
                    "attempted_tools": [report.get("tool_used")],
                    "importance": "media",
                    "can_be_collected_publicly": "variable",
                    "how_to_collect": [f"Proveer el link público correcto de {platform}."] + report.get("how_to_collect_missing", []),
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
                    "can_be_collected_publicly": "sí, si la API key está configurada y el dato es público",
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
                    "why_not_collected": report.get("reason") or "El dato no apareció en la recolección pública.",
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
        ("meta_ads.reach_impressions_clicks", "alcance, impresiones y clics de campañas"),
        ("crm.lead_quality", "calidad de lead"),
        ("sales.revenue_close", "ventas, revenue y cierre"),
    ]:
        guide.append(
            {
                "platform": field.split(".")[0],
                "field": field,
                "label_es": label,
                "status": "requires_owner_access",
                "why_not_collected": "No es información pública; requiere acceso del cliente o export manual.",
                "attempted_tools": [],
                "importance": "alta",
                "can_be_collected_publicly": "no",
                "how_to_collect": [
                    "Solicitar acceso del cliente a la plataforma correspondiente.",
                    "Aceptar export CSV/Excel o capturas fechadas si no se puede conectar API.",
                    "Registrar período analizado y fuente exacta del dato.",
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
        ("services_or_products", "services_or_products", "Señales de servicios/productos detectadas"),
        ("pricing", "pricing", "Señales de precios/planes detectadas"),
        ("faq", "faq", "Señales de FAQ/preguntas frecuentes detectadas"),
        ("blog_or_news", "blog_or_news", "Señales de blog/noticias/contenido detectadas"),
        ("testimonials_or_clients", "testimonials_or_clients", "Señales de testimonios/clientes/logos detectadas"),
        ("website_claims", "website_claims", "Claims del sitio detectados; requieren verificación externa"),
    ]:
        if features.get(fname):
            collected_fields.append(dtype)
            evidence_type = "website_claim" if dtype == "website_claims" else "website_observed"
            evidence.add(platform, normalized, collector, dtype, label, "medium", raw_excerpt=all_text[:1200], evidence_type=evidence_type)
    if features.get("tracking_scripts"):
        collected_fields.append("tracking_scripts")
        evidence.add(platform, normalized, collector, "tracking_scripts_detected", features["tracking_scripts"], "medium", limitations=["Detectar un script no prueba que el tracking esté bien configurado."])
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
        return {"reports": [collector_report(collector, platform, "failed_runtime", "firecrawl_api", normalized, reason="httpx no está disponible en el entorno.", confidence="none")], "summary": {}}
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
        "iniciar sesión",
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
        raise HTTPException(status_code=400, detail="URL inválida.")

    if not BROWSERBASE_API_KEY:
        return {
            "status": "skipped_missing_api_key",
            "collector": "browserbase_visual_debug",
            "url": normalized,
            "reason": "BROWSERBASE_API_KEY no está configurada.",
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
                "reason": "Browserbase no devolvió connect_url.",
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
                    "No afirma conversión, ventas, velocidad, Core Web Vitals ni performance.",
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
        evidence.add(platform, normalized, collector, "public_profile_metadata", parsed_data or {"title": meta.get("title"), "description": meta.get("meta_description")}, "low", raw_excerpt=text[:1000], limitations=["Datos públicos best-effort; la plataforma puede ocultar métricas o requerir login."])
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
        raise RuntimeError("httpx no está disponible")
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
        evidence.add(platform, normalized, collector, "youtube_channel_statistics", summary, "high", limitations=["subscriberCount puede estar oculto por configuración del canal."])
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
            "tavily": "Proveedor principal de discovery/search. No reemplaza Firecrawl para extracción profunda.",
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
                    "Resultado de búsqueda usado para discovery; el snippet no reemplaza extracción directa de la fuente.",
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
        level = "básica"
    else:
        level = "débil"

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
        "interpretation": "Score de presencia pública observable. No mide ventas, ROAS, CPA, CPL, conversión ni calidad de lead.",
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
            "finding": "El sitio público fue leído con collector estático y Firecrawl; hay evidencia de propuesta comercial, productos, claims y páginas indexables.",
            "evidence": "website_static_collector + firecrawl_website_collector",
            "risk_or_opportunity": "Base suficiente para auditoría pública inicial, pero conviene profundizar páginas internas críticas como compras mayoristas, contacto y categorías.",
        })
    if search_results:
        findings.append({
            "area": "Búsqueda pública",
            "finding": f"El router de búsqueda encontró {len(search_results)} resultados públicos relevantes usando Tavily.",
            "evidence": ", ".join([str(ev.get("source_url")) for ev in search_results[:4] if ev.get("source_url")]),
            "risk_or_opportunity": "Hay superficie pública suficiente para discovery; los snippets deben validarse con extracción directa antes de usarse como prueba fuerte.",
        })
    social_detected = [p for p in ["instagram", "facebook", "linkedin", "tiktok"] if (metrics.get(p) or {}).get("evidence_count", 0) > 0]
    if social_detected:
        findings.append({
            "area": "Redes sociales",
            "finding": "Se detectaron perfiles públicos en: " + ", ".join(social_detected) + ".",
            "evidence": "metadata pública best-effort",
            "risk_or_opportunity": "Las plataformas limitan métricas y posteos sin autorización; para análisis de performance hacen falta accesos o export manual del cliente.",
        })
    if linkedin_samples:
        findings.append({
            "area": "LinkedIn",
            "finding": "LinkedIn entregó señales públicas útiles, incluyendo título, muestra textual y followers visibles cuando estuvieron disponibles.",
            "evidence": "linkedin_public_collector",
            "risk_or_opportunity": "Puede usarse como evidencia pública de posicionamiento B2B, no como insight interno de performance.",
        })

    recommendations = [
        {
            "priority": "alta",
            "action": "Validar y extraer páginas internas descubiertas por búsqueda: sobre-nosotros, compras-mayoristas, sucursales-contacto y categorías comerciales.",
            "impact": "alto",
            "effort": "medio",
            "reason": "El discovery ya encontró URLs de valor; falta convertirlas en evidencia extraída y resumida.",
        },
        {
            "priority": "alta",
            "action": "Separar claramente evidencia pública, claims declarados y datos que requieren acceso privado.",
            "impact": "alto",
            "effort": "bajo",
            "reason": "Evita inferencias falsas sobre ventas, performance o calidad de lead.",
        },
        {
            "priority": "media-alta",
            "action": "Usar Browserbase visual debug para capturar screenshots de home, contacto, compras mayoristas y perfiles sociales prioritarios.",
            "impact": "medio-alto",
            "effort": "medio",
            "reason": "Aporta prueba visual cuando HTML/Firecrawl no alcanza o la página depende de JavaScript.",
        },
        {
            "priority": "media",
            "action": "Solicitar al cliente exports o capturas fechadas de Meta Business Suite, LinkedIn, TikTok, GA4, Search Console y CRM si se quiere diagnosticar performance.",
            "impact": "alto",
            "effort": "alto",
            "reason": "Los datos internos no son públicos y no deben inferirse desde presencia pública.",
        },
    ]

    matrix = [
        {"initiative": "Deduplicar y compactar datos faltantes en el reporte", "impact": "medio", "effort": "bajo"},
        {"initiative": "Extraer páginas internas descubiertas por Tavily con Firecrawl", "impact": "alto", "effort": "medio"},
        {"initiative": "Capturar screenshots con Browserbase para evidencia visual", "impact": "medio-alto", "effort": "medio"},
        {"initiative": "Conectar datos privados del cliente para performance real", "impact": "muy alto", "effort": "alto"},
    ]

    return {
        "summary": f"La presencia pública observable es {score.get('level')} ({score.get('score')}/100). El sistema encontró sitio, evidencia textual, perfiles/redes y resultados públicos; las métricas de performance siguen fuera de alcance sin acceso del cliente.",
        "readiness_level": score.get("level"),
        "score": score.get("score"),
        "key_findings": findings,
        "priority_recommendations": recommendations,
        "impact_effort_matrix": matrix,
        "critical_limitations": [
            "No mide ventas, ROAS, CPA, CPL, conversión ni calidad de lead.",
            "Los snippets de búsqueda sirven para discovery, no como prueba definitiva.",
            "Instagram, Facebook, LinkedIn y TikTok pueden ocultar métricas o requerir login/API/autorización.",
        ],
        "next_data_requests": [
            "GA4 / Search Console para tráfico orgánico, eventos y páginas principales.",
            "Google Ads / Meta Ads para inversión, leads, costos y conversiones.",
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

    lines.append("AUDITORÍA DE PRESENCIA DIGITAL PÚBLICA")
    lines.append("=" * 58)
    lines.append("")
    lines.append(f"Empresa: {payload.get('company_name') or 'No informada'}")
    lines.append(f"Fecha de recolección: {payload.get('created_at')}")
    lines.append(f"Versión del collector: {payload.get('collector_version')}")
    lines.append(f"Estado general: {payload.get('collection_status')}")
    lines.append(f"Hash de recolección: {payload.get('collection_hash')}")
    lines.append("")

    lines.append("1. RESUMEN EJECUTIVO")
    lines.append(audit.get("summary") or "No se generó resumen ejecutivo.")
    lines.append("")
    lines.append(f"Score de presencia pública: {score.get('score', 'n/d')}/100")
    lines.append(f"Nivel: {score.get('level', 'n/d')}")
    lines.append("Nota: este score mide presencia pública observable, no performance comercial.")
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
        lines.append("Señales usadas:")
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

    lines.append("9. DATOS FALTANTES CRÍTICOS")
    critical = [x for x in recovery_deduped if x.get("requires_client_permission") or x.get("importance") in {"alta", "media-alta"}]
    if critical:
        for item in critical[:18]:
            lines.append("")
            lines.append(f"Campo: {item.get('label_es')} ({item.get('field')})")
            lines.append(f"Plataforma: {item.get('platform')} | Importancia: {item.get('importance')} | Permiso cliente: {'sí' if item.get('requires_client_permission') else 'no'}")
            lines.append(f"Motivo: {item.get('why_not_collected')}")
            how = item.get("how_to_collect") or []
            if how:
                lines.append("Cómo recuperarlo: " + " | ".join([str(x) for x in how[:3]]))
    else:
        lines.append("- No se detectaron faltantes críticos.")
    lines.append("")

    lines.append("10. DATOS QUE REQUIEREN ACCESO DEL CLIENTE")
    for item in audit.get("next_data_requests") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("11. LIMITACIONES Y GUARDRAILS")
    for item in audit.get("critical_limitations") or []:
        lines.append(f"- {item}")
    lines.append("- Los claims del sitio se registran como claims declarados, no como hechos verificados externamente.")
    lines.append("- Este reporte no afirma ROAS, CPA, CPL, conversión, ventas ni calidad de lead.")
    lines.append("")

    lines.append("12. ANEXO TÉCNICO - RESUMEN DE EJECUCIÓN")
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
        "visual_site": "POST /audit/visual-site renderiza home y páginas internas candidatas en desktop/mobile para resumen visual estructurado.",
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
            "GET /deliverables/social-text/{report_id}.txt",
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
            "GET /debug/search-provider-config",
            "POST /debug/search-test",
            "POST /debug/browser-render",
            "POST /audit/visual-site",
            "POST /audit/social-public",
            "GET /deliverables/social-text/{report_id}.txt",
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
    text = payload.get("text") or payload.get("query") or "Search public web for Cotillón Chialvo Córdoba and return public URLs."
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

    # Fallback regex básico si BeautifulSoup no estuviera disponible.
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
            "Alta cantidad de links puede indicar catálogo amplio o navegación compleja; no prueba mala conversión por sí sola.",
            "Imágenes sin alt afectan accesibilidad/SEO básico observable; no prueban ranking orgánico.",
            "Screenshots permiten evaluar fricción visual observable; no reemplazan UX research, PageSpeed ni datos de conversión.",
        ],
    }


async def audit_visual_site_summary(req: VisualSiteAuditRequest) -> Dict[str, Any]:
    raw_url = req.url or req.website
    normalized = normalize_url(raw_url)

    if not normalized:
        raise HTTPException(status_code=400, detail="URL inválida. Enviar url o website.")

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
            "Este endpoint recolecta evidencia visual pública observable; no mide conversiones, ventas, ROAS, CPA ni margen.",
            "No reemplaza PageSpeed, Core Web Vitals, heatmaps ni pruebas de usuario.",
            "La selección de categoría/producto/contacto es heurística sobre links públicos; puede requerir validación manual.",
            "Algunas páginas pueden variar por cookies, geolocalización, login, stock o contenido dinámico.",
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
        r"\b\d{1,2}\s+de\s+[a-záéíóúñ]+\s+de\s+\d{4}\b",
        r"\b\d{1,2}\s+de\s+[a-záéíóúñ]+\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\b",
        r"\b\d+\s+(d|h|min|days|hours|minutes|días|horas|minutos)\b",
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
        "product_or_catalog": ["producto", "productos", "catálogo", "catalogo", "stock", "comprar", "precio", "oferta"],
        "promotions": ["promo", "promoción", "promocion", "descuento", "off", "cuotas", "envío", "envio"],
        "events": ["evento", "eventos", "cumpleaños", "egresados", "fiesta", "cumple", "casamiento", "despedida"],
        "b2b_or_wholesale": ["mayorista", "minorista", "revendedor", "distribución", "distribucion", "importador", "importadores"],
        "social_proof": ["cliente", "clientes", "testimonio", "reseña", "reviews", "seguidores"],
        "video_or_reels": ["reel", "reels", "video", "videos", "viral", "visualizaciones", "views"],
        "cta": ["link", "whatsapp", "mensaje", "consult", "comprar", "contact", "contacto", "ver más", "ver mas"],
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
        " · ",
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
        r"(like|likes|me gusta|comentario|comentarios|comments|views|visualizaciones|reproducciones|followers|seguidores|reel|post|publicaci[oó]n|hoy|ayer|\d{1,2}/\d{1,2}/\d{2,4}|october|november|december|january|february|march|april|may|june|july|august|september)",
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

    # Query deliberadamente filtrada por plataforma para reducir contaminación cruzada.
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
                "Solo platform_results se usan para extraer métricas candidatas de la plataforma. "
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




async def _sp_browser_render(platform: str, url: str, req: SocialPublicAuditRequest) -> Dict[str, Any]:
    if not req.use_browser_render:
        return {
            "status": "skipped",
            "reason": "use_browser_render=false",
        }

    if "render_browserbase_visual" not in globals():
        return {
            "status": "skipped_missing_dependency",
            "reason": "render_browserbase_visual no disponible.",
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

        return {
            "status": result.get("status"),
            "final_url": result.get("final_url"),
            "http_status": result.get("http_status"),
            "page_title": result.get("page_title"),
            "screenshot_url": screenshot.get("screenshot_url"),
            "screenshot_id": screenshot.get("screenshot_id"),
            "text_sample": _sp_trunc(summary.get("text_sample"), req.max_visible_text_chars),
            "links_count": summary.get("links_count"),
            "forms_count": summary.get("forms_count"),
            "images_count": summary.get("images_count"),
            "visible_ctas": summary.get("visible_ctas") or [],
            "limitations": result.get("limitations") or [],
        }

    except Exception as exc:
        return {
            "status": "failed",
            "reason": str(exc),
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
    # Los valores extraídos desde HTML/snippets/render son candidatos textuales.
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
            "Las métricas visibles son candidatos textuales de HTML/snippets/render. "
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

    # Máximo medium porque la evidencia pública social puede venir de HTML/snippets/render,
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
        "Las métricas sociales visibles se tratan como candidatos públicos, no como analytics nativo."
    )

    if fetch_status != "completed":
        limitations.append("La lectura pública directa fue parcial, fallida o bloqueada.")

    if search_status not in ("completed", "skipped"):
        limitations.append("La búsqueda pública fue parcial, fallida o no disponible.")

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
            "public_observed_field": "perfil público / identidad",
            "real_data_to_request": "captura fechada o acceso autorizado al perfil/cuenta",
            "source_expected": "plataforma nativa o captura fechada",
            "why": "Validar que el perfil leído corresponde a la marca y no a un resultado ambiguo.",
        },
        {
            "public_observed_field": "seguidores visibles",
            "real_data_to_request": "seguidores actuales y evolución últimos 90/180 días",
            "source_expected": "Insights nativos",
            "why": "Contrastar visibilidad pública contra crecimiento real.",
        },
        {
            "public_observed_field": "posts/fechas/interacciones visibles",
            "real_data_to_request": "export de últimos 30/60/90 contenidos con fecha, formato, alcance, impresiones, views, likes, comentarios, guardados, compartidos, clics y mensajes",
            "source_expected": "Meta Business Suite / LinkedIn Analytics / TikTok Analytics / YouTube Studio",
            "why": "Calcular frecuencia, engagement y performance real con datos confiables.",
        },
        {
            "public_observed_field": "clics / mensajes / leads",
            "real_data_to_request": "clics al link, clics a WhatsApp, mensajes, formularios, leads y tasa de respuesta",
            "source_expected": "Insights + CRM + WhatsApp/Inbox",
            "why": "Medir si el contenido genera acciones comerciales, no solo interacción.",
        },
        {
            "public_observed_field": "ventas atribuidas",
            "real_data_to_request": "ventas/leads por campaña, contenido, UTMs o CRM",
            "source_expected": "GA4, Ads, CRM, ecommerce backend",
            "why": "No inferir ventas desde métricas sociales públicas.",
        },
    ]

    if platform == "linkedin":
        common.append({
            "public_observed_field": "señal B2B",
            "real_data_to_request": "impresiones, clics, seguidores, visitantes, leads, cargos/industrias y posteos de empresa",
            "source_expected": "LinkedIn Analytics / CRM",
            "why": "Validar si LinkedIn aporta confianza B2B o generación de demanda.",
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

    # Solo resultados del mismo dominio/plataforma alimentan métricas candidatas.
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

    return {
        "platforms_analyzed": len(platform_reports),
        "platforms_with_any_visible_metrics": platforms_with_any_metrics,
        "platforms_with_engagement_possible": platforms_with_engagement_possible,
        "platforms_with_frequency_possible": platforms_with_frequency_possible,
        "platforms_partial_or_blocked": platforms_blocked_or_partial,
        "global_limitations": [
            "Las plataformas sociales pueden ocultar datos públicos, requerir login, bloquear HTML o entregar contenido regionalizado.",
            "Los snippets de búsqueda sirven como discovery y evidencia débil/media, no reemplazan analytics nativos.",
            "No afirmar engagement, frecuencia, alcance, clics, mensajes, ventas ni calidad de audiencia sin datos suficientes.",
            "Calcular engagement solo si existen seguidores visibles e interacciones visibles suficientes.",
            "Calcular frecuencia solo si existen fechas y publicaciones visibles suficientes.",
        ],
        "owner_exports_required": [
            "Meta Business Suite: alcance, impresiones, seguidores, clics, mensajes, guardados, compartidos y contenidos últimos 90 días.",
            "Instagram Insights: posts/reels con fecha, formato, alcance, views, likes, comentarios, guardados, shares y clics.",
            "Facebook Insights: alcance, reacciones, comentarios, compartidos, clics, mensajes y crecimiento.",
            "LinkedIn Analytics: followers, impresiones, clics, visitantes, interacciones, posteos y datos de audiencia.",
            "TikTok Analytics: videos, views, retención, likes, comentarios, shares, seguidores y tráfico al perfil.",
            "YouTube Studio: videos, views, retención, CTR, suscriptores, tráfico y engagement.",
            "CRM/WhatsApp: consultas, tasa de respuesta, calidad de lead, cierre y ventas atribuidas.",
        ],
    }


def _sp_txt(payload: Dict[str, Any]) -> str:
    lines: List[str] = []

    lines.append("AUDITORÍA SOCIAL PÚBLICA EXHAUSTIVA")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Empresa: {payload.get('company_name') or 'No especificada'}")
    lines.append(f"Fecha de recolección: {payload.get('retrieved_at')}")
    lines.append(f"Versión del collector: {payload.get('version')}")
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
    lines.append(f"Con alguna métrica visible: {summary.get('platforms_with_any_visible_metrics')}")
    lines.append(f"Engagement calculable con evidencia pública estructurada: {summary.get('platforms_with_engagement_possible')}")
    lines.append(f"Frecuencia calculable con evidencia pública estructurada: {summary.get('platforms_with_frequency_possible')}")
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
        lines.append("Lectura pública directa")
        lines.append(f"- status: {fetch.get('status')}")
        lines.append(f"- http_status: {fetch.get('http_status')}")
        lines.append(f"- final_url: {fetch.get('final_url')}")
        lines.append(f"- content_type: {fetch.get('content_type')}")
        lines.append(f"- html_length: {fetch.get('html_length')}")
        lines.append(f"- reason: {fetch.get('reason')}")

        identity = report.get("public_identity") or {}
        lines.append("")
        lines.append("Identidad pública detectada")
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
        lines.append("Métricas visibles detectadas")
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
            lines.append(f"- limitación: {limitation}")

        lines.append("")
        lines.append("Plan de contraste contra datos reales")
        for row in report.get("contrast_plan") or []:
            lines.append(f"- Campo público: {row.get('public_observed_field')}")
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
    lines.append("- Los snippets de búsqueda son señales de discovery, no analytics nativo.")
    lines.append("- La información social pública puede estar incompleta por login, bloqueo, región, HTML dinámico o cambios de plataforma.")
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


@app.post("/audit/social-public")
async def audit_social_public(req: SocialPublicAuditRequest, _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    import uuid as _uuid

    sources = _sp_inputs(req)

    if not sources:
        raise HTTPException(
            status_code=400,
            detail="Enviar al menos un link social público: instagram, facebook, linkedin, tiktok, youtube o x.",
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
            "Módulo basado en evidencia pública observable, HTML público, search discovery y render opcional.",
            "No reemplaza Meta Business Suite, Instagram Insights, Facebook Insights, LinkedIn Analytics, TikTok Analytics, YouTube Studio ni CRM.",
            "No calcula engagement/frecuencia si faltan seguidores, fechas, publicaciones o interacciones visibles suficientes.",
            "No afirma ventas, ROAS, CPA, CPL, tráfico, conversión, margen ni calidad de lead.",
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
        raise HTTPException(status_code=400, detail="Se requiere al menos un link público: sitio web o red social.")

    evidence = EvidenceBuilder()
    reports: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}

    # Declared input evidence, clearly separated from observed evidence.
    if req.company_name:
        evidence.add("declared_input", None, "input_parser", "company_name", req.company_name, "medium", evidence_type="declared_input")
    for platform, url in assets.items():
        if url:
            evidence.add(platform, url, "input_parser", "asset_url_declared", url, "low", limitations=["Un link declarado no prueba que el contenido haya sido leído."], evidence_type="declared_input")

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
            "No afirmar performance, ROAS, CPA, CPL, conversión, ventas ni calidad de lead con este output.",
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






