from contest import Contest
from codeforcesContest import CodeforcesContest
from atcoderContest import AtcoderContest
from contestDates import ContestDates
from util import Table
import time
import datetime

import codeforcesApi as cfapi
from codeforcesGymContest import CodeforcesGymContest

class Ranking:
  def __init__(self, config):
    self.conf = config
    self.contestObjList = []  # Contains only past or started contest objects
    self.contestDateList = []  # Contains past and future contest dates
    self.specialContestObjList = []  # Special four contests (past only objects)
    self.handleMap = config['users']
    self.startDate = config['startDate']
    self.endDate = config['endDate']
    self.startDate_onsite = config['startDate_onsite']
    self.endDate_onsite = config['endDate_onsite']
    
    # Scoring parameters
    self.BASELINE_TOP_K = 4  # Best 4 from last 12 baseline contests
    self.SPECIAL_TOP_K = 2   # Best 2 from 4 special contests
    self.SPECIAL_MULTIPLIER = 2  # Special contest score multiplier
    
  def updateConfig(self, config):
    self.conf = config
    self.handleMap = config['users']
    self.startDate = config['startDate']
    self.endDate = config['endDate']

  def getRanking(self):
    return self.ranking

  def getNames(self):
    return self.names

  def getDates(self):
    return self.contestDateList

  def getContestNames(self):
    # Return all contest names: baseline + special contests
    baseline_names = [c.name for c in self.contestObjList]
    special_names = [c.name for c in self.specialContestObjList]
    return baseline_names + special_names

  def updateDates(self):
    self.contestDateList = []
    self.fetchContests()

  def updateRanking(self):
    self.updateDates()
    self.calcStandings()

  def fetchContests(self):
    self.contestDates = ContestDates(self.conf)
    newContestDates = self.contestDates.getDates()
    AtcoderContest.initSession()
    if newContestDates != self.contestDates:
      self.contestDateList = newContestDates
      self.contestObjList = []
      self.specialContestObjList = []
      for date in self.contestDateList:
        if date['time'] > time.time():
          continue
        if date['type'] == 'atcoder':
          self.contestObjList.append(AtcoderContest(date['id'], self.handleMap))
        else:
          self.contestObjList.append(CodeforcesContest(date['id'], self.handleMap))
      # Keep only the last 12 baseline contests
      if len(self.contestObjList) > 12:
        self.contestObjList = self.contestObjList[-12:]
      # Integrate special contests (outside of config window)
      for sdate in self._build_special_contest_dates():
        if sdate['time'] > time.time():
          continue
        cobj = self._make_special_contest_obj(sdate)
        if cobj is not None:
          self.specialContestObjList.append(cobj)
    AtcoderContest.endSession()

  def calcStandings(self):
    self.names = self.handleMap.keys()
    self.ranking = []
    self.specialScores = {}

    for name in self.names:
      # Baseline contest scores
      currentNameScores = []
      for c in self.contestObjList:
        currentNameScores.append(c.getScore(name))
      
      # Special contest scores (original normalized)
      sscores = []
      for c in self.specialContestObjList:
        sscores.append(c.getScore(name))
      
      # Special contest display scores (multiplied by SPECIAL_MULTIPLIER)
      sscores_display = [s * self.SPECIAL_MULTIPLIER for s in sscores]
      
      # Combine for table display (baseline + special display scores)
      allScores = currentNameScores + sscores_display
      self.ranking.append(allScores)
      # Save original special scores for sorting calculation
      self.specialScores[name] = sscores

  def sortingKey(self, scores, name=None):
    """
    Calculate total score for sorting:
    1. Best 4 from baseline contests (first N contests)
    2. Best 2 from special contests × 2
    
    Note: scores contains display values where special contest scores
    are already multiplied by 2, so we use saved specialScores for calculation.
    """
    # Separate baseline and special contest scores
    num_baseline = len(self.contestObjList)
    baseline_scores = scores[:num_baseline] if len(scores) >= num_baseline else scores
    
    # Use saved original special scores (not multiplied) for sorting
    special_scores = self.specialScores.get(name, [])
    
    # Baseline: sum of best 4
    baseline_sorted = sorted(baseline_scores, reverse=True)
    baseline_sum = sum(baseline_sorted[:self.BASELINE_TOP_K])
    
    # Special bonus: sum of best 2 × 2
    special_sorted = sorted(special_scores, reverse=True)
    special_bonus = sum(special_sorted[:self.SPECIAL_TOP_K]) * self.SPECIAL_MULTIPLIER
    
    total = baseline_sum + special_bonus
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

  # -------------------- Helpers for special contests --------------------
  def _build_special_contest_dates(self):
    """
    Create the four special contests AFTER baseline period.
    These are onsite/special contests outside the baseline time window:
    - 2025-10-18 (yesterday): Gym 643235 (friends standings, official Edu 817 distribution)
    - 2025-10-19 (today): regular CF Div.2 (auto-resolve id)
    - next Saturday: gym clone (id unknown), will be ignored until known
    - next Sunday: regular CF Div.2 (auto)
    Returns list of dicts with fields: {time, type, id?, hint}
    type in { 'cf_gym', 'cf_div2_auto' }
    """
    # Fixed timestamps for onsite special contests (outside baseline window)
    # Yesterday: Gym at midday
    yesterday = datetime.datetime(2025, 10, 18, 12, 0, 0)
    # Today: Div.2 at expected time (typically 14:35 UTC for CF)
    today = datetime.datetime(2025, 10, 19, 14, 35, 0)
    
    # Future placeholders
    now = datetime.datetime.now()
    def next_weekday(d: datetime.datetime, weekday: int):
      days_ahead = (weekday - d.weekday() + 7) % 7
      if days_ahead == 0:
        days_ahead = 7
      return d + datetime.timedelta(days=days_ahead)
    
    next_saturday = datetime.datetime.combine(
      next_weekday(now, 5).date(),
      datetime.time(12, 0, 0)
    )
    next_sunday = datetime.datetime.combine(
      next_weekday(now, 6).date(),
      datetime.time(14, 35, 0)
    )

    def ts(d: datetime.datetime):
      return d.timestamp()

    specials = [
      {"time": ts(yesterday), "type": "cf_gym", "id": 643235, "hint": "yesterday_gym_friends"},
      {"time": ts(today), "type": "cf_div2_auto", "id": None, "hint": "today_div2"},
      {"time": ts(next_saturday), "type": "cf_gym", "id": None, "hint": "next_saturday_gym_clone"},
      {"time": ts(next_sunday), "type": "cf_div2_auto", "id": None, "hint": "next_sunday_div2"},
    ]
    return specials

  def _make_special_contest_obj(self, sdate):
    """Instantiate a Contest object for a special contest date (past only)."""
    stype = sdate.get('type')
    cid = sdate.get('id')
    hint = sdate.get('hint', '')
    
    if stype == 'cf_gym':
      if cid is None:
        return None
      obj = CodeforcesGymContest(cid, self.handleMap)
      # Yesterday's gym uses friends standings HTML + official Edu 817 distribution
      if hint == 'yesterday_gym_friends':
        obj._offline_html_path = 'cf817_friends_standings.html'
        obj._display_name = 'Gym'
        obj._reference_contest_id = 817
      return obj
    
    if stype == 'cf_div2_auto':
      # Auto-resolve Div.2 contest id near scheduled time
      rid = self._resolve_div2_id(around_ts=sdate['time'])
      if rid is None:
        return None
      return CodeforcesContest(rid, self.handleMap)
    
    return None

  def _resolve_div2_id(self, around_ts: float, tolerance_hours: int = 18):
    """
    Use Codeforces API to locate a regular Div. 2 contest near the given timestamp.
    Returns contest id or None.
    """
    contests = cfapi.request('contest.list', {'gym': 'false'})
    if contests is False or contests is None:
      return None
    lo = around_ts - tolerance_hours * 3600
    hi = around_ts + tolerance_hours * 3600
    candidates = []
    for c in contests:
      st = c.get('startTimeSeconds')
      name = c.get('name', '')
      if st is None:
        continue
      if lo <= st <= hi and ('Div. 2' in name) and ('unrated' not in name.lower()):
        candidates.append(c)
    if not candidates:
      return None
    # Pick the closest in time
    candidates.sort(key=lambda c: abs(c['startTimeSeconds'] - around_ts))
    return candidates[0]['id']
