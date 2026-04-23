import csv
import base64
import json
import os
import urllib.parse
from pathlib import Path

import requests
from dotenv import load_dotenv

from src.logger import get_logger

load_dotenv()

log = get_logger("bitrix")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUSINESS_CARD_DATA_FILE = os.path.join(BASE_DIR, "business_card_data.csv")

BITRIX_DEAL_UPDATE_URL = "https://eticaweb.bitrix24.com.br/rest/9011/d2eng022cz3e6hqg/crm.deal.update"
BITRIX_TIMELINE_COMMENT_URL = "https://eticaweb.bitrix24.com.br/rest/9011/d2eng022cz3e6hqg/crm.timeline.comment.add"


def add_timeline_comment(deal_id: str, comment: str) -> None:
    """Adiciona um comentário na timeline do deal. Falhas são logadas e silenciadas."""
    try:
        payload = {
            "fields": {
                "ENTITY_ID": int(deal_id),
                "ENTITY_TYPE": "deal",
                "COMMENT": comment,
            }
        }
        response = requests.post(
            BITRIX_TIMELINE_COMMENT_URL,
            json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15,
        )
        resp_json = response.json() if response.ok else response.text
        if not (response.ok and isinstance(resp_json, dict) and resp_json.get("result")):
            log.warning("deal=%s timeline_comment=falha http=%s resposta=%s", deal_id, response.status_code, str(resp_json)[:200])
        else:
            log.info("deal=%s timeline_comment=ok", deal_id)
    except Exception as exc:
        log.warning("deal=%s timeline_comment=erro exc=%s", deal_id, exc)


def upload_validation_result(
    deal_id: str,
    field_name: str,
    pdf_path: str,
    filename: str | None = None,
) -> dict:
    """Converte o PDF validado para base64 e salva no campo do deal via crm.deal.update.

    Retorna dict com status_code e response da API.
    crm.deal.update retorna {"result": true} em caso de sucesso.
    """
    pdf_bytes = Path(pdf_path).read_bytes()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    fname = filename or Path(pdf_path).name

    payload = {
        "id": int(deal_id),
        "fields": {
            field_name: {"fileData": [fname, pdf_b64]},
        },
    }

    response = requests.post(
        BITRIX_DEAL_UPDATE_URL,
        json=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=60,
    )

    try:
        resp_json = response.json()
    except Exception:
        resp_json = response.text

    success = response.ok and resp_json.get("result") is True if isinstance(resp_json, dict) else False

    if success:
        log.info("deal=%s campo=%s upload=sucesso", deal_id, field_name)
    else:
        log.warning(
            "deal=%s campo=%s upload=falha http=%s resposta=%s",
            deal_id, field_name, response.status_code, str(resp_json)[:300],
        )

    return {
        "status_code": response.status_code,
        "success": success,
        "response": resp_json,
    }


