"""Authentication views."""

import json
import logging
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import HttpRequest, HttpResponse, JsonResponse

logger = logging.getLogger(__name__)


def login_view(request: HttpRequest) -> HttpResponse:
    """Render the dedicated laboratory access gate."""
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'flavors/login.html')


@csrf_exempt
@require_http_methods(["POST"])
def login_api(request: HttpRequest) -> JsonResponse:
    """AJAX login endpoint for the laboratory."""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            logger.info(f"LaboratoryAccess - Info - Successfully authenticated user: {user.username}")
            return JsonResponse({'status': 'success', 'user': user.username})
        else:
            logger.warning(f"LaboratoryAccess - Warning - Authentication failed for username: {username}")
            return JsonResponse({'status': 'error', 'message': 'Invalid laboratory credentials.'}, status=401)
    except Exception as e:
        logger.error(f"LaboratoryAccess - Error - Error during login authentication: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def logout_api(request: HttpRequest) -> JsonResponse:
    """AJAX logout endpoint."""
    username = request.user.username if request.user.is_authenticated else "Anonymous"
    logout(request)
    logger.info(f"LaboratoryAccess - Info - User logged out: {username}")
    return JsonResponse({'status': 'success'})
