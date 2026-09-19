from contest import Contest
import codeforcesApi as cfApi
import math
import re


# user.status is shared by every CodeforcesContest object in one bot process.
# Keeping only the normalized OOC solves makes later contests cheap to query.
_user_status_cache = {}
_USER_STATUS_PAGE_SIZE = 1000

def getLongestNum(name):
	numbers = re.findall(r"\d+", name)
	return max(numbers, key=len) if numbers else "???"

def getName(name):
	if "Educational" in name:
		return "Edu" + getLongestNum(name)
	elif "Global" in name:
		return "Glo" + getLongestNum(name)
	elif "Div. 1" in name or "Div. 2" in name or "Div. 3" in name:
		return "CF" + getLongestNum(name)
	elif name == "Grakn Forces 2020":
		return "Grakn"
	print("unknown contest type:", name)
	return "CF???"

class CodeforcesContest(Contest):

	def __init__(self, id, handleMap):
		self.handleString = "codeforces-handle"
		self._official_handle_lookup = {}
		self._problem_index_lookup = {}
		self._contest_start_time = 0
		super().__init__(id, handleMap)

	def updateScores(self):
		print("fetching scores for CF contest ", self.id)
		# A failed request is represented as an empty contest, not partial state.
		self.handlesSolved = {}
		self.numberSolved = {}
		self._official_handle_lookup = {}
		self._problem_index_lookup = {}
		self._contest_start_time = 0
		cfStandings = cfApi.request("contest.standings", {"contestId": self.id})
		if cfStandings is False:
			print(f"[WARN] Codeforces standings unavailable for contest {self.id}; using 0 scores.")
			return False
		self.name = getName(cfStandings["contest"]["name"])
		self._contest_start_time = cfStandings["contest"].get("startTimeSeconds", 0)
		self._problem_index_lookup = {
			problem["index"]: i
			for i, problem in enumerate(cfStandings["problems"])
		}

		# reset everything
		self.handlesSolved = {}
		self.numberSolved = {}
		for i in range(len(cfStandings["problems"])):
			self.numberSolved[i] = 0

		rows = cfStandings["rows"]
		for r in rows:
			members = r.get("party", {}).get("members", [])
			if not members:
				continue
			handle = members[0]["handle"]
			self._official_handle_lookup[handle.casefold()] = handle
			for i in range(len(r["problemResults"])):
				solved =  r["problemResults"][i]["points"] > 0
				if not handle in self.handlesSolved:
					self.handlesSolved[handle] = []
				if solved:
					self.handlesSolved[handle].append(i)
					self.numberSolved[i] += 1

		return True

	def getRawScore(self, handle: str) -> float:
		"""Score official and OOC participants against the official distribution."""
		participants = len(self.handlesSolved)
		if participants == 0:
			return 0

		official_handle = self._official_handle_lookup.get(handle.casefold())
		if official_handle is not None:
			solved_indices = self.handlesSolved.get(official_handle, [])
		else:
			solved_indices = self._get_ooc_solved_indices(handle)

		score = 0
		for task_index in solved_indices:
			# An OOC participant can be the only solver of a problem.  Use one
			# pseudo-solver for a finite out-of-sample problem weight.
			solved_count = max(self.numberSolved.get(task_index, 0), 1)
			solved_fraction = solved_count / participants
			score += 1 - math.log(solved_fraction)
		return score

	def _get_ooc_solved_indices(self, handle):
		cache_key = handle.casefold()
		entry = _user_status_cache.setdefault(
			cache_key,
			{
				"next_from": 1,
				"oldest_time": None,
				"exhausted": False,
				"failed": False,
				"ooc_solves": {},
			},
		)

		while (
			not entry["failed"]
			and not entry["exhausted"]
			and (
				entry["oldest_time"] is None
				or entry["oldest_time"] > self._contest_start_time
			)
		):
			submissions = cfApi.request(
				"user.status",
				{
					"handle": handle,
					"from": entry["next_from"],
					"count": _USER_STATUS_PAGE_SIZE,
				},
			)
			if submissions is False:
				entry["failed"] = True
				break

			for submission in submissions:
				creation_time = submission.get("creationTimeSeconds")
				if creation_time is not None:
					if entry["oldest_time"] is None:
						entry["oldest_time"] = creation_time
					else:
						entry["oldest_time"] = min(entry["oldest_time"], creation_time)

				author = submission.get("author", {})
				if author.get("participantType") != "OUT_OF_COMPETITION":
					continue
				if submission.get("verdict") != "OK":
					continue

				contest_id = submission.get("contestId")
				problem_index = submission.get("problem", {}).get("index")
				if contest_id is None or problem_index is None:
					continue
				entry["ooc_solves"].setdefault(str(contest_id), set()).add(problem_index)

			entry["next_from"] += len(submissions)
			if len(submissions) < _USER_STATUS_PAGE_SIZE:
				entry["exhausted"] = True

		if entry["failed"]:
			return []

		return sorted(
			self._problem_index_lookup[index]
			for index in entry["ooc_solves"].get(str(self.id), set())
			if index in self._problem_index_lookup
		)
