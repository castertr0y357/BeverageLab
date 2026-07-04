import logging
import threading
from typing import Callable, Any
from django.db import connection, transaction
from .models import BackgroundExecutionTask

logger = logging.getLogger(__name__)


def update_progress_factory(task_uuid: Any) -> Callable[..., None]:
    """Generates a thread-safe helper to update task progress."""
    def update_progress(progress_val: int, status: str = 'RUNNING', error_msg: str = None, result_data: Any = None) -> None:
        try:
            with transaction.atomic():
                task = BackgroundExecutionTask.objects.get(uuid=task_uuid)
                task.progress = progress_val
                task.status = status
                if error_msg is not None:
                    task.error_message = error_msg
                if result_data is not None:
                    task.result_data = result_data
                task.save()
        except Exception as e:
            logger.error(f"TaskRegistry - Error - Failed to update task {task_uuid} progress: {e}")
    return update_progress


def run_task_in_thread(task_uuid: Any, func: Callable[..., None], *args: Any, **kwargs: Any) -> None:
    """Wrapper running the task and ensuring database connection cleanup."""
    update_progress = update_progress_factory(task_uuid)
    update_progress(0, status='RUNNING')
    
    try:
        func(update_progress, *args, **kwargs)
        # Check task state at completion
        task = BackgroundExecutionTask.objects.get(uuid=task_uuid)
        if task.status == 'RUNNING':
            update_progress(100, status='SUCCESS')
    except Exception as e:
        logger.error(f"TaskRegistry - Error - Task {task_uuid} execution failed: {e}", exc_info=True)
        update_progress(100, status='FAILURE', error_msg=str(e))
    finally:
        # Close connection in thread to prevent postgres connection leaks
        import sys
        if 'test' not in sys.argv:
            connection.close()


def submit_task(task_name: str, func: Callable[..., None], *args: Any, **kwargs: Any) -> BackgroundExecutionTask:
    """Submits a background task executed via a daemon thread (or synchronously in tests)."""
    task = BackgroundExecutionTask.objects.create(task_name=task_name)
    import sys
    if 'test' in sys.argv:
        run_task_in_thread(task.uuid, func, *args, **kwargs)
    else:
        thread = threading.Thread(
            target=run_task_in_thread,
            args=(task.uuid, func) + args,
            kwargs=kwargs,
            daemon=True
        )
        thread.start()
    return task
