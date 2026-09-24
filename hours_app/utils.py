# hours_app/utils.py
from django.core.mail import send_mail
from django.conf import settings

def send_reminder_email(recipient_email, subject, message):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        print(f"DEBUG: Email sent successfully to {recipient_email}")
        return True
    except Exception as e:
        print(f"EMAIL ERROR: {str(e)}")
        return False