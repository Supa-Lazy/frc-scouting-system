import re

from django.http import JsonResponse

from helpers import login_required
from teams.models import Team_Match_Data


@login_required
def get_broken_alerts(request):
    comp_code = request.GET.get('comp', '')
    try:
        since_id = int(request.GET.get('since_id', 0))
    except (ValueError, TypeError):
        since_id = 0

    # Return empty payload for missing or testing comp codes
    if not comp_code or comp_code == 'testing':
        return JsonResponse({'alerts': [], 'latest_id': 0})

    # Validate comp_code to prevent injection / unexpected values
    if not re.match(r'^[A-Za-z0-9_\-]{1,20}$', comp_code):
        return JsonResponse({'alerts': [], 'latest_id': 0})

    matches = (
        Team_Match_Data.objects
        .filter(event=comp_code, is_broken=True, id__gt=since_id)
        .order_by('id')[:20]
    )

    alerts = [
        {
            'id': m.id,
            'team_number': m.team_number,
            'match_number': m.match_number,
            'scout_name': m.scout_name,
            'quantifier': m.quantifier,
        }
        for m in matches
    ]

    latest_id = alerts[-1]['id'] if alerts else since_id

    return JsonResponse({'alerts': alerts, 'latest_id': latest_id})
