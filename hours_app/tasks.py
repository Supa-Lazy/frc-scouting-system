# hours_app/tasks.py
from background_task import background
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User

@background()
def send_scheduled_reminder(user_id):
    try:
        user = User.objects.get(pk=user_id)
        if user.email:
            send_mail(
                subject="Eagleforce: Checkout Reminder",
                message=f"Hi {user.first_name},\n\nThis is a reminder to check out of your robotics session. Have a great evening!",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            print(f"SUCCESS: Reminder email sent to {user.email}")
    except Exception as e:
        print(f"TASK ERROR: {e}")