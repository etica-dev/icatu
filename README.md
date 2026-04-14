# ICATU

Sistema de automacao para:

- buscar dados de um card no Bitrix
- permitir revisao humana via app PyQt
- disparar a automacao em uma API FastAPI
- executar scraper com Playwright
- reportar resultado e anexos no Bitrix

## Estrutura

- [server.py](/c:/Users/lucas.sabino/Desktop/dev/icatu/server.py): API FastAPI
- [pyqt_app.py](/c:/Users/lucas.sabino/Desktop/dev/icatu/pyqt_app.py): app desktop da analista
- [main.py](/c:/Users/lucas.sabino/Desktop/dev/icatu/main.py): execucao manual via terminal
- [src/automation_service.py](/c:/Users/lucas.sabino/Desktop/dev/icatu/src/automation_service.py): orquestracao principal
- [src/auto_icatu.py](/c:/Users/lucas.sabino/Desktop/dev/icatu/src/auto_icatu.py): integracao entre dados e portal
- [src/bitrix_requests.py](/c:/Users/lucas.sabino/Desktop/dev/icatu/src/bitrix_requests.py): coleta e retorno no Bitrix
- [src/icatu_data.py](/c:/Users/lucas.sabino/Desktop/dev/icatu/src/icatu_data.py): montagem dos dados do card
- [src/icatu_portal.py](/c:/Users/lucas.sabino/Desktop/dev/icatu/src/icatu_portal.py): automacao Playwright
- [src/validador.py](/c:/Users/lucas.sabino/Desktop/dev/icatu/src/validador.py): validacao de PDF no portal do ITI
- [API_ENDPOINTS.md](/c:/Users/lucas.sabino/Desktop/dev/icatu/API_ENDPOINTS.md): documentacao dos endpoints

## Variaveis de Ambiente

Copie `.env.example` para `.env` e preencha:

```env
LOGIN=seu_login_icatu
SENHA=sua_senha_icatu
api_key=sua_api_key_vista

BOT_HOST=127.0.0.1
BOT_PORT=8000
BOT_SERVER_URL=http://127.0.0.1:8000
BOT_WEBHOOK_TOKEN=troque_este_token

BITRIX_STATUS_FIELD=
BITRIX_MESSAGE_FIELD=
BITRIX_FILE_FIELD=UF_CRM1732291331
```

## Instalacao Local

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
playwright install
```

## Rodando Localmente

### API

```powershell
.\venv\Scripts\activate
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

### App da analista

Em outro terminal:

```powershell
.\venv\Scripts\activate
python pyqt_app.py
```

### Execucao manual

```powershell
.\venv\Scripts\activate
python main.py
```

## Fluxo do App

1. Abrir o app PyQt
2. Ir em `Opcoes > Configuracoes`
3. Informar:
   - servidor
   - token
4. Informar o `ID do card`
5. Clicar em `Carregar Dados`
6. Revisar e editar os campos
7. Clicar em `Enviar Para Processamento`
8. Acompanhar o status

## Configuracao e Logs do App

Quando empacotado no Windows, o app salva configuracao e logs em:

```text
%LOCALAPPDATA%\ICATU\
```

Exemplo:

```text
C:\Users\NOME_USUARIO\AppData\Local\ICATU\app_config.json
C:\Users\NOME_USUARIO\AppData\Local\ICATU\logs\
```

Formato dos logs:

```text
{id_card}_{dd-mm-yy_hh-mm}.txt
```

## Build do Executavel

O script recomendado e [build_pyqt_app.bat](/c:/Users/lucas.sabino/Desktop/dev/icatu/build_pyqt_app.bat).

Ele gera:

```text
dist\ICATU.exe
```

Se quiser rodar manualmente:

```powershell
pyinstaller --noconfirm --onefile --windowed --name ICATU pyqt_app.py
```

## Teste em Rede Local

No computador que executa a automacao:

```powershell
uvicorn server:app --host 0.0.0.0 --port 8000
```

No computador da analista, configurar:

```text
Servidor: http://IP_DO_SERVIDOR:8000
Token: mesmo valor de BOT_WEBHOOK_TOKEN
```

## Observacoes

- o processamento hoje roda uma tarefa por vez
- o estado dos jobs fica em memoria
- o computador que roda a API precisa ter Playwright e credenciais configurados
- arquivos gerados e artefatos de build nao fazem parte do commit
- os PDFs da ICATU sao salvos automaticamente em `Z:\ArquivoDigital\CONTRATOS\LOCACAO\CADASTROS ONLINE\ANALISE\ANO\MES`
- o nome base dos arquivos segue o padrao `BEM {codigo_do_bem} {Nome do locatario}`
