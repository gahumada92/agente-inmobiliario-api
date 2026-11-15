"""Errores de dominio traducibles a respuestas HTTP."""


class DomainError(Exception):
    status_code = 500


class NotFoundError(DomainError):
    status_code = 404


class UpstreamServiceError(DomainError):
    status_code = 502


class DependencyUnavailableError(DomainError):
    status_code = 503


class RateLimitExceededError(DomainError):
    status_code = 429
