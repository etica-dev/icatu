import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.automation_service import IcatuAutomationService
from src.bitrix_requests import upload_validation_result
from src.validador import ValidadorService


HOST = os.getenv("BOT_HOST", "0.0.0.0")
PORT = int(os.getenv("BOT_PORT", "5000"))
WEBHOOK_TOKEN = os.getenv("BOT_WEBHOOK_TOKEN", "")
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Icatu Bot", version="0.1.0")
service = IcatuAutomationService()
validador_service = ValidadorService(work_dir=DOWNLOADS_DIR / "validador")


class IcatuPayload(BaseModel):
    card_id: str
    mission: str
    overrides: dict | None = None
    token: str | None = None


class CardLoadPayload(BaseModel):
    card_id: str
    token: str | None = None


class ValidadorPayload(BaseModel):
    card_id: str
    pdf_url: str | None = None
    pdf_base64: str | None = None
    result_field: str | None = None
    token: str | None = None


def _check_token(token: str):
    if WEBHOOK_TOKEN and token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="invalid_token")


def _file_url(request: Request, file_path: str) -> str:
    relative = Path(file_path).relative_to(DOWNLOADS_DIR)
    base = str(request.base_url).rstrip("/")
    return f"{base}/files/{relative.as_posix()}"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/files/{filename:path}")
def serve_file(filename: str):
    file_path = DOWNLOADS_DIR / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="file_not_found")
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=file_path.name,
    )


@app.post("/cards/load")
def load_card(
    payload: CardLoadPayload,
    x_webhook_token: str | None = Header(default=None),
):
    _check_token(x_webhook_token or payload.token or "")
    card_id = payload.card_id.strip()
    if not card_id:
        raise HTTPException(status_code=400, detail="card_id_is_required")
    try:
        return service.load_card_data(card_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/webhooks/icatu")
def run_icatu(
    request: Request,
    payload: IcatuPayload,
    x_webhook_token: str | None = Header(default=None),
):
    _check_token(x_webhook_token or payload.token or "")
    card_id = payload.card_id.strip()
    mission = payload.mission.strip()
    if not card_id or not mission:
        raise HTTPException(status_code=400, detail="card_id_and_mission_are_required")

    print(f"[icatu] Requisição recebida — card_id={card_id} mission={mission}", flush=True)
    events: list[str] = []
    result = service.run_card(
        card_id,
        mission,
        overrides=payload.overrides or {},
        log_callback=events.append,
    )

    file_url = None
    if result.file_path and os.path.isfile(result.file_path):
        file_url = _file_url(request, result.file_path)

    return {
        "success": result.success,
        "card_id": result.card_id,
        "mission": result.mission,
        "status": result.status,
        "message": result.message,
        "file_url": file_url,
        "events": events,
    }


@app.post("/webhooks/validador")
def run_validador(
    request: Request,
    payload: ValidadorPayload,
    x_webhook_token: str | None = Header(default=None),
):
    _check_token(x_webhook_token or payload.token or "")
    card_id = payload.card_id.strip()
    pdf_url = (payload.pdf_url or "").strip() or None
    pdf_base64 = (payload.pdf_base64 or "").strip() or None
    result_field = (payload.result_field or "").strip() or os.getenv("BITRIX_VALIDATION_FIELD", "")
    if not card_id or (not pdf_url and not pdf_base64):
        raise HTTPException(status_code=400, detail="card_id e pdf_url (ou pdf_base64) sao obrigatorios")

    print(f"[validador] Requisição recebida — card_id={card_id}", flush=True)
    events: list[str] = []
    try:
        result = validador_service.run(
            card_id, pdf_url=pdf_url, pdf_base64=pdf_base64, log_callback=events.append
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    file_url = None
    bitrix_upload = None
    validation_path = result.get("validation_pdf_path")

    if validation_path and os.path.isfile(validation_path):
        file_url = _file_url(request, validation_path)

        if result_field:
            print(f"[validador] Enviando comprovante para Bitrix24 — deal={card_id} campo={result_field}", flush=True)
            try:
                bitrix_upload = upload_validation_result(
                    deal_id=card_id,
                    field_name=result_field,
                    pdf_path=validation_path,
                )
                events.append(f"Comprovante enviado ao Bitrix24 campo {result_field}: status {bitrix_upload.get('status_code')}")
            except Exception as exc:
                events.append(f"Aviso: falha ao enviar comprovante ao Bitrix24 — {exc}")
                print(f"[validador] Falha upload Bitrix24: {exc}", flush=True)

    return {
        "success": result.get("success", False),
        "card_id": card_id,
        "message": result.get("message", ""),
        "file_url": file_url,
        "bitrix_upload": bitrix_upload,
        "events": events,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
