class ShipTrackerError(Exception):
    """Base app error shown to users in a friendly way."""

class NotAuthorized(ShipTrackerError):
    pass

class NotFound(ShipTrackerError):
    pass

class InvalidInput(ShipTrackerError):
    pass
