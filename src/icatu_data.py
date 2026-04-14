import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


DECLARACAO_RENDA_ANUAL = [
    (0, 180000.00, "Até R$ 180.000,00"),
    (180000.01, 360000.00, "De R$ 180.000,01 a R$ 360.000,00"),
    (360000.01, 720000.00, "De R$ 360.000,01 a R$ 720.000,00"),
    (720000.01, 1800000.00, "De R$ 720.000,01 a R$ 1.800.000,00"),
    (1800000.01, 3600000.00, "De R$ 1.800.000,01 a R$ 3.600.000,00"),
    (3600000.01, float("inf"), "Acima de R$ 3.600.000,00"),
]

PRODUTO_ICATU_MAP = {
    "15937": "12",
    "15939": "15",
    "15941": "18",
    "15943": "24",
    "15945": "30",
}

FONTE_RENDA_MAP = {
    "Funcionario Público (CLT)": "Salário / Pro Labore",
    "Funcionário Público (Estatutário)": "Salário / Pro Labore",
    "Func. registrado por empresa ou pessoa física (CLT)": "Salário / Pro Labore",
    "Militar": "Salário / Pro Labore",
    "Aposentado / Pensionista": "Aposentadoria",
}


def faixa_renda_anual(renda_anual: float) -> str:
    for minimo, maximo, label in DECLARACAO_RENDA_ANUAL:
        if minimo <= renda_anual <= maximo:
            return label
    return "Não Informado"


@dataclass
class IcatuDataBundle:
    dados_locatario: dict
    dados_locador: dict


