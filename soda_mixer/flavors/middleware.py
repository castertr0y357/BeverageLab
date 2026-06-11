from typing import Callable, List
from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpRequest, HttpResponse

class LaboratoryAccessMiddleware:
    """
    Middleware to ensure the entire laboratory is restricted to authorized personnel.
    Redirects unauthenticated users to the login page.
    """
    get_response: Callable[[HttpRequest], HttpResponse]
    whitelist: List[str]

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        # Whitelist paths that don't require authentication
        self.whitelist = [
            reverse('login'),
            reverse('login_api'),
            '/admin/',
            '/static/',
            '/media/',
        ]

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_authenticated:
            # Check if the path is in the whitelist or starts with a whitelisted path
            path = request.path
            is_whitelisted = any(path.startswith(w) for w in self.whitelist)
            
            if not is_whitelisted:
                return redirect('login')

        response = self.get_response(request)
        return response


from django.middleware.csrf import CsrfViewMiddleware
import urllib.parse
import logging

logger = logging.getLogger('django')

class LaboratoryCsrfMiddleware(CsrfViewMiddleware):
    """
    Custom CSRF middleware that matches the request host header against the origin hostname
    to support reverse proxy setups with SSL termination where the scheme might mismatch.
    """
    def _origin_verified(self, request: HttpRequest) -> bool:
        if super()._origin_verified(request):
            return True

        if "HTTP_ORIGIN" in request.META:
            try:
                parsed_origin = urllib.parse.urlsplit(request.META["HTTP_ORIGIN"])
            except ValueError:
                return False

            try:
                request_host = request.get_host().split(':')[0]
            except Exception:
                request_host = request.META.get('HTTP_HOST', '').split(':')[0]

            origin_host = parsed_origin.netloc.split(':')[0]

            if origin_host and request_host and origin_host == request_host:
                return True

            # Diagnostic log for production troubleshooting
            from django.conf import settings
            try:
                gh = request.get_host()
            except Exception as ex:
                gh = f"Error: {ex}"
            logger.warning(f"🔬 CSRF Reject Debug - Origin Host: '{origin_host}', Request Host: '{request_host}', get_host(): '{gh}', HTTP_HOST: '{request.META.get('HTTP_HOST', 'N/A')}', X-Forwarded-Host: '{request.META.get('HTTP_X_FORWARDED_HOST', 'N/A')}', CSRF_TRUSTED_ORIGINS: {settings.CSRF_TRUSTED_ORIGINS}")

        return False

