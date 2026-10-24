from codeforcesContest import CodeforcesContest
from atcoderContest import AtcoderContest
from contestDates import ContestDates
from util import Table
import time
from datetime import datetime

from codeforcesGymContest import CodeforcesGymContest

class Ranking:
  def __init__(self, config):
    self.conf = config
    self.contestObjList = []  # Contains only past or started contest objects
    self.contestDateList = []  # Contains past and future contest dates
    self.onsiteContestObjList = []
    self.handleMap = config['users']
    
    # Scoring parameters
    self.BASELINE_TOP_K = 4  # Best 4 from last 12 baseline contests
    self.ONSITE_TOP_K = 2
    self.ONSITE_MULTIPLIER = 2
    
  def updateConfig(self, config):
    self.conf = config
    self.handleMap = config['users']

  def getRanking(self):
    return self.ranking

  def getNames(self):
    return self.names

  def getDates(self):
    return self.contestDateList

  def getContestNames(self):
    baseline_names = [c.name for c in self.contestObjList]
    onsite_names = [c.name for c in self.onsiteContestObjList]
    return baseline_names + onsite_names

  def updateDates(self):
    self.contestDateList = []
    self.fetchContests()

  def updateRanking(self):
    self.updateDates()
    self.calcStandings()

  def fetchContests(self):
    baseline_dates = ContestDates(self.conf).getDates()
    onsite_dates = self._build_onsite_contest_dates()
    self.contestDateList = sorted(
      baseline_dates + onsite_dates,
      key=lambda contest: contest['time'],
    )

    AtcoderContest.initSession()
    try:
      self.contestObjList = []
      self.onsiteContestObjList = []
      for date in baseline_dates:
        if date['time'] > time.time():
          continue
        if date['type'] == 'atcoder':
          self.contestObjList.append(AtcoderContest(date['id'], self.handleMap))
        else:
          self.contestObjList.append(CodeforcesContest(date['id'], self.handleMap))
      # Keep only the last 12 baseline contests
      if len(self.contestObjList) > 12:
        self.contestObjList = self.contestObjList[-12:]

      for sdate in onsite_dates:
        if sdate['time'] > time.time():
          continue
        cobj = self._make_onsite_contest_obj(sdate)
        if cobj is not None:
          self.onsiteContestObjList.append(cobj)
    finally:
      AtcoderContest.endSession()

  def calcStandings(self):
    self.names = self.handleMap.keys()
    self.ranking = []
    self.onsiteScores = {}

    for name in self.names:
      # Baseline contest scores
      currentNameScores = []
      for c in self.contestObjList:
        currentNameScores.append(c.getScore(name))
      
      # Onsite Gym scores (already normalized in the source contests)
      onsite_scores = []
      for c in self.onsiteContestObjList:
        onsite_scores.append(c.getScore(name))
      
      # Onsite scores are worth twice a baseline contest score.
      onsite_display = [s * self.ONSITE_MULTIPLIER for s in onsite_scores]
      
      allScores = currentNameScores + onsite_display
      self.ranking.append(allScores)
      self.onsiteScores[name] = onsite_scores

  def sortingKey(self, scores, name=None):
    """
    Calculate total score for sorting:
    1. Best 4 from baseline contests (first N contests)
    2. Best 2 from configured onsite Gym contests × 2
    
    Note: scores contains display values where onsite scores are already
    multiplied by 2, so sorting uses the saved original onsite scores.
    """
    # Separate baseline scores from the appended onsite display scores.
    num_baseline = len(self.contestObjList)
    baseline_scores = scores[:num_baseline] if len(scores) >= num_baseline else scores
    
    onsite_scores = self.onsiteScores.get(name, [])
    
    # Baseline: sum of best 4
    baseline_sorted = sorted(baseline_scores, reverse=True)
    baseline_sum = sum(baseline_sorted[:self.BASELINE_TOP_K])
    
    onsite_sorted = sorted(onsite_scores, reverse=True)
    onsite_bonus = sum(onsite_sorted[:self.ONSITE_TOP_K]) * self.ONSITE_MULTIPLIER
    
    total = baseline_sum + onsite_bonus
    return total

  def getTable(self) -> Table:
    self.updateRanking()
    table = Table()
    table.setHead("", self.getContestNames())
    lst = zip(self.names, self.ranking)
    positiveScoreExists = any([self.sortingKey(scores, name) > 0 for name, scores in zip(self.names, self.ranking)])
    for name, scores in lst:
      key = self.sortingKey(scores, name)
      if key > 0 or not positiveScoreExists:
        scoreStrings = ["{: 5.2f}".format(s) for s in scores]
        table.addRow("{:.15}".format(name), scoreStrings, key)
    table.sort()
    return table

  # -------------------- Onsite Gym configuration --------------------
  def _build_onsite_contest_dates(self):
    """Validate and normalize ``config.json``'s ``onsiteGyms`` list."""
    configured = self.conf.get('onsiteGyms', [])
    if not isinstance(configured, list):
      raise ValueError("config.json: onsiteGyms must be a list")

    onsite_dates = []
    seen_ids = set()
    for index, gym in enumerate(configured):
      location = f"config.json: onsiteGyms[{index}]"
      if not isinstance(gym, dict):
        raise ValueError(f"{location} must be an object")

      contest_id = gym.get('id')
      if isinstance(contest_id, bool) or not isinstance(contest_id, int) or contest_id <= 0:
        raise ValueError(f"{location}.id must be a positive integer")
      if contest_id in seen_ids:
        raise ValueError(f"{location}.id duplicates Gym {contest_id}")
      seen_ids.add(contest_id)

      start_time = gym.get('startTime')
      if not isinstance(start_time, str):
        raise ValueError(f"{location}.startTime must be an ISO-8601 string")
      try:
        parsed_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
      except ValueError as error:
        raise ValueError(f"{location}.startTime is invalid: {start_time}") from error
      if parsed_time.tzinfo is None:
        raise ValueError(f"{location}.startTime must include a timezone")

      problem_sources = gym.get('problemSources')
      if not isinstance(problem_sources, list) or not problem_sources:
        raise ValueError(f"{location}.problemSources must be a non-empty list")
      try:
        CodeforcesGymContest.parse_problem_sources(problem_sources)
      except ValueError as error:
        raise ValueError(f"{location}: {error}") from error

      display_name = gym.get('displayName', f"Gym{contest_id}")
      if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError(f"{location}.displayName must be a non-empty string")

      onsite_dates.append({
        'time': parsed_time.timestamp(),
        'type': 'cf_gym',
        'id': contest_id,
        'display_name': display_name.strip(),
        'problem_sources': problem_sources,
      })

    return sorted(onsite_dates, key=lambda contest: contest['time'])

  def _make_onsite_contest_obj(self, sdate):
    """Instantiate one configured onsite Gym."""
    if sdate.get('type') != 'cf_gym':
      return None
    return CodeforcesGymContest(
      sdate['id'],
      self.handleMap,
      problem_sources=sdate['problem_sources'],
      display_name=sdate['display_name'],
    )
