import os
import shutil
from datetime import datetime
from pathlib import Path

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


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

    def download_pdf(
        self,
        card_id: str,
        pdf_url: str,
        log_callback=None,
    ) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = self.work_dir / f"{card_id}_{timestamp}_entrada.pdf"

        self._log(log_callback, "Baixando PDF informado no webhook")
        response = requests.get(pdf_url, timeout=60)
        response.raise_for_status()
        target_path.write_bytes(response.content)
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

    def run(self, card_id: str, pdf_url: str, log_callback=None) -> dict:
        input_pdf = self.download_pdf(card_id, pdf_url, log_callback=log_callback)
        return self.validate_pdf(card_id, input_pdf, log_callback=log_callback)
