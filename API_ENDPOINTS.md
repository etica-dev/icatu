# Endpoints Da API

Este arquivo centraliza os endpoints disponiveis no projeto e exemplos de como acessa-los.

## Autenticacao

Quando `BOT_WEBHOOK_TOKEN` estiver configurado no ambiente, os endpoints protegidos exigem o token:

- no header `X-Webhook-Token`
- ou no campo `token` do JSON

Exemplo de header:

```http
X-Webhook-Token: seu_token
```

## 1. Health Check

### `GET /health`

Verifica se a API esta online.

Resposta:

```json
{
  "status": "ok"
}
```

Exemplo:

```bash
curl http://127.0.0.1:8000/health
```

## 2. Consultar Job

### `GET /jobs/{job_id}`

Retorna o status do job e o historico de eventos.

Exemplo:

```bash
curl http://127.0.0.1:8000/jobs/SEU_JOB_ID
```

Resposta exemplo:

```json
{
  "job_id": "uuid",
  "card_id": "12345",
  "mission": "run",
  "status": "running",
  "result": null,
  "events": [
    "Job recebido",
    "Iniciando processamento"
  ],
  "last_event": "Iniciando processamento"
}
```

## 3. Carregar Dados Do Card

### `POST /cards/load`

Carrega os dados do card para revisao na interface PyQt.

Payload:

```json
{
  "card_id": "12345",
  "token": "seu_token"
}
```

Exemplo:

```bash
curl -X POST http://127.0.0.1:8000/cards/load \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: seu_token" \
  -d "{\"card_id\":\"12345\"}"
```

## 4. Criar Job De Processamento

### `POST /jobs`

Cria um job com os dados ja revisados no app.

Payload:

```json
{
  "card_id": "12345",
  "mission": "run",
  "token": "seu_token",
  "overrides": {
    "dados_locatario": {},
    "dados_locador": {}
  }
}
```

Exemplo:

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: seu_token" \
  -d "{\"card_id\":\"12345\",\"mission\":\"run\",\"overrides\":{\"dados_locatario\":{},\"dados_locador\":{}}}"
```

## 5. Webhook Bitrix

### `POST /webhooks/bitrix`

Permite disparar o fluxo principal por webhook, sem passar pela interface.

Payload:

```json
{
  "card_id": "12345",
  "mission": "verify",
  "token": "seu_token"
}
```

Exemplo:

```bash
curl -X POST http://127.0.0.1:8000/webhooks/bitrix \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: seu_token" \
  -d "{\"card_id\":\"12345\",\"mission\":\"verify\"}"
```

## 6. Webhook Validador

### `POST /webhooks/validador`

Recebe o ID do card e um link publico de download do PDF. A API:

1. cria um job
2. baixa o PDF
3. acessa `https://validar.iti.gov.br/`
4. envia o arquivo para validacao
5. baixa o comprovante da validacao

Payload:

```json
{
  "card_id": "12345",
  "pdf_url": "https://exemplo.com/arquivo.pdf",
  "token": "seu_token"
}
```

Exemplo:

```bash
curl -X POST http://127.0.0.1:8000/webhooks/validador \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: seu_token" \
  -d "{\"card_id\":\"12345\",\"pdf_url\":\"https://exemplo.com/arquivo.pdf\"}"
```

Resposta:

```json
{
  "job_id": "uuid",
  "status": "queued",
  "card_id": "12345",
  "mission": "validador",
  "pdf_url": "https://exemplo.com/arquivo.pdf"
}
```

## Fluxo Recomendado Para O Bitrix

### Emissao Ou Verificacao

1. Bitrix chama `POST /webhooks/bitrix`
2. API retorna `job_id`
3. acompanhamento em `GET /jobs/{job_id}`

### Validacao De PDF

1. Bitrix chama `POST /webhooks/validador`
2. API retorna `job_id`
3. acompanhamento em `GET /jobs/{job_id}`

## Observacoes

- O webhook do validador exige que `pdf_url` seja um link publico e acessivel pelo servidor.
- Os arquivos de entrada e saida da validacao sao salvos em `data/validador/`.
- O endpoint `GET /jobs/{job_id}` e o lugar certo para acompanhar o andamento de qualquer processamento em background.
