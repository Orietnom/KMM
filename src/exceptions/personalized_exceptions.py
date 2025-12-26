
class KMMProcess(Exception):
    pass

class KMMLoginError(KMMProcess):
    pass

class KMMStatusCteError(KMMProcess):
    pass

class KMMEmittingCTeError(KMMProcess):
    pass

class KMMEmittingContractError(KMMProcess):
    pass

class KMMPaymentError(KMMProcess):
    pass

class KMMQuickAccessError(KMMProcess):
    pass

class KMMBelgoLoadUserProfileError(KMMProcess):
    pass

class KMMArcelorLoadUserProfileError(KMMProcess):
    pass

class KMMJmendesLoadUserProfileError(KMMProcess):
    pass

class KMMVallourecLoadUserProfileError(KMMProcess):
    pass

class KMMGetTaxesError(KMMProcess):
    pass

class KMMGetDriverNameError(KMMProcess):
    pass

class KMMComplementCTEAlreadyEmitted(KMMProcess):
    pass

class KMMPayementError(KMMProcess):
    pass