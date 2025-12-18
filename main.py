from src.ie_driver.kmm_ie_driver import KMMIEDriver

def main():
    kmm = KMMIEDriver()
    kmm.start()
    kmm.open("https://www.google.com")
    kmm.stop()



if __name__ == "__main__":
    main()
