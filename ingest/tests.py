import json

from django.test import Client, TestCase

from ingest import accuracy
from ingest.models import IngestKey, ScoutAccuracy, ScoutingEvent
from teams.models import Team_Match_Data
from vendor.ef_platform_kit import AuthError, NonceCache, PskHmacVerifier, create_envelope, sign_request

URL = "/api/ingest/scouting/"
MATCH = {"event": "2026casj", "match_type": "quals", "match_number": 12}


def delta(seq, team, field, value, op="inc", source="tablet:tab-red1", ts=None):
    return create_envelope("scouting.delta.v1", {**MATCH, "team": team, "field": field, "op": op, "value": value, "scout": "alex"},
                           source=source, seq=seq, ts_src=ts or 1793552400000 + seq)


def commit(seq, team, snapshot, source="tablet:tab-red1", scout="alex", ts=None):
    return create_envelope("scouting.commit.v1", {**MATCH, "team": team, "scout": scout, "snapshot": snapshot},
                           source=source, seq=seq, ts_src=ts or 1793552400000 + seq)


class IngestApiTests(TestCase):
    def setUp(self):
        IngestKey.objects.create(key_id="stands1", secret="s3cret", scopes=["scouting:write", "scouting:read"])
        IngestKey.objects.create(key_id="readonly", secret="ro", scopes=["scouting:read"])

    def post(self, events, key="stands1", secret="s3cret", tamper=False):
        body = json.dumps({"events": events}).encode()
        headers = sign_request(key_id=key, secret=secret, method="POST", target=URL, body=body)
        if tamper:
            body = body.replace(b"2073", b"2074")
        return self.client.post(URL, data=body, content_type="application/json",
                                headers={k: v for k, v in headers.items()})

    def test_commit_lands_in_team_match_data_like_a_qr_scan_and_is_idempotent(self):
        evs = [delta(0, 2073, "autoScore", 1), delta(1, 2073, "autoScore", 1),
               commit(2, 2073, {"teamNumber": 2073, "matchNumber": 12, "comp_code": "2026casj", "name": "alex",
                                "quantifier": "Quals", "autoScore": 2, "autoPass": 0, "autoClimb": 0, "teleScore": 5,
                                "telePass": 0, "endClimb": 0, "shootingAccuracy": 50, "Steal": 0})]
        r = self.post(evs)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(r.json()["accepted"]), 3)
        tmd = Team_Match_Data.objects.get(team_number=2073, event="2026casj", match_number=12, scout_name="alex")
        self.assertEqual(tmd.data["teleScore"], 5.0)
        c = ScoutingEvent.objects.get(pk=evs[2]["id"])
        self.assertEqual(c.commit_status, 200)
        self.assertEqual(c.team_match_data_id, tmd.id)
        again = self.post(evs)
        self.assertEqual(sorted(again.json()["duplicates"]), sorted(e["id"] for e in evs))
        self.assertEqual(ScoutingEvent.objects.count(), 3)

    def test_auth_failures(self):
        ev = [delta(0, 2073, "autoScore", 1)]
        self.assertEqual(self.post(ev, secret="wrong").status_code, 401)
        self.assertEqual(self.post(ev, tamper=True).status_code, 401)
        self.assertEqual(self.post(ev, key="readonly", secret="ro").status_code, 403)
        self.assertEqual(self.client.post(URL, data=b"{}", content_type="application/json").status_code, 401)
        IngestKey.objects.filter(key_id="stands1").update(active=False)
        self.assertEqual(self.post(ev).status_code, 401)

    def test_bad_events_rejected_individually(self):
        good = delta(0, 2073, "autoScore", 1)
        bad_type = {**delta(1, 2073, "x", 1), "type": "scouting.other.v1"}
        bad_team = delta(2, 2073, "x", 1); bad_team["payload"]["team"] = -5
        r = self.post([good, bad_type, bad_team]).json()
        self.assertEqual(r["accepted"], [good["id"]])
        self.assertEqual(len(r["rejected"]), 2)

    def test_invalid_commit_is_recorded_not_retried(self):
        ev = commit(0, 2073, {"teamNumber": "not-a-number"})
        r = self.post([ev]).json()
        self.assertEqual(r["accepted"], [ev["id"]])
        self.assertEqual(ScoutingEvent.objects.get(pk=ev["id"]).commit_status, 400)

    def test_game_config_endpoint(self):
        target = "/api/ingest/game-config/"
        h = sign_request(key_id="readonly", secret="ro", method="GET", target=target, body=b"")
        r = self.client.get(target, headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertIn("metrics", r.json())


class AccuracyTests(TestCase):
    def _store(self, env):
        p = env["payload"]
        ScoutingEvent.objects.create(id=env["id"], type=env["type"], source=env["source"], seq=env["seq"], event=p["event"],
                                     match_type=p["match_type"], match_number=p["match_number"], team=p["team"],
                                     scout=p.get("scout", ""), field=p.get("field", ""), op=p.get("op", ""),
                                     value=p.get("value"), payload=p, ts_src=env["ts_src"])

    def test_delta_vs_commit_flags_typed_in_totals(self):
        for i in range(3):
            self._store(delta(i, 2073, "teleScore", 1))
        self._store(commit(3, 2073, {"teleScore": 10}))  # tapped 3, submitted 10
        accuracy.delta_vs_commit("2026casj")
        row = ScoutAccuracy.objects.get(method="delta_vs_commit", team=2073, metric="teleScore")
        self.assertEqual((row.scouted, row.reference, row.error), (10.0, 3.0, 7.0))
        self.assertEqual(ScoutAccuracy.objects.get(metric="__summary__").scouted, 1.0)

    def test_alliance_vs_tba_with_mapping(self):
        self._store(commit(0, 2073, {"autoScore": 4}, source="tablet:a", scout="a"))
        self._store(commit(0, 254, {"autoScore": 6}, source="tablet:b", scout="b"))
        self._store(commit(1, 254, {"autoScore": 8}, source="tablet:c", scout="c"))  # second scout on 254 → averaged
        fake = {"alliances": {"red": {"team_keys": ["frc2073", "frc254", "frc1678"]}, "blue": {"team_keys": ["frc1", "frc2", "frc3"]}},
                "score_breakdown": {"red": {"autoFuelCount": 12}, "blue": {"autoFuelCount": 3}}}
        out = accuracy.alliance_vs_tba("2026casj", [{"metric": "autoScore", "breakdown_field": "autoFuelCount"}],
                                       lambda key: fake if key == "2026casj_qm12" else None)
        self.assertEqual(out["rows"], 1)
        row = ScoutAccuracy.objects.get(method="alliance_vs_tba", alliance="red")
        self.assertEqual((row.scouted, row.reference, row.error), (11.0, 12.0, -1.0))
        self.assertEqual(row.details["covered"], [2073, 254])
        self.assertIn("skipped", accuracy.alliance_vs_tba("2026casj", [], lambda k: None))


def scan(team, match, data, comp_code="2026casj"):
    """A minimal valid QR snapshot (the scout name comes from the envelope)."""
    return {"teamNumber": team, "matchNumber": match, "comp_code": comp_code, **data}


class IngestCommitResultTests(TestCase):
    """Double scouting and the per-commit `commits` map the mini computer reads after Send Data."""

    def setUp(self):
        IngestKey.objects.create(key_id="stands1", secret="s3cret", scopes=["scouting:write", "scouting:read"])

    def post(self, events):
        body = json.dumps({"events": events}).encode()
        headers = sign_request(key_id="stands1", secret="s3cret", method="POST", target=URL, body=body)
        return self.client.post(URL, data=body, content_type="application/json", headers=headers)

    def test_double_scouting_keeps_one_row_per_scout(self):
        a = commit(0, 2073, scan(2073, 12, {"autoScore": 1}), source="tablet:a", scout="A")
        b = commit(0, 2073, scan(2073, 12, {"autoScore": 2}), source="tablet:b", scout="B")
        r = self.post([a, b])
        self.assertEqual(r.status_code, 200, r.content)
        rows = Team_Match_Data.objects.filter(team_number=2073, event="2026casj", match_number=12)
        self.assertEqual(sorted(rows.values_list("scout_name", flat=True)), ["A", "B"])

        a2 = commit(1, 2073, scan(2073, 12, {"autoScore": 7}), source="tablet:a", scout="A")
        self.assertEqual(self.post([a2]).json()["commits"], {a2["id"]: {"status": 200}})
        self.assertEqual(rows.count(), 2)
        self.assertEqual(rows.get(scout_name="A").data["autoScore"], 7.0)
        self.assertEqual(rows.get(scout_name="B").data["autoScore"], 2.0)

    def test_commits_field(self):
        good = commit(0, 2073, scan(2073, 12, {"autoScore": 1}))
        bad = commit(1, 2073, scan(2073, 12, {}, comp_code="bad code!"))
        d = delta(2, 2073, "autoScore", 1)
        r = self.post([good, bad, d]).json()
        self.assertEqual(r["accepted"], [good["id"], bad["id"], d["id"]])
        self.assertEqual(r["duplicates"], [])
        self.assertEqual(r["rejected"], [])
        # This repo's validate_scan_data() rejects the code before process_scan's own regex, so the error the
        # stands machine sees is the same one a QR scan of this payload would show.
        self.assertEqual(r["commits"], {
            good["id"]: {"status": 200},
            bad["id"]: {"status": 400,
                        "error": "Competition code must contain 1 to 16 letters, digits, underscores or hyphens"},
        })
        self.assertNotIn(d["id"], r["commits"])

        again = self.post([good, bad, d]).json()
        self.assertEqual(sorted(again["duplicates"]), sorted([good["id"], bad["id"], d["id"]]))
        self.assertEqual((again["accepted"], again["commits"]), ([], {}))

    def test_snapshot_is_not_rejected_on_tablet_clock(self):
        # ts_src is the tablet clock (known to be ~13 months off): stored, never used to validate.
        ev = commit(0, 2073, scan(2073, 12, {"autoScore": 1}), ts=1700000000000)
        r = self.post([ev]).json()
        self.assertEqual(r["commits"], {ev["id"]: {"status": 200}})
        self.assertEqual(ScoutingEvent.objects.get(pk=ev["id"]).ts_src, 1700000000000)


class CrossLanguageSignatureTests(TestCase):
    """A request signed by the replay system's JavaScript signer must verify here."""

    NOW = 1793800000000 + 1000
    HEADERS = {
        "X-EF-Key-Id": "interop-test-key",
        "X-EF-Timestamp": "1793800000000",
        "X-EF-Nonce": "0123456789abcdef0123456789abcdef",
        "X-EF-Content-SHA256": "24de1c4a19c43ad41b013f13dcd858c17b0daa7f33a53f19913e5b11366d1c2e",
        "Authorization": "EF1-HMAC-SHA256 Signature=0b7519147c2acb29c15319d5f9fb3801e8532019acc2d3c0950f81899eaafd77",
    }

    def verifier(self, now):
        def lookup(key_id):
            if key_id != "interop-test-key":
                return None
            return {"secret": "interop-test-secret-not-for-production",
                    "principal": {"sub": key_id, "kind": "device", "scopes": ["scouting:write"]}}
        return PskHmacVerifier(lookup, nonce_cache=NonceCache(), now=lambda: now)

    def authenticate(self, now):
        return self.verifier(now).authenticate(method="POST", target="/api/ingest/scouting/",
                                               headers=dict(self.HEADERS), raw_body=b'{"events":[]}')

    def test_js_signature_verifies(self):
        principal = self.authenticate(self.NOW)
        self.assertEqual(principal["sub"], "interop-test-key")
        self.assertEqual(principal["authn"]["strategy"], "psk-hmac")

    def test_js_signature_outside_skew_is_rejected(self):
        with self.assertRaisesRegex(AuthError, "skew"):
            self.authenticate(self.NOW + 3600 * 1000)


class IngestNoLoginTests(TestCase):
    """Machine endpoints answer 401 JSON (never the Google-login redirect) and need no CSRF cookie."""

    def setUp(self):
        IngestKey.objects.create(key_id="stands1", secret="s3cret", scopes=["scouting:write", "scouting:read"])

    def assert_401_json(self, r):
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r["Content-Type"], "application/json")
        self.assertIn("error", r.json())

    def test_unsigned_requests_get_401_json(self):
        self.assert_401_json(self.client.post(URL, data=b'{"events":[]}', content_type="application/json"))
        self.assert_401_json(self.client.get("/api/ingest/game-config/"))

    def test_signed_post_needs_no_csrf_cookie(self):
        client = Client(enforce_csrf_checks=True)
        body = json.dumps({"events": [delta(0, 2073, "autoScore", 1)]}).encode()
        headers = sign_request(key_id="stands1", secret="s3cret", method="POST", target=URL, body=body)
        r = client.post(URL, data=body, content_type="application/json", headers=headers)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(r.json()["accepted"]), 1)

    def test_live_host_is_allowed(self):
        r = self.client.get("/api/ingest/game-config/", HTTP_HOST="scouts.chrisccluk.live", secure=True)
        self.assert_401_json(r)
