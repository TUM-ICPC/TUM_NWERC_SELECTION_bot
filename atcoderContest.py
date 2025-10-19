# atcoderContest.py
import os
import requests
from bs4 import BeautifulSoup
from contest import Contest

class AtcoderContest(Contest):

    handleString = "atcoder-handle"
    session: requests.Session | None = None

    COOKIE_FILE = ".atcoder_cookies.txt"
    LOGIN_FILE = ".atcoder_config.txt"
    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )

    def __init__(self, id, handleMap):
        super().__init__(id, handleMap)

    # ---------- Session / Auth ----------

    @classmethod
    def _load_cookies_from_file(cls) -> dict:
        cookies = {}
        if not os.path.exists(cls.COOKIE_FILE):
            return cookies
        with open(cls.COOKIE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies

    @classmethod
    def _try_cookie_login(cls) -> bool:
        
        cookies = cls._load_cookies_from_file()
        if not cookies:
            return False
        cls.session.cookies.update(cookies)
        print("[INFO] AtCoder: Logging in using local cookie (.atcoder_cookies.txt).")
        return True

    @classmethod
    def _try_legacy_password_login(cls) -> bool:
        if not os.path.exists(cls.LOGIN_FILE):
            print(f"[WARN] can not find {cls.LOGIN_FILE}.")
            return False

        try:
            with open(cls.LOGIN_FILE, "r", encoding="utf-8") as f:
                lines = [x.rstrip("\n") for x in f.readlines()]
            if len(lines) < 2:
                print(f"[WARN] {cls.LOGIN_FILE} format is incorrect (should be two lines: username, password).")
                return False
            username, password = lines[0], lines[1]
        except Exception as e:
            print(f"[WARN] Failed to read {cls.LOGIN_FILE}: {e}")
            return False

        try:
            login_url = "https://atcoder.jp/login"
            resp = cls.session.get(login_url, timeout=20)
            parsed = BeautifulSoup(resp.text, "html.parser")
            csrf = None
            for inp in parsed.find_all("input"):
                try:
                    if inp.get("name") == "csrf_token":
                        csrf = inp.get("value")
                        break
                except Exception:
                    pass

            if not csrf:
                print("[WARN] can not find csrf_token.")
                return False

            payload = {
                "username": username,
                "password": password,
                "csrf_token": csrf,
            }
            post = cls.session.post(login_url, data=payload, timeout=20)
            if post.status_code != 200:
                print(f"[WARN] Login request returned {post.status_code}.")
                return False

            me = cls.session.get("https://atcoder.jp/settings", timeout=20)
            if me.status_code == 200 and ("Sign Out" in me.text or "Settings" in me.text):
                print("[INFO] AtCoder: Legacy username/password login seems to be successful (not guaranteed).")
                return True

            print("[WARN] Legacy login not confirmed successful.")
            return False

        except Exception as e:
            print(f"[WARN] Legacy login exception: {e}")
            return False

    @classmethod
    def initSession(cls):
        if cls.session is not None:
            return
        cls.session = requests.Session()
        cls.session.headers.update({"User-Agent": cls.USER_AGENT})

        if cls._try_cookie_login():
            return

        print("[WARN] can not find Cookie or legacy login failed. Subsequent requests may be intercepted.")

    @classmethod
    def endSession(cls):
        try:
            if cls.session is not None:
                cls.session.close()
        finally:
            cls.session = None

    # ---------- Scoring ----------

    def updateScores(self):
        print("fetching scores for Atcoder contest", self.id)
        self.handlesSolved = {}
        self.numberSolved = {}
        self.name = self.id  

        if AtcoderContest.session is None:
            AtcoderContest.initSession()

        url = f"https://atcoder.jp/contests/{self.id}/standings/json"
        try:
            r = AtcoderContest.session.get(url, timeout=30)
        except Exception as e:
            print(f"[ERROR] Failed to fetch {url}: {e}")
            return False

        try:
            data = r.json()
        except Exception:
            print(f"[ERROR] AtCoder returned non-JSON (possibly not logged in/Cookie expired): {url}")
            try:
                snippet = r.text[:500].replace("\n", " ")
                print(f"[HINT] Response snippet: {snippet}")
            except Exception:
                pass
            return False

        scoresForTask: dict[str, dict[int, int]] = {}
        idx = 0


        task_infos = data.get("TaskInfo", [])
        for task in task_infos:
            name = task.get("TaskScreenName")
            if name and name not in scoresForTask:
                scoresForTask[name] = {}

        standings = data.get("StandingsData", [])
        for row in standings:
            task_results = row.get("TaskResults", {}) or {}
            for task_name, result in task_results.items():
                try:
                    score = result.get("Score", 0)
                except AttributeError:
                    score = 0
                if score and score > 0:
                    if task_name not in scoresForTask:
                        scoresForTask[task_name] = {}
                    if score not in scoresForTask[task_name]:
                        scoresForTask[task_name][score] = idx
                        self.numberSolved[idx] = 0
                        idx += 1

        for row in standings:
            total = (row.get("TotalResult") or {}).get("Count", 0)
            if total == 0:
                continue
            handle = row.get("UserScreenName")
            if not handle:
                continue

            solved_indices = set()  
            task_results = row.get("TaskResults", {}) or {}
            for task_name, result in task_results.items():
                try:
                    s = result.get("Score", 0)
                except AttributeError:
                    s = 0
                if s and s > 0:

                    for score_value, index in scoresForTask.get(task_name, {}).items():
                        if score_value <= s:
                            if index not in solved_indices:
                                solved_indices.add(index)

            if solved_indices:
                self.handlesSolved[handle] = list(solved_indices)
                for index in solved_indices:
                    self.numberSolved[index] = self.numberSolved.get(index, 0) + 1

        return True



# import json, requests
# from bs4 import BeautifulSoup
# from contest import Contest

# class AtcoderContest(Contest):
# 	def __init__(self, id, handleMap):
# 		self.handleString = "atcoder-handle"
# 		super().__init__(id, handleMap)

# 	def initSession():
# 		[username, password] = [line.rstrip('\n') for line in open('.atcoder_config.txt')]
# 		AtcoderContest.session = requests.Session()
# 		loginUrl = "https://atcoder.jp/login"
# 		request = AtcoderContest.session.get(loginUrl)
# 		parsed = BeautifulSoup(request.text)
# 		csrf_token = [element['value'] for element in parsed.find_all('input') if element['name'] == "csrf_token"][0]
# 		loginData = {'username': username,
# 								 'password': password,
# 								 'csrf_token': csrf_token}
# 		res = AtcoderContest.session.post(loginUrl, data=loginData)

# 	def endSession():
# 		AtcoderContest.session.close()

# 	def updateScores(self):
# 		print("fetching scores for Atcoder contest ", self.id)
# 		self.handlesSolved = {}
# 		self.numberSolved = {}
# #self.name = self.id[:3] + self.id[4:] # leave out '0' -> 5 chars only
# 		self.name = self.id
# 		try:
# 			url = "https://atcoder.jp/contests/" + self.id + "/standings/json"
# 			r = self.session.get(url, timeout=15)
# 			r = r.json()

# 			scoresForTask = {} # taskname -> {score -> index in numberSolved/handlesSolved}
# 			for task in r['TaskInfo']:
# 				scoresForTask[task['TaskScreenName']] = {}

# 			taskIndex = 0
# 			# Initialize scores for task for handling subtasks
# 			for row in r['StandingsData']:
# 				for taskName, result in row['TaskResults'].items():
# 					if result['Score'] > 0 and result['Score'] not in scoresForTask[taskName]:
# 						scoresForTask[taskName][result['Score']] = taskIndex
# 						self.numberSolved[taskIndex] = 0
# 						taskIndex += 1

# 			for row in r['StandingsData']:
# 				# only people with at least one submission are counted
# 				if row['TotalResult']['Count'] == 0:
# 					continue 
# 				handle = row['UserScreenName']
# 				self.handlesSolved[handle] = []
# 				for taskName, result in row['TaskResults'].items():
# 					if result['Score'] > 0:
# 						for score, index in scoresForTask[taskName].items():
# 							# User solved all subtasks with score <= their score
# 							if score <= result['Score']:
# 								self.handlesSolved[handle].append(index)
# 								self.numberSolved[index] += 1
# 		except requests.exceptions.Timeout as e:
# 			print("Fetching Atcoder results failed")
# 			return False
