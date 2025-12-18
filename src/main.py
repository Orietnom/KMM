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
        term='lot'
    )
    kmm.belgo_load_user_profile(
        user=os.getenv("KMM_USER"),
        management='freto',
        freto_lotation='sp'
    )
    kmm.stop()
    pass

if __name__ == "__main__":
    main()