class BusinessCardProcessor:
    def __init__(self, business_card_id):
        self.business_card_id = business_card_id
        self.business_base_url = "https://eticaweb.bitrix24.com.br/rest/9011/mwgwaj2ew7lzfxp2/crm.deal.list.json?"
        self.locatario_base_url = "https://eticaweb.bitrix24.com.br/rest/9011/mwgwaj2ew7lzfxp2/crm.contact.list.json?"
        self.bitrix_update_url = "https://eticaweb.bitrix24.com.br/rest/9011/d2eng022cz3e6hqg/crm.deal.update"
        self.locador_base_url = self.locatario_base_url
        self.vista_base = "http://eticaweb-rest.vistahost.com.br"
        self.api_key = os.getenv("api_key")

    def bitrix_update(self, business_card_id, base64):
        update_data = {
            "ID": business_card_id,
            "FIELDS": {"UF_CRM_1732291331": {"filedata": ["Testfile.pdf", base64]}},
        }

        headers = {"Accept": "application/json"}

        response = requests.post(
            self.bitrix_update_url, json=update_data, headers=headers
        )
        if response.status_code == 200:
            print("Bitrix atualizado com sucesso.")
        else:
            print(f"Erro ao atualizar Bitrix: {response.status_code} - {response.text}")

    def _build_result_fields(self, status, message, file_path=None):
        fields = {}
        status_field = os.getenv("BITRIX_STATUS_FIELD")
        message_field = os.getenv("BITRIX_MESSAGE_FIELD")
        file_field = os.getenv("BITRIX_FILE_FIELD", "UF_CRM1732291331")

        if status_field:
            fields[status_field] = status
        if message_field:
            fields[message_field] = message

        if file_path:
            file_bytes = Path(file_path).read_bytes()
            encoded_file = base64.b64encode(file_bytes).decode("utf-8")
            fields[file_field] = {"fileData": [Path(file_path).name, encoded_file]}

        return fields

    def report_result(self, card_id, status, message, file_path=None):
        fields = self._build_result_fields(status, message, file_path)
        if not fields:
            print(
                "Nenhum campo de retorno configurado no ambiente para reportar o resultado."
            )
            return None

        payload = {"ID": card_id, "fields": fields}
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        response = requests.post(self.bitrix_update_url, json=payload, headers=headers)
        if response.ok:
            print("Resultado reportado ao Bitrix com sucesso.")
        else:
            print(
                f"Falha ao reportar resultado ao Bitrix: {response.status_code} - {response.text}"
            )
        return response

    def fetch_business_card_data(self):
        business_params = {
            "SELECT[]": [
                "UF_CRM_1726515464",
                "UF_CRM_1728651308",
                "UF_CRM_1745425983",
                "UF_CRM_1727722533",
                "UF_CRM_1728648430",
                "UF_CRM_1726069991",
                "UF_CRM_1745424934",
                "UF_CRM_1730137400",
                "UF_CRM_5F008508B0737",
                "UF_CRM_658C5F03995B3",
                "UF_CRM_1747420348508",
                "UF_CRM_658C5F0361915",
                "UF_CRM_658C5F03B2CF4",
                "UF_CRM_658C5F02E807C",
                "UF_CRM_658C5F03136BE",
                "UF_CRM_658C5F0326D6D",
                "UF_CRM_658C5F033CD82",
                "UF_CRM_658C5F034E8F0",
                "UF_CRM_658C5F0461767",
            ],
            "FILTER[ID]": f"{self.business_card_id}",
        }

        business_params["SELECT[]"] = list(dict.fromkeys(business_params["SELECT[]"]))

        business_url = (
            f"{self.business_base_url}"
            f"{urllib.parse.urlencode(business_params, doseq=True)}"
        )
        response = requests.get(business_url)

        if response.status_code == 200:
            business_data = response.json()
            return business_data.get("result", [])

        print(
            f"Erro na requisicao do card de negocio: "
            f"{response.status_code} - {response.text}"
        )
        return []

    def save_to_csv(self, filename, data, field_mapping):
        with open(filename, mode="a", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            for field, friendly_name in field_mapping.items():
                value = data.get(field, "N/A")
                if field in ["EMAIL", "PHONE"] and isinstance(value, list):
                    value = (
                        value[0].get("VALUE", "N/A")
                        if value and isinstance(value[0], dict)
                        else "N/A"
                    )
                writer.writerow([friendly_name, value])

    def process(self, check_payment=False):
        business_cards = self.fetch_business_card_data()
        if not business_cards:
            print("Nenhum resultado encontrado para o card de negocio.")
            return None if check_payment else False

        business_card = business_cards[0]
        business_field_mapping = {
            "ID": "Card_ID",
            "UF_CRM_1726515464": "locatario_id_bitrix",
            "UF_CRM_1730137400": "locatario_finalidade",
            "UF_CRM_1726069991": "imovel_aluguel_bitrix",
            "UF_CRM_1728651308": "locatario_razao_social",
            "UF_CRM_1728648430": "locatario_valor_do_caucao",
            "UF_CRM_1745424934": "locatario_forma_de_pagamento",
            "UF_CRM_1745425983": "locatario_numero_propostaICATU",
            "UF_CRM_1727722533": "locatario_caucao_multiplicador",
            "UF_CRM_1747420348508": "locatario_produto_icatu",
            "UF_CRM_658C5F03B2CF4": "imovel_aluguel_vista",
            "UF_CRM_5F008508B0737": "imovel_codigo_vista",
            "UF_CRM_658C5F0361915": "imovel_complemento",
            "UF_CRM_658C5F0461767": "locador_id_bitrix",
            "UF_CRM_658C5F02E807C": "imovel_endereco",
            "UF_CRM_658C5F034E8F0": "imovel_numero",
            "UF_CRM_658C5F0326D6D": "imovel_bairro",
            "UF_CRM_658C5F03136BE": "imovel_cidade",
            "UF_CRM_658C5F03995B3": "imovel_tipo",
            "UF_CRM_658C5F033CD82": "imovel_cep",
        }

        with open(
            BUSINESS_CARD_DATA_FILE, mode="w", newline="", encoding="utf-8"
        ) as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["Campo", "Valor"])

        self.save_to_csv(BUSINESS_CARD_DATA_FILE, business_card, business_field_mapping)
        print("Dados do card de negocio salvos com sucesso.")

        locatario_id = business_card.get("UF_CRM_1726515464")
        if locatario_id:
            check_payment = self.process_locatario(locatario_id, check_payment)

        locador_id = business_card.get("UF_CRM_658C5F0461767")
        codigo_imovel = business_card.get("UF_CRM_5F008508B0737")

        if locador_id and codigo_imovel and check_payment is False:
            self.process_locador(locador_id, codigo_imovel)
        elif locador_id and not codigo_imovel:
            print(
                "AVISO: Codigo do imovel nao encontrado no card de negocio. "
                "Nao foi possivel buscar dados detalhados do locador na Vista."
            )
        elif not locador_id:
            print("AVISO: ID do Locador nao encontrado no card de negocio.")

        return check_payment

    def process_locatario(self, locatario_id, check_payment):
        locatario_params = {
            "SELECT[]": [
                "NAME",
                "EMAIL",
                "PHONE",
                "BIRTHDATE",
                "SECOND_NAME",
                "UF_CRM_1703704289",
                "UF_CRM_1600093510",
                "UF_CRM_1600438841",
                "UF_CRM_1599746645",
                "UF_CRM_1599746694",
                "UF_CRM_1728394752",
                "UF_CRM_1728394905",
                "UF_CRM_1703705331",
                "UF_CRM_1703705375",
                "UF_CRM_1703705361",
                "UF_CRM_1747679677815",
                "UF_CRM_5F008507C2A5D",
            ],
            "FILTER[ID]": f"{locatario_id}",
        }

        locatario_url = (
            f"{self.locatario_base_url}"
            f"{urllib.parse.urlencode(locatario_params, doseq=True)}"
        )
        response = requests.get(locatario_url)

        if response.status_code != 200:
            print(
                f"Erro na requisicao do locatario (Bitrix): "
                f"{response.status_code} - {response.text}"
            )
            return None if check_payment else False

        locatario_data = response.json().get("result", [])
        if not locatario_data:
            print(
                f"Nenhum resultado encontrado para o locatario com ID {locatario_id} no Bitrix."
            )
            return None if check_payment else False

        locatario_info = locatario_data[0]
        locatario_field_mapping = {
            "NAME": "locatario_nome",
            "EMAIL": "locatario_email",
            "PHONE": "locatario_telefone",
            "BIRTHDATE": "locatario_data_de_nascimento",
            "SECOND_NAME": "locatario_sobrenome",
            "UF_CRM_1600093510": "locatario_cep",
            "UF_CRM_1599746694": "locatario_sexo",
            "UF_CRM_1728394752": "locatario_renda",
            "UF_CRM_1599746645": "locatario_profissao",
            "UF_CRM_1600438841": "locatario_nacionalidade",
            "UF_CRM_1703705331": "locatario_representante",
            "UF_CRM_1728394905": "locatario_fonte_de_renda",
            "UF_CRM_1703704289": "locatario_inscricao_estadual",
            "UF_CRM_1703705375": "locatario_email_representante",
            "UF_CRM_1703705361": "locatario_telefone_representante",
            "UF_CRM_1747679677815": "locatario_finalidade_icatu",
            "UF_CRM_5F008507C2A5D": "locatario_cpf_cnpj",
        }
        self.save_to_csv(
            BUSINESS_CARD_DATA_FILE, locatario_info, locatario_field_mapping
        )
        print("Dados do locatario (Bitrix) salvos com sucesso.")

        if check_payment:
            return locatario_info.get("UF_CRM_5F008507C2A5D")
        return False

    def process_locador(self, locador_id_bitrix, codigo_imovel_vista):
        print(
            f"Processando locador com ID Bitrix: {locador_id_bitrix} "
            f"e Codigo Imovel Vista: {codigo_imovel_vista}"
        )
        pesquisa = {
            "fields": [
                {
                    "proprietarios": [
                        "Nome",
                        "CPFCNPJ",
                        "DataNascimento",
                        "Nacionalidade",
                        "Profissao",
                        "Celular",
                        "EnderecoResidencial",
                        "EnderecoNumero",
                        "BairroResidencial",
                        "CidadeResidencial",
                        "UFResidencial",
                        "CEPResidencial",
                        "PaisResidencial",
                        "FoneResidencial",
                        "EmailResidencial",
                        "FonePrincipal",
                        "EnderecoComercial",
                        "BairroComercial",
                        "CidadeComercial",
                        "UFComercial",
                        "CEPComercial",
                        "PaisComercial",
                        "FoneComercial",
                        "EmailComercial",
                        "Observacoes",
                        "EnderecoComplemento",
                        "TipoPessoa",
                        "Codigo",
                        "Naturalidade",
                        "Sexo",
                        "Complemento",
                    ]
                }
            ]
        }

        pesquisa_encode = urllib.parse.quote(json.dumps(pesquisa))

        vista_url = (
            f"{self.vista_base}/imoveis/detalhes"
            f"?imovel={urllib.parse.quote(str(codigo_imovel_vista))}"
            f"&key={self.api_key}"
            f"&showTotal=1&showSuspended=1&showInternal=1"
            f"&pesquisa={pesquisa_encode}"
        )
        headers = {"Accept": "application/json"}

        vista_response = requests.get(vista_url, headers=headers)

        if vista_response.status_code != 200:
            print(
                f"Erro na requisicao a Vista API para o imovel {codigo_imovel_vista}: "
                f"{vista_response.status_code} - {vista_response.text}"
            )
            return

        vista_data = vista_response.json()
        if not vista_data:
            print(
                f"Nenhum resultado encontrado na Vista API para o imovel "
                f"com codigo: {codigo_imovel_vista}"
            )
            return

        if not isinstance(vista_data, dict):
            print(
                f"AVISO: Resposta da Vista API para o imovel {codigo_imovel_vista} "
                f"nao e um dicionario JSON como esperado. Conteudo: {vista_data}"
            )
            return

        try:
            proprietarios_map = vista_data.get("proprietarios")

            if not isinstance(proprietarios_map, dict):
                print(
                    f"AVISO: Campo 'proprietarios' nao foi encontrado na resposta "
                    f"da Vista API para o imovel {codigo_imovel_vista}."
                )
                return

            if not proprietarios_map:
                print(
                    f"AVISO: Dicionario 'proprietarios' esta vazio para o imovel "
                    f"{codigo_imovel_vista}."
                )
                return

            actual_locador_details_dict = next(iter(proprietarios_map.values()), None)
            if not isinstance(actual_locador_details_dict, dict):
                print(
                    f"AVISO: Os detalhes do proprietario nao estao no formato esperado "
                    f"para o imovel {codigo_imovel_vista}."
                )
                return

            with open(
                BUSINESS_CARD_DATA_FILE, mode="a", newline="", encoding="utf-8"
            ) as csv_file:
                writer = csv.writer(csv_file)
                for field_key, field_value in actual_locador_details_dict.items():
                    friendly_csv_name = f"locador_vista_{field_key.lower()}"
                    writer.writerow([friendly_csv_name, field_value])

            print("Dados do locador (Vista API) salvos com sucesso.")
        except Exception as e:
            print(
                f"Erro inesperado ao processar dados do locador da Vista API "
                f"para o imovel {codigo_imovel_vista}: {e}"
            )


if __name__ == "__main__":
    business_card_id = input("Digite o ID do card de negocio: ")
    if business_card_id.strip():
        processor = BusinessCardProcessor(business_card_id)
        processor.process()
    else:
        print("ID do card de negocio nao pode ser vazio.")
