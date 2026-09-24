"""
Simulation view: exposes the Monte Carlo match prediction engine via HTTP.

URL (to be wired by the caller):
    POST /api/simulate/

Request body (JSON):
    {
        "red_teams":  [2073, 254, 1678],
        "blue_teams": [118, 971, 148],
        "comp":       "2025cada",
        "quantifier": "Quals"
    }
"""

import json
import re

from django.http import JsonResponse

from helpers import login_required
from utils import config_loader
from strategy.simulation import simulate_match

_SAFE_COMP_CODE = re.compile(r'^[A-Za-z0-9_\-]{1,20}$')


@login_required
def simulate_match_view(request):
    """Run a Monte Carlo simulation for a given match and return prediction data."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # --- parse body ---
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    # --- validate teams ---
    red_teams  = body.get('red_teams')
    blue_teams = body.get('blue_teams')

    if not isinstance(red_teams, list) or len(red_teams) != 3:
        return JsonResponse(
            {'error': 'red_teams must be a list of exactly 3 team numbers'}, status=400
        )
    if not isinstance(blue_teams, list) or len(blue_teams) != 3:
        return JsonResponse(
            {'error': 'blue_teams must be a list of exactly 3 team numbers'}, status=400
        )

    try:
        red_teams  = [int(t) for t in red_teams]
        blue_teams = [int(t) for t in blue_teams]
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Team numbers must be integers'}, status=400)

    for t in red_teams + blue_teams:
        if not (1 <= t <= 99999):
            return JsonResponse(
                {'error': f'Team number {t} is out of valid range (1–99999)'}, status=400
            )

    # --- validate comp ---
    comp = body.get('comp', '')
    if not comp or not _SAFE_COMP_CODE.match(str(comp)):
        return JsonResponse({'error': 'Invalid or missing comp code'}, status=400)

    # --- validate quantifier ---
    quantifier = body.get('quantifier', 'Quals')
    if quantifier not in ('Quals', 'Playoff', 'Prac'):
        return JsonResponse({'error': 'quantifier must be Quals, Playoff, or Prac'}, status=400)

    # --- run simulation ---
    try:
        config = config_loader.get_config()
        result = simulate_match(
            red_team_numbers=red_teams,
            blue_team_numbers=blue_teams,
            comp_code=comp,
            quantifier=quantifier,
            config=config,
        )
        return JsonResponse(result)
    except Exception as exc:
        return JsonResponse(
            {'error': 'Simulation failed', 'detail': str(exc)},
            status=500,
        )
