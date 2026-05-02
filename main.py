import os
import html
import math
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
    version="1.4.0",
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


class CampaignMetric(BaseModel):
    channel: Optional[str] = Field(None, description="Canal: Meta Ads, Google Ads, TikTok Ads, etc.")
    campaign_name: str = Field(..., description="Nombre de campaña")
    adset_name: Optional[str] = Field(None, description="Ad set, grupo de anuncios o conjunto")
    ad_name: Optional[str] = Field(None, description="Anuncio o creativo")
    funnel_stage: Optional[str] = Field(None, description="Awareness, interest, consideration, conversion o retargeting")
    temperature: Optional[str] = Field(None, description="Frío, tibio, templado, caliente")
    objective: Optional[str] = Field(None, description="Objetivo declarado de campaña")
    spend: Optional[float] = Field(None, description="Gasto")
    impressions: Optional[int] = None
    reach: Optional[int] = None
    frequency: Optional[float] = None
    clicks: Optional[int] = None
    ctr_percent: Optional[float] = Field(None, description="CTR en porcentaje. Ej: 1.5 para 1.5%")
    cpc: Optional[float] = None
    cpm: Optional[float] = None
    landing_visits: Optional[int] = None
    form_starts: Optional[int] = None
    form_submits: Optional[int] = None
    whatsapp_clicks: Optional[int] = None
    calls: Optional[int] = None
    key_events: Optional[int] = None
    leads: Optional[int] = None
    qualified_leads: Optional[int] = None
    bad_leads: Optional[int] = None
    conversions: Optional[int] = None
    sales: Optional[int] = None
    revenue: Optional[float] = None
    cpl: Optional[float] = None
    cpa: Optional[float] = None
    lead_quality_score: Optional[float] = Field(None, description="Score 0-100 si existe")

    # Enrichment fields for deeper analysis. All optional to keep backward compatibility.
    previous_spend: Optional[float] = Field(None, description="Gasto del período anterior comparable")
    previous_impressions: Optional[int] = Field(None, description="Impresiones del período anterior comparable")
    previous_clicks: Optional[int] = Field(None, description="Clicks del período anterior comparable")
    previous_ctr_percent: Optional[float] = Field(None, description="CTR anterior en porcentaje")
    previous_cpc: Optional[float] = Field(None, description="CPC anterior")
    previous_cpm: Optional[float] = Field(None, description="CPM anterior")
    previous_leads: Optional[int] = Field(None, description="Leads del período anterior comparable")
    previous_conversions: Optional[int] = Field(None, description="Conversiones del período anterior comparable")
    previous_cpl: Optional[float] = Field(None, description="CPL anterior")
    previous_cpa: Optional[float] = Field(None, description="CPA anterior")
    previous_frequency: Optional[float] = Field(None, description="Frecuencia anterior")
    previous_lead_quality_score: Optional[float] = Field(None, description="Score de calidad anterior")

    hook: Optional[str] = Field(None, description="Hook o ángulo principal del anuncio")
    angle: Optional[str] = Field(None, description="Ángulo creativo: inversión, financiación, seguridad, amenities, etc.")
    creative_format: Optional[str] = Field(None, description="Formato creativo: video, carrusel, imagen, search, etc.")
    ad_promise: Optional[str] = Field(None, description="Promesa principal del anuncio")
    landing_url: Optional[str] = None
    landing_message: Optional[str] = Field(None, description="Mensaje principal de la landing")
    audience: Optional[str] = Field(None, description="Audiencia o segmento")
    utms_present: Optional[bool] = Field(None, description="Si la campaña tiene UTMs consistentes")
    events_configured: Optional[bool] = Field(None, description="Si hay eventos configurados en GA4/Pixel/CAPI")
    conversion_event_name: Optional[str] = None
    crm_stage: Optional[str] = None
    meetings: Optional[int] = None
    opportunities: Optional[int] = None
    close_rate_percent: Optional[float] = None
    mobile_share_percent: Optional[float] = None
    notes: Optional[str] = None


class CampaignPerformanceRequest(BaseModel):
    company_name: str = Field(..., description="Nombre de la empresa")
    currency: str = Field("ARS", description="Moneda")
    campaigns: List[CampaignMetric] = Field(default_factory=list)
    notes: Optional[str] = Field(None, description="Notas del analista sobre campañas, tracking o calidad comercial")
    target_cpl: Optional[float] = Field(None, description="CPL objetivo o aceptable")
    target_cpa: Optional[float] = Field(None, description="CPA objetivo o aceptable")
    target_ctr_percent: float = Field(1.0, description="CTR mínimo esperado en porcentaje")
    target_landing_conversion_rate_percent: float = Field(2.0, description="Conversión mínima esperada de landing a lead")
    min_lead_quality_rate_percent: float = Field(50.0, description="Porcentaje mínimo esperado de leads calificados")


class PerformanceFinding(BaseModel):
    title: str
    evidence: str
    interpretation: str
    severity: str
    affected_campaigns: List[str]


class PerformanceAction(BaseModel):
    category: str
    action: str
    trigger: str
    evidence: str
    priority: str
    effort: str
    expected_impact: str
    verification_metric: str
    related_campaign: Optional[str] = None
    funnel_stage: Optional[str] = None
    confidence: str
    data_required: bool = False


class DerivedCampaignMetrics(BaseModel):
    campaign_name: str
    channel: Optional[str] = None
    spend: Optional[float] = None
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    leads: Optional[int] = None
    conversions: Optional[int] = None
    ctr_percent: Optional[float] = None
    cpc: Optional[float] = None
    cpm: Optional[float] = None
    cpl: Optional[float] = None
    cpa: Optional[float] = None
    cvr_percent: Optional[float] = None
    lead_quality_rate_percent: Optional[float] = None
    frequency: Optional[float] = None
    sample_status: str
    tracking_reliability: str


class PerformanceMetricDelta(BaseModel):
    campaign_name: str
    delta_spend_percent: Optional[float] = None
    delta_impressions_percent: Optional[float] = None
    delta_clicks_percent: Optional[float] = None
    delta_ctr_percent: Optional[float] = None
    delta_cpc_percent: Optional[float] = None
    delta_cpm_percent: Optional[float] = None
    delta_leads_percent: Optional[float] = None
    delta_cpl_percent: Optional[float] = None
    delta_cpa_percent: Optional[float] = None
    delta_frequency_percent: Optional[float] = None
    delta_lead_quality_percent: Optional[float] = None
    interpretation: str


class CrossMetricFinding(BaseModel):
    pattern: str
    evidence: str
    interpretation: str
    affected_campaigns: List[str]
    severity: str
    confidence: str
    recommended_action: str


class TrackingHealthFinding(BaseModel):
    campaign_name: Optional[str] = None
    issue: str
    severity: str
    evidence: str
    business_risk: str
    recommended_fix: str
    validation_metric: str


class LeadQualityAssessment(BaseModel):
    campaign_name: str
    lead_quality_score: Optional[float] = None
    quality_level: str
    evidence: str
    recommendation: str


class CostQualityQuadrant(BaseModel):
    campaign_name: str
    quadrant: str
    cpl: Optional[float] = None
    quality_score: Optional[float] = None
    recommendation: str
    confidence: str


class BudgetReallocationRecommendation(BaseModel):
    campaign_name: str
    action: str
    recommended_change_percent: Optional[float] = None
    reason: str
    risk: str
    confidence: str


class CreativeHookInsight(BaseModel):
    hook: str
    affected_campaigns: List[str]
    signal: str
    interpretation: str
    recommended_next_test: str


class LandingFrictionAssessment(BaseModel):
    campaign_name: str
    friction_score: int
    evidence: str
    likely_issue: str
    recommended_fix: str


class MessageMatchAssessment(BaseModel):
    campaign_name: str
    message_match_score: int
    mismatch_detected: bool
    evidence: str
    recommended_fix: str


class FunnelLeakFinding(BaseModel):
    campaign_name: str
    leak_stage: str
    evidence: str
    probable_cause: str
    recommended_action: str
    metric_to_validate: str


class ExperimentRecommendation(BaseModel):
    title: str
    hypothesis: str
    change: str
    primary_metric: str
    secondary_metric: str
    success_criteria: str
    minimum_duration: str
    risk: str
    do_not_touch: str


class DataCompletenessScore(BaseModel):
    score: int
    missing_fields: List[str]
    impact_on_analysis: str
    next_data_to_collect: List[str]


class CommercialReadinessScore(BaseModel):
    overall: int
    tracking_readiness: int
    offer_clarity: int
    message_match: int
    funnel_continuity: int
    lead_quality: int
    creative_relevance: int
    landing_strength: int
    cta_clarity: int
    sales_follow_up: int
    budget_efficiency: int
    strongest_area: str
    weakest_area: str
    recommended_focus: str


class MapCoherenceCheck(BaseModel):
    score: int
    alignment_detected: List[str]
    inconsistencies: List[str]
    correction_needed: List[str]


class ProposalGuidance(BaseModel):
    what_to_sell: List[str]
    what_not_to_sell_yet: List[str]
    what_to_show_in_meeting: List[str]
    what_data_to_request: List[str]
    what_to_promise: List[str]
    what_not_to_promise: List[str]
    closing_angle: str


class TimedActionPlan(BaseModel):
    today_48h: List[str]
    next_7_days: List[str]
    next_14_30_days: List[str]
    next_60_90_days: List[str]


class CampaignPerformanceResponse(BaseModel):
    company_name: str
    audit_type: str
    data_quality: str
    campaigns_analyzed: int
    findings: List[PerformanceFinding]
    strategic_actions: List[PerformanceAction]
    performance_actions: List[PerformanceAction]
    budget_actions: List[PerformanceAction]
    tracking_actions: List[PerformanceAction]
    prioritized_actions: List[PerformanceAction]
    derived_metrics: List[DerivedCampaignMetrics]
    metric_deltas: List[PerformanceMetricDelta]
    internal_benchmarks: Dict[str, Optional[float]]
    cross_metric_findings: List[CrossMetricFinding]
    tracking_health: List[TrackingHealthFinding]
    lead_quality_assessment: List[LeadQualityAssessment]
    cost_quality_matrix: List[CostQualityQuadrant]
    budget_reallocation: List[BudgetReallocationRecommendation]
    creative_hook_insights: List[CreativeHookInsight]
    landing_friction: List[LandingFrictionAssessment]
    message_match: List[MessageMatchAssessment]
    funnel_leaks: List[FunnelLeakFinding]
    experiment_recommendations: List[ExperimentRecommendation]
    data_completeness: DataCompletenessScore
    sample_size_warnings: List[str]
    confidence_by_finding: List[str]
    timed_action_plan: TimedActionPlan
    discovery_questions: List[str]
    proposal_guidance: ProposalGuidance
    next_data_needed: List[str]
    summary: str


class FullCommercialSystemRequest(ProspectWithResearchRequest):
    campaigns: List[CampaignMetric] = Field(default_factory=list)
    campaign_notes: Optional[str] = Field(None, description="Notas específicas de performance/campañas")
    target_cpl: Optional[float] = None
    target_cpa: Optional[float] = None
    target_ctr_percent: float = 1.0
    target_landing_conversion_rate_percent: float = 2.0
    min_lead_quality_rate_percent: float = 50.0


class FullCommercialSystemResponse(BaseModel):
    company_name: str
    audit_type: str
    public_commercial_audit: ProspectWithResearchResponse
    campaign_performance: CampaignPerformanceResponse
    unified_priorities: List[PerformanceAction]
    commercial_readiness_score: CommercialReadinessScore
    data_completeness_score: DataCompletenessScore
    map_coherence_check: MapCoherenceCheck
    discovery_questions: List[str]
    proposal_guidance: ProposalGuidance
    timed_action_plan: TimedActionPlan
    system_summary: str
    recommended_next_step: str


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

Cómo explicarlo:
- El eje horizontal muestra avance comercial: Awareness → Interest → Consideration → Conversion.
- El eje vertical muestra temperatura: Frío → Tibio → Templado → Caliente.
- La intensidad de color muestra concentración diagnóstica, no medición real de clicks.
- La zona dominante indica dónde está el grueso del público.
- La zona bloqueada indica dónde el público pierde avance.
- La zona bloqueada se conecta conceptualmente con el FAULT del blueprint.
- Si la zona dominante está antes de conversión, hay interés sin suficiente movimiento hacia acción.
- Si la zona bloqueada está en conversión, el problema suele estar en CTA, confianza, prueba social o propuesta de valor.

Guion de lectura:
Este mapa cruza etapa del funnel con temperatura del cliente. Sirve para explicar dónde está acumulada la atención, dónde se enfría el recorrido y qué parte del sistema comercial debe rediseñarse en el blueprint.

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

Cómo explicarlo:
- A1–A5 muestran la ruta actual: lo que la marca ya tiene construido.
- FAULT muestra el punto de ruptura donde el recorrido pierde continuidad comercial.
- DG significa Diagnosis Gate: el diagnóstico que convierte la ruptura en rediseño.
- S1–S5 muestran la ruta de reconstrucción recomendada.
- SL-01–SL-05 muestran el support layer: mensajes, prueba, objeciones, CTA y seguimiento.
- Las conexiones moradas muestran que el support layer alimenta la ruta verde; no es una ruta paralela del funnel.
- OUT representa la salida deseada: oportunidad comercial más calificada.
- La relación central es ruta actual → ruptura → diagnosis gate → rediseño → soporte → conversión.

