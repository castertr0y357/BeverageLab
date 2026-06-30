from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from ..models import BackgroundExecutionTask


@csrf_exempt
@require_http_methods(["GET"])
def task_status_api(request: HttpRequest, uuid: str) -> JsonResponse:
    """Fetch status and current telemetry of a background task."""
    task = get_object_or_404(BackgroundExecutionTask, uuid=uuid)
    return JsonResponse({
        'uuid': str(task.uuid),
        'task_name': task.task_name,
        'status': task.status,
        'progress': task.progress,
        'error_message': task.error_message,
        'result_data': task.result_data,
        'created_at': task.created_at.isoformat()
    })
