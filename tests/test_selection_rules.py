import math
import unittest
from datetime import datetime
from unittest.mock import patch

from codeforcesContest import CodeforcesContest, clear_user_status_cache
from codeforcesGymContest import CodeforcesGymContest
from contestDates import ContestDates, getTimestamp
from ranking import Ranking


USERS = {"Alice": {"codeforces-handle": "alice", "atcoder-handle": "alice"}}


class ContestSelectionTests(unittest.TestCase):
    def test_selection_dates_use_berlin_time_in_summer_and_winter(self):
        for local_date, aware_date in (
            ("11.10.2026:23.59.59", "2026-10-11T23:59:59+02:00"),
            ("01.11.2026:00.00.00", "2026-11-01T00:00:00+01:00"),
        ):
            with self.subTest(local_date=local_date):
                self.assertEqual(
                    getTimestamp(local_date),
                    datetime.fromisoformat(aware_date).timestamp(),
                )

    def test_cf_selection_respects_inclusive_window_and_eligibility(self):
        def contest(contest_id, start, name="Codeforces Round 100 (Div. 2)"):
            return {"id": contest_id, "startTimeSeconds": start, "name": name}

        available = [
            contest(2261, 999),
            contest(2277, 2001),
            contest(3000, 1000),
            contest(3001, 2000, "Educational Codeforces Round 100"),
            contest(3002, 1500, "Codeforces Global Round 100"),
            contest(3003, 1600, "Codeforces Round 101 (Div. 1)"),
            contest(3004, 1600, "Codeforces Round 101 (Div. 2)"),
            contest(3005, 1700, "Unrelated special event"),
            contest(3006, 1800, "Codeforces Round 102 (Div. 2, unrated)"),
        ]
        with patch("contestDates.cfapi.request", return_value=available):
            # Avoid __init__, which also fetches AtCoder's remote calendar.
            calendar = ContestDates.__new__(ContestDates)
            selected = calendar.getCFContests(1000, 2000)

        self.assertEqual({contest["id"] for contest in selected}, {3000, 3001, 3002})


class RankingSelectionTests(unittest.TestCase):
    def run_ranking(self, dates, onsite, scores):
        class ScoredContest:
            def __init__(self, contest_id, handle_map, display_name=None):
                self.id = contest_id
                self.name = display_name or f"CF{contest_id}"

            def getScore(self, name):
                return scores[self.id]

        ranking = Ranking({"users": USERS, "onsiteGyms": onsite})
        with (
            patch("ranking.ContestDates") as calendar,
            patch("ranking.CodeforcesContest", ScoredContest),
            patch("ranking.AtcoderContest.initSession"),
            patch("ranking.AtcoderContest.endSession"),
            patch("ranking.time.time", return_value=100_000),
        ):
            calendar.return_value.getDates.return_value = dates
            ranking.updateRanking()
        return ranking

    def test_earliest_result_remains_eligible_when_window_has_more_than_twelve(self):
        dates = [
            {"id": 3000 + index, "time": 1000 + index, "type": "codeforces"}
            for index in range(14)
        ]
        scores = {3000 + index: index for index in range(14)}
        scores[3000] = 100
        ranking = self.run_ranking(dates, [], scores)

        self.assertEqual(len(ranking.getContestNames()), 14)
        self.assertEqual(ranking.sortingKey(ranking.getRanking()[0], "Alice"), 136)

    def test_onsite_rounds_are_counted_once_and_use_configured_names(self):
        dates = [
            {"id": 3000, "time": 1000, "type": "codeforces"},
            {"id": 2261, "time": 1500, "type": "codeforces"},
            {"id": 2277, "time": 2000, "type": "codeforces"},
        ]
        onsite = [
            {
                "id": 2261,
                "type": "codeforces",
                "startTime": "1970-01-01T00:25:00+00:00",
                "displayName": "ONSITE 1",
            },
            {
                "id": 2277,
                "type": "codeforces",
                "startTime": "1970-01-01T00:33:20+00:00",
                "displayName": "ONSITE 3",
            },
        ]
        ranking = self.run_ranking(dates, onsite, {3000: 1, 2261: 3, 2277: 4})

        self.assertEqual(ranking.getContestNames(), ["CF3000", "ONSITE 1", "ONSITE 3"])
        self.assertEqual(ranking.getRanking()[0], [1, 6, 8])
        self.assertEqual(ranking.sortingKey(ranking.getRanking()[0], "Alice"), 15)
        self.assertEqual(len(ranking.getDates()), 3)

    def test_disabled_unknown_contest_does_not_fetch_standings(self):
        config = {
            "users": USERS,
            "onsiteGyms": [{"enabled": False, "displayName": "ONSITE 4"}],
        }
        ranking = Ranking(config)
        with (
            patch("ranking.ContestDates") as calendar,
            patch("ranking.AtcoderContest.initSession"),
            patch("ranking.AtcoderContest.endSession"),
            patch("codeforcesApi.request") as api_request,
        ):
            calendar.return_value.getDates.return_value = []
            ranking.updateRanking()

        self.assertEqual(ranking.getContestNames(), [])
        self.assertEqual(ranking.sortingKey(ranking.getRanking()[0], "Alice"), 0)
        api_request.assert_not_called()

    def test_enabled_flag_requires_a_boolean(self):
        for enabled in ("false", 0, None):
            with self.subTest(enabled=enabled):
                ranking = Ranking({
                    "users": USERS,
                    "onsiteGyms": [{"enabled": enabled, "displayName": "ONSITE 4"}],
                })
                with self.assertRaisesRegex(ValueError, "enabled"):
                    ranking._build_onsite_contest_dates()


