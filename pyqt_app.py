import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


DEFAULT_SERVER_URL = os.getenv("BOT_SERVER_URL", "http://127.0.0.1:8000")
DEFAULT_TOKEN = os.getenv("BOT_WEBHOOK_TOKEN", "")
LEGACY_CONFIG_FILE = Path("app_config.json")
LEGACY_LOGS_DIR = Path("logs")


def get_app_data_dir() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "ICATU"
    return Path.home() / ".icatu"


APP_DATA_DIR = get_app_data_dir()
CONFIG_FILE = APP_DATA_DIR / "app_config.json"
LOGS_DIR = APP_DATA_DIR / "logs"


def load_app_config():
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if "token" not in config and "secret" in config:
            config["token"] = config["secret"]
        return config

    if LEGACY_CONFIG_FILE.exists():
        config = json.loads(LEGACY_CONFIG_FILE.read_text(encoding="utf-8"))
        if "token" not in config and "secret" in config:
            config["token"] = config["secret"]
        save_app_config(config)
        return config

    return {
        "server_url": DEFAULT_SERVER_URL,
        "token": DEFAULT_TOKEN,
    }


def save_app_config(config: dict):
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def prettify_field_name(field_name: str) -> str:
    special_labels = {
        "card_id": "Card ID",
        "cpf_cnpj": "CPF/CNPJ",
        "cep": "CEP",
        "email": "E-mail",
        "email_representante": "E-mail Representante",
        "nome": "Nome",
        "nome_fantasia": "Nome Fantasia",
        "nome_representante": "Nome Representante",
        "numero_casa": "Número",
        "tipo_imovel": "Tipo Imóvel",
        "data_nascimento": "Data Nascimento",
        "valor_aluguel": "Valor Aluguel",
        "valor_unitario": "Valor Unitário",
        "fonte_renda": "Fonte Renda",
        "ramo_icatu": "Ramo Icatu",
        "finalidade_icatu": "Finalidade Icatu",
        "titular_diferente": "Titular Diferente",
    }

    label = field_name
    for old, new in special_labels.items():
        label = label.replace(old, new)

    if label == field_name:
        label = field_name.replace("_", " ")

    return label.title()


