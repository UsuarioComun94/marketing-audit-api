import os

from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional, List


app = FastAPI(
    title="Marketing Audit API",
    description="API para auditar prospectos y devolver información estructurada a un Custom GPT.",
    version="1.1.0",
    servers=[
    {
        "url": "https://marketing-audit-api.onrender.com",
        "description": "Render production server"
    }
]
)


API_KEY = os.getenv("API_KEY", "dev-key")


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


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Marketing Audit API funcionando"
    }


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
        "awareness": "La empresa puede tener baja presencia mental en el mercado y depender demasiado de acciones tácticas de corto plazo."
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
        next_step="Preparar un diagnóstico comercial breve que muestre la brecha principal y proponga una reunión para profundizar la solución.",
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
        opening_angle=f"La presentación debería abrir mostrando cómo {request.company_name} puede estar perdiendo oportunidades por un problema de {bottleneck}.",
        recommended_close="Cerrar con una invitación a revisar el caso en una reunión breve, sin entregar todavía la estrategia completa.",
        do_not_include=[
            "plan completo de contenidos",
            "estructura completa de campañas",
            "copys finales",
            "segmentaciones detalladas",
            "presupuesto táctico completo",
            "implementación paso a paso"
        ]
    )