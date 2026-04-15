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

    def _fetch_bitrix_file_bytes(self, pdf_url: str, log_callback=None) -> bytes:
        """Resolve a Bitrix24 portal file URL to real bytes via REST API.

        Requires a webhook token with 'disk' scope set as BITRIX_DISK_TOKEN env var.
        Falls back to a clear error explaining how to fix it.
        """
        import base64 as _base64

        parsed = urlparse(pdf_url)
        qs = parse_qs(parsed.query)
        owner_id = (qs.get("ownerId") or qs.get("ownerid") or [""])[0]
        field_name = (qs.get("fieldName") or qs.get("fieldname") or [""])[0]
        file_id_from_url = (qs.get("fileId") or qs.get("fileid") or [""])[0]

        if not owner_id or not field_name:
            raise ValueError(
                f"URL do Bitrix24 nao contem ownerId/fieldName: {pdf_url}"
            )

        self._log(
            log_callback,
            f"URL Bitrix24 detectada — buscando via REST API (deal={owner_id}, campo={field_name})",
        )

        disk_base = _bitrix_disk_base()

        # Step 1: get deal to find the file list (always available with crm scope)
        r = requests.get(
            f"{BITRIX_REST_BASE}/crm.deal.get.json",
            params={"id": owner_id},
            timeout=30,
        )
        r.raise_for_status()
        deal = r.json().get("result") or {}
        file_value = deal.get(field_name)

        if not file_value:
            raise ValueError(
                f"Campo '{field_name}' vazio ou nao encontrado no deal {owner_id}."
            )

        # Resolve file entry and get the last (most recent) file
        if not isinstance(file_value, (list, tuple)):
            file_value = [file_value]
        # Use the matching fileId from URL if provided, otherwise the last entry
        file_entry = file_value[-1]
        if file_id_from_url:
            for entry in file_value:
                if isinstance(entry, dict) and str(entry.get("id")) == str(file_id_from_url):
                    file_entry = entry
                    break
        if isinstance(file_entry, dict):
            file_id = str(file_entry.get("id") or file_entry.get("ID", ""))
        else:
            file_id = str(file_entry)

        self._log(log_callback, f"ID do arquivo Bitrix24: {file_id}")

        # Step 2: If we have a disk-scoped token, use disk.attachedObject.get
        if disk_base:
            self._log(log_callback, "Usando BITRIX_DISK_TOKEN para obter URL autenticada")
            r2 = requests.get(
                f"{disk_base}/disk.attachedObject.get.json",
                params={"id": file_id},
                timeout=30,
            )
            r2.raise_for_status()
            file_info = r2.json().get("result") or {}
            download_url = file_info.get("DOWNLOAD_URL") or file_info.get("downloadUrl")
            if download_url:
                self._log(log_callback, "Download URL autenticada obtida — baixando arquivo")
                r3 = requests.get(download_url, timeout=60)
                r3.raise_for_status()
                return r3.content

        # Step 3: No disk token available — raise a clear, actionable error
        raise ValueError(
            "Nao foi possivel baixar o arquivo do Bitrix24: o webhook atual nao tem escopo 'disk'. "
            "Solucoes possiveis:\n"
            "  (A) Envie o PDF como base64 no campo 'pdf_base64' do payload.\n"
            "  (B) Crie um novo webhook no Bitrix24 com escopo 'disk' e defina "
            "a variavel de ambiente BITRIX_DISK_TOKEN com o token gerado."
        )

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
            if "bitrix24" in pdf_url and "show_file.php" in pdf_url:
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
