from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Invoked just before a user logs in via a social provider.
        We use this to skip the signup page if the email already exists.
        """
        # 1. Social login hasn't happened yet, so sociallogin.user is a "ghost" user
        if sociallogin.is_existing:
            return

        # 2. Check if we have an email from Google
        email = sociallogin.account.extra_data.get('email')
        if not email:
            return

        # 3. Find if a user already exists with this email
        try:
            existing_user = User.objects.get(email__iexact=email)
            # Link the social account to the existing user automatically
            sociallogin.connect(request, existing_user)
        except User.DoesNotExist:
            # If user doesn't exist, Allauth will create them automatically
            # because of SOCIALACCOUNT_AUTO_SIGNUP = True in settings.py
            pass

    def save_user(self, request, sociallogin, form=None):
        """
        Forces the user to be active immediately upon creation.
        """
        user = super().save_user(request, sociallogin, form)
        user.is_active = True
        user.save()
        return user