import os

from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional, List


app = FastAPI(
    title="Marketing Audit API",
    description="API para auditar prospectos y devolver información estructurada a un Custom GPT.",
    version="1.0.0"
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
    notes: Optional[str] = Field(None, description="Notas adicionales sobre el prospecto")


class ProspectAuditResponse(BaseModel):
    company_name: str
    audit_type: str
    detected_focus_areas: List[str]
    commercial_risk: str
    next_step: str


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Marketing Audit API funcionando"
    }


@app.post(
    "/audit/prospect",
    response_model=ProspectAuditResponse,
    operation_id="auditProspect",
    summary="Audit a marketing prospect",
    description="Recibe datos básicos de un prospecto y devuelve focos de auditoría comercial.",
    dependencies=[Security(verify_api_key)]
)
def audit_prospect(request: ProspectAuditRequest):
    focus_areas = [
        "awareness",
        "propuesta de valor",
        "contenido",
        "funnel",
        "conversión"
    ]

    return ProspectAuditResponse(
        company_name=request.company_name,
        audit_type="basic_prospect_audit",
        detected_focus_areas=focus_areas,
        commercial_risk="El prospecto puede estar generando visibilidad sin convertirla en demanda calificada.",
        next_step="Generar un diagnóstico comercial breve sin entregar una consultoría completa gratis."
    )