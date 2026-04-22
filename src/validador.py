import os
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from src.logger import get_logger

log = get_logger("validador")

BITRIX_REST_BASE = "https://eticaweb.bitrix24.com.br/rest/9011/mwgwaj2ew7lzfxp2"
BITRIX_REST_BASE_DISK = None  # will be resolved at runtime from BITRIX_DISK_TOKEN env var


def _bitrix_disk_base() -> str | None:
    token = os.getenv("BITRIX_DISK_TOKEN")
    if token:
        return f"https://eticaweb.bitrix24.com.br/rest/9011/{token}"
    return None


def _get_chromium_executable() -> str | None:
    path = os.getenv("CHROMIUM_EXECUTABLE_PATH") or shutil.which("chromium")
    return path or None


class ValidadorService:
    def __init__(self, work_dir: str | Path = "data/validador", headless: bool = False):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless

    def _log(self, log_callback, message: str):
        log.info(message)
        if log_callback:
            log_callback(message)

    def _fetch_bitrix_file_bytes(self, pdf_url: str, log_callback=None) -> bytes:
        """Login no Bitrix24 via Playwright e baixa o arquivo na mesma sessao do browser."""
        login = os.getenv("BITRIX_LOGIN", "")
        senha = os.getenv("BITRIX_SENHA", "")
        if not login or not senha:
            raise ValueError(
                "Credenciais Bitrix24 nao configuradas. "
                "Defina as variaveis de ambiente BITRIX_LOGIN e BITRIX_SENHA."
            )

        BITRIX_BASE = "https://eticaweb.bitrix24.com.br"
        self._log(log_callback, "URL Bitrix24 detectada — abrindo sessao autenticada")

        captured: dict = {}

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                executable_path=_get_chromium_executable(),
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            full_url = pdf_url if pdf_url.startswith("http") else BITRIX_BASE + pdf_url
            file_base = full_url.split("?")[0]

            def _intercept(route, request):
                """Captura bytes quando o servidor devolver o arquivo apos o login."""
                if request.url.startswith(file_base):
                    response = route.fetch()
                    body = response.body()
                    ct = response.headers.get("content-type", "")
                    # So salva se for um arquivo real, nao uma pagina de login/HTML
                    if body[:4] == b"%PDF" or ("application" in ct and "html" not in ct):
                        captured["bytes"] = body
                        captured["content_type"] = ct
                    route.fulfill(response=response)
                else:
                    route.continue_()

            try:
                # Registra interceptor antes de navegar
                page.route("**/*", _intercept)

                # Navega para a URL do arquivo — o Bitrix24 redireciona para login
                self._log(log_callback, "Navegando para URL do arquivo (aguarda redirecionamento de login)")
                try:
                    page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass

                # Se tiver login form, preenche credenciais
                if page.locator("input[name='USER_LOGIN']").is_visible(timeout=8000):
                    self._log(log_callback, "Formulario de login detectado — autenticando")
                    page.locator("input[name='USER_LOGIN']").fill(login)
                    page.locator("input[name='USER_PASSWORD']").fill(senha)
                    submit = page.locator("button[type='submit'], input[type='submit']").first
                    if submit.is_visible(timeout=3000):
                        submit.click()
                    else:
                        page.locator("input[name='USER_PASSWORD']").press("Enter")

                    self._log(log_callback, "Aguardando redirect apos login")
                    # Apos login, aguarda o browser voltar para a URL do arquivo
                    try:
                        page.wait_for_url(
                            lambda url: file_base in url or "/auth" not in url.lower(),
                            timeout=30000,
                        )
                    except Exception:
                        pass
                    self._log(log_callback, "Login Bitrix24 realizado")

                    # Navega para a URL do arquivo na sessao autenticada
                    self._log(log_callback, "Baixando arquivo apos autenticacao")
                    try:
                        page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass

                if "bytes" not in captured:
                    # Fallback: request via sessao do mesmo contexto de browser
                    self._log(log_callback, "Tentando download via contexto autenticado (fallback)")
                    resp = context.request.get(full_url, timeout=30000)
                    body = resp.body()
                    captured["bytes"] = body
                    captured["content_type"] = resp.headers.get("content-type", "")

                content = captured["bytes"]
                self._log(
                    log_callback,
                    f"Arquivo recebido: {len(content)} bytes, "
                    f"content-type={captured.get('content_type', '?')}",
                )
                return content

            finally:
                context.close()
                browser.close()

    def download_pdf(
        self,
        card_id: str,
        pdf_url: str | None = None,
        pdf_base64: str | None = None,
        log_callback=None,
    ) -> Path:
        import base64 as _base64

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = self.work_dir / f"{card_id}_{timestamp}_entrada.pdf"

        if pdf_base64:
            self._log(log_callback, "Decodificando PDF recebido em base64")
            try:
                content = _base64.b64decode(pdf_base64)
            except Exception as exc:
                raise ValueError(f"pdf_base64 invalido: {exc}") from exc

        elif pdf_url:
            self._log(log_callback, "Baixando PDF informado no webhook")
            if "bitrix24" in pdf_url:
                content = self._fetch_bitrix_file_bytes(pdf_url, log_callback=log_callback)
            else:
                response = requests.get(pdf_url, timeout=60)
                response.raise_for_status()
                content = response.content
        else:
            raise ValueError("Informe pdf_url ou pdf_base64 no payload.")

        # Sanity check: make sure we actually got a PDF
        if content[:4] != b"%PDF":
            raise ValueError(
                "O conteudo recebido nao e um PDF valido "
                f"(primeiros bytes: {content[:80]!r}). "
                "Verifique se a URL está correta."
            )

        target_path.write_bytes(content)
        self._log(log_callback, f"PDF salvo em {target_path}")
        return target_path

    def validate_pdf(
        self,
        card_id: str,
        input_pdf_path: str | Path,
        log_callback=None,
    ) -> dict:
        input_pdf = Path(input_pdf_path)
        if not input_pdf.exists():
            raise FileNotFoundError(f"Arquivo nao encontrado: {input_pdf}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_pdf = self.work_dir / f"{card_id}_{timestamp}_validacao.pdf"

        self._log(log_callback, "Abrindo portal do validador")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless, executable_path=_get_chromium_executable())
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            try:
                page.goto("https://validar.iti.gov.br/", wait_until="domcontentloaded")
                self._log(log_callback, "Aceitando termos de uso")
                page.locator("#acceptTerms").check()

                self._log(log_callback, "Enviando PDF para validacao")
                page.locator("#signature_files").set_input_files(
                    str(input_pdf.resolve())
                )
                
                self._log(log_callback, "Iniciando validacao")
                page.locator("#validateSignature").click()

                SEM_ASSINATURA = (
                    "Você submeteu um documento sem assinatura reconhecível"
                    " ou com assinatura corrompida."
                )
                # Aguarda o botão de sucesso OU o popup de erro (SweetAlert2) —
                # o que aparecer primeiro, para não congelar os 120s.
                page.wait_for_selector(
                    "#botaoVisualizarConf, .swal2-container",
                    timeout=120000,
                )
                if page.locator(".swal2-container").is_visible():
                    popup_text = page.locator(".swal2-container").inner_text(timeout=3000)
                    self._log(log_callback, f"Popup detectado: {popup_text[:200]}")
                    if "sem assinatura reconhecível" in popup_text or "assinatura corrompida" in popup_text:
                        raise ValueError(SEM_ASSINATURA)
                    raise RuntimeError(f"Popup inesperado do validador: {popup_text[:300]}")

                self._log(log_callback, "Abrindo resultado da validacao")
                page.locator("#botaoVisualizarConf").click()

                self._log(log_callback, "Baixando comprovante da validacao")
                with page.expect_download(timeout=120000) as download_info:
                    page.locator("#bnt-pdf").click()

                download = download_info.value
                download.save_as(str(output_pdf))
            finally:
                context.close()
                browser.close()

        self._log(log_callback, f"Validacao finalizada: {output_pdf}")
        return {
            "success": True,
            "card_id": card_id,
            "input_pdf_path": str(input_pdf),
            "validation_pdf_path": str(output_pdf),
            "message": "Validacao concluida com sucesso.",
        }

    def run(
        self,
        card_id: str,
        pdf_url: str | None = None,
        pdf_base64: str | None = None,
        log_callback=None,
    ) -> dict:
        input_pdf = self.download_pdf(
            card_id, pdf_url=pdf_url, pdf_base64=pdf_base64, log_callback=log_callback
        )
        return self.validate_pdf(card_id, input_pdf, log_callback=log_callback)
