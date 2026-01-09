from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from pathlib import Path
from shared.logger import logger
import time

def get_items(url: str, download_dir: str, file_name: str):

    config_dirs(download_dir, file_name)

    options = Options()
    options.add_argument("--start-maximized")
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }

    options.add_experimental_option("prefs", prefs)
    driver_path = ChromeDriverManager().install()
    driver = webdriver.Chrome(executable_path=driver_path, options=options)
    driver.get(url)
    flag_download = wait_file(download_dir, f'{file_name}')
    driver.quit()
    return flag_download

def wait_file(download_dir: str, file_name: str):
    file_dir = Path(download_dir).joinpath(file_name)
    logger.info(f"Aguardando o download do arquivo {file_dir}")
    for i in range(120):
        if file_dir.is_file():
            logger.info("Download concluído")
            return True
        else:
            time.sleep(1)
    logger.error("Download não finalizou mesmo após aguardar 120 segundos")
    return False

def config_dirs(file_path, file_name):
    output_file_path = Path(file_path).joinpath(file_name)
    if output_file_path.is_file():
        output_file_path.unlink()