Guion de lectura:
Este blueprint no es un calendario de implementación; es un plano del sistema comercial. La ruta azul muestra lo que existe, FAULT muestra dónde se rompe, DG explica por qué empieza el rediseño, la ruta verde muestra cómo debería reconstruirse el sistema y el Support Layer muestra qué activos sostienen esa reconstrucción.

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
    width = 1320
    height = 720

    def grid_lines() -> str:
        parts = []
        for x in range(0, width + 1, 24):
            major = x % 120 == 0
            parts.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{height}" stroke="#7dd3fc" stroke-width="{1.0 if major else 0.55}" opacity="{0.20 if major else 0.07}"/>')
        for y in range(0, height + 1, 24):
            major = y % 120 == 0
            parts.append(f'<line x1="0" y1="{y}" x2="{width}" y2="{y}" stroke="#7dd3fc" stroke-width="{1.0 if major else 0.55}" opacity="{0.20 if major else 0.07}"/>')
        return ''.join(parts)

    def hex_points(cx: int, cy: int, r: int = 22) -> str:
        coords = [(cx+r,cy),(cx+r*.5,cy+r*.866),(cx-r*.5,cy+r*.866),(cx-r,cy),(cx-r*.5,cy-r*.866),(cx+r*.5,cy-r*.866)]
        return ' '.join([f'{x:.1f},{y:.1f}' for x,y in coords])

    def path_from(points, color, width_px, dash='') -> str:
        if not points:
            return ''
        d = f'M {points[0][0]} {points[0][1]}'
        for i in range(1, len(points)):
            px, py = points[i-1]
            x, y = points[i]
            mx = (px+x)/2
            d += f' C {mx:.1f} {py}, {mx:.1f} {y}, {x} {y}'
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
        return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width_px}" stroke-linecap="round" stroke-linejoin="round" opacity="0.92"{dash_attr}/>'

    def arrow_path(points, color, width_px, marker, dash='') -> str:
        if not points:
            return ''
        d = f'M {points[0][0]} {points[0][1]}'
        for i in range(1, len(points)):
            px, py = points[i-1]
            x, y = points[i]
            mx = (px+x)/2
            d += f' C {mx:.1f} {py}, {mx:.1f} {y}, {x} {y}'
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
        return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width_px}" stroke-linecap="round" stroke-linejoin="round" opacity="0.88" marker-end="url(#{marker})"{dash_attr}/>'

    def node(cx, cy, code, label, color, fill, r=24):
        return f'''
        <g>
          <polygon points="{hex_points(cx, cy, r + 10)}" fill="{color}" opacity="0.12" filter="url(#blueprintGlowSoft)"/>
          <polygon points="{hex_points(cx, cy, r)}" fill="{fill}" stroke="{color}" stroke-width="3"/>
          <text x="{cx}" y="{cy + 5}" text-anchor="middle" font-size="12" font-weight="900" fill="#e0f2fe">{h(code)}</text>
          <text x="{cx}" y="{cy + 45}" text-anchor="middle" font-size="10.5" font-weight="750" fill="#dbeafe">{h(label)}</text>
        </g>'''

    def sl_node(cx, cy, code, label):
        return f'''
        <g>
          <polygon points="{hex_points(cx, cy, 27)}" fill="#22143f" stroke="#c084fc" stroke-width="2.4"/>
          <text x="{cx}" y="{cy - 4}" text-anchor="middle" font-size="10" font-weight="900" fill="#f3e8ff">{h(code)}</text>
          <text x="{cx}" y="{cy + 12}" text-anchor="middle" font-size="13" font-weight="900" fill="#c084fc">SL</text>
          <text x="{cx}" y="{cy + 49}" text-anchor="middle" font-size="10.5" font-weight="750" fill="#f3e8ff">{h(label)}</text>
        </g>'''

    current = [((95,250),'A1','Presencia pública'),((245,250),'A2','Contenido / catálogo'),((395,250),'A3','Interés inicial'),((535,250),'A4','Comparación'),((620,350),'A5','Consulta débil')]
    fault = (635,250)
    dg = (770,250)
    rebuild = [((875,250),'S1','Mensaje diferencial'),((985,250),'S2','Contenido de valor'),((1095,250),'S3','Prueba social'),((1205,250),'S4','CTA claro'),((1268,360),'S5','Seguimiento')]
    out = (1268,455)
    sl_nodes = [((680,500),'SL-01','Mensajes clave',(875,250)),((800,500),'SL-02','Prueba / confianza',(985,250)),((920,500),'SL-03','Objeciones',(1095,250)),((1040,500),'SL-04','CTA / próximos pasos',(1205,250)),((1160,500),'SL-05','Follow-up',(1268,360))]

    current_trace = path_from([c for c,_,_ in current[:4]], '#93c5fd', 4.4)
    current_glow = path_from([c for c,_,_ in current[:4]], '#38bdf8', 13.0)
    fault_trace = arrow_path([(535,250), fault], '#f59e0b', 2.8, 'arrowAmber', '7 6')
    weak_trace = arrow_path([(535,250), (620,350)], '#93c5fd', 2.3, 'arrowBlue', '7 6')
    dg_trace = arrow_path([fault, dg], '#f59e0b', 2.8, 'arrowAmber', '7 6')
    rebuild_trace = path_from([dg]+[c for c,_,_ in rebuild[:4]], '#34d399', 4.4)
    rebuild_glow = path_from([dg]+[c for c,_,_ in rebuild[:4]], '#22c55e', 13.0)
    out_trace = arrow_path([(1205,250),(1268,360),out], '#34d399', 4.2, 'arrowGreen')

    support_arrows = []
    for (cx, cy), code, label, target in sl_nodes:
        tx, ty = target
        support_arrows.append(arrow_path([(cx,cy-27),(cx,410),(tx,ty+35)], '#c084fc', 2.0, 'arrowPurple', '4 6'))

    current_nodes = ''.join([node(cx,cy,code,label,'#93c5fd','#0f2a4a') for (cx,cy),code,label in current])
    rebuild_nodes = ''.join([node(cx,cy,code,label,'#34d399','#062d22') for (cx,cy),code,label in rebuild])
    support_nodes = ''.join([sl_node(cx,cy,code,label) for (cx,cy),code,label,_ in sl_nodes])

    fault_node = f'''
    <g>
      <polygon points="{hex_points(fault[0], fault[1], 34)}" fill="#3a2208" stroke="#f59e0b" stroke-width="3.2"/>
      <text x="{fault[0]}" y="{fault[1] + 5}" text-anchor="middle" font-size="13" font-weight="900" fill="#fcd34d">FAULT</text>
      <text x="{fault[0]}" y="{fault[1] + 48}" text-anchor="middle" font-size="11" fill="#fde68a">Se pierde avance</text>
    </g>'''
    dg_node = f'''
    <g>
      <polygon points="{hex_points(dg[0], dg[1], 28)}" fill="#112816" stroke="#eab308" stroke-width="2.8"/>
      <text x="{dg[0]}" y="{dg[1] - 3}" text-anchor="middle" font-size="12" font-weight="900" fill="#fef3c7">DG</text>
      <text x="{dg[0]}" y="{dg[1] + 13}" text-anchor="middle" font-size="8.5" font-weight="800" fill="#fef3c7">GATE</text>
      <text x="{dg[0]}" y="{dg[1] + 48}" text-anchor="middle" font-size="11" fill="#fef3c7">Diagnosis Gate</text>
    </g>'''
    out_node = f'''
    <g>
      <polygon points="{hex_points(out[0], out[1], 30)}" fill="#062d22" stroke="#86efac" stroke-width="3"/>
      <text x="{out[0]}" y="{out[1] + 5}" text-anchor="middle" font-size="12" font-weight="900" fill="#bbf7d0">OUT</text>
      <text x="{out[0]}" y="{out[1] + 48}" text-anchor="middle" font-size="11" fill="#dcfce7">Oportunidad</text>
    </g>'''

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Commercial system blueprint">
    <defs>
      <radialGradient id="blueprintBg" cx="50%" cy="42%" r="78%"><stop offset="0%" stop-color="#14406f"/><stop offset="100%" stop-color="#061426"/></radialGradient>
      <filter id="blueprintGlowSoft" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="8"/></filter>
      <filter id="traceGlow" x="-45%" y="-45%" width="190%" height="190%"><feGaussianBlur stdDeviation="5"/></filter>
      <marker id="arrowBlue" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#93c5fd"/></marker>
      <marker id="arrowGreen" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#34d399"/></marker>
      <marker id="arrowAmber" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#f59e0b"/></marker>
      <marker id="arrowPurple" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#c084fc"/></marker>
    </defs>
    <rect width="{width}" height="{height}" rx="26" fill="#061426"/>
    <rect x="24" y="20" width="{width-48}" height="{height-36}" rx="24" fill="url(#blueprintBg)" stroke="#2563eb" stroke-width="1.2"/>
    {grid_lines()}
    <text x="660" y="52" text-anchor="middle" font-size="32" font-weight="900" fill="#e0f2fe">Commercial System Blueprint</text>
    <text x="660" y="82" text-anchor="middle" font-size="14" fill="#bfdbfe">Mapa técnico integrado del recorrido comercial, ruptura, Diagnosis Gate y ruta de reconstrucción</text>
    <path d="M 45 180 L 445 180 L 500 225 L 470 325 L 150 340 L 45 310 Z" fill="#0f2a4a" opacity="0.27" stroke="#93c5fd" stroke-width="1.5" stroke-dasharray="12 8"/>
    <text x="82" y="203" font-size="13" font-weight="900" fill="#bfdbfe">RUTA ACTUAL</text><text x="82" y="221" font-size="11" fill="#dbeafe">ACQUISITION + INTEREST LAYER</text>
    <path d="M 480 178 L 805 178 L 835 310 L 750 390 L 555 390 L 470 310 Z" fill="#3a2208" opacity="0.30" stroke="#f59e0b" stroke-width="1.7" stroke-dasharray="10 7"/>
    <text x="550" y="203" font-size="13" font-weight="900" fill="#fcd34d">ZONA DE RUPTURA / VALUE GAP</text>
    <path d="M 840 180 L 1300 180 L 1310 420 L 1210 475 L 850 405 Z" fill="#062d22" opacity="0.30" stroke="#86efac" stroke-width="1.5" stroke-dasharray="12 8"/>
    <text x="1015" y="203" text-anchor="middle" font-size="13" font-weight="900" fill="#bbf7d0">RUTA RECOMENDADA</text><text x="1015" y="221" text-anchor="middle" font-size="11" fill="#dcfce7">REBUILD + CONVERSION LAYER</text>
    <path d="M 560 440 L 1238 440 L 1270 600 L 535 600 Z" fill="#20123d" opacity="0.30" stroke="#c084fc" stroke-width="1.6" stroke-dasharray="8 7"/>
    <text x="584" y="462" font-size="14" font-weight="900" fill="#c084fc">SUPPORT LAYER (SL)</text><text x="584" y="480" font-size="11" fill="#e9d5ff">Infraestructura que alimenta la ruta recomendada; no es una etapa extra del funnel.</text>
    <g opacity="0.20" filter="url(#traceGlow)">{current_glow}{rebuild_glow}</g>
    {current_trace}{fault_trace}{weak_trace}{dg_trace}{rebuild_trace}{out_trace}{''.join(support_arrows)}
    {current_nodes}{fault_node}{dg_node}{rebuild_nodes}{out_node}{support_nodes}
    <g><rect x="44" y="630" width="1232" height="42" rx="10" fill="#061a2f" stroke="#2563eb" stroke-width="1" opacity="0.92"/>
      <line x1="70" y1="651" x2="110" y2="651" stroke="#93c5fd" stroke-width="4" stroke-linecap="round"/><text x="124" y="655" font-size="11" fill="#dbeafe">Ruta actual (A1–A5)</text>
      <line x1="260" y1="651" x2="300" y2="651" stroke="#f59e0b" stroke-width="3" stroke-dasharray="7 6"/><text x="314" y="655" font-size="11" fill="#fef3c7">FAULT / DG</text>
      <line x1="430" y1="651" x2="470" y2="651" stroke="#34d399" stroke-width="4" stroke-linecap="round"/><text x="484" y="655" font-size="11" fill="#dcfce7">Ruta recomendada (S1–S5)</text>
      <line x1="705" y1="651" x2="745" y2="651" stroke="#c084fc" stroke-width="3" stroke-dasharray="4 6"/><text x="759" y="655" font-size="11" fill="#f3e8ff">Support Layer alimenta la ruta verde</text>
      <text x="1110" y="655" font-size="11" fill="#cbd5e1">OUT = salida de conversión</text></g>
    <g><rect x="44" y="682" width="1232" height="28" rx="10" fill="#07182c" stroke="#2563eb" stroke-width="1" opacity="0.88"/><text x="660" y="701" text-anchor="middle" font-size="11.5" fill="#bfdbfe">OBJETIVO DEL SISTEMA: llevar al usuario desde atención e interés hacia preferencia, confianza y conversión calificada.</text></g>
    </svg>'''


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
    height = 500
    chart_x = 108
    chart_y = 128
    chart_w = 870
    chart_h = 295
    stage_step = chart_w / (len(x_axis) - 1)
    temp_step = chart_h / (len(y_axis) - 1)

    def x_pos(label: str) -> float:
        return chart_x + x_axis.index(label) * stage_step

    def y_pos(label: str) -> float:
        # Invert y-axis: Frío abajo, Caliente arriba.
        return chart_y + (len(y_axis) - 1 - y_axis.index(label)) * temp_step

    points = [
        (x_pos(point.x), y_pos(point.y), max(0, min(int(point.value), 100)), point.x, point.y)
        for point in density_map.density_points
    ]

    def deterministic_noise(row: int, col: int, salt: int = 0) -> float:
        raw = (row * 92821 + col * 68917 + row * col * 193 + salt * 8347) % 1000
        return raw / 1000

    def field_value(px: float, py: float, row: int, col: int) -> float:
        total = 0.0
        for gx, gy, value, _, _ in points:
            dx = (px - gx) / 185
            dy = (py - gy) / 34
            total += value * math.exp(-0.5 * ((dx * dx) + (dy * dy)))

        y_ratio = (py - chart_y) / chart_h
        temp_bias = 7 + (1 - y_ratio) * 8
        noise = 0.72 + deterministic_noise(row, col, 11) * 0.58
        return max(0, min(100, (total * 0.64 + temp_bias) * noise))

    raster_parts = []
    raster_rows = 56
    raster_cols = 72
    cell_w = chart_w / raster_cols
    cell_h = chart_h / raster_rows

    for row in range(raster_rows):
        py = chart_y + row * cell_h + cell_h / 2

        for col in range(raster_cols):
            px = chart_x + col * cell_w + cell_w / 2
            value = field_value(px, py, row, col)
            noise = deterministic_noise(row, col, 23)

            if value < 13 and noise < 0.68:
                continue

            fill = density_color(round(value))
            frag_w = cell_w * (0.50 + noise * 1.15)
            frag_h = max(2.0, cell_h * (0.34 + deterministic_noise(row, col, 31) * 0.56))
            x = px - frag_w / 2
            y = py - frag_h / 2

            opacity = min(0.82, 0.045 + value / 135)
            if value < 20:
                opacity *= 0.55

            raster_parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{frag_w:.1f}" height="{frag_h:.1f}" '
                f'rx="1.5" fill="{fill}" opacity="{opacity:.3f}"/>'
            )

    shelves = []
    for gx, gy, value, x_label, y_label in points:
        if value < 35:
            continue

        color = density_color(value)
        for layer in range(3):
            layer_noise = deterministic_noise(int(gx), int(gy), layer + 40)
            shelf_len = 100 + value * (3.2 + layer * 0.55) + layer_noise * 70
            shelf_h = max(2.2, 2 + value * (0.035 + layer * 0.018))
            shelf_y = gy + (layer - 1) * (6 + layer_noise * 5)
            shelf_x = max(chart_x, gx - shelf_len / 2 + (layer_noise - 0.5) * 50)
            shelf_w = min(shelf_len, chart_x + chart_w - shelf_x)

            shelves.append(
                f'<rect x="{shelf_x:.1f}" y="{shelf_y:.1f}" width="{shelf_w:.1f}" height="{shelf_h:.1f}" '
                f'rx="{shelf_h/2:.1f}" fill="{color}" opacity="{0.24 + value/210:.3f}" filter="url(#softGlow)"/>'
            )

        if value >= 55:
            core_len = 70 + value * 2.4
            core_x = max(chart_x, gx - core_len / 2)
            core_w = min(core_len, chart_x + chart_w - core_x)
            shelves.append(
                f'<rect x="{core_x:.1f}" y="{gy-1.8:.1f}" width="{core_w:.1f}" height="3.6" '
                f'rx="1.8" fill="{color}" opacity="0.88"/>'
            )

    clouds = []
    for gx, gy, value, _, _ in points:
        if value < 45:
            continue
        color = density_color(value)
        clouds.append(
            f'<ellipse cx="{gx:.1f}" cy="{gy:.1f}" rx="{95 + value*1.15:.1f}" ry="{22 + value*0.20:.1f}" '
            f'fill="{color}" opacity="{0.09 + value/420:.3f}" filter="url(#heavyBlur)"/>'
        )

    background_zones = []
    band_labels = [
        ("Caliente", "#7f1d1d", 0.23),
        ("Templado", "#713f12", 0.15),
        ("Tibio", "#064e3b", 0.13),
        ("Frío", "#0f2a5f", 0.22),
    ]
    for label, color, opacity in band_labels:
        cy = y_pos(label)
        background_zones.append(
            f'<rect x="{chart_x}" y="{cy - 38:.1f}" width="{chart_w}" height="76" '
            f'fill="{color}" opacity="{opacity}" rx="12"/>'
        )

    x_labels = []
    for label in x_axis:
        x = x_pos(label)
        x_labels.append(
            f'<text x="{x:.1f}" y="{chart_y - 36}" text-anchor="middle" font-size="15" font-weight="900" fill="#f9fafb">{h(label)}</text>'
        )
        x_labels.append(
            f'<line x1="{x:.1f}" y1="{chart_y - 8}" x2="{x:.1f}" y2="{chart_y + chart_h + 8}" '
            f'stroke="#94a3b8" stroke-width="0.8" opacity="0.22" stroke-dasharray="4 6"/>'
        )

    y_labels = []
    for label in y_axis:
        y = y_pos(label)
        y_labels.append(
            f'<text x="{chart_x - 25}" y="{y + 5:.1f}" text-anchor="end" font-size="14" font-weight="900" fill="#f9fafb">{h(label)}</text>'
        )
        y_labels.append(
            f'<line x1="{chart_x - 6}" y1="{y:.1f}" x2="{chart_x + chart_w + 6}" y2="{y:.1f}" '
            f'stroke="#94a3b8" stroke-width="0.8" opacity="0.20" stroke-dasharray="4 6"/>'
        )

    profile_parts = []
    profile_rows = 44
    for row in range(profile_rows):
        py = chart_y + row * (chart_h / profile_rows) + (chart_h / profile_rows) / 2
        samples = [
            field_value(chart_x + col * (chart_w / 28), py, row, col)
            for col in range(29)
        ]
        max_value = max(samples)
        if max_value < 11:
            continue

        bar_w = 10 + max_value * 1.15
        bar_h = max(3.0, chart_h / profile_rows * 0.70)
        color = density_color(round(max_value))
        opacity = min(0.88, 0.12 + max_value / 110)
        profile_parts.append(
            f'<rect x="{chart_x + chart_w + 18}" y="{py - bar_h/2:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'rx="1.5" fill="{color}" opacity="{opacity:.3f}"/>'
        )

    dominant_cx = x_pos(density_map.dominant_zone.x)
    dominant_cy = y_pos(density_map.dominant_zone.y)
    blocked_cx = x_pos(density_map.blocked_zone.x)
    blocked_cy = y_pos(density_map.blocked_zone.y)

    markers = [
        f'<circle cx="{dominant_cx:.1f}" cy="{dominant_cy:.1f}" r="18" fill="#ffffff" opacity="0.20" filter="url(#softGlow)"/>',
        f'<circle cx="{dominant_cx:.1f}" cy="{dominant_cy:.1f}" r="13" fill="none" stroke="#ffffff" stroke-width="3"/>',
        f'<text x="{dominant_cx:.1f}" y="{dominant_cy - 26:.1f}" text-anchor="middle" font-size="11" font-weight="900" fill="#ffffff">DOMINANTE</text>',
        f'<circle cx="{blocked_cx:.1f}" cy="{blocked_cy:.1f}" r="16" fill="#fbbf24" opacity="0.20" filter="url(#softGlow)"/>',
        f'<circle cx="{blocked_cx:.1f}" cy="{blocked_cy:.1f}" r="12" fill="none" stroke="#fbbf24" stroke-width="3"/>',
        f'<text x="{blocked_cx:.1f}" y="{blocked_cy + 32:.1f}" text-anchor="middle" font-size="11" font-weight="900" fill="#fbbf24">BLOQUEO</text>',
    ]

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Customer intent density map">
    <defs>
      <filter id="heavyBlur" x="-45%" y="-220%" width="190%" height="540%">
        <feGaussianBlur stdDeviation="20"/>
      </filter>
      <filter id="softGlow" x="-40%" y="-160%" width="180%" height="420%">
        <feGaussianBlur stdDeviation="5"/>
      </filter>
      <radialGradient id="chartGlow" cx="50%" cy="45%" r="70%">
        <stop offset="0%" stop-color="#1e293b"/>
        <stop offset="100%" stop-color="#0f172a"/>
      </radialGradient>
    </defs>

    <rect width="{width}" height="{height}" rx="28" fill="#0b1220"/>
    <rect x="28" y="24" width="{width - 56}" height="{height - 48}" rx="26" fill="url(#chartGlow)" stroke="#1f2937" stroke-width="1"/>

    <text x="{width/2}" y="58" text-anchor="middle" font-size="28" font-weight="900" fill="#f9fafb">Customer Intent Density Map</text>

    <rect x="{chart_x - 12}" y="{chart_y - 12}" width="{chart_w + 24}" height="{chart_h + 24}" rx="16" fill="#020617" opacity="0.52" stroke="#334155" stroke-width="1"/>

    {''.join(background_zones)}
    {''.join(x_labels)}
    {''.join(y_labels)}
    {''.join(clouds)}
    {''.join(raster_parts)}
    {''.join(shelves)}
    {''.join(profile_parts)}
    {''.join(markers)}
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

    blueprint_current_items = ''.join([
        f'<li><strong>A{index + 1}</strong> · {h(item)}</li>'
        for index, item in enumerate(result.funnel_blueprint.current_flow)
    ])

    blueprint_break_items = ''.join([
        f'<li><strong>R{index + 1}</strong> · {h(item)}</li>'
        for index, item in enumerate(result.funnel_blueprint.breakpoints)
    ])

    blueprint_rebuild_items = ''.join([
        f'<li><strong>S{index + 1}</strong> · {h(item)}</li>'
        for index, item in enumerate(result.funnel_blueprint.recommended_flow)
    ])

    blueprint_missing_items = ''.join([
        f'<li>{h(item)}</li>'
        for item in result.funnel_blueprint.missing_links
    ])

    density_connection_items = ''.join([
        f'<li><strong>Eje horizontal:</strong> ordena el avance comercial de {h(" → ".join(result.customer_intent_density_map.x_axis))}. Sirve para explicar en qué parte del recorrido se acumula o se pierde intención.</li>',
        f'<li><strong>Eje vertical:</strong> ordena la temperatura de {h(" → ".join(result.customer_intent_density_map.y_axis))}. Frío implica atención débil; templado implica interés con posibilidad de avance; caliente implica predisposición más cercana a acción.</li>',
        f'<li><strong>Color e intensidad:</strong> el azul indica baja temperatura, el verde/amarillo indica transición y el naranja/rojo indica mayor calor comercial inferido. Más densidad visual significa mayor concentración diagnóstica.</li>',
        f'<li><strong>Zona dominante:</strong> {h(result.customer_intent_density_map.dominant_zone.x)} / {h(result.customer_intent_density_map.dominant_zone.y)} muestra dónde está el grueso del público según las señales disponibles.</li>',
        f'<li><strong>Zona bloqueada:</strong> {h(result.customer_intent_density_map.blocked_zone.x)} / {h(result.customer_intent_density_map.blocked_zone.y)} muestra dónde el público deja de avanzar. Esa zona se conecta con el FAULT del blueprint.</li>',
        f'<li><strong>Relación con el blueprint:</strong> el heatmap muestra dónde se concentra y bloquea la intención; el blueprint muestra qué parte del sistema comercial habría que rediseñar para mover esa intención hacia conversión.</li>',
        f'<li><strong>Límite metodológico:</strong> este mapa es diagnóstico e inferido; no reemplaza datos reales de GA4, CRM, campañas, Hotjar/Clarity o formularios.</li>',
    ])

    density_script = (
        f"Este mapa no muestra solo colores: muestra movimiento comercial. "
        f"El público se concentra en {h(result.customer_intent_density_map.dominant_zone.x)} / {h(result.customer_intent_density_map.dominant_zone.y)}, "
        f"pero el avance se frena en {h(result.customer_intent_density_map.blocked_zone.x)} / {h(result.customer_intent_density_map.blocked_zone.y)}. "
        f"La lectura es que existe intención o atención, pero el sistema necesita mejorar la conexión entre interés, confianza y acción."
    )

    blueprint_connection_items = ''.join([
        '<li><strong>Nodos hexagonales:</strong> cada hexágono representa un punto funcional del sistema comercial. A1–A5 son la ruta actual; S1–S5 son la ruta recomendada; SL-01–SL-05 son nodos de soporte.</li>',
        '<li><strong>Ruta azul A1–A5:</strong> muestra lo que hoy existe: presencia pública, contenido, interés, comparación y consulta débil. Es el recorrido actual antes del rediseño.</li>',
        '<li><strong>FAULT:</strong> marca la ruptura principal. Ahí el usuario deja de avanzar porque la propuesta de valor, la confianza, el CTA o la diferenciación no son suficientemente claros.</li>',
        '<li><strong>DG / Diagnosis Gate:</strong> explica la transición entre problema y solución. La ruta verde no nace mágicamente del fallo; nace del diagnóstico que convierte la ruptura en rediseño.</li>',
        '<li><strong>Ruta verde S1–S5:</strong> muestra el recorrido reconstruido: mensaje diferencial, contenido de valor, prueba social, CTA claro y seguimiento comercial.</li>',
        '<li><strong>Support Layer SL:</strong> representa la infraestructura que alimenta la ruta recomendada. No es una etapa extra del funnel; son activos que hacen posible que S1–S5 funcionen: mensajes, prueba, objeciones, CTA y follow-up.</li>',
        '<li><strong>Conexiones moradas:</strong> muestran cómo los nodos SL alimentan la ruta verde. Sirven para explicar que la conversión no depende solo de publicar más, sino de sostener el recorrido con evidencia, claridad y seguimiento.</li>',
        '<li><strong>OUT:</strong> representa la salida buscada: oportunidad comercial más calificada, más defendible y con menor fricción.</li>',
    ])

    blueprint_script = (
        "Este blueprint se lee de izquierda a derecha. Primero está la ruta azul: lo que la empresa ya hace. "
        "Luego aparece FAULT: el punto donde el avance se rompe. DG es la compuerta de diagnóstico: convierte la ruptura en criterio de rediseño. "
        "La ruta verde muestra cómo debería moverse el cliente después del rediseño. Abajo, el Support Layer alimenta esa ruta verde con mensajes, prueba, manejo de objeciones, CTA y seguimiento."
    )

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
    .visual-note-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      margin-top: 14px;
    }}
    .visual-note {{
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 16px;
      padding: 14px 16px;
      color: #111827;
      line-height: 1.45;
      box-shadow: 0 8px 18px rgba(17, 24, 39, 0.06);
    }}
    .visual-note h3 {{
      margin: 0 0 8px;
      font-size: 15px;
      letter-spacing: -0.02em;
    }}
    .legend-bar {{
      height: 12px;
      border-radius: 999px;
      background: linear-gradient(90deg, #2563eb 0%, #0ea5e9 35%, #84cc16 55%, #f59e0b 75%, #ef4444 100%);
      margin: 8px 0 6px;
    }}
    .legend-labels {{
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: #4b5563;
      font-weight: 700;
      gap: 10px;
    }}
    .blueprint-code-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 14px;
    }}
    .blueprint-code-card {{
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 16px;
      padding: 14px 16px;
      color: #111827;
      box-shadow: 0 8px 18px rgba(17, 24, 39, 0.06);
    }}
    .blueprint-code-card h3 {{
      margin: 0 0 10px;
      font-size: 15px;
      letter-spacing: -0.02em;
    }}
    .blueprint-code-card ul {{
      margin: 0;
      padding-left: 18px;
    }}
    .blueprint-code-card li {{
      margin: 6px 0;
      line-height: 1.35;
    }}
    .explanation-card {{
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 16px;
      padding: 16px 18px;
      color: #111827;
      line-height: 1.5;
      box-shadow: 0 8px 18px rgba(17, 24, 39, 0.06);
      margin-top: 14px;
    }}
    .explanation-card h3 {{
      margin: 0 0 10px;
      font-size: 16px;
      letter-spacing: -0.02em;
    }}
    .explanation-card ul {{
      margin: 0;
      padding-left: 18px;
    }}
    .explanation-card li {{
      margin: 7px 0;
    }}
    .script-box {{
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 12px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      color: #334155;
    }}
    .script-box p {{
      margin: 6px 0;
    }}
    @media print {{
      body {{ background: white; }}
      .card, .hero {{ box-shadow: none; break-inside: avoid; }}
    }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .visual-note-grid {{ grid-template-columns: 1fr; }}
      .blueprint-code-grid {{ grid-template-columns: 1fr; }}
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
      <div class="card full">
        {density_svg}
        <div class="visual-note-grid">
          <div class="visual-note">
            <h3>Lectura de temperatura</h3>
            <div class="legend-bar"></div>
            <div class="legend-labels">
              <span>Azul = frío</span>
              <span>Verde/amarillo = templado</span>
              <span>Rojo = caliente</span>
            </div>
          </div>
          <div class="visual-note">
            <h3>Interpretación del mapa</h3>
            <p>{h(result.customer_intent_density_map.interpretation)}</p>
            <p><strong>Zona dominante:</strong> {h(result.customer_intent_density_map.dominant_zone.x)} / {h(result.customer_intent_density_map.dominant_zone.y)}</p>
            <p><strong>Zona bloqueada:</strong> {h(result.customer_intent_density_map.blocked_zone.x)} / {h(result.customer_intent_density_map.blocked_zone.y)}</p>
          </div>
        </div>
        <div class="explanation-card">
          <h3>Cómo explicar las conexiones del heatmap</h3>
          <ul>{density_connection_items}</ul>
          <div class="script-box">
            <p><strong>Guion de lectura:</strong> {density_script}</p>
          </div>
        </div>
      </div>
      <div class="card full">{temperature_svg}</div>
      <div class="card full">
        {blueprint_svg}
        <div class="blueprint-code-grid">
          <div class="blueprint-code-card">
            <h3>Current path · A-codes</h3>
            <ul>{blueprint_current_items or '<li>No current-flow items detected.</li>'}</ul>
          </div>
          <div class="blueprint-code-card">
            <h3>Rupture zone · R-codes</h3>
            <ul>{blueprint_break_items or '<li>No rupture points detected.</li>'}</ul>
          </div>
          <div class="blueprint-code-card">
            <h3>Rebuild route · S-codes</h3>
            <ul>{blueprint_rebuild_items or '<li>No rebuild items detected.</li>'}</ul>
          </div>
          <div class="blueprint-code-card">
            <h3>Missing links / support layer</h3>
            <ul>{blueprint_missing_items or '<li>No missing links detected.</li>'}</ul>
            <p><strong>Lectura:</strong> {h(result.funnel_blueprint.summary)}</p>
          </div>
        </div>
        <div class="explanation-card">
          <h3>Cómo explicar el blueprint completo</h3>
          <ul>{blueprint_connection_items}</ul>
          <div class="script-box">
            <p><strong>Guion de lectura:</strong> {blueprint_script}</p>
          </div>
        </div>
      </div>

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


def safe_number(value: Optional[float], default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def calc_ctr_percent(campaign: CampaignMetric) -> Optional[float]:
    if campaign.ctr_percent is not None:
        return campaign.ctr_percent
    if campaign.impressions and campaign.clicks is not None and campaign.impressions > 0:
        return (campaign.clicks / campaign.impressions) * 100
    return None


def calc_cpl(campaign: CampaignMetric) -> Optional[float]:
    if campaign.cpl is not None:
        return campaign.cpl
    leads = campaign.leads or campaign.form_submits or campaign.whatsapp_clicks
    if campaign.spend is not None and leads and leads > 0:
        return campaign.spend / leads
    return None


def calc_cpa(campaign: CampaignMetric) -> Optional[float]:
    if campaign.cpa is not None:
        return campaign.cpa
    conversions = campaign.conversions or campaign.sales
    if campaign.spend is not None and conversions and conversions > 0:
        return campaign.spend / conversions
    return None


def calc_landing_conversion_rate(campaign: CampaignMetric) -> Optional[float]:
    conversions = campaign.leads or campaign.form_submits or campaign.whatsapp_clicks or campaign.calls
    visits = campaign.landing_visits or campaign.clicks
    if visits and visits > 0 and conversions is not None:
        return (conversions / visits) * 100
    return None


def calc_lead_quality_rate(campaign: CampaignMetric) -> Optional[float]:
    if campaign.lead_quality_score is not None:
        return campaign.lead_quality_score
    if campaign.leads and campaign.leads > 0 and campaign.qualified_leads is not None:
        return (campaign.qualified_leads / campaign.leads) * 100
    if campaign.leads and campaign.leads > 0 and campaign.bad_leads is not None:
        return max(0.0, 100.0 - ((campaign.bad_leads / campaign.leads) * 100))
    return None


def campaign_label(campaign: CampaignMetric) -> str:
    parts = [campaign.channel, campaign.campaign_name, campaign.adset_name, campaign.ad_name]
    return " / ".join([part for part in parts if part])


def has_meaningful_campaign_data(campaigns: List[CampaignMetric]) -> bool:
    metric_fields = [
        "spend", "impressions", "clicks", "ctr_percent", "landing_visits", "leads",
        "qualified_leads", "bad_leads", "conversions", "sales", "revenue", "cpl", "cpa",
    ]
    for campaign in campaigns:
        for field in metric_fields:
            if getattr(campaign, field) is not None:
                return True
    return False


def infer_campaign_data_quality(request: CampaignPerformanceRequest) -> str:
    if not request.campaigns:
        return "sin_datos"
    if not has_meaningful_campaign_data(request.campaigns):
        return "baja"

    metric_count = 0
    for campaign in request.campaigns:
        for field in ["spend", "impressions", "clicks", "leads", "qualified_leads", "conversions", "revenue"]:
            if getattr(campaign, field) is not None:
                metric_count += 1

    if metric_count >= len(request.campaigns) * 5:
        return "alta"
    if metric_count >= len(request.campaigns) * 3:
        return "media"
    return "baja"


def make_action(
    category: str,
    action: str,
    trigger: str,
    evidence: str,
    priority: str,
    effort: str,
    expected_impact: str,
    verification_metric: str,
    related_campaign: Optional[str] = None,
    funnel_stage: Optional[str] = None,
    confidence: str = "media",
    data_required: bool = False,
) -> PerformanceAction:
    return PerformanceAction(
        category=category,
        action=action,
        trigger=trigger,
        evidence=evidence,
        priority=priority,
        effort=effort,
        expected_impact=expected_impact,
        verification_metric=verification_metric,
        related_campaign=related_campaign,
        funnel_stage=funnel_stage,
        confidence=confidence,
        data_required=data_required,
    )


def build_default_strategic_actions(company_name: str, has_data: bool = False) -> List[PerformanceAction]:
    confidence = "media" if has_data else "inferida"
    return [
        make_action(
            category="propuesta_de_valor",
            action="Corregir propuesta de valor",
            trigger="La auditoría necesita una razón de elección más explícita.",
            evidence="Señal estratégica: si la marca comunica oferta o disponibilidad sin diferencia, compite por precio, cercanía o conveniencia.",
            priority="alta",
            effort="medio",
            expected_impact="Mayor claridad de posicionamiento y mejor calidad de intención.",
            verification_metric="Aumento de consultas calificadas, mejor ratio visita→consulta y reducción de objeciones repetidas.",
            confidence=confidence,
            data_required=False,
        ),
        make_action(
            category="cta",
            action="Reformular CTA",
            trigger="El recorrido necesita un próximo paso más claro.",
            evidence="Un CTA genérico o débil reduce avance entre interés, consideración y contacto.",
            priority="alta",
            effort="bajo",
            expected_impact="Más usuarios avanzando hacia consulta, diagnóstico, WhatsApp o formulario.",
            verification_metric="CTR a contacto, clicks en WhatsApp, formularios enviados, llamadas o eventos clave.",
            confidence=confidence,
            data_required=False,
        ),
        make_action(
            category="prueba_social",
            action="Agregar prueba social",
            trigger="La decisión requiere evidencia de confianza.",
            evidence="Sin testimonios, casos, reseñas o pruebas visibles, el usuario compara más y avanza menos.",
            priority="alta",
            effort="medio",
            expected_impact="Mayor confianza percibida y menor fricción en etapa de consideración.",
            verification_metric="Conversión en landing, avance a consulta y reducción de abandono antes del contacto.",
            confidence=confidence,
            data_required=False,
        ),
        make_action(
            category="objeciones",
            action="Crear contenido de objeciones",
            trigger="El usuario necesita resolver dudas antes de consultar.",
            evidence="Las objeciones no resueltas suelen frenar consideración y conversión aunque haya interés.",
            priority="media-alta",
            effort="medio",
            expected_impact="Más avance desde interés hacia consideración y consulta calificada.",
            verification_metric="Engagement en piezas de objeciones, tiempo en página, clicks a CTA y preguntas repetidas en ventas.",
            confidence=confidence,
            data_required=False,
        ),
        make_action(
            category="funnel",
            action="Separar contenido de awareness y conversión",
            trigger="No todo contenido debe cumplir el mismo objetivo.",
            evidence="Mezclar contenido de descubrimiento con contenido de conversión debilita lectura del funnel y medición.",
            priority="media-alta",
            effort="medio",
            expected_impact="Mejor organización del mensaje por temperatura y etapa de decisión.",
            verification_metric="Performance por etapa: alcance/engagement para awareness, leads/consultas para conversión.",
            confidence=confidence,
            data_required=False,
        ),
        make_action(
            category="posicionamiento",
            action="Definir mensaje diferencial",
            trigger="La marca necesita una diferencia defendible.",
            evidence="Si el mercado no entiende por qué elegir la marca, la comparación baja a precio, ubicación o disponibilidad.",
            priority="alta",
            effort="medio",
            expected_impact="Mayor preferencia y menor dependencia de argumentos tácticos.",
            verification_metric="Mejor tasa de consulta calificada, feedback comercial y menor presión por descuento/precio.",
            confidence=confidence,
            data_required=False,
        ),
        make_action(
            category="seguimiento",
            action="Crear seguimiento comercial",
            trigger="La conversión no termina en el primer contacto.",
            evidence="Sin seguimiento, leads tibios se pierden aunque hayan mostrado intención.",
            priority="media-alta",
            effort="medio",
            expected_impact="Recuperación de oportunidades que no convierten en el primer contacto.",
            verification_metric="Tasa de respuesta post-consulta, recontactos, citas agendadas y oportunidades recuperadas.",
            confidence=confidence,
            data_required=False,
        ),
    ]


def build_campaign_findings_and_actions(request: CampaignPerformanceRequest) -> tuple[List[PerformanceFinding], List[PerformanceAction], List[PerformanceAction], List[PerformanceAction]]:
    findings: List[PerformanceFinding] = []
    performance_actions: List[PerformanceAction] = []
    budget_actions: List[PerformanceAction] = []
    tracking_actions: List[PerformanceAction] = []

    for campaign in request.campaigns:
        label = campaign_label(campaign)
        ctr = calc_ctr_percent(campaign)
        cpl = calc_cpl(campaign)
        cpa = calc_cpa(campaign)
        landing_cr = calc_landing_conversion_rate(campaign)
        quality_rate = calc_lead_quality_rate(campaign)
        spend = safe_number(campaign.spend)
        clicks = campaign.clicks or 0
        leads = campaign.leads or campaign.form_submits or campaign.whatsapp_clicks or campaign.calls or 0
        conversions = campaign.conversions or campaign.sales or 0
        stage = campaign.funnel_stage or campaign.temperature

        evidence_parts = []
        if campaign.spend is not None:
            evidence_parts.append(f"gasto={campaign.spend:g} {request.currency}")
        if ctr is not None:
            evidence_parts.append(f"CTR={ctr:.2f}%")
        if cpl is not None:
            evidence_parts.append(f"CPL={cpl:.2f} {request.currency}")
        if cpa is not None:
            evidence_parts.append(f"CPA={cpa:.2f} {request.currency}")
        if landing_cr is not None:
            evidence_parts.append(f"landing→lead={landing_cr:.2f}%")
        if quality_rate is not None:
            evidence_parts.append(f"calidad lead={quality_rate:.1f}%")
        evidence = ", ".join(evidence_parts) or "datos parciales disponibles"

        low_ctr = ctr is not None and ctr < request.target_ctr_percent
        high_cpl = (
            cpl is not None
            and request.target_cpl is not None
            and cpl > request.target_cpl * 1.25
        )
        good_cpl = (
            cpl is not None
            and request.target_cpl is not None
            and cpl <= request.target_cpl * 0.75
        )
        low_quality = quality_rate is not None and quality_rate < request.min_lead_quality_rate_percent
        good_quality = quality_rate is None or quality_rate >= request.min_lead_quality_rate_percent
        low_landing_cr = landing_cr is not None and landing_cr < request.target_landing_conversion_rate_percent
        meaningful_spend = spend > 0 and (
            request.target_cpl is None
            or spend >= request.target_cpl * 2
        )

        if high_cpl and low_quality:
            findings.append(PerformanceFinding(
                title="CPL alto con baja calidad de lead",
                evidence=evidence,
                interpretation="El gasto está comprando oportunidades caras y comercialmente débiles.",
                severity="alta",
                affected_campaigns=[label],
            ))
            budget_actions.append(make_action(
                category="presupuesto",
                action="Pausar campañas con CPL alto y baja calidad",
                trigger="CPL por encima del objetivo y calidad por debajo del mínimo.",
                evidence=evidence,
                priority="alta",
                effort="bajo",
                expected_impact="Reducir desperdicio de presupuesto y evitar alimentar ventas con leads débiles.",
                verification_metric="CPL, tasa de lead calificado y costo por oportunidad calificada.",
                related_campaign=label,
                funnel_stage=stage,
                confidence="alta",
            ))

        if good_cpl and leads > 0 and good_quality:
            budget_actions.append(make_action(
                category="presupuesto",
                action="Duplicar presupuesto en campañas con CPL bajo y buena conversión",
                trigger="CPL por debajo del objetivo y calidad/conversión aceptable.",
                evidence=evidence,
                priority="media-alta",
                effort="bajo",
                expected_impact="Escalar inversión en campañas que ya muestran eficiencia.",
                verification_metric="CPL, lead calificado, CPA y saturación/frecuencia después del aumento.",
                related_campaign=label,
                funnel_stage=stage,
                confidence="media-alta",
            ))

        if low_ctr and (campaign.impressions or 0) >= 1000:
            findings.append(PerformanceFinding(
                title="CTR bajo",
                evidence=evidence,
                interpretation="La creatividad, el hook o la promesa inicial no están generando suficiente respuesta.",
                severity="media-alta",
                affected_campaigns=[label],
            ))
            performance_actions.append(make_action(
                category="creativo",
                action="Testear nuevos hooks en anuncios con CTR bajo",
                trigger="CTR inferior al umbral definido.",
                evidence=evidence,
                priority="media-alta",
                effort="medio",
                expected_impact="Mejorar atención inicial y reducir costo de tráfico útil.",
                verification_metric="CTR, CPC, thumbstop/hook rate si existe y visitas calificadas.",
                related_campaign=label,
                funnel_stage=stage,
                confidence="alta",
            ))

        if low_landing_cr and clicks >= 50:
            findings.append(PerformanceFinding(
                title="Tráfico con baja conversión de landing",
                evidence=evidence,
                interpretation="El anuncio consigue tráfico, pero la landing o el siguiente paso no sostienen la intención.",
                severity="alta",
                affected_campaigns=[label],
            ))
            performance_actions.append(make_action(
                category="landing",
                action="Rehacer landing si hay tráfico pero baja conversión",
                trigger="Clicks o visitas suficientes con baja conversión a lead/contacto.",
                evidence=evidence,
                priority="alta",
                effort="alto",
                expected_impact="Convertir mejor el tráfico existente sin depender solo de más inversión.",
                verification_metric="Tasa landing→lead, eventos de contacto, scroll/clicks si hay medición y CPL efectivo.",
                related_campaign=label,
                funnel_stage=stage,
                confidence="alta",
            ))

        if meaningful_spend and clicks > 50 and leads == 0 and conversions == 0:
            performance_actions.append(make_action(
                category="audiencia",
                action="Cambiar audiencia si hay alto gasto y baja intención",
                trigger="Gasto y clicks sin leads/conversiones.",
                evidence=evidence,
                priority="alta",
                effort="medio",
                expected_impact="Reducir tráfico irrelevante y acercar la campaña a usuarios con intención real.",
                verification_metric="Lead rate, CPL, calidad de lead y tasa de conversación comercial.",
                related_campaign=label,
                funnel_stage=stage,
                confidence="media-alta",
            ))

        if (campaign.landing_visits or clicks) >= 100 and leads > 0 and conversions == 0:
            performance_actions.append(make_action(
                category="retargeting",
                action="Crear retargeting para usuarios con interés sin conversión",
                trigger="Hay visitas/clicks/leads iniciales, pero no conversión final.",
                evidence=evidence,
                priority="media-alta",
                effort="medio",
                expected_impact="Recuperar usuarios tibios que ya mostraron interés.",
                verification_metric="Conversión asistida, CPL retargeting, CPA y tasa de retorno a contacto.",
                related_campaign=label,
                funnel_stage=stage,
                confidence="media",
            ))

        # Tracking issue: clicks exist, but no downstream metrics are provided or all are zero.
        downstream_values = [
            campaign.landing_visits, campaign.form_starts, campaign.form_submits,
            campaign.whatsapp_clicks, campaign.calls, campaign.key_events,
            campaign.leads, campaign.conversions, campaign.sales,
        ]
        downstream_known = any(value is not None for value in downstream_values)
        downstream_sum = sum([int(value or 0) for value in downstream_values])
        if clicks >= 50 and (not downstream_known or downstream_sum == 0):
            tracking_actions.append(make_action(
                category="tracking",
                action="Corregir tracking si hay clicks pero no eventos",
                trigger="Clicks relevantes sin eventos posteriores medidos.",
                evidence=evidence,
                priority="alta",
                effort="medio",
                expected_impact="Evitar decisiones a ciegas y separar problema de campaña vs problema de medición.",
                verification_metric="Eventos GA4/Pixel/CAPI, WhatsApp clicks, formularios, llamadas y conversiones importadas.",
                related_campaign=label,
                funnel_stage=stage,
                confidence="media-alta",
            ))

    return findings, performance_actions, budget_actions, tracking_actions


def build_temperature_separation_action(request: CampaignPerformanceRequest) -> Optional[PerformanceAction]:
    if not request.campaigns:
        return make_action(
            category="funnel",
            action="Separar campañas por temperatura",
            trigger="Todavía no hay campañas cargadas para clasificar por etapa.",
            evidence="Acción preparada para cuando existan campañas: separar awareness, consideración, conversión y retargeting.",
            priority="media",
            effort="medio",
            expected_impact="Mejor lectura del funnel y mensajes más coherentes por intención.",
            verification_metric="Performance por etapa: alcance/CTR para frío, lead rate/CPL para templado-caliente, CPA para conversión.",
            confidence="inferida",
            data_required=True,
        )

    stages = set()
    for campaign in request.campaigns:
        if campaign.funnel_stage:
            stages.add(campaign.funnel_stage.casefold())
        if campaign.temperature:
            stages.add(campaign.temperature.casefold())

    mixed_or_missing = len(stages) <= 1 or any(not (campaign.funnel_stage or campaign.temperature) for campaign in request.campaigns)

    if mixed_or_missing:
        return make_action(
            category="funnel",
            action="Separar campañas por temperatura",
            trigger="Las campañas no están claramente clasificadas por etapa/temperatura.",
            evidence="Falta segmentar objetivos y mensajes entre frío, tibio, templado, caliente y retargeting.",
            priority="media-alta",
            effort="medio",
            expected_impact="Mejor asignación de presupuesto y lectura más clara del rendimiento por intención.",
            verification_metric="Reportes separados por etapa: CPM/CTR en awareness, CPL en consideración, CPA/ventas en conversión.",
            confidence="media",
            data_required=False,
        )
    return None


def prioritize_actions(actions: List[PerformanceAction], limit: int = 12) -> List[PerformanceAction]:
    priority_rank = {
        "crítica": 0,
        "critica": 0,
        "alta": 1,
        "media-alta": 2,
        "media": 3,
        "baja": 4,
    }
    return sorted(
        actions,
        key=lambda item: (
            priority_rank.get(item.priority.casefold(), 9),
            1 if item.data_required else 0,
            item.category,
        ),
    )[:limit]


def build_next_data_needed(request: CampaignPerformanceRequest) -> List[str]:
    needed = []

    if not request.campaigns:
        return [
            "Export de campañas con gasto, impresiones, clicks, CTR, CPC, CPM, leads y conversiones.",
            "Datos de calidad de lead: calificados, no calificados, ventas o etapa CRM.",
            "Eventos de landing: visitas, formularios, WhatsApp clicks, llamadas y conversiones.",
            "Objetivos por campaña: awareness, consideración, conversión o retargeting.",
            "Benchmarks internos: CPL objetivo, CPA objetivo y tasa mínima de lead calificado.",
        ]

    if request.target_cpl is None:
        needed.append("CPL objetivo para decidir qué campañas pausar, escalar o revisar.")
    if request.target_cpa is None:
        needed.append("CPA objetivo o costo aceptable por oportunidad/venta.")
    if not any(campaign.qualified_leads is not None or campaign.bad_leads is not None or campaign.lead_quality_score is not None for campaign in request.campaigns):
        needed.append("Calidad de lead por campaña: calificados, malos leads o score comercial.")
    if not any(campaign.landing_visits is not None or campaign.form_submits is not None or campaign.whatsapp_clicks is not None for campaign in request.campaigns):
        needed.append("Eventos de landing/contacto: visitas, formularios, WhatsApp clicks o llamadas.")
    if not any(campaign.conversions is not None or campaign.sales is not None or campaign.revenue is not None for campaign in request.campaigns):
        needed.append("Conversiones finales, ventas o revenue para conectar marketing con negocio.")
    if not needed:
        needed.append("Datos históricos por semana/mes para detectar fatiga, tendencias y estacionalidad.")
    return needed



def calc_cpc_value(campaign: CampaignMetric) -> Optional[float]:
    if campaign.cpc is not None:
        return campaign.cpc
    if campaign.spend is not None and campaign.clicks and campaign.clicks > 0:
        return campaign.spend / campaign.clicks
    return None


def calc_cpm_value(campaign: CampaignMetric) -> Optional[float]:
    if campaign.cpm is not None:
        return campaign.cpm
    if campaign.spend is not None and campaign.impressions and campaign.impressions > 0:
        return (campaign.spend / campaign.impressions) * 1000
    return None


def calc_cvr_percent(campaign: CampaignMetric) -> Optional[float]:
    leads = campaign.leads or campaign.form_submits or campaign.whatsapp_clicks or campaign.calls or campaign.conversions
    if campaign.clicks and campaign.clicks > 0 and leads is not None:
        return (leads / campaign.clicks) * 100
    return None


def median_or_none(values: List[Optional[float]]) -> Optional[float]:
    clean = sorted([float(value) for value in values if value is not None])
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / 2


def pct_delta(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None or previous == 0:
        return None
    return ((current - previous) / abs(previous)) * 100


def quality_score_from_campaign(campaign: CampaignMetric) -> Optional[float]:
    if campaign.lead_quality_score is not None:
        return max(0, min(float(campaign.lead_quality_score), 100))
    rate = calc_lead_quality_rate(campaign)
    if rate is not None:
        return max(0, min(float(rate), 100))
    notes = (campaign.notes or "").casefold()
    if "alta" in notes or "calidad alta" in notes:
        return 80
    if "media-alta" in notes:
        return 70
    if "media" in notes:
        return 55
    if "baja" in notes or "poco calificado" in notes:
        return 25
    return None


def quality_level(score: Optional[float]) -> str:
    if score is None:
        return "desconocida"
    if score >= 75:
        return "alta"
    if score >= 55:
        return "media"
    if score >= 35:
        return "baja-media"
    return "baja"


def sample_status(campaign: CampaignMetric) -> str:
    clicks = campaign.clicks or 0
    leads = campaign.leads or campaign.form_submits or campaign.whatsapp_clicks or campaign.calls or 0
    if clicks < 100 and leads < 5:
        return "muestra_insuficiente"
    if clicks < 300 or leads < 10:
        return "muestra_media"
    return "muestra_suficiente"


def tracking_reliability(campaign: CampaignMetric) -> str:
    clicks = campaign.clicks or 0
    leads = campaign.leads or campaign.form_submits or campaign.whatsapp_clicks or campaign.calls or 0
    events = campaign.key_events or campaign.conversions or campaign.sales or 0
    if campaign.events_configured is False or (clicks >= 100 and leads == 0 and events == 0):
        return "crítica"
    if campaign.utms_present is False or (clicks >= 100 and events == 0 and leads > 0):
        return "media-baja"
    if campaign.events_configured is True or events > 0 or leads > 0:
        return "aceptable"
    return "desconocida"


def derive_campaign_metrics(request: CampaignPerformanceRequest) -> List[DerivedCampaignMetrics]:
    derived = []
    for campaign in request.campaigns:
        derived.append(DerivedCampaignMetrics(
            campaign_name=campaign_label(campaign),
            channel=campaign.channel,
            spend=campaign.spend,
            impressions=campaign.impressions,
            clicks=campaign.clicks,
            leads=campaign.leads or campaign.form_submits or campaign.whatsapp_clicks or campaign.calls,
            conversions=campaign.conversions or campaign.sales,
            ctr_percent=calc_ctr_percent(campaign),
            cpc=calc_cpc_value(campaign),
            cpm=calc_cpm_value(campaign),
            cpl=calc_cpl(campaign),
            cpa=calc_cpa(campaign),
            cvr_percent=calc_cvr_percent(campaign),
            lead_quality_rate_percent=quality_score_from_campaign(campaign),
            frequency=campaign.frequency,
            sample_status=sample_status(campaign),
            tracking_reliability=tracking_reliability(campaign),
        ))
    return derived


def build_internal_benchmarks(derived: List[DerivedCampaignMetrics]) -> Dict[str, Optional[float]]:
    return {
        "median_ctr_percent": median_or_none([item.ctr_percent for item in derived]),
        "median_cpc": median_or_none([item.cpc for item in derived]),
        "median_cpm": median_or_none([item.cpm for item in derived]),
        "median_cpl": median_or_none([item.cpl for item in derived]),
        "median_cpa": median_or_none([item.cpa for item in derived]),
        "median_cvr_percent": median_or_none([item.cvr_percent for item in derived]),
        "median_lead_quality_score": median_or_none([item.lead_quality_rate_percent for item in derived]),
    }


def build_metric_deltas(request: CampaignPerformanceRequest) -> List[PerformanceMetricDelta]:
    deltas: List[PerformanceMetricDelta] = []
    for campaign in request.campaigns:
        current_ctr = calc_ctr_percent(campaign)
        current_cpc = calc_cpc_value(campaign)
        current_cpm = calc_cpm_value(campaign)
        current_cpl = calc_cpl(campaign)
        current_cpa = calc_cpa(campaign)
        current_quality = quality_score_from_campaign(campaign)

        previous_ctr = campaign.previous_ctr_percent
        if previous_ctr is None and campaign.previous_impressions and campaign.previous_clicks is not None and campaign.previous_impressions > 0:
            previous_ctr = (campaign.previous_clicks / campaign.previous_impressions) * 100
        previous_cpc = campaign.previous_cpc
        if previous_cpc is None and campaign.previous_spend is not None and campaign.previous_clicks and campaign.previous_clicks > 0:
            previous_cpc = campaign.previous_spend / campaign.previous_clicks
        previous_cpm = campaign.previous_cpm
        if previous_cpm is None and campaign.previous_spend is not None and campaign.previous_impressions and campaign.previous_impressions > 0:
            previous_cpm = (campaign.previous_spend / campaign.previous_impressions) * 1000
        previous_cpl = campaign.previous_cpl
        if previous_cpl is None and campaign.previous_spend is not None and campaign.previous_leads and campaign.previous_leads > 0:
            previous_cpl = campaign.previous_spend / campaign.previous_leads
        previous_cpa = campaign.previous_cpa
        if previous_cpa is None and campaign.previous_spend is not None and campaign.previous_conversions and campaign.previous_conversions > 0:
            previous_cpa = campaign.previous_spend / campaign.previous_conversions

        delta_ctr = pct_delta(current_ctr, previous_ctr)
        delta_cpc = pct_delta(current_cpc, previous_cpc)
        delta_cpl = pct_delta(current_cpl, previous_cpl)
        interpretation = "Sin período anterior suficiente para interpretar tendencia."
        if delta_ctr is not None and delta_cpc is not None and delta_cpl is not None:
            if delta_ctr < -15 and delta_cpc > 15 and delta_cpl > 20:
                interpretation = "La respuesta relativa empeoró: baja CTR, sube CPC y sube CPL. Posible fatiga creativa, audiencia deteriorada o pérdida de relevancia."
            elif delta_ctr > 10 and delta_cpl < -10:
                interpretation = "La campaña mejora eficiencia: sube CTR y baja CPL. Candidata a escalar con control si la calidad acompaña."
            elif delta_cpc < -15 and delta_cpl > 20:
                interpretation = "Clicks más baratos pero peor costo por lead. Posible caída de calidad o fricción posterior al click."

        if any(value is not None for value in [campaign.previous_spend, campaign.previous_impressions, campaign.previous_clicks, previous_ctr, previous_cpl, previous_cpa]):
            deltas.append(PerformanceMetricDelta(
                campaign_name=campaign_label(campaign),
                delta_spend_percent=pct_delta(campaign.spend, campaign.previous_spend),
                delta_impressions_percent=pct_delta(campaign.impressions, campaign.previous_impressions),
                delta_clicks_percent=pct_delta(campaign.clicks, campaign.previous_clicks),
                delta_ctr_percent=delta_ctr,
                delta_cpc_percent=delta_cpc,
                delta_cpm_percent=pct_delta(current_cpm, previous_cpm),
                delta_leads_percent=pct_delta(campaign.leads, campaign.previous_leads),
                delta_cpl_percent=delta_cpl,
                delta_cpa_percent=pct_delta(current_cpa, previous_cpa),
                delta_frequency_percent=pct_delta(campaign.frequency, campaign.previous_frequency),
                delta_lead_quality_percent=pct_delta(current_quality, campaign.previous_lead_quality_score),
                interpretation=interpretation,
            ))
    return deltas


def build_cross_metric_findings(request: CampaignPerformanceRequest, derived: List[DerivedCampaignMetrics], benchmarks: Dict[str, Optional[float]]) -> List[CrossMetricFinding]:
    findings: List[CrossMetricFinding] = []
    median_ctr = benchmarks.get("median_ctr_percent") or request.target_ctr_percent
    median_cpl = benchmarks.get("median_cpl")
    median_cpc = benchmarks.get("median_cpc")

    for campaign, metrics in zip(request.campaigns, derived):
        label = metrics.campaign_name
        evidence = []
        if metrics.ctr_percent is not None:
            evidence.append(f"CTR={metrics.ctr_percent:.2f}%")
        if metrics.cpc is not None:
            evidence.append(f"CPC={metrics.cpc:.2f} {request.currency}")
        if metrics.cpl is not None:
            evidence.append(f"CPL={metrics.cpl:.2f} {request.currency}")
        if metrics.cvr_percent is not None:
            evidence.append(f"CVR={metrics.cvr_percent:.2f}%")
        evidence_text = ", ".join(evidence) or "datos parciales"

        if metrics.ctr_percent is not None and metrics.ctr_percent < request.target_ctr_percent and metrics.impressions and metrics.impressions >= 1000:
            findings.append(CrossMetricFinding(
                pattern="CTR bajo con volumen de impresiones",
                evidence=evidence_text,
                interpretation="Hay exposición, pero el anuncio no está generando respuesta proporcional. Posible problema de hook, creatividad, audiencia o promesa.",
                affected_campaigns=[label],
                severity="media-alta",
                confidence="media" if metrics.sample_status != "muestra_insuficiente" else "baja",
                recommended_action="Testear nuevos hooks, reformular promesa inicial o separar audiencia por temperatura.",
            ))

        if metrics.ctr_percent is not None and metrics.ctr_percent >= max(median_ctr, request.target_ctr_percent) and metrics.cvr_percent is not None and metrics.cvr_percent < request.target_landing_conversion_rate_percent:
            findings.append(CrossMetricFinding(
                pattern="CTR alto con conversión baja",
                evidence=evidence_text,
                interpretation="El anuncio genera interés, pero la landing, oferta, CTA o formulario no sostienen la promesa posterior al click.",
                affected_campaigns=[label],
                severity="alta",
                confidence="media-alta",
                recommended_action="Auditar message match anuncio→landing, prueba social, CTA, formulario y velocidad/fricción mobile.",
            ))

        if median_cpc and median_cpl and metrics.cpc is not None and metrics.cpl is not None and metrics.cpc < median_cpc * 0.75 and metrics.cpl > median_cpl * 1.25:
            findings.append(CrossMetricFinding(
                pattern="CPC bajo con CPL alto",
                evidence=evidence_text,
                interpretation="El tráfico es barato, pero no se transforma en oportunidad. Posible tráfico de baja intención, audiencia amplia o landing débil.",
                affected_campaigns=[label],
                severity="alta",
                confidence="media",
                recommended_action="No escalar por CPC barato; revisar audiencia, promesa, landing y filtros de calificación.",
            ))

        if campaign.frequency is not None and campaign.frequency >= 2.5 and metrics.ctr_percent is not None and metrics.ctr_percent < max(median_ctr * 0.85, request.target_ctr_percent):
            findings.append(CrossMetricFinding(
                pattern="Frecuencia alta con CTR débil",
                evidence=evidence_text + f", frecuencia={campaign.frequency:.2f}",
                interpretation="La audiencia puede estar saturada o la creatividad perdió novedad.",
                affected_campaigns=[label],
                severity="media",
                confidence="media",
                recommended_action="Rotar creativos, limitar frecuencia, ampliar audiencia o separar retargeting por ventanas.",
            ))

        clicks = metrics.clicks or 0
        leads = metrics.leads or 0
        events = campaign.key_events or campaign.conversions or campaign.sales or 0
        if clicks >= 100 and leads == 0 and events == 0:
            findings.append(CrossMetricFinding(
                pattern="Clicks altos sin eventos ni leads",
                evidence=evidence_text + f", clicks={clicks}",
                interpretation="No se puede distinguir entre mala conversión real y tracking roto. La lectura de CPA/CPL queda contaminada.",
                affected_campaigns=[label],
                severity="crítica",
                confidence="alta",
                recommended_action="Corregir tracking antes de tomar decisiones de presupuesto.",
            ))

    return findings


def build_tracking_health(request: CampaignPerformanceRequest) -> List[TrackingHealthFinding]:
    findings: List[TrackingHealthFinding] = []
    for campaign in request.campaigns:
        label = campaign_label(campaign)
        clicks = campaign.clicks or 0
        leads = campaign.leads or campaign.form_submits or campaign.whatsapp_clicks or campaign.calls or 0
        events = campaign.key_events or campaign.conversions or campaign.sales or 0
        if campaign.events_configured is False or (clicks >= 100 and leads == 0 and events == 0):
            findings.append(TrackingHealthFinding(
                campaign_name=label,
                issue="Tracking crítico o conversiones no registradas",
                severity="crítica",
                evidence=f"Clicks={clicks}, leads={leads}, eventos={events}, events_configured={campaign.events_configured}",
                business_risk="Se pueden pausar campañas que sí funcionan o escalar campañas que no generan negocio real.",
                recommended_fix="Auditar Pixel/CAPI/GA4, eventos de formulario, WhatsApp, llamadas, thank-you page y conversiones importadas.",
                validation_metric="Eventos registrados correctamente y consistencia entre Ads, GA4 y CRM.",
            ))
        if campaign.utms_present is False:
            findings.append(TrackingHealthFinding(
                campaign_name=label,
                issue="UTMs ausentes o inconsistentes",
                severity="media-alta",
                evidence="La campaña declara utms_present=false.",
                business_risk="No se podrá conectar campaña, landing, CRM y calidad real de lead.",
                recommended_fix="Estandarizar UTMs por canal, campaña, adset, anuncio, hook y etapa del funnel.",
                validation_metric="100% de leads con fuente/medio/campaña/anuncio trazables.",
            ))
    if not request.campaigns:
        findings.append(TrackingHealthFinding(
            campaign_name=None,
            issue="Tracking pendiente de validar",
            severity="media",
            evidence="No hay campañas cargadas.",
            business_risk="Las decisiones de presupuesto no deben tomarse sin eventos y UTMs confiables.",
            recommended_fix="Cargar export de Ads + GA4/Pixel/CRM con eventos de contacto y calidad.",
            validation_metric="Data completeness y tracking readiness > 80/100.",
        ))
    return findings


def build_lead_quality_assessment(request: CampaignPerformanceRequest) -> List[LeadQualityAssessment]:
    results: List[LeadQualityAssessment] = []
    for campaign in request.campaigns:
        score = quality_score_from_campaign(campaign)
        level = quality_level(score)
        cpl = calc_cpl(campaign)
        evidence = []
        if score is not None:
            evidence.append(f"score={score:.0f}/100")
        if campaign.qualified_leads is not None:
            evidence.append(f"calificados={campaign.qualified_leads}")
        if campaign.bad_leads is not None:
            evidence.append(f"malos={campaign.bad_leads}")
        if cpl is not None:
            evidence.append(f"CPL={cpl:.2f} {request.currency}")
        recommendation = "Cargar calidad real de lead por CRM antes de decidir escalado." if score is None else "Mantener lectura de calidad en cada decisión de presupuesto."
        if score is not None and score < 35:
            recommendation = "No escalar por volumen barato: ajustar promesa, audiencia y filtros de calificación."
        elif score is not None and score >= 75 and cpl is not None:
            recommendation = "Evaluar escalado gradual si tracking y muestra son suficientes."
        results.append(LeadQualityAssessment(
            campaign_name=campaign_label(campaign),
            lead_quality_score=score,
            quality_level=level,
            evidence=", ".join(evidence) or "calidad no cargada",
            recommendation=recommendation,
        ))
    return results


def build_cost_quality_matrix(request: CampaignPerformanceRequest, benchmarks: Dict[str, Optional[float]]) -> List[CostQualityQuadrant]:
    matrix: List[CostQualityQuadrant] = []
    median_cpl = benchmarks.get("median_cpl") or request.target_cpl
    for campaign in request.campaigns:
        cpl = calc_cpl(campaign)
        score = quality_score_from_campaign(campaign)
        if cpl is None and score is None:
            continue
        cost_high = cpl is not None and median_cpl is not None and cpl > median_cpl
        cost_low = cpl is not None and median_cpl is not None and cpl <= median_cpl
        quality_high = score is not None and score >= 60
        quality_low = score is not None and score < 45
        quadrant = "sin_clasificar"
        recommendation = "Completar CPL y calidad para ubicar la campaña."
        confidence = "baja"
        if cost_low and quality_high:
            quadrant = "barato_alta_calidad"
            recommendation = "Escalar con incremento gradual y monitorear frecuencia/calidad."
            confidence = "media-alta"
        elif cost_low and quality_low:
            quadrant = "barato_baja_calidad"
            recommendation = "No escalar todavía; ajustar promesa, audiencia y filtro comercial."
            confidence = "media"
        elif cost_high and quality_high:
            quadrant = "caro_alta_calidad"
            recommendation = "Optimizar antes de pausar; puede valer la pena si genera oportunidades reales."
            confidence = "media"
        elif cost_high and quality_low:
            quadrant = "caro_baja_calidad"
            recommendation = "Pausar, rehacer o mover presupuesto a campañas más eficientes."
            confidence = "alta"
        matrix.append(CostQualityQuadrant(
            campaign_name=campaign_label(campaign),
            quadrant=quadrant,
            cpl=cpl,
            quality_score=score,
            recommendation=recommendation,
            confidence=confidence,
        ))
    return matrix


def build_budget_reallocation(request: CampaignPerformanceRequest, matrix: List[CostQualityQuadrant]) -> List[BudgetReallocationRecommendation]:
    recommendations: List[BudgetReallocationRecommendation] = []
    for item in matrix:
        if item.quadrant == "barato_alta_calidad":
            recommendations.append(BudgetReallocationRecommendation(
                campaign_name=item.campaign_name,
                action="aumentar_presupuesto_gradual",
                recommended_change_percent=20,
                reason="CPL relativo favorable y calidad alta.",
                risk="Escalar demasiado rápido puede saturar audiencia o bajar calidad.",
                confidence=item.confidence,
            ))
        elif item.quadrant == "caro_baja_calidad":
            recommendations.append(BudgetReallocationRecommendation(
                campaign_name=item.campaign_name,
                action="reducir_o_pausar",
                recommended_change_percent=-50,
                reason="CPL alto y calidad baja.",
                risk="Si la muestra es chica, validar antes de pausar definitivamente.",
                confidence=item.confidence,
            ))
        elif item.quadrant == "barato_baja_calidad":
            recommendations.append(BudgetReallocationRecommendation(
                campaign_name=item.campaign_name,
                action="mantener_con_filtro",
                recommended_change_percent=0,
                reason="Costo bajo pero calidad débil; primero mejorar filtro y promesa.",
                risk="Escalar puede llenar ventas de leads malos.",
                confidence=item.confidence,
            ))
        elif item.quadrant == "caro_alta_calidad":
            recommendations.append(BudgetReallocationRecommendation(
                campaign_name=item.campaign_name,
                action="optimizar_sin_pausar",
                recommended_change_percent=0,
                reason="La calidad justifica análisis; optimizar creativo, landing y segmentación antes de cortar.",
                risk="Pausar puede eliminar una fuente de oportunidades valiosas.",
                confidence=item.confidence,
            ))
    if not recommendations and not request.campaigns:
        recommendations.append(BudgetReallocationRecommendation(
            campaign_name="pendiente",
            action="sin_reasignacion_hasta_cargar_datos",
            recommended_change_percent=None,
            reason="No hay campañas para comparar.",
            risk="Reasignar presupuesto sin CPL, calidad y tracking puede aumentar desperdicio.",
            confidence="preparada",
        ))
    return recommendations


def infer_hook(campaign: CampaignMetric) -> str:
    if campaign.hook:
        return campaign.hook
    if campaign.angle:
        return campaign.angle
    name = campaign.campaign_name.casefold()
    notes = (campaign.notes or "").casefold()
    combined = name + " " + notes
    if "seguridad" in combined or "capital" in combined or "invers" in combined:
        return "seguridad / inversión"
    if "financi" in combined:
        return "financiación"
    if "amenit" in combined or "diseño" in combined or "estilo" in combined:
        return "diseño / amenities"
    if "retarget" in combined:
        return "retargeting"
    return campaign.campaign_name


def build_creative_hook_insights(request: CampaignPerformanceRequest, derived: List[DerivedCampaignMetrics]) -> List[CreativeHookInsight]:
    grouped: Dict[str, List[tuple[CampaignMetric, DerivedCampaignMetrics]]] = {}
    for campaign, metrics in zip(request.campaigns, derived):
        grouped.setdefault(infer_hook(campaign), []).append((campaign, metrics))
    insights: List[CreativeHookInsight] = []
    for hook, rows in grouped.items():
        avg_ctr = median_or_none([metrics.ctr_percent for _, metrics in rows])
        avg_cpl = median_or_none([metrics.cpl for _, metrics in rows])
        avg_quality = median_or_none([metrics.lead_quality_rate_percent for _, metrics in rows])
        campaigns = [metrics.campaign_name for _, metrics in rows]
        signal = f"CTR mediano={avg_ctr:.2f}%" if avg_ctr is not None else "CTR no disponible"
        if avg_cpl is not None:
            signal += f", CPL mediano={avg_cpl:.2f} {request.currency}"
        if avg_quality is not None:
            signal += f", calidad mediana={avg_quality:.0f}/100"
        interpretation = "Ángulo pendiente de validar."
        next_test = "Probar variantes con promesas y objeciones distintas."
        if avg_ctr is not None and avg_quality is not None and avg_ctr >= request.target_ctr_percent and avg_quality >= 60:
            interpretation = "Ángulo con señales de respuesta y calidad. Puede ser base de nuevos tests."
            next_test = "Crear 2-3 variantes del mismo ángulo con diferente prueba, CTA y objeción."
        elif avg_ctr is not None and avg_ctr < request.target_ctr_percent:
            interpretation = "Ángulo con baja respuesta inicial. Puede servir para awareness, pero no parece fuerte para conversión."
            next_test = "Cambiar hook, promesa o primer frame antes de aumentar presupuesto."
        insights.append(CreativeHookInsight(
            hook=hook,
            affected_campaigns=campaigns,
            signal=signal,
            interpretation=interpretation,
            recommended_next_test=next_test,
        ))
    return insights


def build_landing_friction(request: CampaignPerformanceRequest, derived: List[DerivedCampaignMetrics]) -> List[LandingFrictionAssessment]:
    assessments: List[LandingFrictionAssessment] = []
    for campaign, metrics in zip(request.campaigns, derived):
        if metrics.clicks is None and metrics.ctr_percent is None:
            continue
        friction = 35
        evidence = []
        if metrics.ctr_percent is not None and metrics.ctr_percent >= request.target_ctr_percent:
            friction += 15
            evidence.append(f"CTR aceptable/alto={metrics.ctr_percent:.2f}%")
        if metrics.cvr_percent is not None and metrics.cvr_percent < request.target_landing_conversion_rate_percent:
            friction += 30
            evidence.append(f"CVR bajo={metrics.cvr_percent:.2f}%")
        if campaign.landing_visits and (campaign.leads or 0) == 0:
            friction += 25
            evidence.append(f"visitas landing={campaign.landing_visits}, leads=0")
        if campaign.mobile_share_percent is not None and campaign.mobile_share_percent > 70 and metrics.cvr_percent is not None and metrics.cvr_percent < request.target_landing_conversion_rate_percent:
            friction += 10
            evidence.append("alto tráfico mobile con baja conversión")
        if evidence:
            assessments.append(LandingFrictionAssessment(
                campaign_name=metrics.campaign_name,
                friction_score=max(0, min(friction, 100)),
                evidence=", ".join(evidence),
                likely_issue="La landing, formulario, CTA o prueba de confianza no sostienen la promesa del anuncio.",
                recommended_fix="Revisar message match, prueba social above the fold, CTA, formulario, velocidad y experiencia mobile.",
            ))
    return assessments


def build_message_match(request: CampaignPerformanceRequest) -> List[MessageMatchAssessment]:
    assessments: List[MessageMatchAssessment] = []
    for campaign in request.campaigns:
        promise = (campaign.ad_promise or campaign.hook or campaign.angle or "").casefold()
        landing = (campaign.landing_message or "").casefold()
        score = 70
        mismatch = False
        evidence = "No hay promesa/landing suficientes para evaluar message match."
        if promise and landing:
            overlap = set(promise.split()) & set(landing.split())
            if len(overlap) < 2:
                score = 35
                mismatch = True
                evidence = f"Promesa='{campaign.ad_promise or campaign.hook or campaign.angle}' vs landing='{campaign.landing_message}'."
            else:
                evidence = "Promesa y landing comparten términos principales."
        elif promise and not landing:
            score = 50
            evidence = "Hay promesa de anuncio, pero no se cargó mensaje de landing."
        if mismatch or score < 70:
            assessments.append(MessageMatchAssessment(
                campaign_name=campaign_label(campaign),
                message_match_score=score,
                mismatch_detected=mismatch,
                evidence=evidence,
                recommended_fix="Alinear headline, prueba social, CTA y oferta de la landing con el hook del anuncio.",
            ))
    return assessments


def build_funnel_leaks(request: CampaignPerformanceRequest, derived: List[DerivedCampaignMetrics]) -> List[FunnelLeakFinding]:
    leaks: List[FunnelLeakFinding] = []
    for campaign, metrics in zip(request.campaigns, derived):
        label = metrics.campaign_name
        if metrics.impressions and metrics.impressions >= 1000 and metrics.ctr_percent is not None and metrics.ctr_percent < request.target_ctr_percent:
            leaks.append(FunnelLeakFinding(
                campaign_name=label,
                leak_stage="Awareness",
                evidence=f"Impresiones={metrics.impressions}, CTR={metrics.ctr_percent:.2f}%",
                probable_cause="Hook, creatividad, audiencia o promesa inicial poco relevante.",
                recommended_action="Testear hooks y separar mensajes por temperatura.",
                metric_to_validate="CTR, CPC y engagement de calidad.",
            ))
        if metrics.ctr_percent is not None and metrics.ctr_percent >= request.target_ctr_percent and metrics.cvr_percent is not None and metrics.cvr_percent < request.target_landing_conversion_rate_percent:
            leaks.append(FunnelLeakFinding(
                campaign_name=label,
                leak_stage="Consideration / Landing",
                evidence=f"CTR={metrics.ctr_percent:.2f}%, CVR={metrics.cvr_percent:.2f}%",
                probable_cause="La landing, CTA o prueba de confianza no convierte el interés.",
                recommended_action="Rehacer bloque inicial de landing, CTA y prueba social.",
                metric_to_validate="CVR landing→lead, CPL y calidad del lead.",
            ))
        if metrics.leads and campaign.meetings is not None and campaign.meetings < max(1, metrics.leads * 0.15):
            leaks.append(FunnelLeakFinding(
                campaign_name=label,
                leak_stage="Sales / Follow-up",
                evidence=f"Leads={metrics.leads}, reuniones={campaign.meetings}",
                probable_cause="Lead follow-up, velocidad de contacto o calificación débil.",
                recommended_action="Crear seguimiento comercial y SLA de contacto.",
                metric_to_validate="tasa lead→reunión y tiempo de primera respuesta.",
            ))
    return leaks


def build_experiment_recommendations(
    request: CampaignPerformanceRequest,
    cross_findings: List[CrossMetricFinding],
    landing_friction: List[LandingFrictionAssessment],
    hook_insights: List[CreativeHookInsight],
) -> List[ExperimentRecommendation]:
    experiments: List[ExperimentRecommendation] = []
    if any("CTR bajo" in finding.pattern for finding in cross_findings):
        experiments.append(ExperimentRecommendation(
            title="Test de hooks para recuperar respuesta inicial",
            hypothesis="Si cambiamos el hook principal hacia dolor, seguridad, prueba o beneficio concreto, subirá el CTR sin deteriorar calidad.",
            change="Crear 3 variantes de hook para campañas con CTR bajo.",
            primary_metric="CTR",
            secondary_metric="CPC y calidad de lead",
            success_criteria="+20% CTR sin caída de calidad respecto al control.",
            minimum_duration="7–14 días o hasta alcanzar muestra mínima.",
            risk="Confundir engagement superficial con intención real.",
            do_not_touch="No cambiar audiencia, landing y presupuesto al mismo tiempo que el hook.",
        ))
    if landing_friction:
        experiments.append(ExperimentRecommendation(
            title="Test de landing para cerrar fuga post-click",
            hypothesis="Si alineamos headline, prueba social y CTA con la promesa del anuncio, aumentará la tasa landing→lead.",
            change="Crear variante de landing con mensaje específico, prueba social visible y CTA de menor fricción.",
            primary_metric="CVR landing→lead",
            secondary_metric="CPL y lead quality score",
            success_criteria="+20% CVR sin caída de calidad.",
            minimum_duration="7–14 días o hasta 300+ clicks.",
            risk="Aumentar leads pero bajar calidad si el CTA es demasiado amplio.",
            do_not_touch="No cambiar tracking ni evento primario durante el test.",
        ))
    if hook_insights:
        best = next((item for item in hook_insights if "respuesta" in item.interpretation or "calidad" in item.interpretation), None)
        if best:
            experiments.append(ExperimentRecommendation(
                title=f"Profundizar ángulo ganador: {best.hook}",
                hypothesis="Si expandimos un ángulo con señal de calidad, podemos aumentar volumen manteniendo intención.",
                change="Crear variantes del ángulo ganador con objeciones, prueba y CTA distintos.",
                primary_metric="CPL de lead calificado",
                secondary_metric="CTR, frecuencia y tasa de reunión",
                success_criteria="Mantener CPL relativo y calidad mientras sube volumen.",
                minimum_duration="14 días o muestra mínima de leads calificados.",
                risk="Saturar un ángulo ganador si se escala demasiado rápido.",
                do_not_touch="No duplicar presupuesto más de 20–30% sin monitoreo.",
            ))
    if not experiments:
        experiments.append(ExperimentRecommendation(
            title="Preparar primer ciclo de experimentos",
            hypothesis="Con datos de campaña y tracking confiable se podrán aislar fugas por creativo, landing, audiencia o seguimiento.",
            change="Cargar métricas completas y definir un control antes de modificar múltiples variables.",
            primary_metric="CPL de lead calificado",
            secondary_metric="CTR, CVR, reuniones y CPA",
            success_criteria="Decisiones basadas en muestra suficiente y tracking confiable.",
            minimum_duration="7–14 días por test.",
            risk="Tomar decisiones con datos incompletos.",
            do_not_touch="No mezclar cambios de creativo, audiencia, landing y tracking en el mismo test.",
        ))
    return experiments[:6]


def build_data_completeness(request: CampaignPerformanceRequest) -> DataCompletenessScore:
    checks = {
        "gasto": any(c.spend is not None for c in request.campaigns),
        "impresiones": any(c.impressions is not None for c in request.campaigns),
        "clicks": any(c.clicks is not None for c in request.campaigns),
        "leads": any(c.leads is not None or c.form_submits is not None or c.whatsapp_clicks is not None for c in request.campaigns),
        "conversiones/ventas": any(c.conversions is not None or c.sales is not None or c.revenue is not None for c in request.campaigns),
        "calidad de lead": any(c.qualified_leads is not None or c.bad_leads is not None or c.lead_quality_score is not None for c in request.campaigns),
        "eventos/tracking": any(c.key_events is not None or c.events_configured is not None for c in request.campaigns),
        "UTMs": any(c.utms_present is not None for c in request.campaigns),
        "landing/formulario": any(c.landing_visits is not None or c.form_starts is not None or c.form_submits is not None for c in request.campaigns),
        "CRM/reuniones": any(c.meetings is not None or c.opportunities is not None or c.crm_stage is not None for c in request.campaigns),
        "período anterior": any(c.previous_spend is not None or c.previous_clicks is not None or c.previous_leads is not None for c in request.campaigns),
    }
    if not request.campaigns:
        return DataCompletenessScore(
            score=0,
            missing_fields=list(checks.keys()),
            impact_on_analysis="Sin campañas, el sistema solo puede devolver acciones preparadas e inferencias estratégicas.",
            next_data_to_collect=build_next_data_needed(request),
        )
    present = sum(1 for value in checks.values() if value)
    score = round((present / len(checks)) * 100)
    missing = [name for name, ok in checks.items() if not ok]
    impact = "Alta capacidad analítica." if score >= 80 else "Análisis útil pero todavía incompleto." if score >= 50 else "Alta incertidumbre: faltan datos clave para decisiones de presupuesto."
    return DataCompletenessScore(
        score=score,
        missing_fields=missing,
        impact_on_analysis=impact,
        next_data_to_collect=missing[:8] or ["Datos históricos por período para detectar tendencia y fatiga."],
    )


def build_sample_size_warnings(request: CampaignPerformanceRequest) -> List[str]:
    warnings = []
    for campaign in request.campaigns:
        clicks = campaign.clicks or 0
        leads = campaign.leads or campaign.form_submits or campaign.whatsapp_clicks or campaign.calls or 0
        if clicks < 100 and leads < 5:
            warnings.append(f"{campaign_label(campaign)}: muestra insuficiente; evitar decisiones fuertes hasta superar 100–300 clicks o 5–10 leads.")
        elif leads < 5:
            warnings.append(f"{campaign_label(campaign)}: pocos leads; no concluir calidad todavía.")
    return warnings


def build_confidence_notes(cross_findings: List[CrossMetricFinding], tracking: List[TrackingHealthFinding], data_score: DataCompletenessScore) -> List[str]:
    notes = []
    if data_score.score < 50:
        notes.append("Confianza general baja-media: faltan datos de tracking, calidad, CRM o histórico.")
    elif data_score.score < 80:
        notes.append("Confianza general media: hay datos suficientes para priorizar, pero conviene completar CRM/histórico.")
    else:
        notes.append("Confianza general alta: dataset suficientemente completo para decisiones accionables.")
    if any(item.severity == "crítica" for item in tracking):
        notes.append("Las conclusiones de CPA/CPL deben leerse con cautela hasta corregir tracking crítico.")
    for finding in cross_findings[:5]:
        notes.append(f"{finding.pattern}: confianza {finding.confidence}; severidad {finding.severity}.")
    return notes


def build_timed_action_plan(data_score: DataCompletenessScore, tracking: List[TrackingHealthFinding], budget: List[BudgetReallocationRecommendation], experiments: List[ExperimentRecommendation]) -> TimedActionPlan:
    today = []
    if any(item.severity == "crítica" for item in tracking):
        today.append("Corregir tracking crítico antes de tomar decisiones de presupuesto.")
    today.append("Identificar campañas con desperdicio evidente y bloquear escalado de campañas con baja calidad.")
    if data_score.score < 70:
        today.append("Completar datos mínimos: gasto, clicks, leads, eventos, calidad y CRM.")

    seven = ["Reformular CTA y prueba social en puntos de contacto principales."]
    if budget:
        seven.append("Aplicar reasignación gradual: reducir desperdicio y escalar solo campañas con calidad suficiente.")
    if experiments:
        seven.append("Lanzar primer ciclo de tests con una variable por vez.")

    thirty = ["Rediseñar landing o message match donde exista CTR alto con CVR bajo.", "Separar campañas por temperatura: frío, tibio, templado, caliente y retargeting."]
    ninety = ["Crear sistema de seguimiento comercial y scoring de leads en CRM.", "Conectar campañas, GA4/Pixel/CAPI y CRM para reporting de calidad real."]
    return TimedActionPlan(today_48h=today, next_7_days=seven, next_14_30_days=thirty, next_60_90_days=ninety)


def build_discovery_questions() -> List[str]:
    return [
        "¿Qué porcentaje de leads agenda reunión?",
        "¿Qué campañas generan clientes reales, no solo leads?",
        "¿Qué objeciones aparecen con más frecuencia en ventas?",
        "¿Cuál es el tiempo medio desde primer contacto hasta decisión?",
        "¿Qué evento se usa como conversión principal y dónde se dispara?",
        "¿Los leads tienen UTMs y fuente/campaña en CRM?",
        "¿Cuál es la tasa de contacto, reunión, oportunidad y cierre por canal?",
        "¿Qué lead se considera calificado y quién lo valida?",
    ]


def build_proposal_guidance(data_score: DataCompletenessScore) -> ProposalGuidance:
    return ProposalGuidance(
        what_to_sell=[
            "Diagnóstico profundo de sistema comercial y performance.",
            "Corrección de tracking, eventos, UTMs y reporting de calidad.",
            "Rediseño de propuesta de valor, CTA, prueba social y ruta de conversión.",
            "Plan de experimentos para hooks, landing, audiencias y retargeting.",
        ],
        what_not_to_sell_yet=[
            "Calendario completo de contenidos antes de ordenar mensaje y medición.",
            "Escalado agresivo de campañas sin tracking y calidad validados.",
            "Implementación táctica completa sin discovery comercial.",
        ],
        what_to_show_in_meeting=[
            "Heatmap de intención y zona bloqueada.",
            "Blueprint con FAULT, DG, ruta verde y Support Layer.",
            "Matriz costo/calidad y riesgos de presupuesto.",
            "Preguntas de datos necesarias para pasar de inferencia a evidencia.",
        ],
        what_data_to_request=data_score.next_data_to_collect,
        what_to_promise=[
            "Mayor claridad diagnóstica y priorización de decisiones.",
            "Mejor trazabilidad entre campañas, leads y oportunidades.",
            "Sistema de pruebas para mejorar conversión y calidad.",
        ],
        what_not_to_promise=[
            "Resultados garantizados sin datos ni control de implementación.",
            "Bajar CPL sin considerar calidad de lead.",
            "Escalar ventas solo aumentando presupuesto.",
        ],
        closing_angle="El problema no es solo publicar o invertir más; es construir un sistema medible que convierta intención en oportunidades calificadas.",
    )


def build_commercial_readiness_score(public_audit: ProspectWithResearchResponse, campaign_performance: CampaignPerformanceResponse) -> CommercialReadinessScore:
    tracking_score = max(0, min(100, campaign_performance.data_completeness.score + 10))
    if any(item.severity == "crítica" for item in campaign_performance.tracking_health):
        tracking_score = min(tracking_score, 40)
    offer_clarity = max(20, min(100, public_audit.commercial_score.value_proposition * 10))
    funnel_continuity = max(20, min(100, public_audit.commercial_score.cta_strength * 10))
    lead_quality = int(median_or_none([item.lead_quality_score for item in campaign_performance.lead_quality_assessment]) or 45)
    budget_efficiency = 70 if any(item.action == "aumentar_presupuesto_gradual" for item in campaign_performance.budget_reallocation) else 45
    message_match = 100 - int(median_or_none([100 - item.message_match_score for item in campaign_performance.message_match]) or 35)
    landing_strength = 100 - int(median_or_none([item.friction_score for item in campaign_performance.landing_friction]) or 45)
    creative_relevance = 70 if campaign_performance.creative_hook_insights else 45
    cta_clarity = max(20, min(100, public_audit.commercial_score.cta_strength * 10))
    sales_follow_up = 55 if any("seguimiento" in action.action.casefold() for action in campaign_performance.strategic_actions) else 40
    components = [tracking_score, offer_clarity, message_match, funnel_continuity, lead_quality, creative_relevance, landing_strength, cta_clarity, sales_follow_up, budget_efficiency]
    overall = round(sum(components) / len(components))
    component_map = {
        "tracking_readiness": tracking_score,
        "offer_clarity": offer_clarity,
        "message_match": message_match,
        "funnel_continuity": funnel_continuity,
        "lead_quality": lead_quality,
        "creative_relevance": creative_relevance,
        "landing_strength": landing_strength,
        "cta_clarity": cta_clarity,
        "sales_follow_up": sales_follow_up,
        "budget_efficiency": budget_efficiency,
    }
    weakest = min(component_map, key=component_map.get)
    strongest = max(component_map, key=component_map.get)
    return CommercialReadinessScore(
        overall=overall,
        tracking_readiness=int(tracking_score),
        offer_clarity=int(offer_clarity),
        message_match=int(message_match),
        funnel_continuity=int(funnel_continuity),
        lead_quality=int(lead_quality),
        creative_relevance=int(creative_relevance),
        landing_strength=int(landing_strength),
        cta_clarity=int(cta_clarity),
        sales_follow_up=int(sales_follow_up),
        budget_efficiency=int(budget_efficiency),
        strongest_area=strongest,
        weakest_area=weakest,
        recommended_focus=f"Priorizar {weakest.replace('_', ' ')} antes de escalar el sistema.",
    )


def build_map_coherence_check(public_audit: ProspectWithResearchResponse, campaign_performance: CampaignPerformanceResponse) -> MapCoherenceCheck:
    alignment = []
    inconsistencies = []
    corrections = []
    density = public_audit.customer_intent_density_map
    blocked = f"{density.blocked_zone.x} / {density.blocked_zone.y}"
    alignment.append(f"Heatmap marca bloqueo en {blocked}; blueprint debe leerse desde FAULT hacia DG y ruta verde.")
    if any("CTR alto con conversión baja" in item.pattern for item in campaign_performance.cross_metric_findings):
        alignment.append("Performance detecta interés post-click con baja conversión; coincide con FAULT entre interés, confianza y acción.")
    if any(item.issue.startswith("Tracking crítico") for item in campaign_performance.tracking_health):
        inconsistencies.append("Hay tracking crítico: los mapas pueden ser estratégicamente coherentes, pero la evidencia de CPA/CPL no es confiable todavía.")
        corrections.append("Corregir tracking antes de usar performance para confirmar el heatmap.")
    if any("baja calidad" in item.quadrant for item in campaign_performance.cost_quality_matrix):
        alignment.append("La matriz costo/calidad refuerza la necesidad del Support Layer: prueba, objeciones, CTA y follow-up.")
    score = 85 - len(inconsistencies) * 15
    return MapCoherenceCheck(
        score=max(40, score),
        alignment_detected=alignment,
        inconsistencies=inconsistencies,
        correction_needed=corrections or ["Mantener explicación separada: heatmap diagnostica intención; blueprint explica rediseño."],
    )

def run_campaign_performance_audit(request: CampaignPerformanceRequest) -> CampaignPerformanceResponse:
    data_quality = infer_campaign_data_quality(request)
    has_data = data_quality not in ["sin_datos", "baja"] or has_meaningful_campaign_data(request.campaigns)

    strategic_actions = build_default_strategic_actions(
        company_name=request.company_name,
        has_data=has_data,
    )

    findings, performance_actions, budget_actions, tracking_actions = build_campaign_findings_and_actions(request)

    temperature_action = build_temperature_separation_action(request)
    if temperature_action:
        performance_actions.append(temperature_action)

    derived_metrics = derive_campaign_metrics(request)
    internal_benchmarks = build_internal_benchmarks(derived_metrics)
    metric_deltas = build_metric_deltas(request)
    cross_metric_findings = build_cross_metric_findings(request, derived_metrics, internal_benchmarks)
    tracking_health = build_tracking_health(request)
    lead_quality_assessment = build_lead_quality_assessment(request)
    cost_quality_matrix = build_cost_quality_matrix(request, internal_benchmarks)
    budget_reallocation = build_budget_reallocation(request, cost_quality_matrix)
    creative_hook_insights = build_creative_hook_insights(request, derived_metrics)
    landing_friction = build_landing_friction(request, derived_metrics)
    message_match = build_message_match(request)
    funnel_leaks = build_funnel_leaks(request, derived_metrics)
    experiment_recommendations = build_experiment_recommendations(request, cross_metric_findings, landing_friction, creative_hook_insights)
    data_completeness = build_data_completeness(request)
    sample_size_warnings = build_sample_size_warnings(request)
    confidence_by_finding = build_confidence_notes(cross_metric_findings, tracking_health, data_completeness)
    timed_action_plan = build_timed_action_plan(data_completeness, tracking_health, budget_reallocation, experiment_recommendations)
    discovery_questions = build_discovery_questions()
    proposal_guidance = build_proposal_guidance(data_completeness)

    # Turn richer findings into actionable items so they appear in the prioritized list.
    for finding in cross_metric_findings:
        performance_actions.append(make_action(
            category="cruce_metricas",
            action=finding.recommended_action,
            trigger=finding.pattern,
            evidence=finding.evidence,
            priority="crítica" if finding.severity == "crítica" else "alta" if finding.severity in ["alta", "media-alta"] else "media",
            effort="medio",
            expected_impact="Mejorar eficiencia del funnel y evitar decisiones basadas en métricas aisladas.",
            verification_metric="CTR, CPC, CVR, CPL, calidad de lead y reuniones.",
            related_campaign=", ".join(finding.affected_campaigns),
            confidence=finding.confidence,
            data_required=False,
        ))

    for item in tracking_health:
        tracking_actions.append(make_action(
            category="tracking",
            action=item.recommended_fix,
            trigger=item.issue,
            evidence=item.evidence,
            priority="crítica" if item.severity == "crítica" else "alta" if item.severity in ["alta", "media-alta"] else "media",
            effort="medio",
            expected_impact="Mejorar confiabilidad de CPA/CPL y atribución real de oportunidades.",
            verification_metric=item.validation_metric,
            related_campaign=item.campaign_name,
            confidence="alta" if item.severity == "crítica" else "media",
            data_required=False,
        ))

    for item in budget_reallocation:
        budget_actions.append(make_action(
            category="presupuesto",
            action=item.action,
            trigger="Matriz costo/calidad y benchmarks internos.",
            evidence=item.reason,
            priority="alta" if item.action in ["reducir_o_pausar", "aumentar_presupuesto_gradual"] else "media",
            effort="bajo",
            expected_impact="Asignar presupuesto según eficiencia y calidad, no solo volumen de leads.",
            verification_metric="CPL, CPL calificado, CPA, frecuencia, calidad y reuniones.",
            related_campaign=item.campaign_name,
            confidence=item.confidence,
            data_required=False,
        ))

    # Ensure the requested performance rules exist even before data is available.
    if not request.campaigns:
        performance_actions.extend([
            make_action(
                category="creativo",
                action="Testear nuevos hooks en anuncios con CTR bajo",
                trigger="Pendiente de CTR por campaña/anuncio.",
                evidence="No hay campañas cargadas todavía.",
                priority="media",
                effort="medio",
                expected_impact="Mejorar respuesta inicial cuando se detecten anuncios con bajo CTR.",
                verification_metric="CTR, CPC y tasa de visita calificada.",
                confidence="preparada",
                data_required=True,
            ),
            make_action(
                category="landing",
                action="Rehacer landing si hay tráfico pero baja conversión",
                trigger="Pendiente de clicks, visitas y conversiones por landing.",
                evidence="No hay campañas cargadas todavía.",
                priority="media",
                effort="alto",
                expected_impact="Mejorar conversión de tráfico existente cuando se detecte fuga landing→lead.",
                verification_metric="Landing conversion rate, CPL y eventos de contacto.",
                confidence="preparada",
                data_required=True,
            ),
            make_action(
                category="audiencia",
                action="Cambiar audiencia si hay alto gasto y baja intención",
                trigger="Pendiente de gasto, clicks y leads/conversiones.",
                evidence="No hay campañas cargadas todavía.",
                priority="media",
                effort="medio",
                expected_impact="Reducir gasto en tráfico poco calificado.",
                verification_metric="CPL, CPA, tasa de lead calificado y engagement de calidad.",
                confidence="preparada",
                data_required=True,
            ),
            make_action(
                category="retargeting",
                action="Crear retargeting para usuarios con interés sin conversión",
                trigger="Pendiente de eventos de visita, interacción y no conversión.",
                evidence="No hay campañas cargadas todavía.",
                priority="media",
                effort="medio",
                expected_impact="Recuperar usuarios tibios que no completan la acción.",
                verification_metric="Conversiones asistidas, CPL retargeting y tasa de retorno.",
                confidence="preparada",
                data_required=True,
            ),
        ])
        budget_actions.extend([
            make_action(
                category="presupuesto",
                action="Pausar campañas con CPL alto y baja calidad",
                trigger="Pendiente de CPL y calidad de lead.",
                evidence="No hay campañas cargadas todavía.",
                priority="media",
                effort="bajo",
                expected_impact="Evitar desperdicio cuando haya datos suficientes.",
                verification_metric="CPL, calidad de lead y costo por oportunidad calificada.",
                confidence="preparada",
                data_required=True,
            ),
            make_action(
                category="presupuesto",
                action="Duplicar presupuesto en campañas con CPL bajo y buena conversión",
                trigger="Pendiente de CPL, conversiones y calidad.",
                evidence="No hay campañas cargadas todavía.",
                priority="media",
                effort="bajo",
                expected_impact="Escalar lo que funcione cuando exista evidencia.",
                verification_metric="CPL, CPA, frecuencia y volumen incremental.",
                confidence="preparada",
                data_required=True,
            ),
        ])

    all_actions = strategic_actions + performance_actions + budget_actions + tracking_actions
    prioritized_actions = prioritize_actions(all_actions, limit=20)

    if data_quality == "sin_datos":
        summary = (
            "No hay campañas cargadas todavía. El endpoint queda preparado con reglas estratégicas, performance, tracking, calidad, presupuesto y experimentos; "
            "las acciones tácticas aparecen como preparadas y requieren datos para activarse con evidencia."
        )
    elif cross_metric_findings or findings:
        summary = (
            f"Se analizaron {len(request.campaigns)} campañas. Además de hallazgos básicos, se detectaron {len(cross_metric_findings)} cruces métricos, "
            f"{len(tracking_health)} alertas de tracking y {len(funnel_leaks)} fugas de funnel."
        )
    else:
        summary = (
            f"Se analizaron {len(request.campaigns)} campañas. No hay anomalías fuertes con los umbrales actuales, "
            "pero se devuelven benchmarks internos, guardrails, experimentos y próximos datos necesarios."
        )

    return CampaignPerformanceResponse(
        company_name=request.company_name,
        audit_type="campaign_intelligence_rules_v2",
        data_quality=data_quality,
        campaigns_analyzed=len(request.campaigns),
        findings=findings,
        strategic_actions=strategic_actions,
        performance_actions=performance_actions,
        budget_actions=budget_actions,
        tracking_actions=tracking_actions,
        prioritized_actions=prioritized_actions,
        derived_metrics=derived_metrics,
        metric_deltas=metric_deltas,
        internal_benchmarks=internal_benchmarks,
        cross_metric_findings=cross_metric_findings,
        tracking_health=tracking_health,
        lead_quality_assessment=lead_quality_assessment,
        cost_quality_matrix=cost_quality_matrix,
        budget_reallocation=budget_reallocation,
        creative_hook_insights=creative_hook_insights,
        landing_friction=landing_friction,
        message_match=message_match,
        funnel_leaks=funnel_leaks,
        experiment_recommendations=experiment_recommendations,
        data_completeness=data_completeness,
        sample_size_warnings=sample_size_warnings,
        confidence_by_finding=confidence_by_finding,
        timed_action_plan=timed_action_plan,
        discovery_questions=discovery_questions,
        proposal_guidance=proposal_guidance,
        next_data_needed=build_next_data_needed(request),
        summary=summary,
    )


def convert_corrective_to_performance_action(item: CorrectiveActionItem) -> PerformanceAction:
    return make_action(
        category="auditoria_comercial",
        action=item.recommended_action,
        trigger=item.issue,
        evidence=item.evidence,
        priority=item.priority,
        effort=item.effort,
        expected_impact=item.expected_impact,
        verification_metric=item.verification_metric,
        confidence="media",
        data_required=False,
    )


@app.post(
    "/audit/campaign-performance",
    response_model=CampaignPerformanceResponse,
    operation_id="auditCampaignPerformance",
    summary="Audit campaign performance",
    description="Audita campañas con reglas de performance. Puede funcionar sin campañas cargadas devolviendo acciones preparadas y datos requeridos.",
    dependencies=[Security(verify_api_key)],
)
def audit_campaign_performance(request: CampaignPerformanceRequest):
    return run_campaign_performance_audit(request)


@app.post(
    "/audit/full-commercial-system",
    response_model=FullCommercialSystemResponse,
    operation_id="auditFullCommercialSystem",
    summary="Audit full commercial system",
    description="Une investigación pública, auditoría comercial, blueprint, heatmap y auditoría de campañas en un sistema único.",
    dependencies=[Security(verify_api_key)],
)
def audit_full_commercial_system(request: FullCommercialSystemRequest):
    public_audit_request = ProspectWithResearchRequest(
        company_name=request.company_name,
        industry=request.industry,
        city=request.city,
        country=request.country,
        website=request.website,
        instagram=request.instagram,
        linkedin=request.linkedin,
        offer=request.offer,
        notes=request.notes,
        num_results_per_query=request.num_results_per_query,
    )

    public_audit = audit_prospect_with_research(public_audit_request)

    campaign_request = CampaignPerformanceRequest(
        company_name=request.company_name,
        campaigns=request.campaigns,
        notes=request.campaign_notes or request.notes,
        target_cpl=request.target_cpl,
        target_cpa=request.target_cpa,
        target_ctr_percent=request.target_ctr_percent,
        target_landing_conversion_rate_percent=request.target_landing_conversion_rate_percent,
        min_lead_quality_rate_percent=request.min_lead_quality_rate_percent,
    )

    campaign_performance = run_campaign_performance_audit(campaign_request)

    strategic_from_public_audit = [
        convert_corrective_to_performance_action(action)
        for action in public_audit.corrective_action_plan[:5]
    ]

    unified_priorities = prioritize_actions(
        strategic_from_public_audit + campaign_performance.prioritized_actions,
        limit=18,
    )

    if campaign_performance.data_quality == "sin_datos":
        system_summary = (
            "El sistema comercial ya puede unir investigación pública, diagnóstico estratégico y estructura visual. "
            "La capa de campañas está preparada, pero todavía necesita datos reales para activar decisiones de presupuesto, creatividad, landing, audiencia, retargeting y tracking."
        )
    else:
        system_summary = (
            "El sistema comercial combina señales públicas con datos de campaña. Las prioridades deben leerse como una secuencia: "
            "primero corregir mensaje/CTA/confianza, luego presupuesto/tracking, y después escalar o pausar según evidencia."
        )

    commercial_readiness_score = build_commercial_readiness_score(public_audit, campaign_performance)
    map_coherence_check = build_map_coherence_check(public_audit, campaign_performance)

    return FullCommercialSystemResponse(
        company_name=request.company_name,
        audit_type="full_commercial_system_audit_v2",
        public_commercial_audit=public_audit,
        campaign_performance=campaign_performance,
        unified_priorities=unified_priorities,
        commercial_readiness_score=commercial_readiness_score,
        data_completeness_score=campaign_performance.data_completeness,
        map_coherence_check=map_coherence_check,
        discovery_questions=campaign_performance.discovery_questions,
        proposal_guidance=campaign_performance.proposal_guidance,
        timed_action_plan=campaign_performance.timed_action_plan,
        system_summary=system_summary,
        recommended_next_step=(
            "Cargar un export real de campañas, eventos, calidad de lead, CRM y período anterior para pasar de acciones preparadas a decisiones con evidencia."
            if campaign_performance.data_quality == "sin_datos"
            else "Revisar primero tracking, data completeness, mapa de coherencia y acciones con impacto alto/esfuerzo bajo."
        ),
    )
