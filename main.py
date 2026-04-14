from src.automation_service import IcatuAutomationService


def main(business_card_id, mission):
    service = IcatuAutomationService()
    result = service.run_card(business_card_id, mission)
    print(result.to_dict())


if __name__ == "__main__":
    business_card_id = input("Digite o ID do card de negocio: ")
    mission = input("Informe a missao (Verify/Run): ")
    main(business_card_id, mission)
