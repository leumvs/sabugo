from typing import Any


ERROR_STATUS = {
    "INVALID_PARAMS": 400,
    "INVALID_IMAGE": 400,
    "NOT_FOUND": 404,
    "UNSUPPORTED_FORMAT": 415,
    "IMAGE_TOO_LARGE": 413,
    "NO_ROOTS_DETECTED": 422,
    "RATE_LIMITED": 429,
    "SERVICE_AT_CAPACITY": 503,
    "PROCESSING_TIMEOUT": 500,
    "INTERNAL_ERROR": 500,
}


def envelope(code: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {"code": code, "message": code.lower()}
    if details is not None:
        result["details"] = details
    return result


class ApiError(Exception):
    def __init__(self, code: str, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.status = ERROR_STATUS[code]
        self.envelope = envelope(code, details)
