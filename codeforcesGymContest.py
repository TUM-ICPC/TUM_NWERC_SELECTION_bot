import os
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

from contest import Contest
import codeforcesApi as cfapi


class CodeforcesGymContest(Contest):
    """
    Fetch standings for a Codeforces Gym contest which typically requires login.
    Login credentials are read from a two-line file '.codeforce_config.txt':
      line1: handleOrEmail
      line2: password
    """

    handleString = "codeforces-handle"
    _session: Optional[requests.Session] = None

    LOGIN_FILE = ".codeforce_config.txt"
    COOKIE_FILE = ".codeforces_cookies.txt"
    UA = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )

    def __init__(self, id, handleMap):
        super().__init__(id, handleMap)

    # ---------- Session / Auth ----------
    @classmethod
    def _ensure_session(cls):
        if cls._session is not None:
            return
        sess = requests.Session()
        sess.headers.update({
            "User-Agent": cls.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://codeforces.com/enter",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })

        # Try cookie-based auth first (most reliable when login page is protected)
        try:
            if os.path.exists(cls.COOKIE_FILE):
                with open(cls.COOKIE_FILE, "r", encoding="utf-8") as f:
                    raw = f.read()
                # support three formats:
                # 1) one-per-line: key=value
                # 2) single header line: key=value; key2=value2; ...
                # 3) standalone token (assume RCPC)
                def set_cookie_line(line: str):
                    line = line.strip()
                    if not line:
                        return
                    # Allow pasting lines starting with 'Cookie:' from browser
                    if line.lower().startswith("cookie:"):
                        line = line.split(":", 1)[1].strip()
                    if ";" in line and "=" in line:
                        # header format
                        parts = [p.strip() for p in line.split(";") if p.strip()]
                        for p in parts:
                            if "=" in p:
                                k, v = p.split("=", 1)
                                sess.cookies.set(k.strip(), v.strip(), domain="codeforces.com")
                    elif "=" in line:
                        k, v = line.split("=", 1)
                        sess.cookies.set(k.strip(), v.strip(), domain="codeforces.com")
                    else:
                        # assume RCPC token
                        sess.cookies.set("RCPC", line, domain="codeforces.com")

                ua_overridden = False
                if "\n" in raw:
                    for ln in raw.splitlines():
                        if ln.strip().lower().startswith("user-agent:"):
                            ua = ln.split(":", 1)[1].strip()
                            if ua:
                                sess.headers["User-Agent"] = ua
                                ua_overridden = True
                        else:
                            set_cookie_line(ln)
                else:
                    # single line: could be cookie header; could also be 'User-Agent: ...'
                    if raw.strip().lower().startswith("user-agent:"):
                        ua = raw.split(":", 1)[1].strip()
                        if ua:
                            sess.headers["User-Agent"] = ua
                            ua_overridden = True
                    else:
                        set_cookie_line(raw)
                print("  -> Loaded cookies from .codeforces_cookies.txt")
                if ua_overridden:
                    print("  -> Using User-Agent from cookie file")
        except Exception as e:
            print(f"  -> Failed to load cookies: {e}")
        # Attempt login
        try:
            creds = cls._read_creds()
            if creds is not None:
                handle, password = creds
                print(f"  -> Attempting to login as '{handle}'...")

                # Get login page and extract CSRF token
                r = sess.get("https://codeforces.com/enter", timeout=20)
                soup = BeautifulSoup(r.text, "html.parser")
                token = None
                for inp in soup.find_all("input"):
                    if inp.get("name") == "csrf_token":
                        token = inp.get("value")
                        break

                if not token:
                    print("  -> WARNING: Could not find CSRF token")
                else:
                    # Submit login form
                    payload = {
                        "csrf_token": token,
                        "action": "enter",
                        "handleOrEmail": handle,
                        "password": password,
                        "remember": "on",
                    }
                    sess.post("https://codeforces.com/enter", data=payload, timeout=20)

                    # Check if login was successful by trying to access settings page
                    check = sess.get("https://codeforces.com/settings/general", timeout=10)
                    if "logout" in check.text.lower() or handle.lower() in check.text.lower():
                        print(f"  -> Successfully logged in as '{handle}'")
                    else:
                        print("  -> WARNING: Login may have failed (didn't find logout link)")
            else:
                print("  -> No credentials file found, proceeding without login")
        except Exception as e:
            print(f"  -> Login exception: {e}")
            # Continue anyway - some gyms might be public
            pass

        cls._session = sess

    @classmethod
    def _read_creds(cls) -> Optional[tuple[str, str]]:
        if not os.path.exists(cls.LOGIN_FILE):
            return None
        try:
            with open(cls.LOGIN_FILE, "r", encoding="utf-8") as f:
                lines = [x.rstrip("\n") for x in f.readlines()]
            if len(lines) >= 2:
                return lines[0], lines[1]
        except Exception:
            return None
        return None

    # ---------- Standings ----------
    def updateScores(self):
        print("=" * 70)
        print(f"Fetching CF Gym {self.id}")
        print("=" * 70)
        
        self.handlesSolved = {}
        self.numberSolved = {}
        # Allow external override of display name
        self.name = getattr(self, "_display_name", f"Gym{self.id}")

        # Check for offline HTML file FIRST (recommended approach) unless forced online
        # Allow external override of offline HTML file path
        offline_file = getattr(self, "_offline_html_path", f"gym_{self.id}_standings.html")
        force_online = os.environ.get("CF_GYM_FORCE_ONLINE") in ("1", "true", "True")
        if os.path.exists(offline_file) and not force_online:
            print(f"✓ Found offline HTML: {offline_file}")
            with open(offline_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            ok = self._parse_html(html_content)
            # If requested, override difficulty distribution with official contest data
            if ok:
                self._maybe_override_with_official_distribution()
            return ok
        
        # No offline file or force online - print instructions
        if not os.path.exists(offline_file):
            print("\n⚠ Offline HTML not found!")
        else:
            print("\n↻ Forcing online refresh (CF_GYM_FORCE_ONLINE=1) ...")
        print("Due to Cloudflare protection, online access often fails unless you use real browser cookies.")
        print("If you get 403, open your browser, login to Codeforces, copy document.cookie for codeforces.com,")
        print("paste into .codeforces_cookies.txt, and optionally add a line 'User-Agent: <your browser UA>'.\n")

        # Try API approach
        CodeforcesGymContest._ensure_session()
        try:
            api_url = (
                f"https://codeforces.com/api/contest.standings?contestId={self.id}"
                f"&gym=true&showUnofficial=true&from=1&count=100000"
            )
            r = CodeforcesGymContest._session.get(api_url, timeout=20)
            data = r.json()
            if data.get('status') == 'OK':
                print(f"✓ API worked for Gym {self.id}!")
                return self._parse_api_response(data['result'])
        except Exception as e:
            print(f"  API failed: {e}")

        # Try web scraping
        print(f"Trying web scraping...")
        try:
            url = f"https://codeforces.com/gym/{self.id}/standings?locale=en"
            r = CodeforcesGymContest._session.get(url, timeout=30)
            print(f"  Status: {r.status_code}")
            
            if r.status_code == 200:
                # Save for future use if successful
                result = self._parse_html(r.text)
                if result:
                    with open(offline_file, 'w', encoding='utf-8') as f:
                        f.write(r.text)
                    print(f"✓ Saved to {offline_file} for future use")
                    # post-parse override if configured
                    self._maybe_override_with_official_distribution()
                return result
            else:
                print(f"✗ Failed: HTTP {r.status_code}")
                with open(f"gym_{self.id}_error.html", 'w') as f:
                    f.write(r.text[:10000])
                print(f"  (Error page saved to gym_{self.id}_error.html)")
        except Exception as e:
            print(f"✗ Web scraping failed: {e}")
        
        return False

    def _parse_api_response(self, cfStandings):
        """Parse API response."""
        for i in range(len(cfStandings["problems"])):
            self.numberSolved[i] = 0

        rows = cfStandings["rows"]
        for r in rows:
            if not r["party"]["members"]:
                continue
            handle = r["party"]["members"][0]["handle"]
            for i in range(len(r["problemResults"])):
                solved = r["problemResults"][i]["points"] > 0
                if not handle in self.handlesSolved:
                    self.handlesSolved[handle] = []
                if solved:
                    self.handlesSolved[handle].append(i)
                    self.numberSolved[i] += 1
        
        print(f"✓ Parsed {len(self.handlesSolved)} participants")
        return True

    # ---------- Difficulty override from official contest ----------
    def _maybe_override_with_official_distribution(self):
        """If a reference contest id is configured, fetch official per-problem
        solved counts and total participants, and use them for scoring weights.
        """
        ref_id = getattr(self, "_reference_contest_id", None)
        if not ref_id:
            return
        try:
            counts, participants = self._load_official_distribution(ref_id)
            if not counts or participants <= 0:
                return
            # Align problem count
            # Keep only the first min(len(self.numberSolved), len(counts)) problems
            k = min(len(self.numberSolved), len(counts))
            new_counts = {i: counts[i] for i in range(k)}
            # Replace numberSolved with official counts (aligned)
            self.numberSolved = new_counts
            # Record participants override for scoring
            self._participants_override = participants
            print(f"✓ Using official distribution from contest {ref_id}: participants={participants}, problems={k}")
        except Exception as e:
            print(f"  -> Could not load official distribution: {e}")

    def _load_official_distribution(self, contest_id: int):
        """Return (solved_counts_per_problem:list[int], participants:int) from CF API."""
        params = {
            "contestId": contest_id,
            "participantTypes": "CONTESTANT,OUT_OF_COMPETITION",
            "from": 1,
            "count": 100000,
        }
        res = cfapi.request("contest.standings", params)
        if not res:
            return None, 0
        problems = res.get("problems", [])
        rows = res.get("rows", [])
        participants = len(rows)
        counts = [0 for _ in range(len(problems))]
        for r in rows:
            prs = r.get("problemResults", [])
            for i in range(min(len(counts), len(prs))):
                if prs[i].get("points", 0) > 0:
                    counts[i] += 1
        return counts, participants

    # ---------- Override scoring to use official participants if available ----------
    def getRawScore(self, handle: str) -> float:
        participants = getattr(self, "_participants_override", None)
        if not participants:
            participants = len(self.handlesSolved)
        score = 0
        for taskI in self.handlesSolved.get(handle, []):
            solvedFraction = (self.numberSolved.get(taskI, 0) / participants) if participants else 0
            if solvedFraction > 0:
                score += (1 - __import__('math').log(solvedFraction))
        return score

    def getAvgScore(self) -> float:
        participants = getattr(self, "_participants_override", None)
        if not participants:
            participants = len(self.handlesSolved)
        avgScore = 0
        for taskI in self.numberSolved:
            solvedFraction = (self.numberSolved.get(taskI, 0) / participants) if participants else 0
            if solvedFraction > 0:
                avgScore += solvedFraction * (1 - __import__('math').log(solvedFraction))
        return avgScore

    def _parse_html(self, html_content):
        """Parse HTML standings page."""
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Find standings table
        table = soup.find("table", class_="standings")
        if table is None:
            for t in soup.find_all("table"):
                cls_names = " ".join(t.get("class", []))
                if "standings" in cls_names or "result" in cls_names:
                    table = t
                    break
        
        if table is None:
            print("✗ No standings table found in HTML")
            return False

        # Count problems from header
        problems = []
        header_row = table.find("tr")
        if header_row:
            for th in header_row.find_all("th"):
                # Accept both gym and contest links
                problem_link = th.find("a", href=re.compile(r"/(gym|contest)/\d+/problem/"))
                if problem_link:
                    problems.append(th)
        
        num_problems = len(problems)
        if num_problems == 0:
            data_rows = table.find_all("tr")[1:]
            if data_rows:
                first_row = data_rows[0]
                # Fallback: try to infer by counting from the end, assuming columns are:
                # [#, Who, =, Penalty, A, B, C, ...]
                # We'll detect by finding td count and subtracting known prefix columns.
                all_tds = first_row.find_all("td")
                if len(all_tds) >= 5:
                    # Assume 4 non-problem columns
                    num_problems = max(0, len(all_tds) - 4)

        for i in range(num_problems):
            self.numberSolved[i] = 0

        # Parse participant rows
        participant_count = 0
        for row in table.find_all("tr")[1:]:
            handle = None
            participant_cell = (
                row.find("td", class_="standings-cell-participant")
                or row.find("td", class_="contestant-cell")
                or row
            )
            handle_link = participant_cell.find("a", href=re.compile(r"/profile/")) if participant_cell else None
            if handle_link:
                href = handle_link.get("href", "")
                m = re.search(r"/profile/([^/?#]+)", href)
                if m:
                    handle = m.group(1)
            
            if not handle:
                continue

            # Determine problem cells by position: take the last num_problems td's
            tds_in_row = row.find_all("td")
            if not tds_in_row or num_problems == 0 or len(tds_in_row) < num_problems:
                continue
            problem_cells = tds_in_row[-num_problems:]
            
            solved_indices = []
            for idx, td in enumerate(problem_cells[:num_problems]):
                classes = " ".join(td.get("class", []))
                text = td.get_text(strip=True)

                # Consider accepted if there is an inner element with class 'cell-accepted'
                has_span_accepted = td.find(class_=re.compile(r"cell-accepted|accepted")) is not None
                is_accepted = (
                    has_span_accepted or
                    "cell-accepted" in classes or
                    "accepted" in classes.lower() or
                    (text and text.startswith("+"))
                )

                if is_accepted:
                    solved_indices.append(idx)

            if solved_indices:
                self.handlesSolved[handle] = solved_indices
                participant_count += 1
                for si in solved_indices:
                    self.numberSolved[si] = self.numberSolved.get(si, 0) + 1

        print(f"✓ Parsed {participant_count} participants, {num_problems} problems")
        return True