class BusinessCardDataLoader:
    def __init__(
        self, business_card_file: str, data_dir: str, interactive: bool = True
    ):
        self.business_card_file = Path(business_card_file)
        self.data_dir = Path(data_dir)
        self.interactive = interactive

        try:
            self.df = pd.read_csv(self.business_card_file, encoding="utf-8")
            self.df_fonte_renda = pd.read_csv(
                self.data_dir / "fonte_renda.csv", encoding="utf-8"
            )
            self.df_tipo_imovel = pd.read_csv(
                self.data_dir / "tipo_imovel.csv", encoding="utf-8"
            )
            self.df_ramos_icatu = pd.read_csv(
                self.data_dir / "ramos_icatu.csv", encoding="utf-8"
            )
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Erro ao carregar CSV: {e}. Verifique se os arquivos "
                "business_card_data.csv, fonte_renda.csv, tipo_imovel.csv "
                "e ramos_icatu.csv estão no diretório correto."
            ) from e

        self.df_fonte_renda.columns = self.df_fonte_renda.columns.str.strip()
        self.df_tipo_imovel.columns = self.df_tipo_imovel.columns.str.strip()
        self.df_ramos_icatu.columns = self.df_ramos_icatu.columns.str.strip()

        self.mapa_fonte_renda = dict(
            zip(self.df_fonte_renda["ID"], self.df_fonte_renda["VALUE"])
        )
        self.mapa_tipo_imovel = dict(
            zip(self.df_tipo_imovel["ID"], self.df_tipo_imovel["VALUE"])
        )
        self.mapa_ramos_icatu = dict(
            zip(self.df_ramos_icatu["ID"], self.df_ramos_icatu["VALUE"])
        )

    def load(self) -> IcatuDataBundle:
        return IcatuDataBundle(
            dados_locatario=self._build_locatario(),
            dados_locador=self._build_locador(),
        )

    def _extract_value(self, campo: str):
        resultado = self.df.query(f"Campo == '{campo}'")["Valor"]
        if resultado.empty:
            return None

        valor = resultado.iloc[0]
        # print(f"Valor extraído para '{campo}': {valor}")
        return None if pd.isna(valor) else str(valor)

    def _clean_currency(self, value):
        return value.replace("|BRL", "").strip() if value else None

    def _to_cents(self, value) -> str:
        if not value:
            return "0"
        try:
            return str(int(float(str(value).replace(",", "."))) * 100)
        except ValueError:
            return "0"

    def _format_date(self, value):
        if not value:
            return None
        try:
            return pd.to_datetime(value).strftime("%d/%m/%Y")
        except ValueError:
            return None

    def _clean_document(self, value):
        return re.sub(r"[./-]", "", value) if value else None

    def _clean_phone(self, value):
        return value.replace("+55", "") if value else ""

    def _fixed_phone_from_mobile(self, value):
        if not value:
            return ""
        match = re.match(r"^\+55(\d{2})9(\d{8})$", value)
        if match:
            return match.group(1) + match.group(2)
        return re.sub(r"^\+55", "", value)

    def _normalize_landlord_phone(self, value):
        if not value:
            return "", ""

        telefone_limpo = re.sub(r"\D", "", value)
        if telefone_limpo.startswith("55") and len(telefone_limpo) > 11:
            telefone_limpo = telefone_limpo[2:]

        if len(telefone_limpo) >= 11 and telefone_limpo[2] == "9":
            fixo = telefone_limpo[:2] + telefone_limpo[3:]
        else:
            fixo = telefone_limpo

        return telefone_limpo, fixo

    def _map_tipo_imovel(self, raw_value):
        if not raw_value:
            return "Outros"
        try:
            nome = self.mapa_tipo_imovel.get(int(raw_value), "Outros")
        except ValueError:
            return "Outros"
        if nome in {"Sala", "Comercial"}:
            return "Sala comercial"
        return nome

    def _map_fonte_renda(self, raw_value):
        if not raw_value:
            return "Outros"
        try:
            nome = self.mapa_fonte_renda.get(int(raw_value), "Outros")
        except ValueError:
            return "Outros"
        return FONTE_RENDA_MAP.get(nome, "Outros")

    def _map_ramo_icatu(self, raw_value):
        default = "SERVIÇOS PRESTADOS PRINCIPALMENTE AS EMPRESAS"
        if not raw_value:
            return default
        try:
            return self.mapa_ramos_icatu.get(int(raw_value), default)
        except ValueError:
            return default

    def _map_forma_pagamento(self, raw_value):
        if not raw_value:
            return "Boleto"
        try:
            return "Boleto" if int(raw_value) == 15817 else "Cartão de Crédito"
        except ValueError:
            return "Boleto"

    def _build_locatario(self) -> dict:
        produto_icatu = PRODUTO_ICATU_MAP.get(
            self._extract_value("locatario_produto_icatu"),
            self._extract_value("locatario_produto_icatu"),
        )
        finalidade = self._extract_value("locatario_finalidade")
        valor_aluguel = self._clean_currency(
            self._extract_value("imovel_aluguel_bitrix")
            or self._extract_value("imovel_aluguel_vista")
        )
        multiplicador = self._extract_value("locatario_caucao_multiplicador")
        if not multiplicador and self.interactive:
            multiplicador = input("Digite o multiplicador do título: ")

        renda_mensal = self._clean_currency(self._extract_value("locatario_renda"))
        renda_mensal_cents = self._to_cents(renda_mensal)
        valor_aluguel_cents = self._to_cents(valor_aluguel)

        valor_unitario_cents = "0"
        multiplicador_float = 0.0
        if valor_aluguel and multiplicador:
            try:
                aluguel_float = float(str(valor_aluguel).replace(",", "."))
                multiplicador_float = float(str(multiplicador).replace(",", "."))
                valor_unitario_cents = str(
                    int(aluguel_float * multiplicador_float * 100)
                )
            except (ValueError, TypeError):
                pass

        telefone = self._extract_value("locatario_telefone")
        sexo_id = self._extract_value("locatario_sexo")
        sexo = None
        if sexo_id:
            try:
                sexo = "M" if int(sexo_id) == 5855 else "F"
            except ValueError:
                sexo = None

        inscricao = re.sub(
            r"[,.-]", "", self._extract_value("locatario_inscricao_estadual") or ""
        )
        inscricao = inscricao if inscricao.isdigit() else ""

        return {
            "card_id": self._extract_value("Card_ID"),
            "codigo_bem": self._extract_value("imovel_codigo_vista"),
            "documento": self._clean_document(
                self._extract_value("locatario_cpf_cnpj")
            ),
            "nome": self._extract_value("locatario_nome"),
            "sexo": sexo,
            "telefone": self._clean_phone(telefone),
            "fixo": self._fixed_phone_from_mobile(telefone),
            "data_nascimento": self._format_date(
                self._extract_value("locatario_data_de_nascimento")
            ),
            "pais": "Brasil",
            "pais_residencia": "Brasil",
            "email": self._extract_value("locatario_email"),
            "cep": self._extract_value("imovel_cep"),
            "numero_casa": self._extract_value("imovel_numero"),
            "complemento": self._extract_value("imovel_complemento"),
            "profissao": "outro",
            "renda_mensal": renda_mensal_cents,
            "fonte_renda": self._map_fonte_renda(
                self._extract_value("locatario_fonte_de_renda")
            ),
            "finalidade_icatu": self._extract_value("locatario_finalidade_icatu"),
            "ramo_icatu": self._map_ramo_icatu(
                self._extract_value("locatario_finalidade_icatu")
            ),
            "tipo_imovel": self._map_tipo_imovel(self._extract_value("imovel_tipo")),
            "origem": "Extratos",
            "produto": (
                f"{produto_icatu if produto_icatu not in ['N/A', '', None] else '18'} "
                "Meses - Icatu Garantia de Aluguel"
            ),
            "finalidade": "Residencial" if finalidade == "13735" else "Comercial",
            "valor_aluguel": valor_aluguel_cents,
            "multiplicador": round(multiplicador_float),
            "valor_unitario": valor_unitario_cents,
            "pagamento": self._map_forma_pagamento(
                self._extract_value("locatario_forma_de_pagamento")
            ),
            "titular_diferente": False,
            "razao_social": self._extract_value("locatario_nome"),
            "nome_fantasia": self._extract_value("locatario_nome"),
            "isento_inscricao": not bool(inscricao),
            "inscricao": inscricao,
            "nome_representante": self._extract_value("locatario_representante"),
            "email_representante": self._extract_value("locatario_email_representante"),
            "telefone_representante": re.sub(
                r"\+55\s|-|\s",
                "",
                self._extract_value("locatario_telefone_representante") or "",
            ),
        }

    def _build_locador(self) -> dict:
        telefone, fixo = self._normalize_landlord_phone(
            self._extract_value("locador_vista_foneprincipal") or ""
        )

        nacionalidade = self._extract_value("locador_vista_nacionalidade")
        pais = "Brasil"
        if not nacionalidade or nacionalidade.lower().startswith("bra"):
            nacionalidade = "Brasil"

        return {
            "documento": self._clean_document(
                self._extract_value("locador_vista_cpfcnpj")
            ),
            "pais": pais,
            "numero_casa": self._extract_value("locador_vista_endereconumero"),
            "complemento": self._extract_value("locador_vista_enderecocomplemento"),
            "razao_social": self._extract_value("locador_vista_nome"),
            "nome_fantasia": self._extract_value("locador_vista_nome"),
            "isento_inscricao": True,
            "inscricao": "",
            "tipo_imovel": self._map_tipo_imovel(self._extract_value("imovel_tipo")),
            "finalidade_icatu": self._extract_value("locatario_finalidade_icatu")
            or "Outros",
            "nome_representante": "Ciclano dos santos",
            "email_representante": "ciclado2@gmail.com",
            "telefone_representante": "11999999999",
            "nacionalidade": nacionalidade,
            "nome": self._extract_value("locador_vista_nome"),
            "sexo": (
                "M"
                if (self._extract_value("locador_vista_sexo") or "").lower()
                in ["m", "masculino"]
                else "F"
            ),
            "telefone": telefone,
            "fixo": fixo,
            "data_nascimento": self._format_date(
                self._extract_value("locador_vista_datanascimento")
            ),
            "cep": re.sub(
                r"[.-]",
                "",
                self._extract_value("locador_vista_cepresidencial") or "",
            )
            or None,
            "email": self._extract_value("locador_vista_emailresidencial"),
            "administracao": True,
            "administrador": "04.808.267/0001-60",
        }
