# ICATU Bot

## Overview
ICATU is a FastAPI-based automation backend that streamlines the "Garantia de Aluguel" (Rental Guarantee) process on the Icatu insurance portal. It integrates with the Bitrix24 CRM, uses Playwright for browser automation, and exposes a REST API for job orchestration.

## Architecture

- **server.py** – FastAPI application entry point; manages background job threads
- **src/automation_service.py** – High-level orchestrator for automation jobs
- **src/auto_icatu.py** – Bridge between CRM data and portal automation
- **src/icatu_portal.py** – Playwright-based Icatu portal interactions (login, form fill, downloads)
- **src/bitrix_requests.py** – Bitrix24 CRM API client
- **src/icatu_data.py** – Data transformation and cleaning
- **src/validador.py** – PDF validation via the ITI portal
- **pyqt_app.py** – Desktop GUI (PyQt6) for analyst review (Windows only)
- **main.py** – CLI entry point for manual testing
- **data/** – CSV lookup files for data mapping

## Running

The server starts via:
```
python server.py
```
It listens on `127.0.0.1:8000` by default (configurable via `BOT_HOST` / `BOT_PORT` env vars).

## Environment Variables

Copy `.env.example` to `.env` and fill in:
- `LOGIN` / `SENHA` – Icatu portal credentials
- `api_key` – Vista CRM API key
- `BOT_HOST` / `BOT_PORT` – Server bind address (default: 127.0.0.1:8000)
- `BOT_SERVER_URL` – Server URL for internal use
- `BOT_WEBHOOK_TOKEN` – Shared secret for webhook authentication
- `BITRIX_STATUS_FIELD` / `BITRIX_MESSAGE_FIELD` / `BITRIX_FILE_FIELD` – Bitrix24 field IDs

## Dependencies

- Python 3.12
- fastapi, uvicorn, pydantic
- playwright (browser automation)
- pandas (data processing)
- python-dotenv, requests
- PyQt6 (desktop GUI, Windows distribution only)

## Workflow

**Start application** – Runs `python server.py` on port 8000 (console output)

## Key API Endpoints

- `GET /health` – Health check
- `GET /jobs/{job_id}` – Get job status and events
- `POST /cards/load` – Load card data from Bitrix24
- `POST /webhooks/bitrix` – Receive webhook from Bitrix24 to queue a job
- `POST /webhooks/validador` – Queue a PDF validation job
- `POST /jobs` – Create a job with optional field overrides
