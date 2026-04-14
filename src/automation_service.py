import io
import sys
import threading
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass

from src.auto_icatu import AutoIcatu
from src.bitrix_requests import BusinessCardProcessor


@dataclass
class AutomationResult:
    success: bool
    card_id: str
    mission: str
    status: str
    message: str
    file_path: str | None = None

    def to_dict(self):
        return {
            "success": self.success,
            "card_id": self.card_id,
            "mission": self.mission,
            "status": self.status,
            "message": self.message,
            "file_path": self.file_path,
        }


class TeeLineWriter(io.TextIOBase):
    def __init__(self, callback=None, original_stream=None):
        self.callback = callback
        self.original_stream = original_stream
        self.buffer = ""

    def write(self, text):
        if self.original_stream:
            self.original_stream.write(text)

        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self._emit(line)
        return len(text)

    def flush(self):
        if self.original_stream:
            self.original_stream.flush()
        if self.buffer:
            self._emit(self.buffer)
            self.buffer = ""

    def _emit(self, line):
        clean_line = line.strip()
        if clean_line and self.callback:
            self.callback(clean_line)


class IcatuAutomationService:
    def __init__(self):
        self.execution_lock = threading.Lock()

    def load_card_data(self, card_id: str) -> dict:
        with self.execution_lock:
            processor = BusinessCardProcessor(card_id)
            processor.process(check_payment=False)
            auto_icatu = AutoIcatu(interactive=False)
            return {
                "card_id": card_id,
                "dados_locatario": auto_icatu.dados_locatario,
                "dados_locador": auto_icatu.dados_locador,
            }

    def run_card(
        self,
        card_id: str,
        mission: str,
        overrides: dict | None = None,
        log_callback=None,
    ) -> AutomationResult:
        normalized_mission = mission.lower().strip()
        if normalized_mission not in {"verify", "run"}:
            return AutomationResult(
                success=False,
                card_id=card_id,
                mission=normalized_mission,
                status="ERRO_PARAMETRO",
                message="Mission inválida. Use 'verify' ou 'run'.",
            )

        with self.execution_lock:
            processor = BusinessCardProcessor(card_id)
            processor.report_result(
                card_id, "EM_PROCESSAMENTO", f"Missão recebida: {normalized_mission}"
            )

            writer = TeeLineWriter(callback=log_callback, original_stream=sys.stdout)
            try:
                with redirect_stdout(writer), redirect_stderr(writer):
                    print("Iniciando coleta de dados do card")
                    processor.process(check_payment=normalized_mission == "verify")

                    print("Preparando dados para automação")
                    auto_icatu = AutoIcatu(
                        interactive=False,
                        overrides=overrides or {},
                    )

                    if normalized_mission == "verify":
                        print("Executando verificação de pagamento")
                        file_path = auto_icatu.check_payment()
                        result = AutomationResult(
                            success=True,
                            card_id=card_id,
                            mission=normalized_mission,
                            status="SUCESSO",
                            message="Verificação concluída com sucesso.",
                            file_path=file_path,
                        )
                    else:
                        print("Executando emissão e automação")
                        file_path = auto_icatu.run_automation()
                        result = AutomationResult(
                            success=bool(file_path),
                            card_id=card_id,
                            mission=normalized_mission,
                            status="SUCESSO" if file_path else "ERRO_AUTOMACAO",
                            message=(
                                "Emissão concluída com sucesso."
                                if file_path
                                else "A automação terminou sem gerar arquivo."
                            ),
                            file_path=file_path,
                        )

            except Exception as e:
                result = AutomationResult(
                    success=False,
                    card_id=card_id,
                    mission=normalized_mission,
                    status="ERRO_AUTOMACAO",
                    message=str(e),
                )
            finally:
                writer.flush()

            processor.report_result(
                card_id,
                result.status,
                result.message,
                file_path=result.file_path,
            )
            return result
