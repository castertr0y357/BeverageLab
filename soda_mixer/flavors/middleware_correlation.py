import uuid
import logging
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger('django.request')


class LaboratoryCorrelationMiddleware:
    """Middleware to inject a unique correlation ID per request for traceback matching."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        correlation_id = request.headers.get('X-Correlation-ID') or uuid.uuid4().hex
        request.correlation_id = correlation_id
        
        # Pre-log request with correlation ID
        logger.info(f"[{correlation_id}] - Request - {request.method} {request.path}")
        
        response = self.get_response(request)
        response['X-Correlation-ID'] = correlation_id
        return response

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
        correlation_id = getattr(request, 'correlation_id', 'unknown')
        logger.error(f"[{correlation_id}] - Server Error - Exception raised during processing: {exception}", exc_info=True)
