# ICATU Bot

## Overview
ICATU é um backend de automação em FastAPI para o processo de "Garantia de Aluguel" do portal Icatu. Integra com o CRM Bitrix24, usa Playwright para automação de browser/webscraping, e expõe uma API REST rodando no Replit.

## Arquitetura

- **server.py** – Aplicação FastAPI; entry point, roteamento, middleware de segurança e logging
- **src/automation_service.py** – Orquestrador de alto nível para jobs de automação Icatu
- **src/auto_icatu.py** – Ponte entre dados do CRM e automação do portal Icatu
- **src/icatu_portal.py** – Interações Playwright com o portal Icatu (login, preenchimento de formulário, downloads)
- **src/icatu_data.py** – Transformação e limpeza de dados vindos do Bitrix24
- **src/bitrix_requests.py** – Cliente da API REST do Bitrix24 (deals, timeline, upload de arquivos)
- **src/validador.py** – Validação de assinaturas PDF via portal ITI (validar.iti.gov.br)
- **src/token_store.py** – Gerenciamento de tokens de acesso (multi-usuário, expiração, persistência em data/tokens.json)
- **src/logger.py** – Logging estruturado padronizado (formato: `YYYY-MM-DD HH:MM:SS [LEVEL] módulo — chave=valor`)
- **business_card_data.csv** – Cache local de dados do deal gerado pelo fluxo Icatu
- **downloads/validador/** – PDFs temporários usados durante a validação (entrada e comprovante)

## Executando

O servidor inicia via workflow **Start application**:
```
python server.py
```
Escuta em `0.0.0.0:5000` (configurável via `BOT_HOST` / `BOT_PORT`).

## Segurança

- **Tokens por usuário** – Cada consumidor tem seu próprio token com metadados (criação, expiração)
- **Rate limiting** – 30 req/60s por token (configurável via `RATE_LIMIT_MAX` / `RATE_LIMIT_WINDOW`)
- **Request ID** – UUID por requisição, retornado no header `X-Request-ID` e no body `request_id`
- **Endpoints admin** – Gerenciamento de tokens via `ADMIN_TOKEN`, ocultos do Swagger

## Variáveis de Ambiente (Secrets)

- `ADMIN_TOKEN` – Token de administração para gerenciar tokens de usuário
- `BITRIX_LOGIN` / `BITRIX_SENHA` – Credenciais do Bitrix24 para download de arquivos via Playwright
- `BITRIX_VALIDATION_FIELD` – (opcional) Campo UF padrão para salvar comprovantes de validação
- `RATE_LIMIT_MAX` – (opcional) Máximo de requisições por janela (default: 30)
- `RATE_LIMIT_WINDOW` – (opcional) Janela de rate limit em segundos (default: 60)

## Dependências Principais

- Python 3.12
- fastapi, uvicorn, pydantic
- playwright (automação de browser)
- requests, python-dotenv

## Endpoints Principais

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Health check |
| POST | `/cards/load` | Carrega dados do deal do Bitrix24 |
| POST | `/webhooks/icatu` | Dispara automação Icatu (verify/run) |
| POST | `/webhooks/validador` | Valida assinatura de PDF e salva comprovante no Bitrix24 |
| POST | `/tokens/` | (admin) Cria token de usuário |
| GET | `/tokens/` | (admin) Lista tokens com metadados |
| DELETE | `/tokens/{username}` | (admin) Revoga token |

## Comentários na Timeline Bitrix24

O endpoint `/webhooks/validador` posta automaticamente 2 comentários BBCode na timeline do deal:
1. **Início** – ao receber a requisição
2. **Conclusão** – sucesso (verde), falha de validação (vermelho) ou erro interno (vermelho)
