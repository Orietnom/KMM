from kmm.services.kmm_actions import KMMActions, LoginParams
from kmm.ie_driver.ie_driver import IEDriverConfig
from dotenv import load_dotenv
import os
load_dotenv()

def main():
    config = IEDriverConfig(
        driver_path=os.getenv("WEBDRIVER_PATH")
    )

    kmm = KMMActions(config=config)
    params = LoginParams(
        url=os.getenv('KMM_URL'),
        username=os.getenv("KMM_USERNAME"),
        password=os.getenv("KMM_PASSWORD")
    )
    kmm.login(
        params=params,
        management="levo"
    )

    kmm.belgo_load_user_profile(
        user='EMISSAO.AUTOMATICA',
        management='levo',
        lotation='mg'
    )

    kmm.quick_access('REPOMFRETED')
    kmm.emitting_contract(
        contract_value='1',
        complement_cte='44404',
        serie='1',
        submotive='descarga',
        transport='12341234',
        liberation_user='FABIANA.HONORATO'
    )

    # kmm.emitting_cte(
    #     cte='145243',
    #     serie='1',
    #     driver_name='givanildo nicacio da silva',
    #     management='fretolog',
    #     cte_value=512.41,
    #     taxes=True
    # )
    input('aa')
    kmm.stop()
    pass

if __name__ == "__main__":
    main()
