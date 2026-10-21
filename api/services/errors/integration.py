from services.errors.base import BaseServiceError


class ExternalBindingNotFoundError(BaseServiceError):
    pass


class IntegrationVersionConflictError(BaseServiceError):
    pass


class UnsupportedIntegrationEventError(BaseServiceError):
    pass


class ExternalIntegrityError(BaseServiceError):
    pass