class ApiWorker(QThread):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.finished.emit(self.fn())
        except Exception as e:
            self.failed.emit(str(e))


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self.resize(500, 160)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.server_url_input = QLineEdit(config.get("server_url", DEFAULT_SERVER_URL))
        self.token_input = QLineEdit(config.get("token", DEFAULT_TOKEN))
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Servidor", self.server_url_input)
        form.addRow("Token", self.token_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_config(self):
        return {
            "server_url": self.server_url_input.text().strip(),
            "token": self.token_input.text().strip(),
        }


class IcatuOperatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ICATU Operação")
        self.resize(1100, 800)

        self.config = load_app_config()
        self.current_job_id = None
        self.current_log_file = None
        self.current_logged_events_count = 0
        self.current_data = {"dados_locatario": {}, "dados_locador": {}}
        self.field_widgets = {"dados_locatario": {}, "dados_locador": {}}
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(3000)
        self.poll_timer.timeout.connect(self.poll_job_status)

        self._build_ui()

    def _build_ui(self):
        self._build_menu()

        central = QWidget()
        root = QVBoxLayout(central)

        card_box = QGroupBox("Solicitação")
        card_layout = QHBoxLayout(card_box)
        self.card_id_input = QLineEdit()
        self.card_id_input.setPlaceholderText("Informe o ID do card do Bitrix")
        self.mission_input = QComboBox()
        self.mission_input.addItem("Emitir Boleto", "run")
        self.mission_input.addItem("Verificar Pagamento", "verify")
        self.load_button = QPushButton("Carregar Dados")
        self.process_button = QPushButton("Enviar Para Processamento")
        self.process_button.setEnabled(False)
        card_layout.addWidget(QLabel("ID do Card"))
        card_layout.addWidget(self.card_id_input, 2)
        card_layout.addWidget(QLabel("Missão"))
        card_layout.addWidget(self.mission_input)
        card_layout.addWidget(self.load_button)
        card_layout.addWidget(self.process_button)

        self.tabs = QTabWidget()
        self.locatario_form, self.locatario_container = self._build_form_tab()
        self.locador_form, self.locador_container = self._build_form_tab()
        self.tabs.addTab(self.locatario_container, "Locatário")
        self.tabs.addTab(self.locador_container, "Locador")

        self.status_output = QPlainTextEdit()
        self.status_output.setReadOnly(True)

        root.addWidget(card_box)
        root.addWidget(self.tabs, 1)
        root.addWidget(QLabel("Status"))
        root.addWidget(self.status_output, 1)

        self.setCentralWidget(central)

        self.load_button.clicked.connect(self.load_card_data)
        self.process_button.clicked.connect(self.process_card)

    def _build_menu(self):
        menu_bar = self.menuBar()
        options_menu = menu_bar.addMenu("Opções")
        settings_action = options_menu.addAction("Configurações")
        settings_action.triggered.connect(self.open_settings_dialog)

    def _build_form_tab(self):
        content = QWidget()
        layout = QFormLayout(content)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return layout, scroll

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.config = dialog.get_config()
            save_app_config(self.config)
            self.log("Configurações atualizadas.")

    def log(self, message: str):
        self.status_output.appendPlainText(message)
        if self.current_log_file:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with self.current_log_file.open("a", encoding="utf-8") as log_file:
                log_file.write(f"{message}\n")

    def api_post(self, path: str, payload: dict):
        headers = {"Content-Type": "application/json"}
        token = self.config.get("token", "").strip()
        if token:
            headers["X-Webhook-Token"] = token
        response = requests.post(
            f"{self.config.get('server_url', DEFAULT_SERVER_URL).rstrip('/')}{path}",
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def api_get(self, path: str):
        response = requests.get(
            f"{self.config.get('server_url', DEFAULT_SERVER_URL).rstrip('/')}{path}",
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def clear_form(self, form_layout: QFormLayout, widget_map: dict):
        while form_layout.rowCount():
            form_layout.removeRow(0)
        widget_map.clear()

    def populate_form(self, form_layout: QFormLayout, widget_map: dict, data: dict):
        self.clear_form(form_layout, widget_map)
        for key, value in sorted(data.items()):
            if isinstance(value, bool):
                widget = QCheckBox()
                widget.setChecked(value)
            else:
                widget = QLineEdit("" if value is None else str(value))
            widget_map[key] = widget
            form_layout.addRow(prettify_field_name(key), widget)

    def collect_form_data(self, widget_map: dict):
        data = {}
        for key, widget in widget_map.items():
            if isinstance(widget, QCheckBox):
                data[key] = widget.isChecked()
            else:
                text = widget.text().strip()
                data[key] = text if text != "" else None
        return data

    def load_card_data(self):
        card_id = self.card_id_input.text().strip()
        if not card_id:
            QMessageBox.warning(self, "Campo Obrigatório", "Informe o ID do card.")
            return

        self.load_button.setEnabled(False)
        self.process_button.setEnabled(False)
        self.status_output.clear()
        self.log(f"Carregando dados do card {card_id}...")

        worker = ApiWorker(
            lambda: self.api_post(
                "/cards/load",
                {"card_id": card_id, "token": self.config.get("token", "")},
            )
        )
        worker.finished.connect(self.on_card_loaded)
        worker.failed.connect(self.on_worker_error)
        worker.finished.connect(lambda _: self.load_button.setEnabled(True))
        worker.failed.connect(lambda _: self.load_button.setEnabled(True))
        self.load_worker = worker
        worker.start()

    def on_card_loaded(self, payload: dict):
        self.current_data = payload
        self.populate_form(
            self.locatario_form,
            self.field_widgets["dados_locatario"],
            payload.get("dados_locatario", {}),
        )
        self.populate_form(
            self.locador_form,
            self.field_widgets["dados_locador"],
            payload.get("dados_locador", {}),
        )
        self.process_button.setEnabled(True)
        self.log("Dados carregados com sucesso.")

    def process_card(self):
        card_id = self.card_id_input.text().strip()
        if not card_id:
            QMessageBox.warning(self, "Campo Obrigatório", "Informe o ID do card.")
            return

        overrides = {
            "dados_locatario": self.collect_form_data(
                self.field_widgets["dados_locatario"]
            ),
            "dados_locador": self.collect_form_data(
                self.field_widgets["dados_locador"]
            ),
        }

        self.process_button.setEnabled(False)
        self.status_output.clear()
        self.current_logged_events_count = 0
        timestamp = datetime.now().strftime("%d-%m-%y_%H-%M")
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.current_log_file = LOGS_DIR / f"{card_id}_{timestamp}.txt"
        self.log(f"Enviando card {card_id} para processamento...")

        worker = ApiWorker(
            lambda: self.api_post(
                "/jobs",
                {
                    "card_id": card_id,
                    "mission": self.mission_input.currentData(),
                    "token": self.config.get("token", ""),
                    "overrides": overrides,
                },
            )
        )
        worker.finished.connect(self.on_job_created)
        worker.failed.connect(self.on_worker_error)
        worker.failed.connect(lambda _: self.process_button.setEnabled(True))
        self.process_worker = worker
        worker.start()

    def on_job_created(self, payload: dict):
        self.current_job_id = payload["job_id"]
        self.log("Solicitação enviada ao servidor.")
        self.poll_timer.start()

    def poll_job_status(self):
        if not self.current_job_id:
            return

        worker = ApiWorker(lambda: self.api_get(f"/jobs/{self.current_job_id}"))
        worker.finished.connect(self.on_job_status)
        worker.failed.connect(self.on_worker_error)
        self.poll_worker = worker
        worker.start()

    def on_job_status(self, payload: dict):
        status = payload.get("status")
        events = payload.get("events", [])
        new_events = events[self.current_logged_events_count :]
        for event in new_events:
            self.log(f"> {event}")
        self.current_logged_events_count = len(events)

        if status in {"finished", "failed"}:
            self.poll_timer.stop()
            self.process_button.setEnabled(True)
            result = payload.get("result") or {}
            if status == "finished":
                self.log("> Processamento concluído com sucesso.")
                QMessageBox.information(
                    self,
                    "Processamento Concluído",
                    "Processamento finalizado com sucesso.",
                )
            else:
                self.log(f"> Falha: {result.get('message', 'Falha no processamento.')}")
                QMessageBox.warning(
                    self,
                    "Processamento Falhou",
                    result.get("message", "Falha no processamento."),
                )

    def on_worker_error(self, message: str):
        self.poll_timer.stop()
        self.process_button.setEnabled(True)
        self.log(f"Erro: {message}")
        QMessageBox.warning(self, "Erro", message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IcatuOperatorWindow()
    window.show()
    sys.exit(app.exec())