class ContestScoringTests(unittest.TestCase):
    def setUp(self):
        clear_user_status_cache()
        CodeforcesGymContest._source_distribution_cache.clear()

    def tearDown(self):
        clear_user_status_cache()
        CodeforcesGymContest._source_distribution_cache.clear()

    def test_onsite_name_survives_lazy_standings_load(self):
        standings = {
            "contest": {
                "name": "Codeforces Round 1128 (Div. 1 + Div. 2)",
                "startTimeSeconds": 1000,
            },
            "problems": [{"index": "A"}],
            "rows": [{
                "party": {"members": [{"handle": "alice"}]},
                "problemResults": [{"points": 1}],
            }],
        }
        submissions = [{
            "contestId": 2261,
            "creationTimeSeconds": 1001,
            "author": {"participantType": "CONTESTANT"},
            "verdict": "OK",
            "problem": {"index": "A"},
        }]

        def response(method, params, **kwargs):
            return standings if method == "contest.standings" else submissions

        with patch("codeforcesApi.request", side_effect=response):
            contest = CodeforcesContest(2261, USERS, display_name="ONSITE 1")
            self.assertEqual(contest.name, "ONSITE 1")
            self.assertEqual(contest.getScore("Alice"), 1)
            self.assertEqual(contest.name, "ONSITE 1")

    def test_gym_uses_original_problem_weights_and_ignores_unrated_problem(self):
        gym_standings = {
            "problems": [{"index": label} for label in "ABC"],
            "rows": [{
                "party": {"members": [{"handle": "ALICE"}]},
                "problemResults": [{"points": 1}, {"points": 0}, {"points": 1}],
            }],
        }
        source_standings = {
            "problems": [{"index": label} for label in "AB"],
            "rows": [
                {"problemResults": [{"points": 1}, {"points": 1}]},
                {"problemResults": [{"points": 1}, {"points": 0}]},
                {"problemResults": [{"points": 0}, {"points": 0}]},
            ],
        }

        def response(method, params, **kwargs):
            if params["contestId"] == 724795:
                return gym_standings
            return source_standings

        contest = CodeforcesGymContest(
            724795,
            USERS,
            problem_sources=[
                {"contestId": 9999, "problem": "A"},
                {"contestId": 9999, "problem": "B"},
                None,
            ],
            display_name="ONSITE 2",
            group_code="R7sYOrgVJM",
        )
        with patch("codeforcesApi.request", side_effect=response):
            score = contest.getScore("Alice")

        expected = 1 / (1 + 0.5 * (1 + math.log(2)))
        self.assertAlmostEqual(score, expected)
        self.assertEqual(contest.name, "ONSITE 2")


if __name__ == "__main__":
    unittest.main()
