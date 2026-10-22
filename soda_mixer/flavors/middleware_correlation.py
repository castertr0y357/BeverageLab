import uuid
import time
import json
import os
import sys
import threading
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Dict, Any, Optional
from django.http import HttpRequest, HttpResponse

_thread_locals = threading.local()

APP_NAME = "beveragelab"
_debug_enabled = os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG" or os.environ.get("DEBUG_LOGGING", "").lower() in ("true", "1")

class CorrelationIDFilter(logging.Filter):
    """Injects thread-local correlation ID and default action into log records."""
    def filter(self, record):
        record.correlation_id = getattr(_thread_locals, "correlation_id", "none")
        if not hasattr(record, "action"):
            record.action = "general"
        return True

class LokiJsonFormatter(logging.Formatter):
    """Outputs standardized single-line JSON log events for Loki ingestion."""
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "app": APP_NAME,
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", "none"),
            "action": getattr(record, "action", "general"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        context = getattr(record, "context", None)
        if context:
            log_entry["context"] = context
        return json.dumps(log_entry)

def set_debug_logging(enabled: bool):
    global _debug_enabled
    _debug_enabled = enabled
    target_level = logging.DEBUG if enabled else logging.INFO
    for name in ["django", "soda_mixer", "flavors", ""]:
        logging.getLogger(name).setLevel(target_level)
    logging.getLogger("flavors").info(
        f"[Observability] - Debug logging dynamically set to {enabled}",
        extra={"action": "observability.toggle_debug"}
    )

def is_debug_enabled() -> bool:
    return _debug_enabled

# Lightweight Prometheus Metrics
class BeverageMetrics:
    def __init__(self):
        self.requests_total: Dict[str, int] = {}
        self.actions_total: Dict[str, int] = {}
        self.start_time = time.time()

    def record_request(self, method: str, path: str, status: int):
        normalized = path.split("?")[0]
        if normalized.startswith("/recipe/") and len(normalized.split("/")) > 2:
            normalized = "/recipe/{id}/"
        key = f'{APP_NAME}_http_requests_total{{method="{method}",path="{normalized}",status="{status}"}}'
        self.requests_total[key] = self.requests_total.get(key, 0) + 1

    def record_action(self, action: str, status: str = "success"):
        key = f'{APP_NAME}_actions_total{{action="{action}",status="{status}"}}'
        self.actions_total[key] = self.actions_total.get(key, 0) + 1

    def generate_metrics(self) -> str:
        lines = [
            f"# HELP {APP_NAME}_uptime_seconds Process uptime in seconds",
            f"# TYPE {APP_NAME}_uptime_seconds gauge",
            f"{APP_NAME}_uptime_seconds {round(time.time() - self.start_time, 2)}",
            f"# HELP {APP_NAME}_http_requests_total Total HTTP requests handled",
            f"# TYPE {APP_NAME}_http_requests_total counter"
        ]
        for k, v in sorted(self.requests_total.items()):
            lines.append(f"{k} {v}")
        lines.append(f"# HELP {APP_NAME}_actions_total Total domain actions executed")
        lines.append(f"# TYPE {APP_NAME}_actions_total counter")
        for k, v in sorted(self.actions_total.items()):
            lines.append(f"{k} {v}")
        return "\n".join(lines) + "\n"

metrics = BeverageMetrics()

logger = logging.getLogger("flavors.requests")

class LaboratoryCorrelationMiddleware:
    """Middleware to inject a unique correlation ID per request and record Prometheus metrics."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
        request.correlation_id = correlation_id
        _thread_locals.correlation_id = correlation_id
        start_time = time.perf_counter()

        response = self.get_response(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response["X-Correlation-ID"] = correlation_id

        # Record metrics and request log
        metrics.record_request(request.method, request.path, response.status_code)
        if not request.path.endswith("/metrics"):
            logger.info(
                f"{request.method} {request.path} -> {response.status_code} ({duration_ms}ms)",
                extra={
                    "action": "http.request",
                    "context": {"method": request.method, "path": request.path, "status": response.status_code, "duration_ms": duration_ms}
                }
            )

        return response

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
        correlation_id = getattr(request, "correlation_id", "unknown")
        metrics.record_request(request.method, request.path, 500)
        logger.error(
            f"Server Error - Exception raised during processing: {exception}",
            exc_info=True,
            extra={"action": "http.error", "correlation_id": correlation_id}
        )
