import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from src.automation_service import IcatuAutomationService
from src.bitrix_requests import upload_validation_result
from src import token_store
from src.validador import ValidadorService


HOST = os.getenv("BOT_HOST", "0.0.0.0")
PORT = int(os.getenv("BOT_PORT", "5000"))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

_DESCRIPTION = """
## Icatu Bot API

Automação de processos do portal Icatu Seguros integrada ao Bitrix24.

---

### Autenticação

Todos os endpoints (exceto `/health`) exigem um **token de acesso** válido,
vinculado a um nome de usuário e gerenciado pelo administrador.

O token pode ser enviado de duas formas:

1. **Header HTTP** (recomendado):
```
X-Webhook-Token: <seu-token>
```

2. **Campo no corpo JSON**:
```json
{ "token": "<seu-token>", ... }
```

Sem token válido a API retorna **401 Unauthorized**.

---

### Endpoints disponíveis

| Endpoint | Método | Descrição |
|---|---|---|
| `/health` | GET | Status da API |
| `/cards/load` | POST | Carregar dados de um card do Bitrix24 |
| `/webhooks/icatu` | POST | Executar automação no portal Icatu |
| `/webhooks/validador` | POST | Validar assinatura de PDF e salvar comprovante no Bitrix24 |
"""

app = FastAPI(
    title="Icatu Bot API",
    version="1.0.0",
    description=_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
)

service = IcatuAutomationService()
validador_service = ValidadorService(work_dir=DOWNLOADS_DIR / "validador")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TokenCreatePayload(BaseModel):
    username: str = Field(
        ...,
        description="Nome de identificação do usuário (ex: 'joao', 'sistema_bitrix').",
        examples=["joao"],
    )
    admin_token: str | None = Field(
        default=None,
        description="ADMIN_TOKEN de autorização. Alternativa ao header X-Admin-Token.",
    )


class IcatuPayload(BaseModel):
    card_id: str = Field(..., description="ID do card no Bitrix24.", examples=["27505"])
    mission: str = Field(
        ...,
        description="Missão a executar no portal Icatu.",
        examples=["garantia_aluguel"],
    )
    overrides: dict | None = Field(
        default=None,
        description="Campos opcionais para sobrescrever dados do card.",
    )
    token: str | None = Field(
        default=None,
        description="Token de acesso. Alternativa ao header X-Webhook-Token.",
    )


class CardLoadPayload(BaseModel):
    card_id: str = Field(..., description="ID do card no Bitrix24.", examples=["27505"])
    token: str | None = Field(
        default=None,
        description="Token de acesso. Alternativa ao header X-Webhook-Token.",
    )


class ValidadorPayload(BaseModel):
    card_id: str = Field(..., description="ID do card / deal no Bitrix24.", examples=["27505"])
    pdf_url: str | None = Field(
        default=None,
        description="URL do PDF a validar (suporta URLs autenticadas do Bitrix24).",
    )
    pdf_base64: str | None = Field(
        default=None,
        description="Conteúdo do PDF codificado em Base64, como alternativa a `pdf_url`.",
    )
    result_field: str | None = Field(
        default=None,
        description=(
            "Nome do campo UF no deal Bitrix24 onde o comprovante de validação será salvo. "
            "Ex: `UF_CRM_1741981593`. Se omitido, usa a variável de ambiente BITRIX_VALIDATION_FIELD."
        ),
        examples=["UF_CRM_1741981593"],
    )
    token: str | None = Field(
        default=None,
        description="Token de acesso. Alternativa ao header X-Webhook-Token.",
    )


# ---------------------------------------------------------------------------
# Helpers de autenticação
# ---------------------------------------------------------------------------

def _require_admin(header_token: str | None, body_token: str | None) -> None:
    """Valida ADMIN_TOKEN. Levanta 401 se inválido."""
    provided = header_token or body_token or ""
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_TOKEN não configurado no servidor. Defina a variável de ambiente ADMIN_TOKEN.",
        )
    if not provided or provided != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="admin_token_invalido")


