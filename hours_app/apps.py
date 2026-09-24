from django.apps import AppConfig

class HoursAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hours_app'

    def ready(self):
        pass