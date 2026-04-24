# ICATU — API de Automação

Backend FastAPI para automação do processo de **Garantia de Aluguel** no portal Icatu, com integração ao CRM Bitrix24 e webscraping via Playwright.

## Estrutura

```
server.py                  # Entry point FastAPI
src/
  automation_service.py    # Orquestrador de jobs Icatu
  auto_icatu.py            # Integração CRM → portal Icatu
  icatu_portal.py          # Playwright: login, formulários, downloads
  icatu_data.py            # Transformação de dados do Bitrix24
  bitrix_requests.py       # Cliente REST Bitrix24 (deals, timeline, uploads)
  validador.py             # Validação de assinaturas PDF via portal ITI
  token_store.py           # Tokens de acesso multi-usuário com expiração
  logger.py                # Logging estruturado
data/
  tokens.json              # Tokens persistidos
downloads/validador/       # PDFs temporários de validação
business_card_data.csv     # Cache de dados do deal
```

## Iniciar

```bash
python server.py
```

API disponível em `http://0.0.0.0:5000` — documentação em `/docs`.

## Secrets necessários

| Variável | Uso |
|----------|-----|
| `ADMIN_TOKEN` | Gerenciar tokens de usuário |
| `BITRIX_LOGIN` | Login Bitrix24 (download de arquivos via Playwright) |
| `BITRIX_SENHA` | Senha Bitrix24 |
| `BITRIX_VALIDATION_FIELD` | (opcional) Campo UF padrão para comprovantes |

## Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Health check |
| POST | `/cards/load` | Carrega dados do deal do Bitrix24 |
| POST | `/webhooks/icatu` | Dispara automação Icatu (verify/run) |
| POST | `/webhooks/validador` | Valida assinatura PDF e salva no Bitrix24 |
| POST | `/tokens/` | (admin) Cria token de usuário |
| GET | `/tokens/` | (admin) Lista tokens |
| DELETE | `/tokens/{username}` | (admin) Revoga token |
