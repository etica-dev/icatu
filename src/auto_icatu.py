import base64
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from src.icatu_data import BusinessCardDataLoader
from src.icatu_portal import IcatuPortal


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(sys._MEIPASS, "ms-playwright")


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUSINESS_CARD_DATA_FILE = os.path.join(BASE_DIR, "business_card_data.csv")
DATA_DIR = os.path.join(BASE_DIR, "data")
DOWNLOAD_ROOT = (
    r"Z:\ArquivoDigital\CONTRATOS\LOCACAO\CADASTROS ONLINE\ANALISE"
)
MESES_PT_BR = {
    1: "1.JANEIRO",
    2: "2.FEVEREIRO",
    3: "3.MARCO",
    4: "4.ABRIL",
    5: "5.MAIO",
    6: "6.JUNHO",
    7: "7.JULHO",
    8: "8.AGOSTO",
    9: "9.SETEMBRO",
    10: "10.OUTUBRO",
    11: "11.NOVEMBRO",
    12: "12.DEZEMBRO",
}


def build_current_download_root() -> str:
    now = datetime.now()
    month_folder = MESES_PT_BR[now.month]
    return os.path.join(DOWNLOAD_ROOT, str(now.year), month_folder)


class AutoIcatu:
    def __init__(self, interactive: bool = True, overrides: dict | None = None):
        load_dotenv()
        self.login = os.getenv("LOGIN")
        self.senha = os.getenv("SENHA")
        if not self.login or not self.senha:
            raise ValueError("Environment variables LOGIN and SENHA must be set.")

        bundle = BusinessCardDataLoader(
            BUSINESS_CARD_DATA_FILE,
            DATA_DIR,
            interactive=interactive,
        ).load()
        self.dados_locatario = bundle.dados_locatario
        self.dados_locador = bundle.dados_locador
        if overrides:
            self.dados_locatario.update(overrides.get("dados_locatario", {}))
            self.dados_locador.update(overrides.get("dados_locador", {}))
        self.portal = IcatuPortal(
            self.login,
            self.senha,
            build_current_download_root(),
            interactive=interactive,
        )

    @staticmethod
    def encode_file(file_path: str) -> str:
        with open(file_path, "rb") as file:
            return base64.b64encode(file.read()).decode("utf-8")

    def check_payment(self) -> str | None:
        return self.portal.check_payment(self.dados_locatario)

    def run_automation(self) -> str | None:
        return self.portal.run_automation(
            self.dados_locatario,
            self.dados_locador,
        )


if __name__ == "__main__":
    AutoIcatu().run_automation()