def _require_token(header_token: str | None, body_token: str | None) -> str:
    """Valida token de acesso contra o repositório de tokens. Retorna o username."""
    provided = (header_token or body_token or "").strip()
    username = token_store.validate_token(provided)
    if username is None:
        raise HTTPException(
            status_code=401,
            detail="Token inválido ou não autorizado. Solicite um token ao administrador.",
        )
    return username


# ---------------------------------------------------------------------------
# Sistema
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    tags=["Sistema"],
    summary="Status da API",
    response_description="Retorna `ok` se o servidor está funcionando.",
)
def health():
    """Verifica se a API está respondendo. Não requer autenticação."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Gerenciamento de tokens — ocultos do Swagger (requerem ADMIN_TOKEN)
# ---------------------------------------------------------------------------

@app.post("/tokens/", include_in_schema=False, status_code=201)
def create_token(
    payload: TokenCreatePayload,
    x_admin_token: str | None = Header(default=None),
):
    _require_admin(x_admin_token, payload.admin_token)
    try:
        token = token_store.create_token(payload.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "username": payload.username.strip().lower(),
        "token": token,
        "message": "Token criado com sucesso. Guarde-o em local seguro.",
    }


@app.get("/tokens/", include_in_schema=False)
def list_tokens(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token, None)
    tokens = token_store.list_tokens()
    return {
        "count": len(tokens),
        "tokens": [{"username": u, "token": t} for u, t in tokens.items()],
    }


@app.delete("/tokens/{username}", include_in_schema=False)
def delete_token(
    username: str,
    x_admin_token: str | None = Header(default=None),
):
    _require_admin(x_admin_token, None)
    removed = token_store.revoke_token(username)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Usuário '{username}' não encontrado.")
    return {"message": f"Token do usuário '{username}' revogado com sucesso."}


# ---------------------------------------------------------------------------
# Endpoints de automação (requerem token de usuário)
# ---------------------------------------------------------------------------

@app.post(
    "/cards/load",
    tags=["Automação"],
    summary="Carregar dados de um card do Bitrix24",
)
def load_card(
    payload: CardLoadPayload,
    x_webhook_token: str | None = Header(default=None),
):
    """
    Busca e retorna os dados estruturados de um deal/card no Bitrix24.

    Requer **token de usuário** via header `X-Webhook-Token` ou campo `token` no corpo.

    **Exemplo de uso:**
    ```
    POST /cards/load
    X-Webhook-Token: <token>

    { "card_id": "27505" }
    ```
    """
    username = _require_token(x_webhook_token, payload.token)
    print(f"[cards/load] Usuário: {username} | card_id={payload.card_id}", flush=True)
    card_id = payload.card_id.strip()
    if not card_id:
        raise HTTPException(status_code=400, detail="card_id é obrigatório.")
    try:
        return service.load_card_data(card_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post(
    "/webhooks/icatu",
    tags=["Automação"],
    summary="Executar automação no portal Icatu",
)
def run_icatu(
    payload: IcatuPayload,
    x_webhook_token: str | None = Header(default=None),
):
    """
    Executa automação no portal Icatu Seguros para o card informado.

    Requer **token de usuário** via header `X-Webhook-Token` ou campo `token` no corpo.

    **Exemplo de uso:**
    ```
    POST /webhooks/icatu
    X-Webhook-Token: <token>

    {
      "card_id": "27505",
      "mission": "garantia_aluguel"
    }
    ```

    **Resposta de sucesso:**
    ```json
    {
      "success": true,
      "card_id": "27505",
      "mission": "garantia_aluguel",
      "status": "completed",
      "message": "...",
      "events": ["Abrindo portal...", "..."]
    }
    ```
    """
    username = _require_token(x_webhook_token, payload.token)
    card_id = payload.card_id.strip()
    mission = payload.mission.strip()
    if not card_id or not mission:
        raise HTTPException(status_code=400, detail="card_id e mission são obrigatórios.")

    print(f"[icatu] Usuário: {username} | card_id={card_id} mission={mission}", flush=True)
    events: list[str] = []
    result = service.run_card(
        card_id,
        mission,
        overrides=payload.overrides or {},
        log_callback=events.append,
    )

    return {
        "success": result.success,
        "card_id": result.card_id,
        "mission": result.mission,
        "status": result.status,
        "message": result.message,
        "events": events,
    }


@app.post(
    "/webhooks/validador",
    tags=["Automação"],
    summary="Validar assinatura de PDF",
)
def run_validador(
    payload: ValidadorPayload,
    x_webhook_token: str | None = Header(default=None),
):
    """
    Envia um PDF ao validador de assinaturas da Icatu e salva o comprovante de validação no Bitrix24.

    O PDF pode ser fornecido via `pdf_url` (incluindo URLs autenticadas do Bitrix24)
    ou diretamente em `pdf_base64`.

    Se `result_field` for informado, o comprovante validado é salvo automaticamente
    no campo UF do deal no Bitrix24 via `crm.deal.update`.

    Requer **token de usuário** via header `X-Webhook-Token` ou campo `token` no corpo.

    **Exemplo de uso:**
    ```
    POST /webhooks/validador
    X-Webhook-Token: <token>

    {
      "card_id": "27505",
      "pdf_url": "https://eticaweb.bitrix24.com.br/.../show_file.php?...",
      "result_field": "UF_CRM_1741981593"
    }
    ```

    **Resposta de sucesso:**
    ```json
    {
      "success": true,
      "card_id": "27505",
      "message": "Validacao concluida com sucesso.",
      "bitrix_upload": { "success": true, "status_code": 200, "response": { "result": true } },
      "events": ["Baixando PDF...", "...", "Comprovante salvo no Bitrix24..."]
    }
    ```
    """
    username = _require_token(x_webhook_token, payload.token)
    card_id = payload.card_id.strip()
    pdf_url = (payload.pdf_url or "").strip() or None
    pdf_base64 = (payload.pdf_base64 or "").strip() or None
    result_field = (payload.result_field or "").strip() or os.getenv("BITRIX_VALIDATION_FIELD", "")

    if not card_id or (not pdf_url and not pdf_base64):
        raise HTTPException(
            status_code=400,
            detail="card_id e pdf_url (ou pdf_base64) são obrigatórios.",
        )

    print(f"[validador] Usuário: {username} | card_id={card_id}", flush=True)
    events: list[str] = []
    try:
        result = validador_service.run(
            card_id, pdf_url=pdf_url, pdf_base64=pdf_base64, log_callback=events.append
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    bitrix_upload = None
    validation_path = result.get("validation_pdf_path")

    if validation_path and os.path.isfile(validation_path) and result_field:
        print(
            f"[validador] Enviando comprovante — deal={card_id} campo={result_field}",
            flush=True,
        )
        try:
            bitrix_upload = upload_validation_result(
                deal_id=card_id,
                field_name=result_field,
                pdf_path=validation_path,
            )
            uploaded_ok = bitrix_upload.get("success", False)
            events.append(
                f"Comprovante {'salvo' if uploaded_ok else 'ERRO ao salvar'} no Bitrix24 "
                f"campo {result_field} (HTTP {bitrix_upload.get('status_code')})"
            )
        except Exception as exc:
            events.append(f"Aviso: falha ao enviar comprovante ao Bitrix24 — {exc}")
            print(f"[validador] Falha upload Bitrix24: {exc}", flush=True)

    return {
        "success": result.get("success", False),
        "card_id": card_id,
        "message": result.get("message", ""),
        "bitrix_upload": bitrix_upload,
        "events": events,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
