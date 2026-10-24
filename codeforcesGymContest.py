import math

from contest import Contest
import codeforcesApi as cfapi


class CodeforcesGymContest(Contest):
    """Score a Gym from configured original-problem mappings."""

    handleString = "codeforces-handle"
    _source_distribution_cache = {}

    def __init__(
        self,
        contest_id,
        handle_map,
        problem_sources=(),
        display_name=None,
    ):
        super().__init__(contest_id, handle_map)
        self.name = display_name or f"Gym{contest_id}"
        self.problem_sources = self.parse_problem_sources(problem_sources)
        self._scored_problem_indices = set()
        self._source_problem_weights = {}

    @classmethod
    def parse_problem_sources(cls, problem_sources):
        return tuple(
            cls._parse_problem_source(source) for source in problem_sources
        )

    @staticmethod
    def _parse_problem_source(source):
        """Convert one config entry to ``(contest_id, problem_index)``.

        ``None`` marks an unrated Gym problem.
        """
        if source is None:
            return None
        if not isinstance(source, dict):
            raise ValueError("Each problemSources entry must be an object or null.")

        contest_id = source.get("contestId")
        problem_index = source.get("problem")
        if isinstance(contest_id, bool) or not isinstance(contest_id, int):
            raise ValueError("problemSources.contestId must be a positive integer.")
        if contest_id <= 0:
            raise ValueError("problemSources.contestId must be a positive integer.")
        if not isinstance(problem_index, str) or not problem_index.strip():
            raise ValueError("problemSources.problem must be a non-empty string.")
        return contest_id, problem_index.strip()

    def updateScores(self):
        self.handlesSolved = {}
        self.numberSolved = {}
        self._scored_problem_indices = set()
        self._source_problem_weights = {}

        if not self.problem_sources:
            print(f"✗ Gym {self.id} has no problemSources configuration.")
            return False

        print(f"Fetching CF Gym {self.id} through the authenticated API.")
        standings = cfapi.request(
            "contest.standings",
            {
                "contestId": self.id,
                "participantTypes": "CONTESTANT",
            },
            authenticated=True,
        )
        if not isinstance(standings, dict):
            print(f"✗ Could not fetch Gym {self.id}.")
            return False
        if not self._parse_gym_standings(standings):
            return False
        return self._configure_source_problem_weights()

    def _parse_gym_standings(self, standings):
        """Read solve sets from Gym common standings.

        Only a party with at least one rated AC is active. Gym solve counts are
        retained for diagnostics; problem difficulty always comes from the
        configured source contest.
        """
        problems = standings.get("problems", [])
        rows = standings.get("rows", [])
        if not problems or not rows:
            print(f"✗ Gym {self.id} returned empty standings.")
            return False
        if len(self.problem_sources) < len(problems):
            print(
                f"✗ Gym {self.id} has {len(problems)} problems but only "
                f"{len(self.problem_sources)} problemSources entries."
            )
            return False

        problem_count = len(problems)
        self.numberSolved = {index: 0 for index in range(problem_count)}
        unrated_indices = {
            index
            for index, source in enumerate(self.problem_sources[:problem_count])
            if source is None
        }
        unrated_indices.update(
            index
            for index, problem in enumerate(problems)
            if "unrated" in problem.get("name", "").casefold()
        )
        self._scored_problem_indices = set(range(problem_count)) - unrated_indices
        if not self._scored_problem_indices:
            print(f"✗ Gym {self.id} has no rated problems to score.")
            return False

        configured_handles = {
            user["codeforces-handle"].casefold(): user["codeforces-handle"]
            for user in self.handleMap.values()
            if user.get("codeforces-handle")
        }
        active_participants = 0

        for row in rows:
            solved = {
                index
                for index, result in enumerate(
                    row.get("problemResults", [])[:problem_count]
                )
                if result.get("points", 0) > 0
            }
            rated_solved = solved & self._scored_problem_indices
            if not rated_solved:
                continue

            active_participants += 1
            for index in solved:
                self.numberSolved[index] += 1

            # A team is one standings party, but every configured team member
            # receives the team's solved set.
            for member in row.get("party", {}).get("members", []):
                configured = configured_handles.get(
                    member.get("handle", "").casefold()
                )
                if configured is None:
                    continue
                previous = set(self.handlesSolved.get(configured, []))
                self.handlesSolved[configured] = sorted(previous | rated_solved)

        counts = [self.numberSolved[index] for index in range(problem_count)]
        unrated_labels = [problems[index].get("index", str(index))
                          for index in sorted(unrated_indices)]
        print(
            f"✓ Gym active participants={active_participants}, "
            f"solved={counts}, unrated={unrated_labels}, "
            f"matched handles={len(self.handlesSolved)}"
        )
        return active_participants > 0

    def _configure_source_problem_weights(self):
        source_contests = {}
        gym_weights = {}
        details = []

        for gym_index in sorted(self._scored_problem_indices):
            source_contest_id, source_problem_index = self.problem_sources[gym_index]
            if source_contest_id not in source_contests:
                distribution = self._load_source_distribution(source_contest_id)
                if distribution is None:
                    return False
                participants, solved_counts = distribution
                weights = self._normalize_source_weights(
                    participants,
                    solved_counts,
                )
                if weights is None:
                    print(f"✗ Source contest {source_contest_id} has zero average.")
                    return False
                source_contests[source_contest_id] = (
                    participants,
                    solved_counts,
                    weights,
                )

            participants, solved_counts, weights = source_contests[source_contest_id]
            if source_problem_index not in weights:
                print(
                    f"✗ Problem {source_contest_id}{source_problem_index} "
                    "is absent from its source standings."
                )
                return False
            gym_weights[gym_index] = weights[source_problem_index]
            details.append(
                f"{gym_index}:{source_contest_id}{source_problem_index}="
                f"{solved_counts[source_problem_index]}/{participants}"
            )

        self._source_problem_weights = gym_weights
        print("✓ Original problem distributions: " + ", ".join(details))
        return True

    @staticmethod
    def _normalize_source_weights(participants, solved_counts):
        raw_weights = {}
        average = 0
        for problem_index, solved in solved_counts.items():
            if solved <= 0:
                raw_weights[problem_index] = 0
                continue
            solved_fraction = solved / participants
            raw_weight = 1 - math.log(solved_fraction)
            raw_weights[problem_index] = raw_weight
            average += solved_fraction * raw_weight
        if average <= 0:
            return None
        return {
            problem_index: raw_weight / average
            for problem_index, raw_weight in raw_weights.items()
        }

    @classmethod
    def _load_source_distribution(cls, contest_id):
        if contest_id in cls._source_distribution_cache:
            return cls._source_distribution_cache[contest_id]

        standings = cfapi.request(
            "contest.standings",
            {"contestId": contest_id},
        )
        if not isinstance(standings, dict):
            print(f"✗ Could not fetch source contest {contest_id}.")
            return None

        problems = standings.get("problems", [])
        rows = standings.get("rows", [])
        if not problems or not rows:
            print(f"✗ Source contest {contest_id} returned empty standings.")
            return None

        # The fixed 8.72 rule: source N contains only parties with at least one AC.
        active_rows = [
            row
            for row in rows
            if any(
                result.get("points", 0) > 0
                for result in row.get("problemResults", [])
            )
        ]
        if not active_rows:
            print(f"✗ Source contest {contest_id} has no active participants.")
            return None

        solved_counts = {problem["index"]: 0 for problem in problems}
        for row in active_rows:
            for problem, result in zip(problems, row.get("problemResults", [])):
                if result.get("points", 0) > 0:
                    solved_counts[problem["index"]] += 1

        distribution = len(active_rows), solved_counts
        cls._source_distribution_cache[contest_id] = distribution
        return distribution

    def getRawScore(self, handle):
        return sum(
            self._source_problem_weights.get(problem_index, 0)
            for problem_index in self.handlesSolved.get(handle, [])
        )

    def getAvgScore(self):
        # Source weights are already normalized in their original contests.
        return 1 if self._source_problem_weights else 0
