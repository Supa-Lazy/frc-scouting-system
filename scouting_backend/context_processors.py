from utils import config_loader
from authenticate.models import SiteSettings, AuthorizedUser

def config_context(request):
    """Make config values available in all templates"""
    config = config_loader.get_config()
    try:
        settings = SiteSettings.objects.first()
    except Exception:
        settings = None

    # Resolve is_admin: use cached session value if present, otherwise check DB.
    # This handles existing sessions that predate the is_admin session key.
    is_admin = request.session.get('is_admin')
    if is_admin is None:
        email = request.session.get('email')
        if email:
            try:
                is_admin = AuthorizedUser.objects.filter(email=email).exists()
            except Exception:
                is_admin = False
            # Cache it so subsequent requests skip the DB query
            request.session['is_admin'] = is_admin
        else:
            is_admin = False

    role = request.session.get('role')
    if role is None:
        email = request.session.get('email')
        if email:
            try:
                au = AuthorizedUser.objects.filter(email=email).first()
                role = au.roles if au else 'student'
            except Exception:
                role = 'student'
            request.session['role'] = role
        else:
            role = None

    return {
        'app_name': config.get('app_name', 'Scouting System'),
        'team_name': config.get('team_name', 'Team'),
        'theme_color': (settings.theme_color if settings and settings.theme_color else config.get('theme_color', '#e74c3c')),
        'logo_url': (settings.logo_url if settings and settings.logo_url else config.get('logo_url', '/static/images/logo.png')),
        'is_admin': is_admin,
        'role': role,
        # Roles are stored comma-separated (e.g. "scout_tech,strategist").
        # helpers.role_required() splits them, so templates must too — an exact
        # `role == 'scout_tech'` check hides nav links from multi-role users who
        # can actually open the page.
        'roles': [r.strip() for r in role.split(',') if r.strip()] if role else [],
    }
