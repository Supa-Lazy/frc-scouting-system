import json

from django.test import TestCase
from django.urls import reverse

# Create your tests here.
from strategy.models import PickList_Data
from strategy.views import fetch_team_match_averages
from teams.models import Team_Match_Data


class PicklistSubmitTests(TestCase):
    """Picklist autosaves and manual saves persist through the database."""

    COMP_CODE = 'testpicklist2026'

    def setUp(self):
        self.client.defaults['HTTP_HOST'] = 'localhost'
        self.client.defaults['wsgi.url_scheme'] = 'https'
        session = self.client.session
        session['email'] = 'strategist@team2073.com'
        session['role'] = 'strategist'
        session.save()

    def _url(self, save_to_db=True):
        qs = f'?comp={self.COMP_CODE}'
        if save_to_db:
            qs += '&save_to_db=true'
        return reverse('picklist_submit') + qs

    def test_valid_payload_is_saved_to_database_without_filesystem_storage(self):
        payload = [[1], [2, 3], [], [], []]
        response = self.client.post(
            self._url(save_to_db=False),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

        row = PickList_Data.objects.get(event=self.COMP_CODE)
        self.assertEqual(row.no_pick, [1])
        self.assertEqual(row.first_pick, [2, 3])
        self.assertEqual(row.second_pick, [])
        self.assertEqual(row.third_pick, [])
        self.assertEqual(row.dn_pick, [])

        sync_response = self.client.get(self._url(False) + '&timestamp=0')
        self.assertEqual(sync_response.json()['status'], 'updated')
        self.assertEqual(sync_response.json()['data'], payload)

    def test_malformed_payload_returns_400_and_does_not_create_database_row(self):
        # Wrong length (3 slots instead of exactly 5) — locks in the FUNC-006 fix:
        # this must be rejected cleanly, not raise an unhandled IndexError/500, and
        # must not create a database row before validating.
        payload = [[1], [2], [3]]
        response = self.client.post(
            self._url(save_to_db=True),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'error')

        self.assertFalse(PickList_Data.objects.filter(event=self.COMP_CODE).exists())

    def test_non_list_payload_returns_400_without_creating_a_database_row(self):
        payload = {'not': 'a list'}
        response = self.client.post(
            self._url(save_to_db=True),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PickList_Data.objects.filter(event=self.COMP_CODE).exists())


class DoubleScoutedMatchAveragingTests(TestCase):
    """
    A match scouted by two people must count once.

    Before this, both scouting rows fed the average directly, so a
    double-scouted match pulled the mean toward whatever those two scouts saw
    and counted twice against every singly-scouted match.
    """

    COMP_CODE = 'testavg2026'

    def _match(self, match_number, scout, tele_score, driver=0):
        return Team_Match_Data.objects.create(
            team_number=1234,
            event=self.COMP_CODE,
            match_number=match_number,
            scout_name=scout,
            quantifier='Quals',
            driverRanking=driver,
            data={'teleScore': tele_score},
        )

    def test_double_scouted_match_counts_once(self):
        # Match 1 seen by two scouts who disagree; matches 2 and 3 seen by one.
        self._match(1, 'alice', 10)
        self._match(1, 'bob', 20)
        self._match(2, 'alice', 30)
        self._match(3, 'alice', 50)

        result = fetch_team_match_averages(1234, self.COMP_CODE, 'Quals')

        # Match 1 collapses to (10+20)/2 = 15, then (15+30+50)/3 = 31.667.
        # Averaging the four rows directly would have given 27.5.
        self.assertAlmostEqual(result['teleScore'], 31.667, places=2)

    def test_match_count_is_distinct_matches_not_rows(self):
        self._match(1, 'alice', 10)
        self._match(1, 'bob', 20)
        self._match(2, 'alice', 30)

        result = fetch_team_match_averages(1234, self.COMP_CODE, 'Quals')

        self.assertEqual(result['match_count'], 2)

    def test_scout_who_left_field_blank_is_not_counted_as_zero(self):
        # Only one of the two scouts recorded teleScore for match 1.
        self._match(1, 'alice', 10)
        Team_Match_Data.objects.create(
            team_number=1234,
            event=self.COMP_CODE,
            match_number=1,
            scout_name='bob',
            quantifier='Quals',
            data={'autoScore': 5},          # no teleScore key at all
        )

        result = fetch_team_match_averages(1234, self.COMP_CODE, 'Quals')

        # The blank must not drag the match down to (10+0)/2 = 5.
        self.assertAlmostEqual(result['teleScore'], 10.0, places=2)

    def test_agreeing_scouts_leave_the_average_unchanged(self):
        # When both scouts record the same value, collapsing is a no-op.
        self._match(1, 'alice', 20)
        self._match(1, 'bob', 20)
        self._match(2, 'alice', 40)

        result = fetch_team_match_averages(1234, self.COMP_CODE, 'Quals')

        self.assertAlmostEqual(result['teleScore'], 30.0, places=2)


class PicklistFlagsTests(TestCase):
    """Star and strike persist per team and survive a column change."""

    COMP_CODE = 'testflags2026'

    def setUp(self):
        self.client.defaults['HTTP_HOST'] = 'localhost'
        self.client.defaults['wsgi.url_scheme'] = 'https'
        session = self.client.session
        session['email'] = 'strategist@team2073.com'
        session['role'] = 'strategist'
        session['is_admin'] = True
        session.save()

    def _post(self, payload):
        return self.client.post(
            reverse('picklist_flags') + '?comp=' + self.COMP_CODE,
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_star_is_stored_and_toggles_off(self):
        response = self._post({'flag': 'starred', 'team': '1234', 'on': True})
        self.assertEqual(response.status_code, 200)
        self.assertIn('1234', response.json()['flags']['starred'])

        response = self._post({'flag': 'starred', 'team': '1234', 'on': False})
        self.assertNotIn('1234', response.json()['flags']['starred'])

    def test_strike_is_independent_of_star(self):
        self._post({'flag': 'starred', 'team': '1234', 'on': True})
        response = self._post({'flag': 'struck', 'team': '1234', 'on': True})
        flags = response.json()['flags']
        self.assertIn('1234', flags['starred'])
        self.assertIn('1234', flags['struck'])

    def test_unknown_flag_is_rejected(self):
        response = self._post({'flag': 'sabotage', 'team': '1234', 'on': True})
        self.assertEqual(response.status_code, 400)

    def test_non_numeric_team_is_rejected(self):
        response = self._post({'flag': 'starred', 'team': 'DROP TABLE', 'on': True})
        self.assertEqual(response.status_code, 400)

    def test_flag_survives_the_team_moving_between_columns(self):
        self._post({'flag': 'struck', 'team': '1234', 'on': True})
        # Saving the board is a separate write path; it must not clear flags.
        self.client.post(
            reverse('picklist_submit') + '?comp=' + self.COMP_CODE + '&save_to_db=true',
            data=json.dumps([[], ['1234'], [], [], []]),
            content_type='application/json',
        )
        row = PickList_Data.objects.get(event=self.COMP_CODE)
        self.assertEqual([str(t) for t in row.struck], ['1234'])
        self.assertEqual([str(t) for t in row.first_pick], ['1234'])
