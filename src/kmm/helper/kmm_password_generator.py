import random
from datetime import datetime


def password_generate(license_plate, control_number, p6: bool = False) -> str:
    number_1 = random.randint(0, 9)
    number_2 = random.randint(0, 9)

    if int(license_plate) % 2 == 0:
        licence_plate = int(license_plate) * 2
    else:
        licence_plate = int(license_plate) * 3

    now = datetime.now()
    aux = int(licence_plate) + int(now.day)
    aux = int(aux) + int(control_number)
    aux = int(aux) * int(now.hour)
    password_4 = str(aux)
    password_6 = str(number_1) + str(aux) + str(number_2)
    return password_4