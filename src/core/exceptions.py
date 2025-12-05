class InvoiceAuditorError(Exception):
    pass

class ExtractionError(InvoiceAuditorError):
    pass

class TranslationError(InvoiceAuditorError):
    pass

class ValidationError(InvoiceAuditorError):
    pass

class ERPConnectionError(InvoiceAuditorError):
    pass

class AgentCommunicationError(InvoiceAuditorError):
    pass