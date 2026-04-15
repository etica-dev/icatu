import os
import re
import shutil
import time

from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from src.icatu_data import faixa_renda_anual


def _get_chromium_executable() -> str | None:
    path = os.getenv("CHROMIUM_EXECUTABLE_PATH") or shutil.which("chromium")
    return path or None


class IcatuPortal:
    def __init__(
        self, login: str, senha: str, download_root: str, interactive: bool = True
    ):
        self.login_value = login
        self.senha_value = senha
        self.download_root = download_root
        self.interactive = interactive

    @staticmethod
    def _sanitize_file_component(value: str) -> str:
        if not value:
            return ""
        cleaned = re.sub(r'[\\/:*?"<>|]', "", str(value))
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _build_file_base_name(self, dados_locatario: dict) -> str:
        codigo_bem = self._sanitize_file_component(
            dados_locatario.get("codigo_bem") or "SEM_CODIGO"
        )
        nome_locatario = self._sanitize_file_component(
            dados_locatario.get("nome") or "SEM_NOME"
        )
        return f"BEM {codigo_bem} {nome_locatario}"

    def _preencher_campo(
        self, page: Page, nome_campo: str, seletor: str, valor: str, delay: int = 0
    ) -> None:
        if not valor:
            if not self.interactive:
                raise ValueError(f"Campo obrigatório ausente: {nome_campo}")
            valor = input(
                f"  ? O campo '{nome_campo}' está vazio. "
                "Por favor, digite o valor (ou pressione Enter para ignorar): "
            )

        if not valor:
            print(f"  - Campo '{nome_campo}' não preenchido (ignorado pelo usuário).")
            return

        try:
            print(f"  > Preenchendo campo '{nome_campo}': Valor {valor}...")
            if delay > 0:
                page.locator(seletor).clear()
                page.locator(seletor).type(valor, delay=delay)
            else:
                page.locator(seletor).fill(valor)
        except PlaywrightTimeoutError as e:
            raise PlaywrightTimeoutError(
                f"Timeout ao tentar encontrar o campo '{nome_campo}'. Seletor: '{seletor}'"
            ) from e

    def _clicar_elemento(
        self, page: Page, nome_elemento: str, seletor: str, tipo_acao: str = "click"
    ) -> None:
        try:
            print(f"  > Ação '{tipo_acao}' no elemento '{nome_elemento}'...")
            elemento = (
                page.get_by_role("button", name="Acessar")
                if nome_elemento == "Botão Login"
                else page.locator(seletor)
            )
            if tipo_acao == "check":
                elemento.check()
            elif tipo_acao == "dblclick":
                elemento.dblclick()
            elif tipo_acao == "first":
                elemento.first.click()
            else:
                elemento.click()
        except PlaywrightTimeoutError:
            if nome_elemento != "Aceitar Cookies":
                raise

    def _selecionar_opcao(self, page: Page, nome_campo: str, seletor: str, **kwargs):
        if not any(kwargs.values()):
            print(f"  - Campo '{nome_campo}' não selecionado (sem valor).")
            return
        page.locator(seletor).select_option(**kwargs)

    def login(self, page: Page):
        self._clicar_elemento(
            page, "Aceitar Cookies", 'button:has-text("Aceitar todos os cookies")'
        )
        self._preencher_campo(
            page, "Usuário", 'input[placeholder="Usuário"]', self.login_value
        )
        self._preencher_campo(
            page, "Senha", 'input[placeholder="Senha"]', self.senha_value
        )
        self._clicar_elemento(page, "Botão Login", "text=Acessar")

    def open_new_proposal_flow(self, page: Page):
        self._clicar_elemento(page, "CapOnline", "text=CapOnline")
        self._clicar_elemento(
            page,
            nome_elemento="Link Proposta",
            seletor="a.ng-binding[href='#!/proposta/lista']",
        )
        self._clicar_elemento(
            page, "Menu Icatu Garantia de Aluguel", "text=Icatu Garantia de Aluguel"
        )
        self._clicar_elemento(page, "Botão Nova Proposta", "text=Nova Proposta")

    def pesquisar_documento(
        self, page: Page, document: str, search_field_id="searchAccount"
    ) -> bool:
        if not document:
            print(
                f"Aviso: Documento não fornecido para pesquisa no campo {search_field_id}."
            )
            return False

        page.click(f"#{search_field_id}")
        page.type(f"#{search_field_id}_value", document, delay=10)
        page.wait_for_selector(".angucomplete-row", timeout=10000)

        if (
            page.locator(".angucomplete-row .angucomplete-title")
            .filter(has_text="Nenhum cadastro encontrado")
            .count()
            > 0
        ):
            return False

        page.locator(".angucomplete-row .angucomplete-title").first.click()
        return True

    def criar_cadastro(self, page: Page, dados: dict) -> None:
        documento = re.sub(r"\D", "", dados.get("documento", ""))
        if len(documento) == 11:
            self.criar_cadastro_pf(page, dados)
        elif len(documento) == 14:
            self.criar_cadastro_pj(page, dados)
        else:
            raise ValueError(
                f"Documento inválido para cadastro: {dados.get('documento')}"
            )

    def criar_cadastro_pf(self, page: Page, dados: dict) -> None:
        self._preencher_campo(
            page, "CPF", '[placeholder="000.000.000-00"]', dados.get("documento")
        )
        self._preencher_campo(
            page, "Nome Completo", '[placeholder="Nome"]', dados.get("nome")
        )

        if dados.get("sexo"):
            self._clicar_elemento(
                page,
                f"Sexo ({dados['sexo']})",
                f"input[type=radio][value='{dados['sexo']}']",
                tipo_acao="check",
            )

        if dados.get("data_nascimento"):
            self._clicar_elemento(
                page, "Campo Data Nascimento", ".custom-datepicker", "dblclick"
            )
            self._preencher_campo(
                page,
                "Data de Nascimento",
                "#birthDateId",
                dados["data_nascimento"],
                delay=500,
            )

        if dados.get("pais"):
            self._preencher_campo(
                page, "País", "#searchPais_value", dados["pais"], delay=20
            )
            page.wait_for_selector(
                "#searchPais_dropdown .angucomplete-row", timeout=5000
            )
            self._clicar_elemento(
                page,
                "País selecionado",
                "#searchPais_dropdown .angucomplete-row",
                "first",
            )

        self._preencher_campo(
            page,
            "Telefone",
            "[placeholder='(00)00000-0000']",
            dados.get("telefone", ""),
        )
        self._preencher_campo(
            page, "Fixo", "[placeholder='(00)0000-0000']", dados.get("fixo", "")
        )
        self._preencher_campo(
            page,
            "Email",
            'input[ng-model="newAccount.newAccountObj.personal.email.value"]',
            dados.get("email", ""),
        )
        self._preencher_campo(
            page,
            "CEP",
            'input[ng-model="newAccount.newAccountObj.address.cep.value"]',
            dados.get("cep", ""),
        )
        self._preencher_campo(
            page,
            "Número",
            'input[ng-model="newAccount.newAccountObj.address.addressNumber.value"]',
            dados.get("numero_casa", ""),
        )
        self._preencher_campo(
            page,
            "Complemento",
            'input[ng-model="newAccount.newAccountObj.address.complement.value"]',
            dados.get("complemento", ""),
        )

        residencia_selector = (
            "input[type=radio][value='true'][name='optIsResidenciaFiscalBrasil']"
            if dados.get("pais") == "Brasil"
            else "input[type=radio][value='false'][name='optIsResidenciaFiscalBrasil']"
        )
        self._clicar_elemento(page, "Residência Fiscal", residencia_selector, "check")

    def criar_cadastro_pj(self, page: Page, dados: dict) -> None:
        self._preencher_campo(
            page, "CNPJ", '[placeholder="00.000.000/0000-00"]', dados.get("documento")
        )
        self._preencher_campo(
            page,
            "Razão Social",
            'input[ng-model="newJuridicalAccount.newAccountObj.company.companyName.value"]',
            dados.get("razao_social"),
        )

        checkbox = page.locator("input#check2")
        if dados.get("isento_inscricao", False) != checkbox.is_checked():
            self._clicar_elemento(
                page, "Checkbox Isento Inscrição", "label[for='check2']"
            )

        if not dados.get("isento_inscricao", False) and dados.get("inscricao"):
            self._preencher_campo(
                page,
                "Inscrição Estadual",
                'input[ng-model="newJuridicalAccount.newAccountObj.company.registration.value"]',
                dados.get("inscricao"),
            )

        self._preencher_campo(
            page,
            "Telefone Comercial 1",
            'input[ng-model="newJuridicalAccount.newAccountObj.company.phone1.value"]',
            dados.get("telefone"),
        )
        self._preencher_campo(
            page,
            "CEP",
            'input[ng-model="newJuridicalAccount.newAccountObj.address.cep.value"]',
            dados.get("cep"),
        )
        self._preencher_campo(
            page,
            "Número",
            'input[ng-model="newJuridicalAccount.newAccountObj.address.addressNumber.value"]',
            dados.get("numero_casa"),
        )
        self._preencher_campo(
            page,
            "Complemento",
            'input[ng-model="newJuridicalAccount.newAccountObj.address.complement.value"]',
            dados.get("complemento"),
        )
        self._preencher_campo(
            page, "País", "#searchPais_value", dados.get("pais", "Brasil"), delay=20
        )
        page.wait_for_selector("#searchPais_dropdown .angucomplete-row", timeout=5000)
        self._clicar_elemento(
            page, "País selecionado", "#searchPais_dropdown .angucomplete-row", "first"
        )

        self._preencher_campo(
            page,
            "Nome do Representante",
            'input[ng-model="newJuridicalAccount.newAccountObj.representative.name.value"]',
            dados.get("nome_representante"),
        )
        self._preencher_campo(
            page,
            "Email do Representante",
            'input[ng-model="newJuridicalAccount.newAccountObj.representative.email.value"]',
            dados.get("email_representante"),
        )
        self._preencher_campo(
            page,
            "Telefone do Representante",
            'input[ng-model="newJuridicalAccount.newAccountObj.representative.cel.value"]',
            dados.get("telefone_representante"),
        )

    def preencher_informacoes_proposta(self, page: Page, dados: dict) -> None:
        documento = re.sub(r"\D", "", dados.get("documento", ""))
        if len(documento) == 11:
            self.preencher_informacoes_proposta_pf(page, dados)
        elif len(documento) == 14:
            self.preencher_informacoes_proposta_pj(page, dados)
        else:
            raise ValueError("Documento obrigatório para preencher a proposta.")

    def _preencher_dados_comuns_proposta(self, page: Page, dados: dict) -> None:
        self._selecionar_opcao(
            page,
            "Produto",
            'select[ng-model="propostaInformation.formField.product"]',
            label=dados.get("produto"),
        )
        self._preencher_campo(
            page,
            "Registro SUSEP",
            'input[ng-model="propostaInformation.formField.susepRegistry"]',
            "1",
        )
        self._selecionar_opcao(
            page,
            "Corretora",
            'select[ng-model="propostaInformation.formField.corretora"]',
            value="0013i00000WoPvzAAF",
        )
        self._preencher_campo(
            page,
            "Valor do Aluguel",
            'input[ng-model="propostaInformation.formField.rentValue"]',
            dados.get("valor_aluguel"),
        )
        self._preencher_campo(
            page,
            "Multiplicador do Título",
            'input[ng-model="propostaInformation.formField.titleMultiplier"]',
            str(dados.get("multiplicador")),
        )
        self._preencher_campo(
            page,
            "Valor Unitário do Título",
            'input[ng-model="propostaInformation.title.value"]',
            dados.get("valor_unitario"),
            delay=20,
        )
        self._clicar_elemento(
            page,
            "Rádio 'Não' (Possui outro título)",
            "input[type=radio][value='Não']",
            tipo_acao="check",
        )
        self._clicar_elemento(
            page, "Botão Próximo (2/4)", 'button.pull-right:has-text("Próximo")'
        )

    def preencher_informacoes_proposta_pf(self, page: Page, dados: dict) -> None:
        if dados.get("profissao"):
            self._preencher_campo(
                page,
                "Profissão",
                "#searchProfession_value",
                dados["profissao"],
                delay=20,
            )
            page.wait_for_selector(
                "#searchProfession_dropdown .angucomplete-row", timeout=200000
            )
            self._clicar_elemento(
                page,
                "Seleção de Profissão",
                "#searchProfession_dropdown .angucomplete-row",
                "first",
            )

        self._preencher_campo(
            page,
            "Renda Mensal",
            "[placeholder='R$ 1.000,00']",
            dados.get("renda_mensal"),
        )

        if dados.get("fonte_renda"):
            self._clicar_elemento(
                page,
                f"Fonte de Renda ({dados['fonte_renda']})",
                f"input[type=radio][value='{dados['fonte_renda']}']",
                "check",
            )
            if dados["fonte_renda"] == "Outros":
                self._preencher_campo(
                    page,
                    "Origem da Renda",
                    'input[ng-model="propostaNew.formField.resourceOriginOutros"]',
                    dados.get("origem"),
                )

        self._clicar_elemento(
            page, "Botão Próximo (1/4)", 'button.pull-right:has-text("Próximo")'
        )
        self._preencher_dados_comuns_proposta(page, dados)

    def preencher_informacoes_proposta_pj(self, page: Page, dados: dict) -> None:
        if dados.get("ramo_icatu"):
            self._preencher_campo(
                page,
                "Ramo de Atividade",
                "#searchProfession_value",
                dados["ramo_icatu"],
                delay=20,
            )
            page.wait_for_selector(
                "#searchProfession_dropdown .angucomplete-row", timeout=200000
            )
            self._clicar_elemento(
                page,
                "Seleção de Ramo",
                "#searchProfession_dropdown .angucomplete-row",
                "first",
            )

        if dados.get("renda_mensal"):
            try:
                renda_mensal_float = float(
                    dados["renda_mensal"].replace(".", "").replace(",", ".")
                )
                faixa = faixa_renda_anual(renda_mensal_float * 12)
                self._selecionar_opcao(
                    page,
                    "Faixa de Renda Anual",
                    'select[ng-model="propostaNew.formField.declarationCode"]',
                    label=faixa,
                )
            except Exception as e:
                print(f"Falha ao selecionar a faixa de renda: {e}")

        origem = (
            input(
                "\nQual a origem dos recursos?\n\n"
                "[1] - Faturamento\n"
                "[2] - Aplicações Financeiras\n"
                "[3] - Bens Imóveis\n"
                "[4] - Recuso-me a informar\n"
                "[5] - Outros\n"
                "Digite o número correspondente: "
            )
            if self.interactive
            else dados.get("origem", "")
        )
        origens_map = {
            "1": "Faturamento",
            "2": "Aplicações Financeiras",
            "3": "Bens Imóveis",
            "4": "Recuso-me a informar",
        }
        espec_origem = ""
        if origem in origens_map:
            origem = origens_map[origem]
        elif origem == "5":
            espec_origem = input("Especifique a origem dos recursos: ")
        elif not self.interactive:
            espec_origem = dados.get("origem", "")

        if dados["fonte_renda"] == "Outros":
            self._clicar_elemento(
                page,
                "Rádio Fonte de renda",
                f"input[type=radio][value='{origem}']",
                "check",
            )
            self._preencher_campo(
                page,
                "Origem da Renda",
                'input[ng-model="propostaNew.formField.resourceOriginOutros"]',
                espec_origem,
            )

        self._clicar_elemento(
            page, "Botão Próximo (1/4)", 'button.pull-right:has-text("Próximo")'
        )
        self._preencher_dados_comuns_proposta(page, dados)

    def preencher_informacoes_garantia(self, page: Page, dados: dict) -> None:
        if not self.pesquisar_documento(
            page, dados.get("documento"), search_field_id="searchLocator"
        ):
            self._clicar_elemento(
                page,
                "Botão + Criar Cadastro (Locador)",
                '.angucomplete-row:has-text("Criar Cadastro"), .angucomplete-title:has-text("+ Criar Cadastro")',
                "first",
            )
            documento = re.sub(r"\D", "", dados.get("documento", ""))
            if len(documento) == 11:
                self._clicar_elemento(
                    page, "Link Nova Conta PF", '[href="#!/nova-conta"]'
                )
            elif len(documento) == 14:
                self._clicar_elemento(
                    page, "Link Nova Conta PJ", '[href="#!/nova-conta-juridica"]'
                )
            else:
                raise ValueError("Documento do locador inválido para cadastro.")

            self.criar_cadastro(page, dados)
            time.sleep(2)
            self._clicar_elemento(
                page,
                "Botão Criar Cadastro (Final)",
                'button.btn.btn-default.pull-right:has-text("Criar Cadastro")',
            )
            page.wait_for_timeout(3000)

        administracao_selector = (
            "input[type=radio][value='true']"
            if dados.get("administracao", False)
            else "input[type=radio][value='false']"
        )
        self._clicar_elemento(page, "Administração", administracao_selector, "check")

        if dados.get("administracao") and dados.get("administrador"):
            self.pesquisar_documento(
                page, dados["administrador"], search_field_id="searchEstateAdmin"
            )

        self._clicar_elemento(page, "Checkbox 'Li e concordo'", 'label[for="check8"]')
        self._selecionar_opcao(
            page,
            "Finalidade do Imóvel",
            'select[ng-model="propostaCaucao.formField.estatePurpose"]',
            value=dados.get("finalidade", "Residencial"),
        )
        self._selecionar_opcao(
            page,
            "Tipo do Imóvel",
            'select[ng-model="propostaCaucao.formField.estateType"]',
            value=dados.get("tipo_imovel", "Outros"),
        )
        self._clicar_elemento(
            page, "Botão Próximo (3/4)", 'button.pull-right:has-text("Próximo")'
        )

    def preencher_forma_de_pagamento(self, page: Page, dados: dict) -> None:
        if dados.get("pagamento"):
            self._clicar_elemento(
                page,
                f"Forma de Pagamento ({dados['pagamento']})",
                f'input[type="radio"][name="choosePayment"][value="{dados["pagamento"]}"]',
                "check",
            )

        titular_diferente = "true" if dados.get("titular_diferente", False) else "false"
        self._clicar_elemento(
            page,
            "Titular Diferente",
            f'input[type="radio"][name="responsavelFinanceiro"][value="{titular_diferente}"]',
            "check",
        )
        self._clicar_elemento(
            page, "Botão Próximo (4/4)", 'button.pull-right:has-text("Próximo")'
        )

        continuar = (
            "s"
            if not self.interactive
            else input(" ? Deseja confirmar e gerar a proposta? (s/n): ")
        )
        if continuar.lower().strip() != "s":
            raise Exception(
                "Operação cancelada pelo usuário antes da geração da proposta."
            )

        self._clicar_elemento(
            page,
            "Botão Gerar Proposta",
            'button.btn.pull-right:has-text("Gerar Proposta")',
        )

    def baixar_documento(
        self, page: Page, seletor: str, nome_arquivo: str = None
    ) -> str | None:
        try:
            with page.expect_download(timeout=30000) as download_info:
                page.locator(seletor).click()
            download = download_info.value
            os.makedirs(self.download_root, exist_ok=True)
            destino = os.path.join(
                self.download_root, nome_arquivo or download.suggested_filename
            )
            download.save_as(destino)
            print(f"Documento salvo com sucesso em: {destino}")
            return destino
        except Exception as e:
            print(f"Erro ao baixar documento com seletor '{seletor}': {e}")
            return None

    def check_payment(self, dados_locatario: dict) -> str | None:
        cliente_cpf = dados_locatario.get("documento")
        if not cliente_cpf:
            print("CPF do cliente não encontrado.")
            return

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, executable_path=_get_chromium_executable())
            page = browser.new_page()
            try:
                page.goto("https://www.icatuseguros.com.br/casadocorretor")
                try:
                    page.click(
                        'button:has-text("Aceitar todos os cookies")', timeout=5000
                    )
                except PlaywrightTimeoutError:
                    pass

                page.locator('input[placeholder="Usuário"]').fill(self.login_value)
                page.locator('input[placeholder="Senha"]').fill(self.senha_value)
                page.get_by_role("button", name="Acessar").click()
                page.get_by_text("CapOnline").click()
                page.locator("#searchMain_value:visible").type(cliente_cpf, delay=30)
                page.wait_for_selector(".angucomplete-row", timeout=10000)

                pagamento_locator = page.locator(
                    ".gs-type-garantia-Aluguel:has-text('Garantia de Aluguel')"
                )
                if pagamento_locator.is_visible():
                    pagamento_locator.click()
                    page.wait_for_load_state("networkidle", timeout=30000)
                    nome_documento = (
                        f"{self._build_file_base_name(dados_locatario)} - CONSULTA.pdf"
                    )
                    return self.baixar_documento(
                        page, ".shield-detalhe-opt", nome_documento
                    )

                solicitacao_locator = page.locator(
                    ".gs-type-case:has-text('Solicitação')"
                )
                if solicitacao_locator.is_visible():
                    print("Info: Apenas a 'Solicitação' foi encontrada.")
                else:
                    print(
                        "Nenhum registro de garantia encontrado para o CPF informado."
                    )
                    return None
            except Exception as e:
                print(f"Erro: {e}")
                return None
            finally:
                browser.close()

    def run_automation(self, dados_locatario: dict, dados_locador: dict) -> str | None:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=["--start-maximized"], executable_path=_get_chromium_executable())
            context = browser.new_context(viewport=None, accept_downloads=True)
            page = context.new_page()

            try:
                page.goto(
                    "https://www.icatuseguros.com.br/casadocorretor", timeout=60000
                )
                self.login(page)
                self.open_new_proposal_flow(page)

                if not dados_locatario.get("documento"):
                    raise ValueError("Dados do locatário incompletos.")

                if not self.pesquisar_documento(page, dados_locatario["documento"]):
                    page.locator(
                        '.angucomplete-title:has-text("+ Criar Cadastro")'
                    ).click()
                    print("Locatário não encontrado. Criando novo cadastro.")
                    documento = re.sub(r"\D", "", dados_locatario["documento"])
                    if len(documento) == 11:
                        page.click('[href="#!/nova-conta"]')
                    elif len(documento) == 14:
                        page.click('[href="#!/nova-conta-juridica"]')
                    else:
                        raise ValueError(
                            "Documento do locatário inválido para cadastro."
                        )
                    self.criar_cadastro(page, dados_locatario)
                    page.click(
                        'button.btn.btn-default.pull-right:has-text("Criar Cadastro")'
                    )
                    page.wait_for_timeout(3000)

                self.preencher_informacoes_proposta(page, dados_locatario)

                if not dados_locador.get("documento"):
                    raise ValueError("Dados do locador incompletos.")

                self.preencher_informacoes_garantia(page, dados_locador)
                self.preencher_forma_de_pagamento(page, dados_locatario)

                page.wait_for_selector(
                    'button:has-text("Imprimir Boleto")', timeout=30000
                )
                page.wait_for_selector(
                    'button:has-text("Imprimir Documento da Capitalização")',
                    timeout=30000,
                )

                file_base_name = self._build_file_base_name(dados_locatario)
                nome_boleto = f"{file_base_name} - BOLETO.pdf"
                nome_proposta = f"{file_base_name} - PROPOSTA.pdf"

                self.baixar_documento(
                    page, 'button:has-text("Imprimir Boleto")', nome_boleto
                )
                proposta_path = self.baixar_documento(
                    page,
                    'button:has-text("Imprimir Documento da Capitalização")',
                    nome_proposta,
                )

                page.wait_for_selector('button:has-text("Fechar")', timeout=60000)
                print("Automação concluída com sucesso!")
                return proposta_path
            except Exception as e:
                print(f"Ocorreu um erro durante a automação: {e}")
                screenshot_path = os.path.join(
                    os.getcwd(), "img", "error_screenshot.png"
                )
                os.makedirs(os.path.join(os.getcwd(), "img"), exist_ok=True)
                try:
                    page.screenshot(path=screenshot_path)
                    print(f"Screenshot do erro salvo em: {screenshot_path}")
                except Exception as screenshot_error:
                    print(f"Não foi possível salvar o screenshot: {screenshot_error}")
                return None
            finally:
                time.sleep(15)
                browser.close()
