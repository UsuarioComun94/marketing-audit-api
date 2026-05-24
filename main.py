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

APP_VERSION = "public-presence-collector-mvp-0.3"
API_KEY = os.getenv("API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://marketing-audit-api.onrender.com").rstrip("/")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "").strip()
BROWSERBASE_API_KEY = os.getenv("BROWSERBASE_API_KEY", "").strip()
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY", "").strip()
COMPOSIO_API_BASE = os.getenv("COMPOSIO_API_BASE", "https://backend.composio.dev/api/v3.1").rstrip("/")
COMPOSIO_DEFAULT_USER_ID = os.getenv("COMPOSIO_DEFAULT_USER_ID", "default").strip() or "default"
COMPOSIO_CONNECTED_ACCOUNT_ID = os.getenv("COMPOSIO_CONNECTED_ACCOUNT_ID", "").strip()
COMPOSIO_SEARCH_TOOL_SLUG = os.getenv("COMPOSIO_SEARCH_TOOL_SLUG", "").strip()
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


async def collect_composio_search_placeholder(company_name: Optional[str], website: Optional[str]) -> Dict[str, Any]:
    collector = "composio_search_enrichment_collector"
    platform = "search"

    if not company_name and not website:
        return {
            "reports": [
                collector_report(
                    collector,
                    platform,
                    "skipped_missing_input",
                    "composio_search",
                    None,
                    intended_data=["public_search_results", "possible_profiles", "mentions"],
                    reason_code="missing_input",
                    confidence="none",
                )
            ],
            "summary": {},
        }

    if not COMPOSIO_API_KEY:
        return {
            "reports": [
                collector_report(
                    collector,
                    platform,
                    "skipped_missing_api_key",
                    "composio_search",
                    website,
                    intended_data=["public_search_results", "possible_profiles", "mentions"],
                    reason_code="missing_api_key",
                    confidence="none",
                )
            ],
            "summary": {},
        }

    if not COMPOSIO_SEARCH_TOOL_SLUG:
        tools_result = await composio_list_tools("search_api", "search")
        return {
            "reports": [
                collector_report(
                    collector,
                    platform,
                    "collector_not_configured",
                    "composio_search",
                    website,
                    intended_data=["public_search_results", "possible_profiles", "mentions"],
                    collected_fields=["composio_tools_lookup"] if tools_result.get("ok") else [],
                    missing_fields=["public_search_results", "possible_profiles", "mentions"],
                    reason_code="missing_composio_search_tool_slug",
                    confidence="none",
                    details={
                        "message": "COMPOSIO_SEARCH_TOOL_SLUG no esta configurado. Usar /debug/composio-tools para descubrir el slug correcto.",
                        "tools_lookup_status_code": tools_result.get("status_code"),
                        "tools_lookup_ok": tools_result.get("ok"),
                        "tools_lookup_sample": tools_result.get("data"),
                    },
                )
            ],
            "summary": {
                "configured": False,
                "reason": "missing_composio_search_tool_slug",
                "tools_lookup": tools_result,
            },
        }

    query_parts = []
    if company_name:
        query_parts.append(company_name)
    if website:
        query_parts.append(website)

    query = " ".join(query_parts).strip()
    task_text = (
        "Search public web for this company/site and return public URLs, social profiles, mentions, "
        f"and relevant public evidence only. Query: {query}"
    )

    result = await composio_execute_tool(
        tool_slug=COMPOSIO_SEARCH_TOOL_SLUG,
        text=task_text,
        user_id=COMPOSIO_DEFAULT_USER_ID,
    )

    summary = {
        "query": query,
        "tool_slug": COMPOSIO_SEARCH_TOOL_SLUG,
        "user_id": COMPOSIO_DEFAULT_USER_ID,
        "connected_account_id": COMPOSIO_CONNECTED_ACCOUNT_ID or None,
        "composio_ok": result.get("ok"),
        "composio_status_code": result.get("status_code"),
        "composio_error": result.get("error"),
        "composio_response": result.get("data"),
    }

    status = "completed" if result.get("ok") else "failed_runtime"
    reason_code = None if result.get("ok") else "composio_execution_failed"
    confidence = "medium" if result.get("ok") else "none"

    return {
        "reports": [
            collector_report(
                collector,
                platform,
                status,
                "composio_search",
                website,
                intended_data=["public_search_results", "possible_profiles", "mentions"],
                collected_fields=["public_search_results_raw"] if result.get("ok") else [],
                missing_fields=[] if result.get("ok") else ["public_search_results", "possible_profiles", "mentions"],
                reason_code=reason_code,
                confidence=confidence,
                details=summary,
            )
        ],
        "summary": summary,
    }

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


