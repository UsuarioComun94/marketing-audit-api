import os
import html
import uuid
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException, Security
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field


app = FastAPI(
    title="Marketing Audit API",
    description="API para auditar prospectos, investigar presencia pública y devolver información estructurada a un Custom GPT.",
    version="1.3.0",
    servers=[
        {
            "url": "https://marketing-audit-api.onrender.com",
            "description": "Render production server",
        }
    ],
)


API_KEY = os.getenv("API_KEY", "dev-key")
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_BASE_URL = "https://backend.composio.dev/api/v3.1"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://marketing-audit-api.onrender.com")
VISUAL_REPORT_STORE: Dict[str, str] = {}

ALLOWED_COMPOSIO_TOOLS = {
    "SEARCH_API_SEARCH",
    "SEARCH_API_LOCATIONS",
    "COMPOSIO_SEARCH_DUCK_DUCK_GO_SEARCH",
}

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="API key inválida o ausente")
    return api_key


class ProspectAuditRequest(BaseModel):
    company_name: str = Field(..., description="Nombre de la empresa o prospecto")
    website: Optional[str] = Field(None, description="Sitio web de la empresa")
    instagram: Optional[str] = Field(None, description="Perfil de Instagram")
    linkedin: Optional[str] = Field(None, description="Perfil de LinkedIn")
    industry: Optional[str] = Field(None, description="Rubro o industria del prospecto")
    offer: Optional[str] = Field(None, description="Oferta principal del prospecto")
    notes: Optional[str] = Field(None, description="Notas adicionales sobre el prospecto")


class ProspectAuditResponse(BaseModel):
    company_name: str
    audit_type: str
    awareness_level: str
    primary_bottleneck: str
    detected_focus_areas: List[str]
    commercial_risk: str
    recommended_angle: str
    next_step: str
    do_not_give_for_free: List[str]
    confidence: str


class ReportBriefRequest(BaseModel):
    company_name: str = Field(..., description="Nombre de la empresa o prospecto")
    awareness_level: Optional[str] = Field(None, description="Nivel de awareness detectado")
    primary_bottleneck: Optional[str] = Field(None, description="Principal cuello de botella")
    audit_findings: List[str] = Field(..., description="Hallazgos principales de la auditoría")


class ReportBriefResponse(BaseModel):
    company_name: str
    report_type: str
    report_sections: List[str]
    opening_angle: str
    recommended_close: str
    do_not_include: List[str]


class ToolInfo(BaseModel):
    slug: str
    name: Optional[str] = None
    toolkit: Optional[str] = None
    description: Optional[str] = None


class ToolkitStatus(BaseModel):
    toolkit: str
    available: bool
    tool_count: int
    sample_tools: List[str]
    error: Optional[str] = None


class ToolsStatusResponse(BaseModel):
    composio_configured: bool
    checked_toolkits: List[ToolkitStatus]
    recommendation: str


class ToolsSearchRequest(BaseModel):
    query: str = Field(..., description="Texto para buscar herramientas")
    toolkit_slug: Optional[str] = Field(None, description="Toolkit específico")
    limit: int = Field(10, description="Cantidad máxima de herramientas a devolver")


class ToolsSearchResponse(BaseModel):
    query: str
    toolkit_slug: Optional[str]
    results: List[ToolInfo]


class ToolDetailsResponse(BaseModel):
    tool_slug: str
    raw_response: Dict[str, Any]


class ToolExecuteRequest(BaseModel):
    tool_slug: str = Field(..., description="Slug exacto de la herramienta de Composio")
    arguments: Optional[Dict[str, Any]] = Field(None, description="Argumentos estructurados")
    text: Optional[str] = Field(None, description="Instrucción en lenguaje natural")
    user_id: str = Field("default", description="Identificador del usuario en Composio")


class ToolExecuteResponse(BaseModel):
    tool_slug: str
    successful: Optional[bool] = None
    data: Optional[Any] = None
    error: Optional[Any] = None
    raw_response: Dict[str, Any]


class PublicPresenceRequest(BaseModel):
    company_name: str = Field(..., description="Nombre de la empresa a investigar")
    industry: Optional[str] = Field(None, description="Rubro o industria")
    city: Optional[str] = Field(None, description="Ciudad o zona principal")
    country: Optional[str] = Field("Argentina", description="País de referencia")
    website: Optional[str] = Field(None, description="Sitio web conocido")
    instagram: Optional[str] = Field(None, description="Perfil de Instagram conocido")
    linkedin: Optional[str] = Field(None, description="Perfil de LinkedIn conocido")
    num_results_per_query: int = Field(5, description="Cantidad de resultados por búsqueda")


class PublicSourceResult(BaseModel):
    category: str
    query: str
    title: Optional[str] = None
    url: Optional[str] = None
    displayed_url: Optional[str] = None
    snippet: Optional[str] = None
    source: str = "search_api"


class PublicPresenceResponse(BaseModel):
    company_name: str
    research_type: str
    queries_used: List[str]
    sources_found: List[PublicSourceResult]
    presence_summary: str
    research_confidence: str
    next_step: str
    raw_result_count: int


class ReviewedPublicSource(BaseModel):
    category: str
    title: Optional[str] = None
    url: Optional[str] = None
    signal: str


class ProspectWithResearchRequest(BaseModel):
    company_name: str = Field(..., description="Nombre de la empresa o prospecto")
    industry: Optional[str] = Field(None, description="Rubro o industria")
    city: Optional[str] = Field(None, description="Ciudad o zona principal")
    country: Optional[str] = Field("Argentina", description="País de referencia")
    website: Optional[str] = Field(None, description="Sitio web conocido")
    instagram: Optional[str] = Field(None, description="Perfil de Instagram conocido")
    linkedin: Optional[str] = Field(None, description="Perfil de LinkedIn conocido")
    offer: Optional[str] = Field(None, description="Oferta principal del prospecto")
    notes: Optional[str] = Field(None, description="Notas adicionales del usuario")
    num_results_per_query: int = Field(5, description="Cantidad de resultados por búsqueda")


class IntegratedAuditBlock(BaseModel):
    awareness_level: str
    primary_bottleneck: str
    detected_focus_areas: List[str]
    commercial_risk: str
    recommended_angle: str
    confidence: str


class AwarenessStage(BaseModel):
    stage: str
    weight: int
    state: str


class AwarenessFunnelLocator(BaseModel):
    dominant_stage: str
    blocked_stage: str
    stage_distribution: List[AwarenessStage]
    explanation: str


class TemperatureHeatmapValues(BaseModel):
    attention: int
    interest: int
    intent: int
    trust: int
    action: int
    average: int


class TemperatureHeatmapRow(BaseModel):
    temperature: str
    values: TemperatureHeatmapValues


class TemperatureHeatmap(BaseModel):
    average_temperature: str
    rows: List[TemperatureHeatmapRow]
    summary: str


class DensityPoint(BaseModel):
    x: str
    y: str
    value: int


class DensityZone(BaseModel):
    x: str
    y: str
    label: str


class CustomerIntentDensityMap(BaseModel):
    x_axis: List[str]
    y_axis: List[str]
    density_points: List[DensityPoint]
    dominant_zone: DensityZone
    blocked_zone: DensityZone
    interpretation: str


class CommercialScore(BaseModel):
    overall: float
    value_proposition: int
    public_presence: int
    differentiation: int
    cta_strength: int
    trust_signals: int
    competitive_pressure: int


class ScoreInterpretation(BaseModel):
    level: str
    summary: str
    main_leverage: str
    main_risk: str


class FunnelBlueprint(BaseModel):
    current_flow: List[str]
    missing_links: List[str]
    breakpoints: List[str]
    recommended_flow: List[str]
    summary: str


class CorrectiveActionItem(BaseModel):
    issue: str
    evidence: str
    recommended_action: str
    priority: str
    effort: str
    expected_impact: str
    verification_metric: str
    do_not_give_for_free: str


class ReportPage(BaseModel):
    page: int
    title: str
    content: str
    visual_element: Optional[str] = None


class ProspectWithResearchResponse(BaseModel):
    company_name: str
    audit_type: str
    research_confidence: str
    public_sources_summary: List[ReviewedPublicSource]
    diagnosis_initial: str
    audit: IntegratedAuditBlock
    commercial_score: CommercialScore
    score_interpretation: ScoreInterpretation
    awareness_funnel_locator: AwarenessFunnelLocator
    temperature_heatmap: TemperatureHeatmap
    customer_intent_density_map: CustomerIntentDensityMap
    visual_diagram_mermaid: str
    funnel_blueprint: FunnelBlueprint
    corrective_action_plan: List[CorrectiveActionItem]
    report_pages: List[ReportPage]
    report_sections: List[str]
    report_ready_markdown: str
    do_not_give_for_free: List[str]
    next_step: str
    raw_sources_count: int


class VisualReportResponse(BaseModel):
    company_name: str
    report_id: str
    report_url: str
    awareness_funnel_svg: str
    temperature_heatmap_svg: str
    customer_intent_density_svg: str
    funnel_blueprint_svg: str
    score_chart_svg: str
    report_html: str
    report_markdown: str


def get_composio_headers() -> Dict[str, str]:
    if not COMPOSIO_API_KEY:
        raise HTTPException(status_code=500, detail="COMPOSIO_API_KEY no está configurada en el servidor")
    return {"x-api-key": COMPOSIO_API_KEY, "accept": "application/json"}


