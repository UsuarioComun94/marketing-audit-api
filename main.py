import os
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field


app = FastAPI(
    title="Marketing Audit API",
    description="API para auditar prospectos y devolver información estructurada a un Custom GPT.",
    version="1.2.0",
    servers=[
        {
            "url": "https://marketing-audit-api.onrender.com",
            "description": "Render production server"
        }
    ]
)


API_KEY = os.getenv("API_KEY", "dev-key")

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_BASE_URL = "https://backend.composio.dev/api/v3.1"

ALLOWED_COMPOSIO_TOOLS = {
    "SEARCH_API_SEARCH",
    "SEARCH_API_LOCATIONS",
    "COMPOSIO_SEARCH_DUCK_DUCK_GO_SEARCH"
}


api_key_header = APIKeyHeader(
    name="x-api-key",
    auto_error=False
)


def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="API key inválida o ausente"
        )
    return api_key


# =========================
# MODELOS DE AUDITORÍA
# =========================

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


# =========================
# MODELOS DE TOOLS / COMPOSIO
# =========================

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
    query: str = Field(
        ...,
        description="Texto para buscar herramientas, por ejemplo: search api, google, apify, sheets"
    )
    toolkit_slug: Optional[str] = Field(
        None,
        description="Toolkit específico, por ejemplo: search_api, apify, google_sheets"
    )
    limit: int = Field(10, description="Cantidad máxima de herramientas a devolver")


class ToolsSearchResponse(BaseModel):
    query: str
    toolkit_slug: Optional[str]
    results: List[ToolInfo]


class ToolDetailsResponse(BaseModel):
    tool_slug: str
    raw_response: Dict[str, Any]


class ToolExecuteRequest(BaseModel):
    tool_slug: str = Field(
        ...,
        description="Slug exacto de la herramienta de Composio, por ejemplo SEARCH_API_SEARCH"
    )
    arguments: Optional[Dict[str, Any]] = Field(
        None,
        description="Argumentos estructurados para la herramienta"
    )
    text: Optional[str] = Field(
        None,
        description="Instrucción en lenguaje natural para ejecutar la herramienta"
    )
    user_id: str = Field(
        "default",
        description="Identificador del usuario en Composio"
    )


class ToolExecuteResponse(BaseModel):
    tool_slug: str
    successful: Optional[bool] = None
    data: Optional[Any] = None
    error: Optional[Any] = None
    raw_response: Dict[str, Any]


# =========================
# HELPERS COMPOSIO
# =========================

def get_composio_headers():
    if not COMPOSIO_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="COMPOSIO_API_KEY no está configurada en el servidor"
        )

    return {
        "x-api-key": COMPOSIO_API_KEY,
        "accept": "application/json"
    }


def composio_get(path: str, params: Optional[dict] = None):
    try:
        response = requests.get(
            f"{COMPOSIO_BASE_URL}{path}",
            headers=get_composio_headers(),
            params=params or {},
            timeout=20
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con Composio: {str(exc)}"
        )

    if response.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="Composio rechazó la API key. Revisá COMPOSIO_API_KEY."
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    return response.json()


def composio_post(path: str, payload: Optional[dict] = None):
    try:
        response = requests.post(
            f"{COMPOSIO_BASE_URL}{path}",
            headers={
                **get_composio_headers(),
                "Content-Type": "application/json"
            },
            json=payload or {},
            timeout=45
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con Composio: {str(exc)}"
        )

    if response.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="Composio rechazó la API key. Revisá COMPOSIO_API_KEY."
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    return response.json()


def extract_tools_list(composio_response):
    if isinstance(composio_response, list):
        return composio_response

    if isinstance(composio_response, dict):
        if isinstance(composio_response.get("items"), list):
            return composio_response["items"]

        if isinstance(composio_response.get("tools"), list):
            return composio_response["tools"]

        if isinstance(composio_response.get("data"), list):
            return composio_response["data"]

    return []


def normalize_tool(tool: dict) -> ToolInfo:
    slug = (
        tool.get("slug")
        or tool.get("name")
        or tool.get("tool_slug")
        or tool.get("id")
        or "unknown"
    )

    name = tool.get("name") or tool.get("display_name") or slug
    toolkit = tool.get("toolkit_slug") or tool.get("toolkit") or tool.get("app")

    description = (
        tool.get("description")
        or tool.get("summary")
        or tool.get("display_description")
    )

    return ToolInfo(
        slug=str(slug),
        name=str(name) if name else None,
        toolkit=str(toolkit) if toolkit else None,
        description=str(description) if description else None
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


# =========================
# ROOT
# =========================

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Marketing Audit API funcionando"
    }


