class RuntimeErrorBase(Exception):
    code = "runtime_error"
    status_code = 500


class ValidationError(RuntimeErrorBase):
    code = "invalid_request"
    status_code = 400


class NotFoundError(RuntimeErrorBase):
    code = "not_found"
    status_code = 404


class ConflictError(RuntimeErrorBase):
    code = "version_conflict"
    status_code = 409


class RateLimitError(RuntimeErrorBase):
    code = "rate_limited"
    status_code = 429


class DependencyUnavailable(RuntimeErrorBase):
    code = "temporarily_unavailable"
    status_code = 503