def composio_get(path: str, params: Optional[dict] = None):
    try:
        response = requests.get(
            f"{COMPOSIO_BASE_URL}{path}",
            headers=get_composio_headers(),
            params=params or {},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con Composio: {str(exc)}")

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Composio rechazó la API key. Revisá COMPOSIO_API_KEY.")
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


def composio_post(path: str, payload: Optional[dict] = None):
    try:
        response = requests.post(
            f"{COMPOSIO_BASE_URL}{path}",
            headers={**get_composio_headers(), "Content-Type": "application/json"},
            json=payload or {},
            timeout=60,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con Composio: {str(exc)}")

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Composio rechazó la API key. Revisá COMPOSIO_API_KEY.")
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


def extract_tools_list(composio_response):
    if isinstance(composio_response, list):
        return composio_response
    if isinstance(composio_response, dict):
        for key in ["items", "tools", "data"]:
            if isinstance(composio_response.get(key), list):
                return composio_response[key]
    return []


def normalize_tool(tool: dict) -> ToolInfo:
    slug = tool.get("slug") or tool.get("name") or tool.get("tool_slug") or tool.get("id") or "unknown"
    name = tool.get("name") or tool.get("display_name") or slug
    toolkit = tool.get("toolkit_slug") or tool.get("toolkit") or tool.get("app")
    description = tool.get("description") or tool.get("summary") or tool.get("display_description")
    return ToolInfo(
        slug=str(slug),
        name=str(name) if name else None,
        toolkit=str(toolkit) if toolkit else None,
        description=str(description) if description else None,
    )


def tool_matches_query(tool: dict, query: str) -> bool:
    text = " ".join([
        str(tool.get("slug", "")),
        str(tool.get("name", "")),
        str(tool.get("display_name", "")),
        str(tool.get("description", "")),
        str(tool.get("toolkit_slug", "")),
        str(tool.get("toolkit", "")),
    ]).casefold()
    return query.casefold() in text


def find_organic_results(obj: Any) -> List[dict]:
    if isinstance(obj, dict):
        for key in ["organic_results", "organic"]:
            value = obj.get(key)
            if isinstance(value, list):
                return value
        for value in obj.values():
            found = find_organic_results(value)
            if found:
                return found

    if isinstance(obj, list):
        for item in obj:
            found = find_organic_results(item)
            if found:
                return found

    return []


def execute_search_api_query(query: str, num_results: int = 5, user_id: str = "default") -> Dict[str, Any]:
    payload = {
        "user_id": user_id,
        "version": "latest",
        "arguments": {
            "engine": "google",
            "q": query,
            "num": num_results,
        },
    }
    return composio_post("/tools/execute/SEARCH_API_SEARCH", payload=payload)


def normalize_search_result(item: dict, category: str, query: str) -> PublicSourceResult:
    return PublicSourceResult(
        category=category,
        query=query,
        title=item.get("title"),
        url=item.get("link") or item.get("url"),
        displayed_url=item.get("displayed_link") or item.get("displayed_url"),
        snippet=item.get("snippet") or item.get("description"),
        source="search_api",
    )


def build_public_presence_queries(request: PublicPresenceRequest) -> List[Dict[str, str]]:
    location = " ".join([part for part in [request.city, request.country] if part])
    base = request.company_name

    queries = [
        {"category": "official_presence", "query": f"{base} sitio web oficial {location}".strip()},
        {"category": "social_profiles", "query": f"{base} Instagram LinkedIn Facebook {location}".strip()},
        {"category": "reputation", "query": f"{base} opiniones reseñas Google {location}".strip()},
    ]

    if request.industry:
        queries.append({"category": "competitors", "query": f"{request.industry} {location} competidores {base}".strip()})
    if request.website:
        queries.append({"category": "known_website", "query": f"site:{request.website} {base}".strip()})
    if request.instagram:
        queries.append({"category": "known_instagram", "query": f"{request.instagram} {base}".strip()})
    if request.linkedin:
        queries.append({"category": "known_linkedin", "query": f"{request.linkedin} {base}".strip()})

    return queries


def build_source_signal(source: PublicSourceResult) -> str:
    text = " ".join([
        source.category or "",
        source.title or "",
        source.snippet or "",
        source.url or "",
    ]).casefold()

    if source.category == "official_presence":
        return "Señal de presencia oficial o catálogo digital. Sirve para evaluar si la marca comunica diferenciación o solo disponibilidad."
    if source.category == "social_profiles":
        return "Señal de presencia social. Sirve para revisar si la comunicación construye preferencia o solo visibilidad."
    if source.category == "reputation":
        return "Señal de reputación pública. Sirve para revisar confianza, prueba social y percepción externa."
    if source.category == "competitors":
        return "Señal de contexto competitivo. Sirve para comparar si el posicionamiento propio se distingue del resto del mercado."
    if "zonaprop" in text or "argenprop" in text or "portal" in text:
        return "Señal de dependencia de portales/catálogos. Riesgo: competir por propiedad visible, precio o ubicación, no por marca."
    if "instagram" in text or "facebook" in text or "linkedin" in text:
        return "Señal de canal social. Conviene revisar si el contenido guía a una acción comercial clara."
    return "Fuente pública útil para validar presencia, mensaje, reputación o contexto competitivo."


def summarize_public_sources(
    sources: List[PublicSourceResult],
    max_sources: int = 5,
) -> List[ReviewedPublicSource]:
    summarized: List[ReviewedPublicSource] = []
    seen_urls = set()

    for source in sources:
        url = source.url or source.displayed_url
        if not url or url in seen_urls:
            continue

        seen_urls.add(url)
        summarized.append(
            ReviewedPublicSource(
                category=source.category,
                title=source.title,
                url=url,
                signal=build_source_signal(source),
            )
        )

        if len(summarized) >= max_sources:
            break

    return summarized


def build_research_notes(
    request: ProspectWithResearchRequest,
    public_sources: List[ReviewedPublicSource],
    presence_summary: str,
) -> str:
    parts = []

    if request.notes:
        parts.append(request.notes)

    parts.append(presence_summary)

    if public_sources:
        source_lines = []
        for source in public_sources:
            source_lines.append(
                f"{source.category}: {source.title or 'sin título'} - {source.signal}"
            )
        parts.append("Fuentes públicas revisadas: " + " | ".join(source_lines))

    return " ".join(parts)


def build_initial_diagnosis(
    request: ProspectWithResearchRequest,
    audit: ProspectAuditResponse,
    public_sources: List[ReviewedPublicSource],
) -> str:
    if public_sources:
        return (
            f"{request.company_name} muestra presencia pública detectable, pero el principal riesgo comercial "
            f"parece estar en {audit.primary_bottleneck}. La empresa puede estar generando visibilidad sin convertirla "
            "en una razón clara de elección."
        )

    return (
        f"No se encontraron suficientes fuentes públicas fuertes para validar la presencia de {request.company_name}. "
        f"Aun así, con las señales disponibles, el cuello de botella probable es {audit.primary_bottleneck}."
    )


def clamp_score(value: int) -> int:
    return max(1, min(value, 10))


def source_count_by_category(
    sources: List[ReviewedPublicSource],
    category: str,
) -> int:
    return sum(1 for source in sources if source.category == category)


def build_commercial_score(
    audit: ProspectAuditResponse,
    public_sources: List[ReviewedPublicSource],
    raw_sources_count: int,
    request: ProspectWithResearchRequest,
) -> CommercialScore:
    notes_text = " ".join([
        request.notes or "",
        request.offer or "",
        " ".join([source.signal for source in public_sources]),
    ]).casefold()

    public_presence = 3
    if raw_sources_count >= 12:
        public_presence = 8
    elif raw_sources_count >= 8:
        public_presence = 7
    elif raw_sources_count >= 4:
        public_presence = 6
    elif raw_sources_count >= 1:
        public_presence = 4

    value_proposition = 7
    if audit.primary_bottleneck == "propuesta de valor":
        value_proposition = 4
    if "propuesta de valor clara" in notes_text or "diferencian" in notes_text or "diferenciación" in notes_text:
        value_proposition = min(value_proposition, 4)

    differentiation = 7
    if audit.primary_bottleneck in ["propuesta de valor", "posicionamiento"]:
        differentiation = 3
    elif "competidores" in notes_text or source_count_by_category(public_sources, "competitors") > 0:
        differentiation = 5

    cta_strength = 7
    if "cta" in notes_text or "llamada a la acción" in notes_text or audit.primary_bottleneck == "conversión":
        cta_strength = 4

    trust_signals = 5
    if source_count_by_category(public_sources, "reputation") >= 2:
        trust_signals = 7
    elif source_count_by_category(public_sources, "reputation") == 1:
        trust_signals = 6
    elif raw_sources_count == 0:
        trust_signals = 3

    competitive_pressure = 5
    if source_count_by_category(public_sources, "competitors") >= 3:
        competitive_pressure = 8
    elif source_count_by_category(public_sources, "competitors") >= 1:
        competitive_pressure = 7
    if request.industry:
        competitive_pressure = max(competitive_pressure, 6)

    positive_scores = [
        value_proposition,
        public_presence,
        differentiation,
        cta_strength,
        trust_signals,
    ]

    pressure_penalty = max(0, competitive_pressure - 5) * 0.35
    overall = round(max(1.0, min(10.0, (sum(positive_scores) / len(positive_scores)) - pressure_penalty)), 1)

    return CommercialScore(
        overall=overall,
        value_proposition=clamp_score(value_proposition),
        public_presence=clamp_score(public_presence),
        differentiation=clamp_score(differentiation),
        cta_strength=clamp_score(cta_strength),
        trust_signals=clamp_score(trust_signals),
        competitive_pressure=clamp_score(competitive_pressure),
    )


def build_score_interpretation(
    score: CommercialScore,
    audit: ProspectAuditResponse,
) -> ScoreInterpretation:
    if score.overall < 4:
        level = "riesgo alto"
    elif score.overall < 6:
        level = "riesgo medio-alto"
    elif score.overall < 8:
        level = "riesgo medio"
    else:
        level = "riesgo bajo"

    if audit.primary_bottleneck == "propuesta de valor":
        main_risk = "competir por precio, disponibilidad o catálogo en vez de valor percibido"
    elif audit.primary_bottleneck == "conversión":
        main_risk = "generar interés sin transformarlo en consultas calificadas"
    elif audit.primary_bottleneck == "funnel":
        main_risk = "tener puntos de contacto aislados sin recorrido comercial claro"
    elif audit.primary_bottleneck == "posicionamiento":
        main_risk = "ser percibido como una alternativa más dentro de un mercado saturado"
    else:
        main_risk = "hacer actividad digital sin convertirla en demanda calificada"

    return ScoreInterpretation(
        level=level,
        summary=(
            f"Score general {score.overall}/10. La marca muestra señales comerciales aprovechables, "
            f"pero el principal cuello de botella está en {audit.primary_bottleneck}."
        ),
        main_leverage=audit.primary_bottleneck,
        main_risk=main_risk,
    )



def build_awareness_funnel_locator(
    audit: ProspectAuditResponse,
    score: CommercialScore,
    request: ProspectWithResearchRequest,
) -> AwarenessFunnelLocator:
    stage_map = {
        "unaware": "Unaware",
        "problem-aware": "Problem Aware",
        "solution-aware": "Solution Aware",
        "product-aware": "Product Aware",
        "most-aware": "Most Aware",
    }

    dominant_stage = stage_map.get(audit.awareness_level, "Problem Aware")

    if dominant_stage == "Unaware":
        blocked_stage = "Problem Aware"
        weights = [45, 30, 15, 7, 3]
    elif dominant_stage == "Problem Aware":
        blocked_stage = "Solution Aware"
        weights = [10, 45, 25, 15, 5]
    elif dominant_stage == "Solution Aware":
        blocked_stage = "Product Aware"
        weights = [5, 20, 40, 25, 10]
    elif dominant_stage == "Product Aware":
        blocked_stage = "Most Aware"
        weights = [3, 12, 25, 40, 20]
    else:
        blocked_stage = "Purchase / Conversion"
        weights = [2, 8, 15, 25, 50]

    stages = ["Unaware", "Problem Aware", "Solution Aware", "Product Aware", "Most Aware"]

    distribution = []
    for stage, weight in zip(stages, weights):
        if stage == dominant_stage:
            state = "dominant"
        elif stage == blocked_stage:
            state = "blocked"
        elif weight >= 20:
            state = "secondary"
        else:
            state = "neutral"

        distribution.append(
            AwarenessStage(
                stage=stage,
                weight=weight,
                state=state,
            )
        )

    if audit.primary_bottleneck == "propuesta de valor":
        explanation = (
            "El grueso del público reconoce la necesidad o la categoría, pero todavía no percibe "
            "una razón clara para elegir esta marca frente a otras alternativas."
        )
    elif audit.primary_bottleneck == "conversión":
        explanation = (
            "El público puede estar más cerca de decidir, pero la acción comercial no está suficientemente "
            "clara para convertir interés en consulta."
        )
    elif audit.primary_bottleneck == "funnel":
        explanation = (
            "Hay señales de recorrido incompleto: el público puede avanzar parcialmente, pero falta una "
            "secuencia clara desde interés hasta oportunidad comercial."
        )
    elif audit.primary_bottleneck == "posicionamiento":
        explanation = (
            "El público compara alternativas, pero la marca no ocupa una posición suficientemente distinta "
            "en la mente del mercado."
        )
    else:
        explanation = (
            "El público muestra señales de consciencia inicial, pero todavía falta construir preferencia "
            "y dirección comercial."
        )

    return AwarenessFunnelLocator(
        dominant_stage=dominant_stage,
        blocked_stage=blocked_stage,
        stage_distribution=distribution,
        explanation=explanation,
    )


def build_temperature_heatmap(
    audit: ProspectAuditResponse,
    score: CommercialScore,
) -> TemperatureHeatmap:
    # Valores 0-100. No son métricas reales; son un mapa diagnóstico inferido desde señales públicas y score.
    if audit.primary_bottleneck in ["propuesta de valor", "posicionamiento"]:
        average_temperature = "Templado"
        rows_data = [
            ("Frío", 75, 35, 15, 20, 10),
            ("Tibio", 65, 50, 25, 30, 15),
            ("Templado", 55, 68, 45, 38, 25),
            ("Caliente", 25, 40, 45, 35, 28),
            ("Muy caliente", 10, 20, 25, 20, 15),
        ]
        summary = (
            "Predomina un cliente templado: hay interés inicial, pero todavía falta confianza, "
            "diferenciación percibida y dirección clara hacia la acción."
        )
    elif audit.primary_bottleneck == "conversión":
        average_temperature = "Caliente"
        rows_data = [
            ("Frío", 45, 25, 10, 15, 5),
            ("Tibio", 55, 45, 25, 25, 15),
            ("Templado", 50, 60, 45, 40, 25),
            ("Caliente", 35, 60, 70, 55, 38),
            ("Muy caliente", 15, 35, 55, 45, 30),
        ]
        summary = (
            "El cliente puede mostrar intención, pero la conversión se enfría porque el CTA, "
            "la confianza o el siguiente paso no están suficientemente resueltos."
        )
    elif audit.primary_bottleneck == "awareness":
        average_temperature = "Frío"
        rows_data = [
            ("Frío", 65, 25, 8, 10, 5),
            ("Tibio", 40, 30, 15, 15, 8),
            ("Templado", 25, 25, 20, 18, 10),
            ("Caliente", 10, 15, 15, 12, 8),
            ("Muy caliente", 5, 8, 10, 8, 5),
        ]
        summary = (
            "Predomina un cliente frío: hay poca presencia mental o baja activación del problema."
        )
    else:
        average_temperature = "Tibio"
        rows_data = [
            ("Frío", 65, 30, 10, 15, 8),
            ("Tibio", 60, 50, 25, 25, 15),
            ("Templado", 45, 55, 35, 30, 20),
            ("Caliente", 20, 35, 40, 35, 22),
            ("Muy caliente", 8, 18, 22, 20, 12),
        ]
        summary = (
            "Predomina un cliente tibio/templado: existe atención, pero el recorrido comercial todavía "
            "no empuja con suficiente fuerza hacia conversión."
        )

    rows = []
    for temperature, attention, interest, intent, trust, action in rows_data:
        average = round((attention + interest + intent + trust + action) / 5)
        rows.append(
            TemperatureHeatmapRow(
                temperature=temperature,
                values=TemperatureHeatmapValues(
                    attention=attention,
                    interest=interest,
                    intent=intent,
                    trust=trust,
                    action=action,
                    average=average,
                ),
            )
        )

    return TemperatureHeatmap(
        average_temperature=average_temperature,
        rows=rows,
        summary=summary,
    )



def build_customer_intent_density_map(
    awareness_funnel_locator: AwarenessFunnelLocator,
    heatmap: TemperatureHeatmap,
    audit: ProspectAuditResponse,
) -> CustomerIntentDensityMap:
    x_axis = ["Awareness", "Interest", "Consideration", "Conversion"]
    y_axis = ["Frío", "Tibio", "Templado", "Caliente"]

    stage_to_x = {
        "Unaware": "Awareness",
        "Problem Aware": "Interest",
        "Solution Aware": "Consideration",
        "Product Aware": "Consideration",
        "Most Aware": "Conversion",
    }

    dominant_x = stage_to_x.get(awareness_funnel_locator.dominant_stage, "Interest")
    blocked_x = stage_to_x.get(awareness_funnel_locator.blocked_stage, "Consideration")

    temp = heatmap.average_temperature
    dominant_y = "Caliente" if temp == "Muy caliente" else temp if temp in y_axis else "Templado"

    if audit.primary_bottleneck in ["propuesta de valor", "posicionamiento"]:
        blocked_y = dominant_y
    elif audit.primary_bottleneck == "conversión":
        blocked_y = "Caliente"
    elif audit.primary_bottleneck == "awareness":
        blocked_y = "Tibio"
    else:
        blocked_y = dominant_y

    values = {}
    for y in y_axis:
        for x in x_axis:
            values[(x, y)] = 12

    def set_value(x: str, y: str, value: int):
        values[(x, y)] = max(values.get((x, y), 0), max(0, min(int(value), 100)))

    set_value(dominant_x, dominant_y, 92)
    set_value(blocked_x, blocked_y, 72)

    x_index = x_axis.index(dominant_x)
    y_index = y_axis.index(dominant_y)

    for dx, dy, value in [
        (-1, 0, 64),
        (1, 0, 58),
        (0, -1, 55),
        (0, 1, 62),
        (-1, -1, 42),
        (1, 1, 46),
        (1, -1, 36),
        (-1, 1, 38),
    ]:
        nx = x_index + dx
        ny = y_index + dy
        if 0 <= nx < len(x_axis) and 0 <= ny < len(y_axis):
            set_value(x_axis[nx], y_axis[ny], value)

    if audit.primary_bottleneck in ["propuesta de valor", "posicionamiento"]:
        set_value("Conversion", "Caliente", 18)
        set_value("Conversion", "Templado", 24)
        set_value("Consideration", "Templado", max(values[("Consideration", "Templado")], 68))
    elif audit.primary_bottleneck == "conversión":
        set_value("Conversion", "Caliente", 78)
        set_value("Conversion", "Templado", 60)
    elif audit.primary_bottleneck == "awareness":
        set_value("Awareness", "Frío", 82)
        set_value("Interest", "Tibio", 45)

    density_points = [
        DensityPoint(x=x, y=y, value=values[(x, y)])
        for y in y_axis
        for x in x_axis
    ]

    interpretation = (
        f"La mayor concentración diagnóstica aparece en {dominant_x} / {dominant_y}. "
        f"La zona de fricción aparece en {blocked_x} / {blocked_y}. "
        "Este mapa no representa comportamiento medido por analítica web; representa una inferencia comercial "
        "a partir de fuentes públicas, awareness, temperatura y cuello de botella detectado."
    )

    return CustomerIntentDensityMap(
        x_axis=x_axis,
        y_axis=y_axis,
        density_points=density_points,
        dominant_zone=DensityZone(
            x=dominant_x,
            y=dominant_y,
            label="Mayor concentración del público",
        ),
        blocked_zone=DensityZone(
            x=blocked_x,
            y=blocked_y,
            label="Zona de bloqueo / pérdida de avance",
        ),
        interpretation=interpretation,
    )




def build_visual_diagram_mermaid(audit: ProspectAuditResponse) -> str:
    bottleneck_label = audit.primary_bottleneck.capitalize()

    return f"""flowchart LR
A[Presencia pública] --> B[Contenido / catálogo]
B --> C[Interés inicial]
C --> D{{¿{bottleneck_label} resuelto?}}
D -- No --> E[Pérdida de diferenciación]
E --> F[Competencia por precio o disponibilidad]
D -- Sí --> G[Preferencia de marca]
G --> H[Consulta calificada]
H --> I[Reunión / oportunidad comercial]"""


def build_funnel_blueprint(audit: ProspectAuditResponse) -> FunnelBlueprint:
    breakpoints = ["CTA débil o poco específico", "Prueba social insuficiente"]

    if audit.primary_bottleneck == "propuesta de valor":
        breakpoints.insert(0, "Propuesta de valor poco clara")
        summary = (
            "El recorrido se rompe entre interés y consideración: la marca muestra presencia u oferta, "
            "pero no construye una razón clara de elección."
        )
    elif audit.primary_bottleneck == "conversión":
        breakpoints.insert(0, "Falta de acción comercial clara")
        summary = (
            "El recorrido se rompe al final del funnel: puede existir interés, pero el siguiente paso "
            "no está suficientemente claro o convincente."
        )
    elif audit.primary_bottleneck == "funnel":
        breakpoints.insert(0, "Recorrido comercial incompleto")
        summary = (
            "El recorrido se rompe porque los puntos de contacto no están conectados en una secuencia "
            "clara desde atención hasta oportunidad comercial."
        )
    elif audit.primary_bottleneck == "posicionamiento":
        breakpoints.insert(0, "Diferenciación insuficiente frente a competidores")
        summary = (
            "El recorrido se rompe durante la comparación: la marca no ocupa una posición distintiva "
            "suficiente para ganar preferencia."
        )
    else:
        breakpoints.insert(0, "Falta de claridad estratégica en el recorrido")
        summary = (
            "La presencia pública existe, pero todavía no se traduce en un recorrido comercial defendible."
        )

    missing_links = list(dict.fromkeys([
        "Mensaje diferencial",
        "Contenido que eduque criterio de elección",
        "Prueba social visible",
        "CTA específico",
        "Seguimiento comercial",
    ]))

    return FunnelBlueprint(
        current_flow=[
            "Presencia pública",
            "Contenido o catálogo",
            "Interés inicial",
            "Comparación con competidores",
            "Consulta débil o poco calificada",
        ],
        missing_links=missing_links,
        breakpoints=list(dict.fromkeys(breakpoints)),
        recommended_flow=[
            "Mensaje diferencial",
            "Contenido que explique criterio y valor",
            "Prueba social o evidencia de confianza",
            "CTA a diagnóstico / consulta / reunión",
            "Seguimiento comercial",
        ],
        summary=summary,
    )


def build_corrective_action_plan(
    request: ProspectWithResearchRequest,
    audit: ProspectAuditResponse,
    public_sources: List[ReviewedPublicSource],
    score: CommercialScore,
) -> List[CorrectiveActionItem]:
    evidence_base = (
        "Las fuentes públicas y las notas disponibles sugieren presencia digital, "
        "pero no una razón de elección suficientemente clara."
    )
    if public_sources:
        evidence_base = (
            f"Se revisaron {len(public_sources)} fuentes públicas resumidas; las señales apuntan a "
            "presencia digital con necesidad de mayor diferenciación comercial."
        )

    actions: List[CorrectiveActionItem] = []

    actions.append(
        CorrectiveActionItem(
            issue="Propuesta de valor débil o poco demostrada",
            evidence=evidence_base,
            recommended_action=(
                "Definir una promesa comercial concreta: qué hace distinto a la marca, para quién, "
                "en qué situación y por qué debería ser elegida."
            ),
            priority="alta",
            effort="medio",
            expected_impact="Mejorar claridad de elección, calidad de consultas y percepción de valor.",
            verification_metric="Comparar tasa de consultas calificadas, respuesta al CTA y calidad de mensajes recibidos.",
            do_not_give_for_free="No entregar copy final ni estrategia completa de posicionamiento sin contratación.",
        )
    )

    if score.cta_strength <= 5 or audit.primary_bottleneck == "conversión":
        actions.append(
            CorrectiveActionItem(
                issue="CTA débil o poco orientado a conversión",
                evidence="El análisis detecta riesgo de atención sin una acción comercial clara.",
                recommended_action=(
                    "Reformular los puntos de conversión hacia una acción concreta: diagnóstico, consulta, "
                    "tasación, reunión o evaluación inicial."
                ),
                priority="alta",
                effort="bajo-medio",
                expected_impact="Reducir fricción y aumentar consultas con intención comercial.",
                verification_metric="Medir clics a contacto, mensajes iniciados, formularios enviados o reuniones agendadas.",
                do_not_give_for_free="No entregar arquitectura completa de funnel ni secuencia completa de automatización.",
            )
        )

    if score.differentiation <= 5 or audit.primary_bottleneck == "posicionamiento":
        actions.append(
            CorrectiveActionItem(
                issue="Diferenciación insuficiente frente a competidores",
                evidence="El contexto público sugiere similitud con otros jugadores del mercado.",
                recommended_action=(
                    "Construir un ángulo de posicionamiento basado en especialización, proceso, criterio, "
                    "experiencia o prueba social."
                ),
                priority="media-alta",
                effort="medio",
                expected_impact="Reducir comparación por precio/disponibilidad y aumentar preferencia de marca.",
                verification_metric="Evaluar recordación de mensaje, objeciones frecuentes y calidad de leads entrantes.",
                do_not_give_for_free="No entregar manifiesto de marca completo ni sistema completo de mensajes.",
            )
        )

    actions.append(
        CorrectiveActionItem(
            issue="Falta de sistema de seguimiento comercial visible",
            evidence="La presencia pública por sí sola no garantiza conversión si no existe recorrido posterior.",
            recommended_action=(
                "Definir un siguiente paso comercial simple y medible: reunión breve, diagnóstico, evaluación "
                "o formulario de intención."
            ),
            priority="media",
            effort="medio",
            expected_impact="Transformar visibilidad en oportunidades comerciales más ordenadas.",
            verification_metric="Medir ratio de contacto a reunión y reunión a oportunidad.",
            do_not_give_for_free="No entregar CRM completo, automatizaciones completas ni guiones finales de venta.",
        )
    )

    return actions


def build_report_pages(
    request: ProspectWithResearchRequest,
    audit: ProspectAuditResponse,
    score: CommercialScore,
    interpretation: ScoreInterpretation,
    public_sources: List[ReviewedPublicSource],
    corrective_actions: List[CorrectiveActionItem],
    awareness_funnel_locator: AwarenessFunnelLocator,
    temperature_heatmap: TemperatureHeatmap,
    funnel_blueprint: FunnelBlueprint,
) -> List[ReportPage]:
    sources_text = "\\n".join([
        f"- {source.title or 'Fuente pública'}: {source.signal}"
        for source in public_sources
    ]) or "No se detectaron fuentes públicas suficientemente fuertes."

    actions_text = "\\n".join([
        f"- {action.issue}: {action.recommended_action} Prioridad: {action.priority}."
        for action in corrective_actions
    ])

    return [
        ReportPage(
            page=1,
            title="Diagnóstico ejecutivo",
            content=interpretation.summary,
            visual_element="score_summary",
        ),
        ReportPage(
            page=2,
            title="Fuentes públicas revisadas",
            content=sources_text,
            visual_element="source_table",
        ),
        ReportPage(
            page=3,
            title="Awareness funnel locator",
            content=(
                f"Etapa dominante: {awareness_funnel_locator.dominant_stage}. "
                f"Etapa bloqueada: {awareness_funnel_locator.blocked_stage}. "
                f"{awareness_funnel_locator.explanation}"
            ),
            visual_element="awareness_funnel",
        ),
        ReportPage(
            page=4,
            title="Customer temperature heatmap",
            content=(
                f"Temperatura promedio: {temperature_heatmap.average_temperature}. "
                f"{temperature_heatmap.summary}"
            ),
            visual_element="temperature_heatmap",
        ),
        ReportPage(
            page=5,
            title="Funnel blueprint",
            content=funnel_blueprint.summary,
            visual_element="system_blueprint",
        ),
        ReportPage(
            page=6,
            title="Plan de acción recomendado",
            content=actions_text,
            visual_element="priority_matrix",
        ),
    ]


def build_report_ready_markdown(
    request: ProspectWithResearchRequest,
    audit: ProspectAuditResponse,
    public_sources: List[ReviewedPublicSource],
    diagnosis_initial: str,
    commercial_score: CommercialScore,
    score_interpretation: ScoreInterpretation,
    awareness_funnel_locator: AwarenessFunnelLocator,
    temperature_heatmap: TemperatureHeatmap,
    customer_intent_density_map: CustomerIntentDensityMap,
    visual_diagram_mermaid: str,
    funnel_blueprint: FunnelBlueprint,
    corrective_action_plan: List[CorrectiveActionItem],
) -> str:
    source_lines = []
    if public_sources:
        for index, source in enumerate(public_sources, start=1):
            source_lines.append(
                f"{index}. {source.title or 'Fuente pública'}\\n"
                f"   URL: {source.url or 'No disponible'}\\n"
                f"   Señal: {source.signal}"
            )
    else:
        source_lines.append("No se detectaron fuentes públicas suficientemente fuertes. Revisar nombre, ciudad, rubro o perfiles conocidos.")

    sources_block = "\\n".join(source_lines)

    action_lines = []
    for index, action in enumerate(corrective_action_plan, start=1):
        action_lines.append(
            f"{index}. {action.issue}\\n"
            f"   Evidencia: {action.evidence}\\n"
            f"   Acción recomendada: {action.recommended_action}\\n"
            f"   Prioridad: {action.priority} | Esfuerzo: {action.effort}\\n"
            f"   Impacto esperado: {action.expected_impact}\\n"
            f"   Validación: {action.verification_metric}\\n"
            f"   No regalar gratis: {action.do_not_give_for_free}"
        )

    actions_block = "\\n\\n".join(action_lines)

    return f"""# Diagnóstico comercial breve — {request.company_name}

## 1. Diagnóstico inicial
{diagnosis_initial}

## 2. Fuentes públicas revisadas
{sources_block}

## 3. Score comercial
Score general: {commercial_score.overall}/10.
- Propuesta de valor: {commercial_score.value_proposition}/10
- Presencia pública: {commercial_score.public_presence}/10
- Diferenciación: {commercial_score.differentiation}/10
- CTA / conversión: {commercial_score.cta_strength}/10
- Señales de confianza: {commercial_score.trust_signals}/10
- Presión competitiva: {commercial_score.competitive_pressure}/10

Lectura: {score_interpretation.summary}

## 4. Awareness funnel locator
Etapa dominante: {awareness_funnel_locator.dominant_stage}.
Etapa bloqueada: {awareness_funnel_locator.blocked_stage}.

Distribución estimada:
{chr(10).join([f"- {stage.stage}: {stage.weight}% ({stage.state})" for stage in awareness_funnel_locator.stage_distribution])}

Lectura:
{awareness_funnel_locator.explanation}

## 5. Customer temperature heatmap
Temperatura promedio: {temperature_heatmap.average_temperature}.

Heatmap diagnóstico:
{chr(10).join([f"- {row.temperature}: atención {row.values.attention}, interés {row.values.interest}, intención {row.values.intent}, confianza {row.values.trust}, acción {row.values.action}, promedio {row.values.average}" for row in temperature_heatmap.rows])}

Lectura:
{temperature_heatmap.summary}

## 6. Customer intent density map
{customer_intent_density_map.interpretation}

Zona dominante: {customer_intent_density_map.dominant_zone.x} / {customer_intent_density_map.dominant_zone.y}.
Zona bloqueada: {customer_intent_density_map.blocked_zone.x} / {customer_intent_density_map.blocked_zone.y}.

## 7. Problema comercial principal
{audit.primary_bottleneck}.

## 8. Riesgo comercial
{audit.commercial_risk}

## 9. Funnel blueprint / system map
Flujo actual:
{chr(10).join([f"- {item}" for item in funnel_blueprint.current_flow])}

Puntos de ruptura:
{chr(10).join([f"- {item}" for item in funnel_blueprint.breakpoints])}

Eslabones faltantes:
{chr(10).join([f"- {item}" for item in funnel_blueprint.missing_links])}

Flujo recomendado:
{chr(10).join([f"- {item}" for item in funnel_blueprint.recommended_flow])}

Resumen:
{funnel_blueprint.summary}

## 10. Blueprint diagram
```mermaid
{visual_diagram_mermaid}
```

## 11. Plan de acción recomendado
{actions_block}

## 12. Próximo paso recomendado
{audit.next_step}

## 13. Límites de esta entrega
No incluye calendario completo de contenido, copys finales, segmentaciones detalladas, arquitectura completa de funnel ni implementación paso a paso.
"""


def h(value: Optional[str]) -> str:
    return html.escape(str(value or ""), quote=True)


def green_scale(value: int) -> str:
    value = max(0, min(int(value), 100))
    if value >= 80:
        return "#22c55e"
    if value >= 60:
        return "#86efac"
    if value >= 40:
        return "#bbf7d0"
    if value >= 20:
        return "#dcfce7"
    return "#f3f4f6"


def render_awareness_funnel_svg(locator: AwarenessFunnelLocator) -> str:
    width = 760
    height = 430
    cx = width / 2
    top_y = 50
    segment_h = 54
    gap = 10
    top_w = 640
    shrink = 86

    polygons = []
    stages = locator.stage_distribution

    for index, stage in enumerate(stages):
        y1 = top_y + index * (segment_h + gap)
        y2 = y1 + segment_h
        w1 = top_w - index * shrink
        w2 = top_w - (index + 1) * shrink

        x1 = cx - w1 / 2
        x2 = cx + w1 / 2
        x3 = cx + w2 / 2
        x4 = cx - w2 / 2

        if stage.state == "dominant":
            fill = "#22c55e"
            stroke = "#15803d"
            text_color = "#ffffff"
            badge = "GRUESO DEL PÚBLICO"
        elif stage.state == "blocked":
            fill = "#fef3c7"
            stroke = "#d97706"
            text_color = "#111827"
            badge = "ETAPA BLOQUEADA"
        elif stage.state == "secondary":
            fill = "#e5e7eb"
            stroke = "#9ca3af"
            text_color = "#111827"
            badge = "SECUNDARIO"
        else:
            fill = "#f5f5f4"
            stroke = "#d6d3d1"
            text_color = "#374151"
            badge = "NEUTRO"

        points = f"{x1},{y1} {x2},{y1} {x3},{y2} {x4},{y2}"
        label_y = y1 + 24
        sub_y = y1 + 43

        polygons.append(f'''
        <polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>
        <text x="{cx}" y="{label_y}" text-anchor="middle" font-size="18" font-weight="700" fill="{text_color}">{h(stage.stage)} · {stage.weight}%</text>
        <text x="{cx}" y="{sub_y}" text-anchor="middle" font-size="11" font-weight="600" fill="{text_color}">{badge}</text>
        ''')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Awareness funnel locator">
    <rect width="{width}" height="{height}" rx="22" fill="#fafaf9"/>
    <text x="{cx}" y="28" text-anchor="middle" font-size="22" font-weight="800" fill="#111827">Awareness Funnel Locator</text>
    {''.join(polygons)}
    <text x="{cx}" y="390" text-anchor="middle" font-size="15" font-weight="700" fill="#111827">Dominante: {h(locator.dominant_stage)} · Bloqueada: {h(locator.blocked_stage)}</text>
    <text x="{cx}" y="414" text-anchor="middle" font-size="12" fill="#4b5563">Verde = concentración principal del público. Neutros = etapas no dominantes.</text>
</svg>'''


def render_temperature_heatmap_svg(heatmap: TemperatureHeatmap) -> str:
    cols = [
        ("attention", "Atención"),
        ("interest", "Interés"),
        ("intent", "Intención"),
        ("trust", "Confianza"),
        ("action", "Acción"),
        ("average", "Promedio"),
    ]

    cell_w = 96
    cell_h = 46
    left_w = 120
    top_h = 96
    width = left_w + cell_w * len(cols) + 40
    height = top_h + cell_h * len(heatmap.rows) + 84

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Customer temperature heatmap">',
        f'<rect width="{width}" height="{height}" rx="22" fill="#fafaf9"/>',
        f'<text x="{width/2}" y="30" text-anchor="middle" font-size="22" font-weight="800" fill="#111827">Customer Temperature Heatmap</text>',
        f'<text x="{width/2}" y="58" text-anchor="middle" font-size="13" fill="#4b5563">Temperatura promedio: {h(heatmap.average_temperature)}</text>',
    ]

    for col_index, (_, label) in enumerate(cols):
        x = left_w + col_index * cell_w
        parts.append(f'<text x="{x + cell_w/2}" y="{top_h - 12}" text-anchor="middle" font-size="12" font-weight="700" fill="#374151">{h(label)}</text>')

    for row_index, row in enumerate(heatmap.rows):
        y = top_h + row_index * cell_h
        is_dominant = row.temperature == heatmap.average_temperature
        row_fill = "#ecfdf5" if is_dominant else "#f5f5f4"
        row_stroke = "#22c55e" if is_dominant else "#d6d3d1"

        parts.append(f'<rect x="18" y="{y}" width="{left_w-24}" height="{cell_h-6}" rx="8" fill="{row_fill}" stroke="{row_stroke}" stroke-width="1.5"/>')
        parts.append(f'<text x="{left_w/2}" y="{y + 28}" text-anchor="middle" font-size="13" font-weight="800" fill="#111827">{h(row.temperature)}</text>')

        values = row.values
        data = {
            "attention": values.attention,
            "interest": values.interest,
            "intent": values.intent,
            "trust": values.trust,
            "action": values.action,
            "average": values.average,
        }

        for col_index, (key, _) in enumerate(cols):
            value = data[key]
            x = left_w + col_index * cell_w
            fill = green_scale(value)
            stroke = "#15803d" if is_dominant and key == "average" else "#d1d5db"
            parts.append(f'<rect x="{x+5}" y="{y}" width="{cell_w-10}" height="{cell_h-6}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
            parts.append(f'<text x="{x + cell_w/2}" y="{y + 28}" text-anchor="middle" font-size="13" font-weight="800" fill="#111827">{value}</text>')

    parts.append(f'<text x="{width/2}" y="{height-32}" text-anchor="middle" font-size="12" fill="#4b5563">Mayor intensidad verde = señal más fuerte. La fila dominante representa la temperatura promedio inferida.</text>')
    parts.append('</svg>')
    return ''.join(parts)


def render_score_chart_svg(score: CommercialScore) -> str:
    rows = [
        ("Propuesta de valor", score.value_proposition),
        ("Presencia pública", score.public_presence),
        ("Diferenciación", score.differentiation),
        ("CTA / conversión", score.cta_strength),
        ("Confianza", score.trust_signals),
        ("Presión competitiva", score.competitive_pressure),
    ]

    width = 760
    row_h = 46
    height = 94 + len(rows) * row_h
    label_x = 36
    bar_x = 250
    bar_w = 410

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Commercial score chart">',
        f'<rect width="{width}" height="{height}" rx="22" fill="#fafaf9"/>',
        f'<text x="{width/2}" y="30" text-anchor="middle" font-size="22" font-weight="800" fill="#111827">Commercial Score</text>',
        f'<text x="{width/2}" y="56" text-anchor="middle" font-size="15" font-weight="700" fill="#15803d">Score general: {score.overall}/10</text>',
    ]

    for i, (label, value) in enumerate(rows):
        y = 82 + i * row_h
        fill_w = bar_w * (value / 10)
        fill = "#22c55e" if value >= 7 else "#84cc16" if value >= 5 else "#f59e0b" if value >= 4 else "#ef4444"
        parts.append(f'<text x="{label_x}" y="{y+20}" font-size="13" font-weight="700" fill="#111827">{h(label)}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="24" rx="12" fill="#e5e7eb"/>')
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{fill_w}" height="24" rx="12" fill="{fill}"/>')
        parts.append(f'<text x="{bar_x + bar_w + 20}" y="{y+18}" font-size="13" font-weight="800" fill="#111827">{value}/10</text>')

    parts.append('</svg>')
    return ''.join(parts)


def render_funnel_blueprint_svg(blueprint: FunnelBlueprint) -> str:
    width = 980
    col_w = 270
    gap = 55
    left_x = 40
    mid_x = left_x + col_w + gap
    right_x = mid_x + col_w + gap

    max_items = max(len(blueprint.current_flow), len(blueprint.breakpoints), len(blueprint.recommended_flow))
    box_h = 46
    box_gap = 16
    top_y = 88
    height = top_y + max_items * (box_h + box_gap) + 96

    def draw_column(items: List[str], x: int, title: str, fill: str, stroke: str, title_fill: str) -> str:
        col_parts = [
            f'<text x="{x + col_w/2}" y="48" text-anchor="middle" font-size="18" font-weight="800" fill="{title_fill}">{h(title)}</text>'
        ]
        for i, item in enumerate(items):
            y = top_y + i * (box_h + box_gap)
            col_parts.append(f'<rect x="{x}" y="{y}" width="{col_w}" height="{box_h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
            col_parts.append(f'<text x="{x + col_w/2}" y="{y+28}" text-anchor="middle" font-size="12" font-weight="700" fill="#111827">{h(item[:42])}</text>')
            if i < len(items) - 1:
                arrow_x = x + col_w/2
                y1 = y + box_h
                y2 = y + box_h + box_gap - 4
                col_parts.append(f'<line x1="{arrow_x}" y1="{y1}" x2="{arrow_x}" y2="{y2}" stroke="{stroke}" stroke-width="2"/>')
                col_parts.append(f'<polygon points="{arrow_x-5},{y2-1} {arrow_x+5},{y2-1} {arrow_x},{y2+7}" fill="{stroke}"/>')
        return ''.join(col_parts)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Funnel blueprint system map">',
        f'<rect width="{width}" height="{height}" rx="22" fill="#fafaf9"/>',
        f'<text x="{width/2}" y="28" text-anchor="middle" font-size="22" font-weight="800" fill="#111827">Funnel Blueprint / System Map</text>',
        draw_column(blueprint.current_flow, left_x, "Flujo actual", "#f5f5f4", "#a8a29e", "#44403c"),
        draw_column(blueprint.breakpoints, mid_x, "Puntos de ruptura", "#fef3c7", "#d97706", "#92400e"),
        draw_column(blueprint.recommended_flow, right_x, "Flujo recomendado", "#dcfce7", "#16a34a", "#166534"),
        f'<line x1="{left_x+col_w+12}" y1="{top_y + 25}" x2="{mid_x-12}" y2="{top_y + 25}" stroke="#6b7280" stroke-width="2" stroke-dasharray="6 6"/>',
        f'<polygon points="{mid_x-12},{top_y+25} {mid_x-24},{top_y+18} {mid_x-24},{top_y+32}" fill="#6b7280"/>',
        f'<line x1="{mid_x+col_w+12}" y1="{top_y + 25}" x2="{right_x-12}" y2="{top_y + 25}" stroke="#6b7280" stroke-width="2" stroke-dasharray="6 6"/>',
        f'<polygon points="{right_x-12},{top_y+25} {right_x-24},{top_y+18} {right_x-24},{top_y+32}" fill="#6b7280"/>',
        f'<text x="{width/2}" y="{height-38}" text-anchor="middle" font-size="13" fill="#4b5563">{h(blueprint.summary[:145])}</text>',
        '</svg>',
    ]

    return ''.join(svg)



def density_color(value: int) -> str:
    value = max(0, min(int(value), 100))

    # Cold -> warm gradient:
    # 0 blue, 35 cyan, 55 yellow-green, 75 amber, 100 red.
    stops = [
        (0, (37, 99, 235)),
        (35, (14, 165, 233)),
        (55, (132, 204, 22)),
        (75, (245, 158, 11)),
        (100, (239, 68, 68)),
    ]

    for index in range(len(stops) - 1):
        left_value, left_rgb = stops[index]
        right_value, right_rgb = stops[index + 1]

        if left_value <= value <= right_value:
            ratio = (value - left_value) / (right_value - left_value)
            rgb = tuple(
                round(left_rgb[channel] + (right_rgb[channel] - left_rgb[channel]) * ratio)
                for channel in range(3)
            )
            return f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"

    return "rgb(239, 68, 68)"




def render_customer_intent_density_svg(density_map: CustomerIntentDensityMap) -> str:
    x_axis = density_map.x_axis
    y_axis = density_map.y_axis

    width = 1100
    height = 560
    chart_x = 112
    chart_y = 92
    chart_w = 880
    chart_h = 335
    stage_step = chart_w / (len(x_axis) - 1)
    temp_step = chart_h / (len(y_axis) - 1)

    def x_pos(label: str) -> float:
        return chart_x + x_axis.index(label) * stage_step

    def y_pos(label: str) -> float:
        # Invert y-axis: Frío abajo, Caliente arriba.
        return chart_y + (len(y_axis) - 1 - y_axis.index(label)) * temp_step

    value_lookup = {
        (point.x, point.y): point.value
        for point in density_map.density_points
    }

    def value_at(x_label: str, y_label: str) -> int:
        return int(value_lookup.get((x_label, y_label), 0))

    ribbons = []
    cores = []
    hotspots = []
    labels = []

    # Connected ribbons across stages. This replaces the previous "cell matrix" look.
    for y_label in y_axis:
        row_values = [value_at(x_label, y_label) for x_label in x_axis]
        y = y_pos(y_label)

        # Row-level faint shelf: gives the continuous liquidity-map base.
        max_row = max(row_values) if row_values else 0
        if max_row >= 28:
            baseline_color = density_color(max_row)
            baseline_width = 20 + max_row * 0.28
            ribbons.append(
                f'<line x1="{chart_x:.1f}" y1="{y:.1f}" x2="{chart_x + chart_w:.1f}" y2="{y:.1f}" '
                f'stroke="{baseline_color}" stroke-width="{baseline_width:.1f}" stroke-linecap="round" '
                f'opacity="0.11" filter="url(#densityBlur)"/>'
            )

        # Segment-level ribbons connect each funnel stage to the next.
        for index in range(len(x_axis) - 1):
            x1 = x_pos(x_axis[index])
            x2 = x_pos(x_axis[index + 1])
            v1 = row_values[index]
            v2 = row_values[index + 1]
            avg = (v1 + v2) / 2

            if avg < 18:
                continue

            color = density_color(round(avg))
            width_outer = 18 + avg * 0.55
            width_inner = 4 + avg * 0.12
            opacity_outer = min(0.70, 0.12 + avg / 135)
            opacity_inner = min(0.80, 0.20 + avg / 160)

            mid_x = (x1 + x2) / 2
            curve_offset = ((v2 - v1) / 100) * 28
            path = f"M {x1:.1f} {y:.1f} C {mid_x:.1f} {y - curve_offset:.1f}, {mid_x:.1f} {y + curve_offset:.1f}, {x2:.1f} {y:.1f}"

            ribbons.append(
                f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width_outer:.1f}" '
                f'stroke-linecap="round" opacity="{opacity_outer:.2f}" filter="url(#densityBlur)"/>'
            )

            if avg >= 34:
                cores.append(
                    f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width_inner:.1f}" '
                    f'stroke-linecap="round" opacity="{opacity_inner:.2f}" filter="url(#softBlur)"/>'
                )

            if avg >= 55:
                cores.append(
                    f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{max(2.0, width_inner/2):.1f}" '
                    f'stroke-linecap="round" opacity="0.75"/>'
                )

    # Hotspots and labels on top of the connected ribbons.
    for point in density_map.density_points:
        value = max(0, min(int(point.value), 100))
        if value < 42:
            continue

        cx = x_pos(point.x)
        cy = y_pos(point.y)
        color = density_color(value)

        is_dominant = (
            point.x == density_map.dominant_zone.x
            and point.y == density_map.dominant_zone.y
        )
        is_blocked = (
            point.x == density_map.blocked_zone.x
            and point.y == density_map.blocked_zone.y
        )

        radius = 10 + value * 0.18
        glow_radius = 24 + value * 0.50

        hotspots.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{glow_radius:.1f}" fill="{color}" opacity="0.22" filter="url(#densityBlur)"/>'
        )
        hotspots.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="{color}" opacity="0.50" filter="url(#softBlur)"/>'
        )

        if is_dominant and is_blocked:
            labels.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="24" fill="none" stroke="#ffffff" stroke-width="4" opacity="0.95"/>'
            )
            labels.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="31" fill="none" stroke="#fbbf24" stroke-width="3" opacity="0.95"/>'
            )
            labels.append(
                f'<text x="{cx:.1f}" y="{cy - 36:.1f}" text-anchor="middle" font-size="12" font-weight="900" fill="#ffffff">DOMINANTE</text>'
            )
            labels.append(
                f'<text x="{cx:.1f}" y="{cy + 46:.1f}" text-anchor="middle" font-size="12" font-weight="900" fill="#fbbf24">BLOQUEO</text>'
            )
        elif is_dominant:
            labels.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="22" fill="none" stroke="#ffffff" stroke-width="4" opacity="0.95"/>'
            )
            labels.append(
                f'<text x="{cx:.1f}" y="{cy - 32:.1f}" text-anchor="middle" font-size="12" font-weight="900" fill="#ffffff">DOMINANTE</text>'
            )
        elif is_blocked:
            labels.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="18" fill="none" stroke="#fbbf24" stroke-width="4" opacity="0.95"/>'
            )
            labels.append(
                f'<text x="{cx:.1f}" y="{cy + 40:.1f}" text-anchor="middle" font-size="12" font-weight="900" fill="#fbbf24">BLOQUEO</text>'
            )

    dominant_cx = x_pos(density_map.dominant_zone.x)
    dominant_cy = y_pos(density_map.dominant_zone.y)
    blocked_cx = x_pos(density_map.blocked_zone.x)
    blocked_cy = y_pos(density_map.blocked_zone.y)

    temp_bands = []
    band_labels = [
        ("Caliente", "#7f1d1d", 0.16),
        ("Templado", "#713f12", 0.12),
        ("Tibio", "#064e3b", 0.11),
        ("Frío", "#0f2a5f", 0.15),
    ]
    for label, color, opacity in band_labels:
        cy = y_pos(label)
        temp_bands.append(
            f'<rect x="{chart_x}" y="{cy - 40}" width="{chart_w}" height="80" '
            f'fill="{color}" opacity="{opacity}" rx="14"/>'
        )

    x_labels = []
    for label in x_axis:
        x = x_pos(label)
        x_labels.append(
            f'<text x="{x:.1f}" y="{chart_y - 28}" text-anchor="middle" font-size="15" font-weight="900" fill="#f9fafb">{h(label)}</text>'
        )
        x_labels.append(
            f'<line x1="{x:.1f}" y1="{chart_y - 8}" x2="{x:.1f}" y2="{chart_y + chart_h + 8}" '
            f'stroke="#334155" stroke-width="1" opacity="0.30"/>'
        )

    y_labels = []
    for label in y_axis:
        y = y_pos(label)
        y_labels.append(
            f'<text x="{chart_x - 26}" y="{y + 5:.1f}" text-anchor="end" font-size="14" font-weight="900" fill="#f9fafb">{h(label)}</text>'
        )
        y_labels.append(
            f'<line x1="{chart_x - 6}" y1="{y:.1f}" x2="{chart_x + chart_w + 6}" y2="{y:.1f}" '
            f'stroke="#334155" stroke-width="1" opacity="0.22"/>'
        )

    profile_bars = []
    for label in y_axis:
        y = y_pos(label)
        row_values = [value_at(x, label) for x in x_axis]
        max_row = max(row_values) if row_values else 0
        bar_w = 18 + max_row * 0.95
        profile_color = density_color(max_row)
        profile_bars.append(
            f'<rect x="{chart_x + chart_w + 20}" y="{y - 18:.1f}" width="{bar_w:.1f}" height="36" rx="8" '
            f'fill="{profile_color}" opacity="0.76" filter="url(#softBlur)"/>'
        )

    legend_y = height - 84
    legend_x = chart_x
    legend_w = chart_w
    interpretation = h(density_map.interpretation[:168])

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Customer intent density map">
    <defs>
      <filter id="densityBlur" x="-45%" y="-180%" width="190%" height="460%">
        <feGaussianBlur stdDeviation="18"/>
      </filter>
      <filter id="softBlur" x="-35%" y="-120%" width="170%" height="340%">
        <feGaussianBlur stdDeviation="7"/>
      </filter>
      <marker id="arrowHead" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
        <path d="M0,0 L0,6 L9,3 z" fill="#f9fafb"/>
      </marker>
      <linearGradient id="legendGradient" x1="0%" x2="100%" y1="0%" y2="0%">
        <stop offset="0%" stop-color="#2563eb"/>
        <stop offset="35%" stop-color="#0ea5e9"/>
        <stop offset="55%" stop-color="#84cc16"/>
        <stop offset="75%" stop-color="#f59e0b"/>
        <stop offset="100%" stop-color="#ef4444"/>
      </linearGradient>
      <radialGradient id="chartGlow" cx="50%" cy="45%" r="70%">
        <stop offset="0%" stop-color="#1e293b"/>
        <stop offset="100%" stop-color="#0f172a"/>
      </radialGradient>
    </defs>

    <rect width="{width}" height="{height}" rx="28" fill="#0b1220"/>
    <rect x="28" y="24" width="{width - 56}" height="{height - 48}" rx="26" fill="url(#chartGlow)" stroke="#1f2937" stroke-width="1"/>

    <text x="{width/2}" y="50" text-anchor="middle" font-size="27" font-weight="900" fill="#f9fafb">Customer Intent Density Map</text>
    <text x="{width/2}" y="76" text-anchor="middle" font-size="14" fill="#d1d5db">Mapa de densidad conectada · Azul frío → verde/amarillo templado → rojo caliente</text>

    <rect x="{chart_x - 12}" y="{chart_y - 12}" width="{chart_w + 24}" height="{chart_h + 24}" rx="20" fill="#020617" opacity="0.48" stroke="#334155" stroke-width="1"/>

    {''.join(temp_bands)}
    {''.join(x_labels)}
    {''.join(y_labels)}
    {''.join(ribbons)}
    {''.join(cores)}
    {''.join(hotspots)}
    {''.join(labels)}
    {''.join(profile_bars)}

    <path d="M {dominant_cx:.1f} {dominant_cy:.1f} C {(dominant_cx + blocked_cx)/2:.1f} {dominant_cy - 46:.1f}, {(dominant_cx + blocked_cx)/2:.1f} {blocked_cy - 46:.1f}, {blocked_cx:.1f} {blocked_cy:.1f}"
      fill="none" stroke="#f9fafb" stroke-width="2.4" stroke-dasharray="8 7" marker-end="url(#arrowHead)" opacity="0.82"/>

    <text x="{chart_x}" y="{chart_y + chart_h + 50}" font-size="12" fill="#cbd5e1">Perfil lateral = concentración máxima por temperatura</text>

    <rect x="{legend_x}" y="{legend_y}" width="{legend_w}" height="14" rx="7" fill="url(#legendGradient)"/>
    <text x="{legend_x}" y="{legend_y + 36}" text-anchor="start" font-size="12" fill="#d1d5db">Frío</text>
    <text x="{legend_x + legend_w/2}" y="{legend_y + 36}" text-anchor="middle" font-size="12" fill="#d1d5db">Templado</text>
    <text x="{legend_x + legend_w}" y="{legend_y + 36}" text-anchor="end" font-size="12" fill="#d1d5db">Caliente</text>

    <text x="{width/2}" y="{height - 20}" text-anchor="middle" font-size="12" fill="#94a3b8">{interpretation}</text>
</svg>'''


def build_visual_report_html(
    result: ProspectWithResearchResponse,
    awareness_svg: str,
    temperature_svg: str,
    density_svg: str,
    blueprint_svg: str,
    score_svg: str,
) -> str:
    sources = ''.join([
        f'''
        <tr>
          <td>{h(source.category)}</td>
          <td>{h(source.title)}</td>
          <td><a href="{h(source.url)}" target="_blank" rel="noopener">Abrir fuente</a></td>
          <td>{h(source.signal)}</td>
        </tr>
        '''
        for source in result.public_sources_summary
    ])

    actions = ''.join([
        f'''
        <div class="action-card">
          <h3>{h(action.issue)}</h3>
          <p><strong>Evidencia:</strong> {h(action.evidence)}</p>
          <p><strong>Acción:</strong> {h(action.recommended_action)}</p>
          <p><strong>Prioridad:</strong> {h(action.priority)} · <strong>Esfuerzo:</strong> {h(action.effort)}</p>
          <p><strong>Impacto esperado:</strong> {h(action.expected_impact)}</p>
          <p><strong>Validación:</strong> {h(action.verification_metric)}</p>
        </div>
        '''
        for action in result.corrective_action_plan
    ])

    return f'''<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Reporte visual — {h(result.company_name)}</title>
  <style>
    body {{
      margin: 0;
      background: #f4f1eb;
      color: #111827;
      font-family: Arial, Helvetica, sans-serif;
    }}
    .page {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 20px 64px;
    }}
    .hero {{
      background: #111827;
      color: white;
      border-radius: 24px;
      padding: 32px;
      margin-bottom: 22px;
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-size: 34px;
      letter-spacing: -0.04em;
    }}
    .hero p {{
      margin: 0 0 8px;
      color: #d1d5db;
      max-width: 850px;
      line-height: 1.5;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 24px;
      padding: 22px;
      box-shadow: 0 12px 30px rgba(17, 24, 39, 0.08);
      margin-bottom: 20px;
      overflow: hidden;
    }}
    .card h2 {{
      margin: 0 0 14px;
      font-size: 21px;
      letter-spacing: -0.03em;
    }}
    .full {{
      grid-column: 1 / -1;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid #e5e7eb;
      text-align: left;
      vertical-align: top;
      padding: 10px;
    }}
    th {{
      background: #f9fafb;
    }}
    .action-card {{
      border: 1px solid #e5e7eb;
      border-left: 5px solid #22c55e;
      border-radius: 16px;
      padding: 16px;
      margin: 12px 0;
      background: #fcfcfc;
    }}
    .action-card h3 {{
      margin: 0 0 8px;
    }}
    .action-card p {{
      margin: 6px 0;
      line-height: 1.45;
    }}
    .muted {{
      color: #6b7280;
    }}
    @media print {{
      body {{ background: white; }}
      .card, .hero {{ box-shadow: none; break-inside: avoid; }}
    }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>Reporte visual de auditoría comercial</h1>
      <p><strong>{h(result.company_name)}</strong> · Confianza de investigación: {h(result.research_confidence)} · Tipo: {h(result.audit_type)}</p>
      <p>{h(result.diagnosis_initial)}</p>
    </section>

    <section class="grid">
      <div class="card">{score_svg}</div>
      <div class="card">{awareness_svg}</div>
      <div class="card full">{density_svg}</div>
      <div class="card full">{temperature_svg}</div>
      <div class="card full">{blueprint_svg}</div>

      <div class="card full">
        <h2>Fuentes públicas revisadas</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Categoría</th>
                <th>Título</th>
                <th>URL</th>
                <th>Señal</th>
              </tr>
            </thead>
            <tbody>
              {sources or '<tr><td colspan="4">No se detectaron fuentes públicas suficientemente fuertes.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>

      <div class="card full">
        <h2>Plan de acción recomendado</h2>
        {actions}
      </div>

      <div class="card full">
        <h2>Próximo paso comercial</h2>
        <p>{h(result.next_step)}</p>
        <p class="muted">Límite de esta entrega: no incluye calendario completo, copys finales, segmentaciones detalladas, arquitectura completa de funnel ni implementación paso a paso.</p>
      </div>
    </section>
  </main>
</body>
</html>'''


@app.post(
    "/deliverables/visual-report",
    response_model=VisualReportResponse,
    operation_id="createVisualAuditReport",
    summary="Create a visual audit report",
    description="Ejecuta la auditoría integrada y genera un reporte visual con embudo, heatmap, blueprint y score chart en SVG/HTML.",
    dependencies=[Security(verify_api_key)],
)
def create_visual_audit_report(request: ProspectWithResearchRequest):
    result = audit_prospect_with_research(request)

    awareness_svg = render_awareness_funnel_svg(result.awareness_funnel_locator)
    temperature_svg = render_temperature_heatmap_svg(result.temperature_heatmap)
    density_svg = render_customer_intent_density_svg(result.customer_intent_density_map)
    blueprint_svg = render_funnel_blueprint_svg(result.funnel_blueprint)
    score_svg = render_score_chart_svg(result.commercial_score)

    report_html = build_visual_report_html(
        result=result,
        awareness_svg=awareness_svg,
        temperature_svg=temperature_svg,
        density_svg=density_svg,
        blueprint_svg=blueprint_svg,
        score_svg=score_svg,
    )

    report_id = uuid.uuid4().hex
    VISUAL_REPORT_STORE[report_id] = report_html
    report_url = f"{PUBLIC_BASE_URL.rstrip('/')}/deliverables/report/{report_id}"

    return VisualReportResponse(
        company_name=result.company_name,
        report_id=report_id,
        report_url=report_url,
        awareness_funnel_svg=awareness_svg,
        temperature_heatmap_svg=temperature_svg,
        customer_intent_density_svg=density_svg,
        funnel_blueprint_svg=blueprint_svg,
        score_chart_svg=score_svg,
        report_html=report_html,
        report_markdown=result.report_ready_markdown,
    )


@app.get(
    "/deliverables/report/{report_id}",
    response_class=HTMLResponse,
    operation_id="getVisualAuditReport",
    summary="Open a generated visual audit report",
)
def get_visual_audit_report(report_id: str):
    report_html = VISUAL_REPORT_STORE.get(report_id)

    if not report_html:
        raise HTTPException(
            status_code=404,
            detail="Reporte no encontrado o expirado. Generá un nuevo visual report.",
        )

    return HTMLResponse(content=report_html)


@app.get("/")
def root():
    return {"status": "ok", "message": "Marketing Audit API funcionando"}


def build_analysis_text(request: ProspectAuditRequest) -> str:
    fields = [
        request.company_name,
        request.website,
        request.instagram,
        request.linkedin,
        request.industry,
        request.offer,
        request.notes,
    ]
    return " ".join([field for field in fields if field]).casefold()


def contains_any(text: str, keywords: List[str]) -> bool:
    return any(keyword.casefold() in text for keyword in keywords)


def infer_focus_areas(text: str, request: ProspectAuditRequest) -> List[str]:
    focus_areas = []

    if request.instagram or contains_any(text, ["instagram", "contenido", "publicaciones", "posteos", "feed", "reels"]):
        focus_areas.append("contenido")
    if contains_any(text, ["awareness", "visibilidad", "alcance", "reconocimiento", "tráfico", "audiencia"]):
        focus_areas.append("awareness")
    if contains_any(text, ["propuesta de valor", "diferenciación", "diferenciacion", "oferta", "por qué elegir", "porque elegir", "posicionamiento"]):
        focus_areas.append("propuesta de valor")
    if contains_any(text, ["cta", "llamada a la acción", "llamada a la accion", "conversión", "conversion", "convertir", "leads", "consulta", "mensaje"]):
        focus_areas.append("conversión")
    if contains_any(text, ["funnel", "embudo", "landing", "retargeting", "seguimiento", "pipeline"]):
        focus_areas.append("funnel")
    if contains_any(text, ["marca", "competidores", "competencia", "precio", "premium", "autoridad"]):
        focus_areas.append("posicionamiento")

    if not focus_areas:
        focus_areas = ["awareness", "propuesta de valor", "contenido", "funnel", "conversión"]

    return list(dict.fromkeys(focus_areas))


def infer_primary_bottleneck(text: str, focus_areas: List[str]) -> str:
    if "propuesta de valor" in focus_areas:
        return "propuesta de valor"
    if "conversión" in focus_areas:
        return "conversión"
    if "funnel" in focus_areas:
        return "funnel"
    if "posicionamiento" in focus_areas:
        return "posicionamiento"
    if "contenido" in focus_areas:
        return "contenido"
    return "awareness"


def infer_awareness_level(text: str, primary_bottleneck: str) -> str:
    if contains_any(text, ["no saben", "desconocen", "educar mercado", "mercado no entiende"]):
        return "unaware"
    if contains_any(text, ["problema", "dolor", "necesidad", "poca claridad", "confusión", "confusion"]):
        return "problem-aware"
    if contains_any(text, ["solución", "solucion", "alternativa", "comparan", "competidores"]):
        return "solution-aware"
    if contains_any(text, ["marca", "producto", "servicio", "testimonios", "casos de éxito", "casos de exito"]):
        return "product-aware"
    if contains_any(text, ["precio", "promoción", "promocion", "agenda", "cotización", "cotizacion", "comprar"]):
        return "most-aware"
    if primary_bottleneck in ["propuesta de valor", "contenido", "funnel"]:
        return "problem-aware"
    return "problem-aware"


def build_commercial_risk(primary_bottleneck: str) -> str:
    risks = {
        "propuesta de valor": "La empresa puede estar generando visibilidad sin lograr que el mercado entienda por qué debería elegirla frente a otras alternativas.",
        "conversión": "La empresa puede estar atrayendo atención, pero perdiendo oportunidades porque no guía al usuario hacia una acción comercial concreta.",
        "funnel": "La empresa puede tener puntos de contacto aislados, pero sin un recorrido claro que transforme interés en oportunidad comercial.",
        "posicionamiento": "La empresa puede quedar atrapada en comparación por precio o apariencia porque no comunica una diferencia estratégica clara.",
        "contenido": "La empresa puede estar publicando con frecuencia, pero sin una narrativa que construya demanda, autoridad o intención de compra.",
        "awareness": "La empresa puede tener baja presencia mental en el mercado y depender demasiado de acciones tácticas de corto plazo.",
    }
    return risks.get(primary_bottleneck, "La empresa puede estar haciendo actividad digital sin convertirla en demanda calificada.")


def build_recommended_angle(primary_bottleneck: str) -> str:
    angles = {
        "propuesta de valor": "Mostrar la brecha entre tener presencia digital y comunicar una razón clara para ser elegido.",
        "conversión": "Mostrar cómo la falta de CTA y dirección comercial reduce la cantidad de consultas calificadas.",
        "funnel": "Mostrar que el problema no es solo publicar más, sino construir un recorrido desde atención hasta conversión.",
        "posicionamiento": "Mostrar cómo una marca sin diferenciación termina compitiendo por precio, estética o disponibilidad.",
        "contenido": "Mostrar que el contenido actual puede entretener o informar, pero no necesariamente vender.",
        "awareness": "Mostrar que sin presencia mental suficiente, cada acción comercial empieza desde cero.",
    }
    return angles.get(primary_bottleneck, "Mostrar una brecha comercial concreta sin entregar todavía la solución completa.")


def infer_confidence(request: ProspectAuditRequest) -> str:
    signal_count = sum([
        bool(request.website),
        bool(request.instagram),
        bool(request.linkedin),
        bool(request.industry),
        bool(request.offer),
        bool(request.notes and len(request.notes) > 40),
    ])
    if signal_count >= 4:
        return "media-alta"
    if signal_count >= 2:
        return "media"
    return "baja"


@app.post(
    "/audit/prospect",
    response_model=ProspectAuditResponse,
    operation_id="auditProspect",
    summary="Audit a marketing prospect",
    description="Recibe datos básicos de un prospecto y devuelve focos de auditoría comercial.",
    dependencies=[Security(verify_api_key)],
)
def audit_prospect(request: ProspectAuditRequest):
    text = build_analysis_text(request)
    focus_areas = infer_focus_areas(text, request)
    primary_bottleneck = infer_primary_bottleneck(text, focus_areas)
    awareness_level = infer_awareness_level(text, primary_bottleneck)

    return ProspectAuditResponse(
        company_name=request.company_name,
        audit_type="smart_prospect_audit",
        awareness_level=awareness_level,
        primary_bottleneck=primary_bottleneck,
        detected_focus_areas=focus_areas,
        commercial_risk=build_commercial_risk(primary_bottleneck),
        recommended_angle=build_recommended_angle(primary_bottleneck),
        next_step="Preparar un diagnóstico comercial breve que muestre la brecha principal y proponga una reunión para profundizar la solución.",
        do_not_give_for_free=[
            "calendario completo de contenido",
            "reescritura integral de la propuesta de valor",
            "estructura completa de campañas",
            "arquitectura completa de funnel",
            "segmentaciones detalladas de pauta",
            "copys finales listos para implementar",
        ],
        confidence=infer_confidence(request),
    )


@app.post(
    "/report/brief",
    response_model=ReportBriefResponse,
    operation_id="createReportBrief",
    summary="Create a commercial audit report brief",
    description="Genera una estructura breve de reporte comercial a partir de hallazgos de auditoría.",
    dependencies=[Security(verify_api_key)],
)
def create_report_brief(request: ReportBriefRequest):
    bottleneck = request.primary_bottleneck or "brecha comercial"
    return ReportBriefResponse(
        company_name=request.company_name,
        report_type="commercial_audit_brief",
        report_sections=[
            "Diagnóstico inicial",
            "Mapa de awareness",
            "Problema comercial principal",
            "Riesgo de mantener la situación actual",
            "Oportunidad estratégica detectada",
            "Qué conviene mostrar en reunión",
            "Próximo paso recomendado",
        ],
        opening_angle=f"La presentación debería abrir mostrando cómo {request.company_name} puede estar perdiendo oportunidades por un problema de {bottleneck}.",
        recommended_close="Cerrar con una invitación a revisar el caso en una reunión breve, sin entregar todavía la estrategia completa.",
        do_not_include=[
            "plan completo de contenidos",
            "estructura completa de campañas",
            "copys finales",
            "segmentaciones detalladas",
            "presupuesto táctico completo",
            "implementación paso a paso",
        ],
    )


@app.get(
    "/tools/status",
    response_model=ToolsStatusResponse,
    operation_id="getToolsStatus",
    summary="Check available Composio toolkits",
    description="Verifica si Composio está configurado y revisa herramientas disponibles para toolkits relevantes.",
    dependencies=[Security(verify_api_key)],
)
def get_tools_status():
    toolkits_to_check = [
        "apify",
        "browser_tool",
        "composio_search",
        "search_api",
        "semrush",
        "similarweb",
        "google_sheets",
        "google_drive",
    ]

    if not COMPOSIO_API_KEY:
        return ToolsStatusResponse(
            composio_configured=False,
            checked_toolkits=[],
            recommendation="COMPOSIO_API_KEY no está configurada. Agregala como variable de entorno antes de usar herramientas externas.",
        )

    checked = []

    for toolkit in toolkits_to_check:
        try:
            data = composio_get("/tools", params={"toolkit_slug": toolkit, "limit": 20})
            tools = extract_tools_list(data)
            sample_tools = [normalize_tool(tool).slug for tool in tools[:5]]
            checked.append(
                ToolkitStatus(
                    toolkit=toolkit,
                    available=len(tools) > 0,
                    tool_count=len(tools),
                    sample_tools=sample_tools,
                )
            )
        except Exception as exc:
            checked.append(
                ToolkitStatus(
                    toolkit=toolkit,
                    available=False,
                    tool_count=0,
                    sample_tools=[],
                    error=str(exc),
                )
            )

    essential = ["search_api", "browser_tool", "apify"]
    available_essential = [
        item.toolkit for item in checked
        if item.toolkit in essential and item.available
    ]

    if len(available_essential) == len(essential):
        recommendation = "Herramientas esenciales disponibles. Se puede avanzar a búsqueda pública, validación de páginas y scraping controlado."
    elif available_essential:
        recommendation = "Hay algunas herramientas esenciales disponibles, pero conviene conectar o verificar las faltantes antes de una auditoría completa."
    else:
        recommendation = "No se detectaron herramientas esenciales. Primero conectá o verificá Search API, Browser Tool o Apify."

    return ToolsStatusResponse(
        composio_configured=True,
        checked_toolkits=checked,
        recommendation=recommendation,
    )


@app.post(
    "/tools/search",
    response_model=ToolsSearchResponse,
    operation_id="searchComposioTools",
    summary="Search Composio tools",
    description="Busca herramientas disponibles en Composio usando texto libre y, opcionalmente, un toolkit específico.",
    dependencies=[Security(verify_api_key)],
)
def search_composio_tools(request: ToolsSearchRequest):
    params = {"limit": 100}

    if request.toolkit_slug:
        params["toolkit_slug"] = request.toolkit_slug

    data = composio_get("/tools", params=params)
    tools = extract_tools_list(data)

    matches = [
        normalize_tool(tool)
        for tool in tools
        if tool_matches_query(tool, request.query)
    ]

    return ToolsSearchResponse(
        query=request.query,
        toolkit_slug=request.toolkit_slug,
        results=matches[:request.limit],
    )


@app.get(
    "/tools/details/{tool_slug}",
    response_model=ToolDetailsResponse,
    operation_id="getComposioToolDetails",
    summary="Get Composio tool details",
    description="Obtiene detalles y schema de una herramienta específica de Composio.",
    dependencies=[Security(verify_api_key)],
)
def get_composio_tool_details(tool_slug: str):
    data = composio_get(f"/tools/{tool_slug}")

    if not isinstance(data, dict):
        data = {"response": data}

    return ToolDetailsResponse(
        tool_slug=tool_slug,
        raw_response=data,
    )


@app.post(
    "/tools/execute",
    response_model=ToolExecuteResponse,
    operation_id="executeComposioTool",
    summary="Execute an allowed Composio tool",
    description="Ejecuta una herramienta permitida de Composio usando argumentos estructurados o texto en lenguaje natural.",
    dependencies=[Security(verify_api_key)],
)
def execute_composio_tool(request: ToolExecuteRequest):
    if request.tool_slug not in ALLOWED_COMPOSIO_TOOLS:
        raise HTTPException(
            status_code=403,
            detail=f"La herramienta {request.tool_slug} no está permitida todavía. Permitidas: {sorted(ALLOWED_COMPOSIO_TOOLS)}",
        )

    if not request.arguments and not request.text:
        raise HTTPException(
            status_code=422,
            detail="Debés enviar arguments o text para ejecutar la herramienta.",
        )

    payload = {"user_id": request.user_id, "version": "latest"}

    if request.arguments:
        payload["arguments"] = request.arguments
    else:
        payload["text"] = request.text

    data = composio_post(f"/tools/execute/{request.tool_slug}", payload=payload)

    if not isinstance(data, dict):
        data = {"response": data}

    return ToolExecuteResponse(
        tool_slug=request.tool_slug,
        successful=data.get("successful"),
        data=data.get("data"),
        error=data.get("error"),
        raw_response=data,
    )


@app.post(
    "/research/company-public-presence",
    response_model=PublicPresenceResponse,
    operation_id="researchCompanyPublicPresence",
    summary="Research public presence of a company",
    description="Busca presencia pública de una empresa usando Search API vía Composio y devuelve fuentes normalizadas para auditoría comercial.",
    dependencies=[Security(verify_api_key)],
)
def research_company_public_presence(request: PublicPresenceRequest):
    if "SEARCH_API_SEARCH" not in ALLOWED_COMPOSIO_TOOLS:
        raise HTTPException(
            status_code=403,
            detail="SEARCH_API_SEARCH no está permitido en ALLOWED_COMPOSIO_TOOLS.",
        )

    queries = build_public_presence_queries(request)
    sources: List[PublicSourceResult] = []
    errors: List[str] = []

    safe_num = max(1, min(request.num_results_per_query, 10))

    for query_item in queries:
        category = query_item["category"]
        query = query_item["query"]

        try:
            raw_response = execute_search_api_query(query=query, num_results=safe_num, user_id="default")
            organic_results = find_organic_results(raw_response)

            for item in organic_results[:safe_num]:
                if isinstance(item, dict):
                    sources.append(normalize_search_result(item=item, category=category, query=query))

        except HTTPException as exc:
            errors.append(f"{category}: {exc.detail}")
        except Exception as exc:
            errors.append(f"{category}: {str(exc)}")

    queries_used = [item["query"] for item in queries]

    if len(sources) >= 8:
        confidence = "media-alta"
    elif len(sources) >= 3:
        confidence = "media"
    else:
        confidence = "baja"

    if sources:
        summary = (
            f"Se encontraron {len(sources)} fuentes públicas relacionadas con {request.company_name}. "
            "La información puede usarse como base para validar presencia digital, perfiles sociales, reputación y contexto competitivo."
        )
    else:
        summary = (
            f"No se encontraron fuentes públicas suficientes para {request.company_name}. "
            "Conviene revisar el nombre, ciudad, rubro o perfiles conocidos."
        )

    if errors:
        summary = summary + f" Algunas búsquedas tuvieron errores: {len(errors)}."

    return PublicPresenceResponse(
        company_name=request.company_name,
        research_type="company_public_presence",
        queries_used=queries_used,
        sources_found=sources,
        presence_summary=summary,
        research_confidence=confidence,
        next_step="Usar estas fuentes como insumo para auditProspect y luego generar un diagnóstico comercial breve.",
        raw_result_count=len(sources),
    )

@app.post(
    "/audit/prospect-with-research",
    response_model=ProspectWithResearchResponse,
    operation_id="auditProspectWithResearch",
    summary="Audit a prospect with public research",
    description="Investiga presencia pública, resume fuentes, audita el prospecto y devuelve scoring, blueprint, plan correctivo y reporte listo para plantilla.",
    dependencies=[Security(verify_api_key)],
)
def audit_prospect_with_research(request: ProspectWithResearchRequest):
    public_presence_request = PublicPresenceRequest(
        company_name=request.company_name,
        industry=request.industry,
        city=request.city,
        country=request.country,
        website=request.website,
        instagram=request.instagram,
        linkedin=request.linkedin,
        num_results_per_query=request.num_results_per_query,
    )

    research = research_company_public_presence(public_presence_request)
    public_sources_summary = summarize_public_sources(
        research.sources_found,
        max_sources=5,
    )

    enriched_notes = build_research_notes(
        request=request,
        public_sources=public_sources_summary,
        presence_summary=research.presence_summary,
    )

    audit_request = ProspectAuditRequest(
        company_name=request.company_name,
        website=request.website,
        instagram=request.instagram,
        linkedin=request.linkedin,
        industry=request.industry,
        offer=request.offer,
        notes=enriched_notes,
    )

    audit = audit_prospect(audit_request)

    diagnosis_initial = build_initial_diagnosis(
        request=request,
        audit=audit,
        public_sources=public_sources_summary,
    )

    commercial_score = build_commercial_score(
        audit=audit,
        public_sources=public_sources_summary,
        raw_sources_count=research.raw_result_count,
        request=request,
    )

    score_interpretation = build_score_interpretation(
        score=commercial_score,
        audit=audit,
    )

    awareness_funnel_locator = build_awareness_funnel_locator(
        audit=audit,
        score=commercial_score,
        request=request,
    )

    temperature_heatmap = build_temperature_heatmap(
        audit=audit,
        score=commercial_score,
    )

    customer_intent_density_map = build_customer_intent_density_map(
        awareness_funnel_locator=awareness_funnel_locator,
        heatmap=temperature_heatmap,
        audit=audit,
    )

    visual_diagram_mermaid = build_visual_diagram_mermaid(audit)
    funnel_blueprint = build_funnel_blueprint(audit)

    corrective_action_plan = build_corrective_action_plan(
        request=request,
        audit=audit,
        public_sources=public_sources_summary,
        score=commercial_score,
    )

    report_pages = build_report_pages(
        request=request,
        audit=audit,
        score=commercial_score,
        interpretation=score_interpretation,
        public_sources=public_sources_summary,
        corrective_actions=corrective_action_plan,
        awareness_funnel_locator=awareness_funnel_locator,
        temperature_heatmap=temperature_heatmap,
        funnel_blueprint=funnel_blueprint,
    )

    report_ready_markdown = build_report_ready_markdown(
        request=request,
        audit=audit,
        public_sources=public_sources_summary,
        diagnosis_initial=diagnosis_initial,
        commercial_score=commercial_score,
        score_interpretation=score_interpretation,
        awareness_funnel_locator=awareness_funnel_locator,
        temperature_heatmap=temperature_heatmap,
        customer_intent_density_map=customer_intent_density_map,
        visual_diagram_mermaid=visual_diagram_mermaid,
        funnel_blueprint=funnel_blueprint,
        corrective_action_plan=corrective_action_plan,
    )

    report_sections = [
        "Diagnóstico inicial",
        "Fuentes públicas revisadas",
        "Score comercial",
        "Awareness funnel locator",
        "Customer temperature heatmap",
        "Customer intent density map",
        "Problema comercial principal",
        "Riesgo comercial",
        "Funnel blueprint / system map",
        "Blueprint diagram",
        "Plan de acción recomendado",
        "Próximo paso recomendado",
        "Límites de esta entrega",
    ]

    return ProspectWithResearchResponse(
        company_name=request.company_name,
        audit_type="prospect_audit_with_public_research_v2",
        research_confidence=research.research_confidence,
        public_sources_summary=public_sources_summary,
        diagnosis_initial=diagnosis_initial,
        audit=IntegratedAuditBlock(
            awareness_level=audit.awareness_level,
            primary_bottleneck=audit.primary_bottleneck,
            detected_focus_areas=audit.detected_focus_areas,
            commercial_risk=audit.commercial_risk,
            recommended_angle=audit.recommended_angle,
            confidence=audit.confidence,
        ),
        commercial_score=commercial_score,
        score_interpretation=score_interpretation,
        awareness_funnel_locator=awareness_funnel_locator,
        temperature_heatmap=temperature_heatmap,
        customer_intent_density_map=customer_intent_density_map,
        visual_diagram_mermaid=visual_diagram_mermaid,
        funnel_blueprint=funnel_blueprint,
        corrective_action_plan=corrective_action_plan,
        report_pages=report_pages,
        report_sections=report_sections,
        report_ready_markdown=report_ready_markdown,
        do_not_give_for_free=audit.do_not_give_for_free,
        next_step=audit.next_step,
        raw_sources_count=research.raw_result_count,
    )
