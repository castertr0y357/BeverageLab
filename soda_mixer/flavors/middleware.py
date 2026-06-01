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
