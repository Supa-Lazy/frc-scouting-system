import os

import requests
from django.core.cache import cache

from utils import config_loader

TEAM_KEY = "frc2073"
X_TBA_Auth_Key = os.environ.get("X_TBA_AUTH_KEY")

TEAM_EVENTS_CACHE_TTL = 300  # seconds


def get_team_events():
    config = config_loader.get_config()
    year = str(config.get('year', 2025))
    cache_key = f"tba_team_events_{year}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    events = {}
    try:
        resp = requests.get(f"https://www.thebluealliance.com/api/v3/team/{TEAM_KEY}/events/{year}",
                            headers={"X-TBA-Auth-Key": X_TBA_Auth_Key},
                            timeout=10)
    except requests.exceptions.RequestException:
        events["testing"] = "Training"
        return events

    # If the API didn't return success, return a sensible default
    if resp.status_code != 200:
        events["testing"] = "Training"
        return events

    try:
        data = resp.json()
    except ValueError:
        # Non-JSON response (e.g., HTML error page)
        events["testing"] = "Training"
        return events

    # Some responses may be a dict with an error message or a string; normalize to list
    if isinstance(data, dict) and data.get("message"):
        events["testing"] = "Training"
        return events

    if not isinstance(data, list):
        data = [data]

    for event in data:
        # Support both dict entries (normal API) and string entries (fallbacks)
        if isinstance(event, dict):
            key = event.get("key")
            name = event.get("name")
            if key and name:
                events[key] = name
        elif isinstance(event, str):
            events[event] = event

    events["testing"] = "Training"

    # Manual addition of data, MUST wait until TBA adds these events
    # to their website or else the API will break... (do I "NEED" to make this a dynamic loader?)

    cache.set(cache_key, events, TEAM_EVENTS_CACHE_TTL)
    return events


def get_match_schedule(event_key):
    try:
        matches_at_event = requests.get(f"https://www.thebluealliance.com/api/v3/event/{event_key}/matches/simple",
                                        headers={"X-TBA-Auth-Key": X_TBA_Auth_Key},
                                        timeout=10).json()
    except requests.exceptions.RequestException:
        return []
    return matches_at_event


def get_teams_list(event_key):
    try:
        resp = requests.get(f"https://www.thebluealliance.com/api/v3/event/{event_key}/teams/simple",
                            headers={"X-TBA-Auth-Key": X_TBA_Auth_Key},
                            timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def get_single_match(event_key, match_id):
    match_key = event_key + "_" + match_id
    try:
        response = requests.get(f"https://www.thebluealliance.com/api/v3/match/{match_key}/simple",
                               headers={"X-TBA-Auth-Key": X_TBA_Auth_Key},
                               timeout=10)
        
        if response.status_code != 200:
            return None
        
        raw_match = response.json()
        
        # Check if alliances data exists
        if not raw_match or 'alliances' not in raw_match:
            return None
        
        match = {"red": [], "blue": []}
        for red_team in raw_match["alliances"]["red"]["team_keys"]:
            match["red"].append(red_team.split("frc")[1])
        for blue_team in raw_match["alliances"]["blue"]["team_keys"]:
            match["blue"].append(blue_team.split("frc")[1])

        return match
    except (KeyError, ValueError, requests.RequestException):
        return None


def get_team_avatar(team_key: str, year: int) -> 'str | None':
    """Fetch the TBA avatar for a team and return a base64 data URI, or None."""
    try:
        resp = requests.get(
            f"https://www.thebluealliance.com/api/v3/team/{team_key}/media/{year}",
            headers={"X-TBA-Auth-Key": X_TBA_Auth_Key},
            timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, list):
            return None
        for item in data:
            if isinstance(item, dict) and item.get("type") == "avatar":
                b64 = item.get("details", {}).get("base64Image")
                if b64:
                    return "data:image/png;base64," + b64
        return None
    except Exception:
        return None


def get_event_rankings(event_key):
    """Return {team_number: rank} for all ranked teams at an event."""
    try:
        resp = requests.get(
            f"https://www.thebluealliance.com/api/v3/event/{event_key}/rankings",
            headers={"X-TBA-Auth-Key": X_TBA_Auth_Key},
            timeout=10)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        if not isinstance(data, dict) or 'rankings' not in data:
            return {}
        result = {}
        for entry in data['rankings']:
            key = entry.get('team_key', '')
            rank = entry.get('rank')
            if key.startswith('frc') and rank is not None:
                result[int(key[3:])] = rank
        return result
    except Exception:
        return {}


def get_match_videos(event_key):
    """Return {match_key: youtube_video_key} for all matches at an event."""
    try:
        resp = requests.get(
            f"https://www.thebluealliance.com/api/v3/event/{event_key}/matches",
            headers={"X-TBA-Auth-Key": X_TBA_Auth_Key},
            timeout=15)
        if resp.status_code != 200:
            return {}
        matches = resp.json()
        if not isinstance(matches, list):
            return {}
        videos = {}
        for m in matches:
            for v in m.get('videos', []):
                if v.get('type') == 'youtube':
                    videos[m['key']] = v['key']
                    break
        return videos
    except Exception:
        return {}