def build_metrics_summary(evidence_items: List[Dict[str, Any]], collector_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_platform: Dict[str, Dict[str, Any]] = {}
    for ev in evidence_items:
        platform = ev.get("platform") or "unknown"
        bucket = by_platform.setdefault(platform, {"evidence_count": 0, "data_types": []})
        bucket["evidence_count"] += 1
        bucket["data_types"].append(ev.get("data_type"))
    for platform in by_platform:
        by_platform[platform]["data_types"] = sorted(set([x for x in by_platform[platform]["data_types"] if x]))
    for report in collector_reports:
        platform = report.get("platform") or "unknown"
        bucket = by_platform.setdefault(platform, {"evidence_count": 0, "data_types": []})
        bucket["collector_status"] = report.get("status")
        bucket["confidence"] = report.get("confidence")
    return by_platform


def build_txt_report(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("REPORTE DE RECOLECCIÓN DE PRESENCIA PÚBLICA")
    lines.append("=" * 58)
    lines.append("")
    lines.append(f"Empresa: {payload.get('company_name') or 'No informada'}")
    lines.append(f"Fecha de recolección: {payload.get('created_at')}")
    lines.append(f"Versión del collector: {payload.get('collector_version')}")
    lines.append(f"Estado general: {payload.get('collection_status')}")
    lines.append(f"Hash de recolección: {payload.get('collection_hash')}")
    lines.append("")
    lines.append("FUENTES RECIBIDAS")
    for k, v in (payload.get("assets_received") or {}).items():
        lines.append(f"- {k}: {v or 'no recibido'}")
    lines.append("")
    lines.append("1. RESUMEN DE EJECUCIÓN")
    rep = payload.get("collection_execution_report") or {}
    for key in ["collectors_attempted_or_evaluated", "collectors_completed", "collectors_partial", "collectors_skipped", "collectors_failed", "collectors_blocked_by_platform", "collectors_not_implemented"]:
        lines.append(f"- {key}: {rep.get(key, 0)}")
    lines.append("")
    lines.append("2. ESTADO POR COLLECTOR")
    for r in payload.get("collector_reports", []):
        lines.append("")
        lines.append(f"Collector: {r.get('collector')}")
        lines.append(f"Plataforma: {r.get('platform')}")
        lines.append(f"Estado: {r.get('status')}")
        lines.append(f"Herramienta usada: {r.get('tool_used')}")
        lines.append(f"URL/input: {r.get('input_url') or 'no aplica'}")
        if r.get("reason"):
            lines.append(f"Motivo: {r.get('reason')}")
        collected = r.get("collected_fields") or []
        missing = r.get("missing_fields") or []
        lines.append("Datos recolectados:")
        if collected:
            for f in collected:
                lines.append(f"  - {f}")
        else:
            lines.append("  - ninguno")
        lines.append("Datos no recolectados:")
        if missing:
            for f in missing[:40]:
                lines.append(f"  - {f}")
        else:
            lines.append("  - ninguno")
        how = r.get("how_to_collect_missing") or []
        if how:
            lines.append("Cómo obtener lo faltante:")
            for step in how:
                lines.append(f"  - {step}")
    lines.append("")
    lines.append("3. RESUMEN DE MÉTRICAS / DATOS OBSERVADOS")
    summary = payload.get("metrics_summary") or {}
    for platform, data in summary.items():
        lines.append(f"\n{platform.upper()}")
        lines.append(f"- Evidencias registradas: {data.get('evidence_count', 0)}")
        lines.append(f"- Estado del collector: {data.get('collector_status', 'n/d')}")
        lines.append(f"- Confianza: {data.get('confidence', 'n/d')}")
        types = data.get("data_types") or []
        if types:
            lines.append("- Tipos de datos observados: " + ", ".join(types))
    lines.append("")
    lines.append("4. EVIDENCIA RECOLECTADA")
    for ev in payload.get("evidence_registry", []):
        lines.append("")
        lines.append(f"{ev.get('evidence_id')} | {ev.get('platform')} | {ev.get('data_type')}")
        lines.append(f"Fuente: {ev.get('source_url') or 'n/d'}")
        lines.append(f"Collector: {ev.get('collector')}")
        lines.append(f"Tipo de evidencia: {ev.get('evidence_type')}")
        lines.append(f"Confianza: {ev.get('confidence')}")
        value = ev.get("value")
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            value_text = str(value)
        lines.append("Valor observado:")
        lines.append(truncate(value_text, 1400))
        if ev.get("limitations"):
            lines.append("Limitaciones:")
            for lim in ev.get("limitations", []):
                lines.append(f"  - {lim}")
    lines.append("")
    lines.append("5. DATOS NO RECOLECTADOS Y CÓMO RECUPERARLOS")
    for item in payload.get("field_recovery_guide", []):
        lines.append("")
        lines.append(f"Campo: {item.get('label_es')} ({item.get('field')})")
        lines.append(f"Plataforma: {item.get('platform')}")
        lines.append(f"Estado: {item.get('status')}")
        lines.append(f"Por qué no se recopiló: {item.get('why_not_collected')}")
        lines.append(f"Importancia: {item.get('importance')}")
        lines.append(f"Requiere permiso del cliente: {'sí' if item.get('requires_client_permission') else 'no'}")
        lines.append("Cómo se puede recopilar:")
        for step in item.get("how_to_collect", [])[:8]:
            lines.append(f"  - {step}")
    lines.append("")
    lines.append("6. DATOS QUE REQUIEREN ACCESO DEL CLIENTE")
    lines.append("- Google Analytics / GA4: tráfico, eventos, conversiones, fuentes y landings.")
    lines.append("- Search Console: queries, clicks, impresiones, CTR, posición media y páginas orgánicas.")
    lines.append("- Google Ads / Meta Ads: inversión, impresiones, clics, leads, conversiones y costos.")
    lines.append("- Instagram/Facebook/LinkedIn/TikTok Insights: alcance, impresiones, demografía, visitas, guardados y clicks.")
    lines.append("- CRM/ventas: calidad de lead, contacto efectivo, cierre, ventas y revenue.")
    lines.append("")
    lines.append("7. LIMITACIONES DEL REPORTE")
    lines.append("- Este archivo recopila presencia pública observable; no diagnostica performance comercial.")
    lines.append("- No afirma ROAS, CPA, CPL real, conversión, ventas ni calidad de lead.")
    lines.append("- Los datos de redes sociales públicas pueden estar incompletos por restricciones de plataforma.")
    lines.append("- Los claims del sitio se registran como claims declarados, no como hechos verificados externamente.")
    return "\n".join(lines) + "\n"



def build_api_capabilities() -> Dict[str, Any]:
    return {
        "current_scope": "public_presence_collection",
        "implemented": {
            "website_static": True,
            "firecrawl_website": bool(FIRECRAWL_API_KEY),
            "browserbase_visual_debug": bool(BROWSERBASE_API_KEY),
            "youtube_data_api": bool(YOUTUBE_API_KEY),
            "text_report": True,
            "public_social_limited": True,
        },
        "configured_but_not_implemented": {
            "browserbase_collect_integration": False,
            "composio_search_enrichment": bool(COMPOSIO_API_KEY and COMPOSIO_SEARCH_TOOL_SLUG),
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
        "composio": "Integracion Composio agregada. Usar /debug/composio-tools para descubrir tool_slug y COMPOSIO_SEARCH_TOOL_SLUG para ejecutar enrichment.",
        "visual": "GET /deliverables/screenshot/{screenshot_id}.png devuelve screenshots generados por debugBrowserRender.",
    }


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "marketing-auditor-public-presence-collector",
        "version": APP_VERSION,
        "endpoints": [
            "GET /api/status",
            "POST /debug/browser-render",
            "GET /debug/composio-tools",
            "POST /debug/composio-execute",
            "POST /collect/public-presence",
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
            "youtube": bool(YOUTUBE_API_KEY),
        },
        "capabilities": build_api_capabilities(),
        "endpoints": [
            "GET /",
            "GET /api/status",
            "GET /debug/collector-config",
            "POST /debug/browser-render",
            "GET /debug/composio-tools",
            "POST /debug/composio-execute",
            "POST /collect/public-presence",
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
            "youtube": bool(YOUTUBE_API_KEY),
        },
        "notes": build_collector_notes(),
    }


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

    composio_result = await collect_composio_search_placeholder(req.company_name, assets.get("website"))
    reports.extend(composio_result["reports"])
    summaries["composio_search"] = composio_result["summary"]

    execution = summarize_execution(reports)
    recovery = build_recovery_guide(reports)
    metrics_summary = build_metrics_summary(evidence.items, reports)
    unavailable_data = [
        {"platform": g.get("platform"), "field": g.get("field"), "reason": g.get("why_not_collected")}
        for g in recovery
        if g.get("status") in {"not_collected", "requires_owner_access"}
    ]
    requires_owner_access = [g for g in recovery if g.get("requires_client_permission")]

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
        "field_recovery_guide": recovery,
        "unavailable_data": unavailable_data,
        "requires_owner_access": requires_owner_access,
        "tool_summaries": summaries,
        "txt_report": {},
        "non_analysis_guards": [
            "Este endpoint solo recolecta presencia pública; no genera diagnóstico comercial.",
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





