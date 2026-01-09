from shared.db_handler.db_handler import DB
from bba_portal import BelgoPortal


class Main:
    def __init__(self):
        self.db=DB()

    def get_incidents(self):
        incidents = self.db.get_data('complementar_belgo2')
        bba = BelgoPortal(incidents)
        new_incidents = bba.run()
        pass

if __name__ == '__main__':
    main = Main()
    main.get_incidents()
