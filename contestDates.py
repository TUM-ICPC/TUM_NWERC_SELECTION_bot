from bs4 import BeautifulSoup
import codeforcesApi as cfapi
import time, requests
import util
import re
from datetime import datetime
from pytz import timezone
from urllib.parse import urlparse

def getTimestamp(dateString) -> float:
	return datetime.timestamp(datetime.strptime(dateString, "%d.%m.%Y:%H.%M.%S"))

# also allows Div. 1 contest, need to be filtered afterwards
# if Div. 2 is also present
def isValidCFContestName(name):
	return not "unrated" in name and ("Educational" in name or "Global" in name or "Div. 2" in name or "Div. 3" in name)

class ContestDates:
	def __init__(self, config):
		self.config = config
		self.contests = []
		self.update()

	def getCFContests(self, start, end):
		contests = cfapi.request('contest.list', {'gym':'false'})
		if contests is False:
			return []
		contests = [c for c in contests if c.get('startTimeSeconds', -1) >= start]
		contests = [c for c in contests if c.get('startTimeSeconds', -1) <= end]
		addContestIds = []
		filteredcontests = [c for c in contests if isValidCFContestName(c['name']) or c['id'] in addContestIds]
		filteredcontests = [c for c in filteredcontests if len(
				[c2 for c2 in contests if c2.get('startTimeSeconds', -1) == c.get('startTimeSeconds', -1)]) == 1 or c['id'] in addContestIds]
		return [{		"time": c['startTimeSeconds'],
								"type": "codeforces",
								"id": 	c["id"]} for c in filteredcontests]



	def getACContests(self, start, end):
		# atcoder grand contest archive
		# request = requests.get("https://atcoder.jp/contests/archive?category=1")
		# html = request.text
		# parsed = BeautifulSoup(html, "html.parser")
		# contests = self.parseACTable(parsed.find('table'), start, end)

		# atcoder regular contest archive
		request = requests.get("https://atcoder.jp/contests/archive?ratedType=2&category=0&keyword=")
		html = request.text
		parsed = BeautifulSoup(html, "html.parser")
		contests = self.parseACTable(parsed.find('table'), start, end)

		# atcoder beginner contest archive
		request = requests.get("https://atcoder.jp/contests/archive?ratedType=1&category=0&keyword=") 
		html = request.text
		parsed = BeautifulSoup(html, "html.parser")
		contests += self.parseACTable(parsed.find('table'), start, end)

		# atcoder current and future contests
		request = requests.get("https://atcoder.jp/contests/")
		html = request.text
		parsed = BeautifulSoup(html, "html.parser")
		upTabl1 = parsed.find(id='contest-table-upcoming')
		if upTabl1 == None:
			print("no upcoming contests found")
		else:
			upcomingTable = upTabl1.find('table')
			contests += self.parseACTable(upcomingTable, start, end)

		curTabl1 = parsed.find(id='contest-table-action')
		if curTabl1 == None:
			print("no currently active contests found")
		else:
			currentTable = curTabl1.find('table')
			contests += self.parseACTable(currentTable, start, end)
		return contests
	
# 	def parseACTable(self, table, start, end):
# 		rows = table.find('tbody').find_all('tr')
# 		contests = []
# 		for row in rows:
# 			values = row.find_all('td')
# 			timeUrl = values[0].find('a').get('href')
# 			timestr = re.search('[0-9]+T[0-9]*', timeUrl).group()
# 			japanTime = datetime.strptime(timestr, "%Y%m%dT%H%M")
# 			utcTime = util.convertTimeZone(japanTime, "Asia/Tokyo", "Europe/Berlin")
# 			timeStmp = datetime.timestamp(utcTime)
# 			contestUrl = values[1].find('a').get('href')
# 			contestRegex = re.search('arc [0-9]*', contestUrl)
# #			if contestRegex is not None and timeStmp >= start-50*24*60*60 and timeStmp <= end:
# 			if contestRegex is not None and timeStmp >= start and timeStmp <= end:
# 				contestId = contestRegex.group()
# 				contests.append({
# 						'time':timeStmp,
# 						'type':'atcoder',
# 						'id':contestId
# 						})
# 		return contests






	def parseACTable(self, table, start, end):
		if table is None:
			return []
		tbody = table.find('tbody')
		if tbody is None:
			return []

		rows = tbody.find_all('tr')
		contests = []

		for row in rows:
			values = row.find_all('td')
			if len(values) < 2:
				continue

			a_time = values[0].find('a')
			a_contest = values[1].find('a')
			if a_time is None or a_contest is None:
				continue

			# Parse time (AtCoder link format: 20250118T2100)
			timeUrl = a_time.get('href', '')
			m_time = re.search(r'[0-9]{8}T[0-9]{4}', timeUrl)
			if not m_time:
				continue
			try:
				japanTime = datetime.strptime(m_time.group(), "%Y%m%dT%H%M")
				berlinTime = util.convertTimeZone(japanTime, "Asia/Tokyo", "Europe/Berlin")
				timeStmp = datetime.timestamp(berlinTime)
			except Exception:
				continue

			contestUrl = a_contest.get('href', '')
			title = a_contest.get_text(" ", strip=True)

			path = urlparse(contestUrl).path.lower()  # e.g. '/contests/arc206'
			if not re.fullmatch(r'/contests/a[rb]c\d+/?', path):
				continue

			if start <= timeStmp <= end:
				contestId = re.search(r'a[rb]c\d+', path).group()  # e.g. 'arc206'
				contests.append({
					'time': timeStmp,
					'type': 'atcoder',
					'id': contestId
				})

		return contests

	def getDates(self):
		return self.contests
		
	def update(self):
		start = getTimestamp(self.config["startDate"])
		end = getTimestamp(self.config["endDate"])
		contests = self.getCFContests(start, end) + self.getACContests(start, end)
		#contests = [{'time': time.time() - 60*60*24*5, 'type':'codeforces', 'id':'1202'}]
		self.contests = sorted(contests, key=lambda k:k['time'])

