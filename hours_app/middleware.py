import logging

from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


class HoursAuthMiddleware:
    """
    Bridges the scouting backend's session-based auth to Django's User system.
    When request.session has 'email' but request.user is anonymous,
    looks up (or creates) the matching Django User and sets request.user.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            email = request.session.get('email')
            name = request.session.get('name', '')
            if email:
                try:
                    user = User.objects.filter(email__iexact=email).first()
                    if not user:
                        username = email.split('@')[0]
                        if User.objects.filter(username=username).exists():
                            username = email.replace('@', '_at_')
                        parts = name.split(' ', 1) if name else ['', '']
                        user, created = User.objects.get_or_create(
                            username=username,
                            defaults={
                                'email': email,
                                'first_name': parts[0],
                                'last_name': parts[1] if len(parts) > 1 else '',
                            },
                        )
                        if created:
                            # Match create_user()'s behavior: no usable password (OAuth-only account).
                            user.set_unusable_password()
                            user.save(update_fields=['password'])
                    elif name and not user.first_name:
                        parts = name.split(' ', 1)
                        user.first_name = parts[0]
                        user.last_name = parts[1] if len(parts) > 1 else ''
                        user.save(update_fields=['first_name', 'last_name'])
                    request.user = user
                except Exception:
                    logger.exception("HoursAuthMiddleware failed to resolve/create user for email=%s", email)
        return self.get_response(request)
