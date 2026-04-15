import os
import threading
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.automation_service import IcatuAutomationService
from src.validador import ValidadorService


HOST = os.getenv("BOT_HOST", "0.0.0.0")
PORT = int(os.getenv("BOT_PORT", "5000"))
WEBHOOK_TOKEN = os.getenv("BOT_WEBHOOK_TOKEN", "")

app = FastAPI(title="Icatu Bot", version="0.1.0")
service = IcatuAutomationService()
validador_service = ValidadorService()
jobs = {}
jobs_lock = threading.Lock()


class WebhookPayload(BaseModel):
    card_id: str
    mission: str
    token: str | None = None


class ProcessPayload(WebhookPayload):
    overrides: dict | None = None


class CardLoadPayload(BaseModel):
    card_id: str
    token: str | None = None


class ValidadorPayload(BaseModel):
    card_id: str
    pdf_url: str
    token: str | None = None


def update_job(job_id, **fields):
    with jobs_lock:
        jobs[job_id].update(fields)


def append_job_event(job_id, message: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job.setdefault("events", []).append(message)
        job["last_event"] = message


def run_job(job_id, card_id, mission):
    update_job(job_id, status="running")
    append_job_event(job_id, "Iniciando processamento")
    result = service.run_card(
        card_id, mission, log_callback=lambda message: append_job_event(job_id, message)
    )
    update_job(
        job_id,
        status="finished" if result.success else "failed",
        result=result.to_dict(),
    )


def run_job_with_overrides(job_id, card_id, mission, overrides):
    update_job(job_id, status="running")
    append_job_event(job_id, "Iniciando processamento")
    result = service.run_card(
        card_id,
        mission,
        overrides=overrides,
        log_callback=lambda message: append_job_event(job_id, message),
    )
    update_job(
        job_id,
        status="finished" if result.success else "failed",
        result=result.to_dict(),
    )


def run_validador_job(job_id, card_id, pdf_url):
    update_job(job_id, status="running")
    append_job_event(job_id, "Iniciando validacao do PDF")
    try:
        result = validador_service.run(
            card_id,
            pdf_url,
            log_callback=lambda message: append_job_event(job_id, message),
        )
        update_job(
            job_id,
            status="finished",
            result=result,
        )
    except Exception as exc:
        append_job_event(job_id, f"Erro na validacao: {exc}")
        update_job(
            job_id,
            status="failed",
            result={
                "success": False,
                "card_id": card_id,
                "pdf_url": pdf_url,
                "message": str(exc),
            },
        )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job


@app.get("/jobs/{job_id}/file")
def get_job_file(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    result = job.get("result") or {}
    file_path = result.get("file_path") or result.get("validation_pdf_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="no_file_for_this_job")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="file_not_found_on_disk")
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=os.path.basename(file_path),
    )


@app.post("/cards/load")
def load_card(
    payload: CardLoadPayload,
    x_webhook_token: str | None = Header(default=None),
):
    token = x_webhook_token or payload.token or ""
    if WEBHOOK_TOKEN and token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="invalid_token")

    card_id = payload.card_id.strip()
    if not card_id:
        raise HTTPException(status_code=400, detail="card_id_is_required")

    try:
        return service.load_card_data(card_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/webhooks/validador", status_code=202)
def receive_validador_webhook(
    payload: ValidadorPayload,
    x_webhook_token: str | None = Header(default=None),
):
    token = x_webhook_token or payload.token or ""
    if WEBHOOK_TOKEN and token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="invalid_token")

    card_id = payload.card_id.strip()
    pdf_url = payload.pdf_url.strip()
    if not card_id or not pdf_url:
        raise HTTPException(status_code=400, detail="card_id_and_pdf_url_are_required")

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "card_id": card_id,
            "mission": "validador",
            "status": "queued",
            "result": None,
            "events": ["Job recebido"],
            "last_event": "Job recebido",
        }

    thread = threading.Thread(
        target=run_validador_job,
        args=(job_id, card_id, pdf_url),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_id,
        "status": "queued",
        "card_id": card_id,
        "mission": "validador",
        "pdf_url": pdf_url,
    }


@app.post("/webhooks/bitrix", status_code=202)
def receive_bitrix_webhook(
    payload: WebhookPayload,
    x_webhook_token: str | None = Header(default=None),
):
    token = x_webhook_token or payload.token or ""
    if WEBHOOK_TOKEN and token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="invalid_token")

    card_id = payload.card_id.strip()
    mission = payload.mission.strip()
    if not card_id or not mission:
        raise HTTPException(status_code=400, detail="card_id_and_mission_are_required")

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "card_id": card_id,
            "mission": mission,
            "status": "queued",
            "result": None,
            "events": ["Job recebido"],
            "last_event": "Job recebido",
        }

    thread = threading.Thread(
        target=run_job,
        args=(job_id, card_id, mission),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_id,
        "status": "queued",
        "card_id": card_id,
        "mission": mission,
    }


@app.post("/jobs", status_code=202)
def create_job(
    payload: ProcessPayload,
    x_webhook_token: str | None = Header(default=None),
):
    token = x_webhook_token or payload.token or ""
    if WEBHOOK_TOKEN and token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="invalid_token")

    card_id = payload.card_id.strip()
    mission = payload.mission.strip()
    if not card_id or not mission:
        raise HTTPException(status_code=400, detail="card_id_and_mission_are_required")

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "card_id": card_id,
            "mission": mission,
            "status": "queued",
            "result": None,
            "events": ["Job recebido"],
            "last_event": "Job recebido",
        }

    thread = threading.Thread(
        target=run_job_with_overrides,
        args=(job_id, card_id, mission, payload.overrides or {}),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_id,
        "status": "queued",
        "card_id": card_id,
        "mission": mission,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
