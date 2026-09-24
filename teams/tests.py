import io
from unittest.mock import patch

from PIL import Image

from django.test import TestCase, Client

# Create your tests here.
from django.urls import reverse, resolve
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import Teams
from .views import display_teams, team_page


def _make_png_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (2, 2), color=(255, 0, 0)).save(buf, format='PNG')
    return buf.getvalue()


class TeamTests(TestCase):

    def setUp(self):
        # Create a team for the testing event and mark the test client as logged in
        self.client.defaults['HTTP_HOST'] = 'localhost'
        # Ensure requests are secure to avoid SECURE_SSL_REDIRECT during tests
        self.client.defaults['wsgi.url_scheme'] = 'https'
        self.team = Teams.objects.create(team_number=2073, event='testing')
        session = self.client.session
        session['email'] = 'test@team2073.com'
        session.save()

        teams_page_url = reverse('teams')
        # Follow redirects (tests run with SECURE_SSL_REDIRECT enabled in test mode)
        self.response = self.client.get(teams_page_url, follow=True)

    # Teams Display
    def test_teams_view_success_status_code(self):
        self.assertEqual(self.response.status_code, 200)

    def test_teams_url_resolves_teams_view(self):
        teams_view = resolve('/teams/')
        self.assertEqual(teams_view.func, display_teams)

    def test_teams_contains_link_to_team_page(self):
        team_page_url = reverse('team_page', kwargs={'team_number': self.team.team_number})
        self.assertContains(self.response, 'href="{0}"'.format(team_page_url))

    # TEST-010: login_required rejects requests with no session at all.
    def test_teams_view_requires_login_when_no_session(self):
        anon_client = Client()
        anon_client.defaults['HTTP_HOST'] = 'localhost'
        anon_client.defaults['wsgi.url_scheme'] = 'https'
        response = anon_client.get(reverse('teams'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/auth/')

    # Teams Page
    def test_team_page_view_success_status_code(self):
        url = reverse('team_page', kwargs={'team_number': self.team.team_number}) + '?comp=testing'
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        # TEST-009: prove real team content actually rendered, not just a 200 on an
        # empty/broken page. "Team 2073" only appears (via the Title block) when the
        # team_number context var made it all the way to the template.
        self.assertContains(response, 'Team {0}'.format(self.team.team_number))

    def test_team_page_view_auto_creates_team_for_unknown_number(self):
        # Renamed from test_team_page_view_not_found_status_code (TEST-012): the name
        # used to claim this tested a 404, but the assertion (and the comment right
        # below it) confirms the view auto-creates the Teams row instead of 404ing.
        url = reverse('team_page', kwargs={'team_number': 0}) + '?comp=testing'
        response = self.client.get(url, follow=True)
        # The current implementation creates the team record when comp is provided,
        # so expect a successful response rather than a 404.
        self.assertEqual(response.status_code, 200)
        # TEST-009: assert on the actual auto-created row and rendered content.
        self.assertTrue(Teams.objects.filter(team_number=0, event='testing').exists())
        self.assertContains(response, 'Team 0')

    def test_team_page_url_resolves_teams_page_view(self):
        view = resolve('/teams/2073/')
        self.assertEqual(view.func, team_page)


class ClearPitDataTests(TestCase):
    """TEST-002: clear_pit_data is an irreversible, single-click wipe of pit data."""

    def setUp(self):
        self.client.defaults['HTTP_HOST'] = 'localhost'
        self.client.defaults['wsgi.url_scheme'] = 'https'
        session = self.client.session
        session['email'] = 'test@team2073.com'
        session.save()

        self.team = Teams.objects.create(
            team_number=4909,
            event='testing',
            pit_data={'drivetrain': 'Swerve'},
            pit_scout_status=True,
            robot_picture='https://res.cloudinary.com/demo/image/upload/robot.png',
        )
        self.other_event_team = Teams.objects.create(
            team_number=4909,
            event='otherevent',
            pit_data={'drivetrain': 'Tank'},
            pit_scout_status=True,
            robot_picture='https://res.cloudinary.com/demo/image/upload/other.png',
        )

    def _url(self):
        return reverse('clear_pit_data', kwargs={'team_number': self.team.team_number})

    def test_valid_post_wipes_matching_team_pit_data(self):
        response = self.client.post(self._url(), data={'comp_code': 'testing'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/teams/4909/?comp=testing')

        self.team.refresh_from_db()
        self.assertEqual(self.team.pit_data, {})
        self.assertFalse(self.team.pit_scout_status)
        self.assertIsNone(self.team.robot_picture)

        # Different event's row for the same team number must be untouched.
        self.other_event_team.refresh_from_db()
        self.assertEqual(self.other_event_team.pit_data, {'drivetrain': 'Tank'})
        self.assertTrue(self.other_event_team.pit_scout_status)

    def test_mismatched_comp_code_leaves_data_untouched(self):
        # 'otherevent' is a validly-formatted comp code, but it doesn't match this
        # team's actual event row for team 4909/testing — the guard must not wipe
        # a different event's data by accident.
        response = self.client.post(self._url(), data={'comp_code': 'otherevent'})
        self.assertEqual(response.status_code, 302)

        self.team.refresh_from_db()
        self.assertEqual(self.team.pit_data, {'drivetrain': 'Swerve'})
        self.assertTrue(self.team.pit_scout_status)
        self.assertIsNotNone(self.team.robot_picture)

    def test_invalid_comp_code_format_is_a_no_op(self):
        # Fails the _SAFE_COMP_CODE regex entirely (contains a space/slash).
        response = self.client.post(self._url(), data={'comp_code': 'bad code/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/teams/4909/')

        self.team.refresh_from_db()
        self.assertEqual(self.team.pit_data, {'drivetrain': 'Swerve'})
        self.assertTrue(self.team.pit_scout_status)

    def test_get_request_does_not_wipe_data(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

        self.team.refresh_from_db()
        self.assertEqual(self.team.pit_data, {'drivetrain': 'Swerve'})
        self.assertTrue(self.team.pit_scout_status)
        self.assertIsNotNone(self.team.robot_picture)


class PitScoutingUploadTests(TestCase):
    """TEST-008: pit-scouting upload path (Cloudinary image + dynamic question validation)."""

    def setUp(self):
        self.client.defaults['HTTP_HOST'] = 'localhost'
        self.client.defaults['wsgi.url_scheme'] = 'https'
        session = self.client.session
        session['email'] = 'test@team2073.com'
        session.save()
        self.team_number = 5555

    def _valid_payload(self):
        return {
            'drivetrain': 'Swerve',
            'weight': '110',
            'length': '30',
            'width': '30',
            'Volume': '50',
            'Shooter': ['Turret'],
            'intake_design': ['Over the Bumper'],
            'Hopper': 'Yes',
            'auto_positions': ['1', '2'],
            'auto_fuel_max': '10',
            'auto_hang': 'Yes',
            'intake_locations': ['Ground'],
            'shooting_distance': ['Middle'],
            'tower_positions': ['Left'],
            'tower_levels': ['L2'],
            'trench': 'No',
            'Bump': 'No',
        }

    @patch('cloudinary.uploader.upload')
    def test_pit_scouting_post_saves_pit_data_and_picture(self, mock_upload):
        mock_upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/test.png'
        }
        url = reverse('pit_scouting', kwargs={'team_number': self.team_number}) + '?comp=testing'
        payload = self._valid_payload()
        payload['robot_picture'] = SimpleUploadedFile(
            'robot.png', _make_png_bytes(), content_type='image/png'
        )

        response = self.client.post(url, data=payload, follow=True)

        self.assertEqual(response.status_code, 200)
        mock_upload.assert_called_once()

        team = Teams.objects.get(team_number=self.team_number, event='testing')
        self.assertTrue(team.pit_scout_status)
        self.assertEqual(team.pit_data.get('drivetrain'), 'Swerve')
        self.assertEqual(team.pit_data.get('weight'), '110')
        self.assertIn('Turret', team.pit_data.get('Shooter'))
        self.assertTrue(str(team.robot_picture).startswith('https://res.cloudinary.com'))

    @patch('cloudinary.uploader.upload')
    def test_pit_scouting_missing_required_field_is_rejected_without_saving(self, mock_upload):
        url = reverse('pit_scouting', kwargs={'team_number': self.team_number}) + '?comp=testing'
        payload = self._valid_payload()
        del payload['drivetrain']  # required select field omitted

        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 200)  # re-renders form with errors, not a redirect
        mock_upload.assert_not_called()
        team = Teams.objects.filter(team_number=self.team_number, event='testing').first()
        self.assertIsNotNone(team)
        self.assertFalse(team.pit_scout_status)
