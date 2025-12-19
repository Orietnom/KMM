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
        management="fretolog"
    )
    kmm.quick_access(
        term='ectecomp'
    )
    kmm.emitting_cte(
        cte='147928',
        serie='1',
        driver_name='LUCAS JOSE ARAUJO AZEVEDO'
    )
    input('')
    kmm.stop()
    pass

if __name__ == "__main__":
    main()
