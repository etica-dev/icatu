import os
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

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
        print(message, flush=True)
        if log_callback:
            log_callback(message)

    def _bitrix_login_cookies(self, log_callback=None) -> dict:
        """Faz login no Bitrix24 via Playwright e retorna os cookies de sessao."""
        login = os.getenv("BITRIX_LOGIN", "")
        senha = os.getenv("BITRIX_SENHA", "")
        if not login or not senha:
            raise ValueError(
                "Credenciais Bitrix24 nao configuradas. "
                "Defina as variaveis de ambiente BITRIX_LOGIN e BITRIX_SENHA."
            )

        BITRIX_BASE = "https://eticaweb.bitrix24.com.br"

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                executable_path=_get_chromium_executable(),
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context()
            page = context.new_page()
            try:
                self._log(log_callback, "Abrindo portal Bitrix24 para login")
                page.goto(f"{BITRIX_BASE}/", wait_until="domcontentloaded", timeout=30000)

                if page.locator("input[name='USER_LOGIN']").is_visible(timeout=5000):
                    self._log(log_callback, "Preenchendo credenciais Bitrix24")
                    page.locator("input[name='USER_LOGIN']").fill(login)
                    page.locator("input[name='USER_PASSWORD']").fill(senha)

                    submit = page.locator("button[type='submit'], input[type='submit']").first
                    if submit.is_visible(timeout=3000):
                        submit.click()
                    else:
                        page.locator("input[name='USER_PASSWORD']").press("Enter")

                    page.wait_for_url(
                        lambda url: "login" not in url.lower() and "/auth" not in url.lower(),
                        timeout=30000,
                    )
                    self._log(log_callback, "Login Bitrix24 realizado")

                # Extrai cookies da sessao autenticada
                cookies = {c["name"]: c["value"] for c in context.cookies()}
                return cookies
            finally:
                context.close()
                browser.close()

    def _fetch_bitrix_file_bytes(self, pdf_url: str, log_callback=None) -> bytes:
        """Login no Bitrix24, extrai cookies de sessao e baixa o arquivo via requests."""
        self._log(log_callback, "URL Bitrix24 detectada — iniciando sessao autenticada")

        cookies = self._bitrix_login_cookies(log_callback=log_callback)

        self._log(log_callback, "Baixando arquivo com sessao autenticada")
        session = requests.Session()
        session.cookies.update(cookies)
        response = session.get(pdf_url, timeout=60, allow_redirects=True)
        response.raise_for_status()

        content = response.content
        self._log(
            log_callback,
            f"Arquivo recebido: {len(content)} bytes, content-type={response.headers.get('content-type', '?')}",
        )
        return content

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
                "Verifique se a URL exige autenticacao ou se o base64 esta correto."
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