# =========================
# LÓGICA DE AUDITORÍA
# =========================

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

    if request.instagram or contains_any(
        text,
        ["instagram", "contenido", "publicaciones", "posteos", "feed", "reels"]
    ):
        focus_areas.append("contenido")

    if contains_any(
        text,
        ["awareness", "visibilidad", "alcance", "reconocimiento", "tráfico", "audiencia"]
    ):
        focus_areas.append("awareness")

    if contains_any(
        text,
        [
            "propuesta de valor",
            "diferenciación",
            "diferenciacion",
            "oferta",
            "por qué elegir",
            "porque elegir",
            "posicionamiento"
        ]
    ):
        focus_areas.append("propuesta de valor")

    if contains_any(
        text,
        [
            "cta",
            "llamada a la acción",
            "llamada a la accion",
            "conversión",
            "conversion",
            "convertir",
            "leads",
            "consulta",
            "mensaje"
        ]
    ):
        focus_areas.append("conversión")

    if contains_any(
        text,
        ["funnel", "embudo", "landing", "retargeting", "seguimiento", "pipeline"]
    ):
        focus_areas.append("funnel")

    if contains_any(
        text,
        ["marca", "competidores", "competencia", "precio", "premium", "autoridad"]
    ):
        focus_areas.append("posicionamiento")

    if not focus_areas:
        focus_areas = [
            "awareness",
            "propuesta de valor",
            "contenido",
            "funnel",
            "conversión"
        ]

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
        "propuesta de valor": (
            "La empresa puede estar generando visibilidad sin lograr que el mercado entienda "
            "por qué debería elegirla frente a otras alternativas."
        ),
        "conversión": (
            "La empresa puede estar atrayendo atención, pero perdiendo oportunidades porque no "
            "guía al usuario hacia una acción comercial concreta."
        ),
        "funnel": (
            "La empresa puede tener puntos de contacto aislados, pero sin un recorrido claro que "
            "transforme interés en oportunidad comercial."
        ),
        "posicionamiento": (
            "La empresa puede quedar atrapada en comparación por precio o apariencia porque no "
            "comunica una diferencia estratégica clara."
        ),
        "contenido": (
            "La empresa puede estar publicando con frecuencia, pero sin una narrativa que construya "
            "demanda, autoridad o intención de compra."
        ),
        "awareness": (
            "La empresa puede tener baja presencia mental en el mercado y depender demasiado de "
            "acciones tácticas de corto plazo."
        )
    }

    return risks.get(
        primary_bottleneck,
        "La empresa puede estar haciendo actividad digital sin convertirla en demanda calificada."
    )


def build_recommended_angle(primary_bottleneck: str) -> str:
    angles = {
        "propuesta de valor": "Mostrar la brecha entre tener presencia digital y comunicar una razón clara para ser elegido.",
        "conversión": "Mostrar cómo la falta de CTA y dirección comercial reduce la cantidad de consultas calificadas.",
        "funnel": "Mostrar que el problema no es solo publicar más, sino construir un recorrido desde atención hasta conversión.",
        "posicionamiento": "Mostrar cómo una marca sin diferenciación termina compitiendo por precio, estética o disponibilidad.",
        "contenido": "Mostrar que el contenido actual puede entretener o informar, pero no necesariamente vender.",
        "awareness": "Mostrar que sin presencia mental suficiente, cada acción comercial empieza desde cero."
    }

    return angles.get(
        primary_bottleneck,
        "Mostrar una brecha comercial concreta sin entregar todavía la solución completa."
    )


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


# =========================
# ENDPOINTS DE AUDITORÍA
# =========================

@app.post(
    "/audit/prospect",
    response_model=ProspectAuditResponse,
    operation_id="auditProspect",
    summary="Audit a marketing prospect",
    description="Recibe datos básicos de un prospecto y devuelve focos de auditoría comercial.",
    dependencies=[Security(verify_api_key)]
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
        next_step=(
            "Preparar un diagnóstico comercial breve que muestre la brecha principal y proponga "
            "una reunión para profundizar la solución."
        ),
        do_not_give_for_free=[
            "calendario completo de contenido",
            "reescritura integral de la propuesta de valor",
            "estructura completa de campañas",
            "arquitectura completa de funnel",
            "segmentaciones detalladas de pauta",
            "copys finales listos para implementar"
        ],
        confidence=infer_confidence(request)
    )


@app.post(
    "/report/brief",
    response_model=ReportBriefResponse,
    operation_id="createReportBrief",
    summary="Create a commercial audit report brief",
    description="Genera una estructura breve de reporte comercial a partir de hallazgos de auditoría.",
    dependencies=[Security(verify_api_key)]
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
            "Próximo paso recomendado"
        ],
        opening_angle=(
            f"La presentación debería abrir mostrando cómo {request.company_name} puede estar "
            f"perdiendo oportunidades por un problema de {bottleneck}."
        ),
        recommended_close=(
            "Cerrar con una invitación a revisar el caso en una reunión breve, sin entregar todavía "
            "la estrategia completa."
        ),
        do_not_include=[
            "plan completo de contenidos",
            "estructura completa de campañas",
            "copys finales",
            "segmentaciones detalladas",
            "presupuesto táctico completo",
            "implementación paso a paso"
        ]
    )


