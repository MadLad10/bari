class ServiceError(Exception):
    """Domain error mapped to an HTTP status by the handler in main.py."""

    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(ServiceError):
    status_code = 404


class Conflict(ServiceError):
    status_code = 409


class BadRequest(ServiceError):
    status_code = 400


class Forbidden(ServiceError):
    status_code = 403
