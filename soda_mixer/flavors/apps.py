from django.apps import AppConfig
import sys
import os

class FlavorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'soda_mixer.flavors'

    def ready(self):
        # Prevent running during test execution or migrations
        if any(cmd in sys.argv for cmd in ['test', 'migrate', 'makemigrations', 'showmigrations', 'sqlmigrate']):
            return
            
        # If runserver is used, only run in the main process (RUN_MAIN is set by reload mechanism)
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true':
            return
            
        # Start keep-warm thread
        from .tasks import start_keep_warm_task
        start_keep_warm_task()
