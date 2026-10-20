class DomainError(Exception):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code


def require(condition, code="forbidden", status=403):
    if not condition:
        raise DomainError(status, code)