# =========================
# ENDPOINTS DE COMPOSIO / TOOLS
# =========================

@app.get(
    "/tools/status",
    response_model=ToolsStatusResponse,
    operation_id="getToolsStatus",
    summary="Check available Composio toolkits",
    description="Verifica si Composio está configurado y revisa herramientas disponibles para toolkits relevantes.",
    dependencies=[Security(verify_api_key)]
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
        "google_drive"
    ]

    if not COMPOSIO_API_KEY:
        return ToolsStatusResponse(
            composio_configured=False,
            checked_toolkits=[],
            recommendation=(
                "COMPOSIO_API_KEY no está configurada. Agregala como variable de entorno antes "
                "de usar herramientas externas."
            )
        )

    checked = []

    for toolkit in toolkits_to_check:
        try:
            data = composio_get(
                "/tools",
                params={
                    "toolkit_slug": toolkit,
                    "limit": 20
                }
            )

            tools = extract_tools_list(data)
            sample_tools = []

            for tool in tools[:5]:
                normalized = normalize_tool(tool)
                sample_tools.append(normalized.slug)

            checked.append(
                ToolkitStatus(
                    toolkit=toolkit,
                    available=len(tools) > 0,
                    tool_count=len(tools),
                    sample_tools=sample_tools
                )
            )

        except Exception as exc:
            checked.append(
                ToolkitStatus(
                    toolkit=toolkit,
                    available=False,
                    tool_count=0,
                    sample_tools=[],
                    error=str(exc)
                )
            )

    essential = ["search_api", "browser_tool", "apify"]
    available_essential = [
        item.toolkit for item in checked
        if item.toolkit in essential and item.available
    ]

    if len(available_essential) == len(essential):
        recommendation = (
            "Herramientas esenciales disponibles. Se puede avanzar a búsqueda pública, "
            "validación de páginas y scraping controlado."
        )
    elif available_essential:
        recommendation = (
            "Hay algunas herramientas esenciales disponibles, pero conviene conectar o verificar "
            "las faltantes antes de una auditoría completa."
        )
    else:
        recommendation = (
            "No se detectaron herramientas esenciales. Primero conectá o verificá Search API, "
            "Browser Tool o Apify."
        )

    return ToolsStatusResponse(
        composio_configured=True,
        checked_toolkits=checked,
        recommendation=recommendation
    )


@app.post(
    "/tools/search",
    response_model=ToolsSearchResponse,
    operation_id="searchComposioTools",
    summary="Search Composio tools",
    description="Busca herramientas disponibles en Composio usando texto libre y, opcionalmente, un toolkit específico.",
    dependencies=[Security(verify_api_key)]
)
def search_composio_tools(request: ToolsSearchRequest):
    params = {
        "limit": 100
    }

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
        results=matches[:request.limit]
    )


@app.get(
    "/tools/details/{tool_slug}",
    response_model=ToolDetailsResponse,
    operation_id="getComposioToolDetails",
    summary="Get Composio tool details",
    description="Obtiene detalles y schema de una herramienta específica de Composio.",
    dependencies=[Security(verify_api_key)]
)
def get_composio_tool_details(tool_slug: str):
    data = composio_get(f"/tools/{tool_slug}")

    if not isinstance(data, dict):
        data = {"response": data}

    return ToolDetailsResponse(
        tool_slug=tool_slug,
        raw_response=data
    )


@app.post(
    "/tools/execute",
    response_model=ToolExecuteResponse,
    operation_id="executeComposioTool",
    summary="Execute an allowed Composio tool",
    description="Ejecuta una herramienta permitida de Composio usando argumentos estructurados o texto en lenguaje natural.",
    dependencies=[Security(verify_api_key)]
)
def execute_composio_tool(request: ToolExecuteRequest):
    if request.tool_slug not in ALLOWED_COMPOSIO_TOOLS:
        raise HTTPException(
            status_code=403,
            detail=(
                f"La herramienta {request.tool_slug} no está permitida todavía. "
                f"Permitidas: {sorted(ALLOWED_COMPOSIO_TOOLS)}"
            )
        )

    if not request.arguments and not request.text:
        raise HTTPException(
            status_code=422,
            detail="Debés enviar arguments o text para ejecutar la herramienta."
        )

    payload = {
        "user_id": request.user_id,
        "version": "latest"
    }

    if request.arguments:
        payload["arguments"] = request.arguments
    else:
        payload["text"] = request.text

    data = composio_post(
        f"/tools/execute/{request.tool_slug}",
        payload=payload
    )

    if not isinstance(data, dict):
        data = {"response": data}

    return ToolExecuteResponse(
        tool_slug=request.tool_slug,
        successful=data.get("successful"),
        data=data.get("data"),
        error=data.get("error"),
        raw_response=data
    )