# TUM NWERC Selection Tool
A tool which 
- fetches the relevant contests for the selection of the TUM NWERC teams from Codeforces and AtCoder
- calculates the score for all participants
- shows the ranking among all TUM participants.

## Usage
Install Python 3 and additionally the Python modules:
- `requests`
- `beautifulsoup4`
- `lxml`
(all available via pip).

For running the tool use `python3 main.py`. The current ranking will be printed to the console.
The `runBot.py` file is used to host a Telegram bot for which Telegram API keys are needed.

Atcoder now requires to be logged in to fetch the rankings. Therfore you need to provide valid login credentials in the file `.atcoder_config.txt`. The first line should contain the username, the second line the password. Starting in 2025, AtCoder began using Cloudflare for login, so you need to create a new file called `.atcoder_cookies.txt`. The administrator must log in to AtCoder manually and copy the session cookie into this file. The code accepts either `REVEL_SESSION=...` or the raw cookie value on a single line.

## Onsite Gym configuration

All onsite Gym information is configured in `config.json` under `onsiteGyms`.
Use an empty list while no onsite contest has been scheduled:

```json
"onsiteGyms": []
```

Once a Gym is known, add one entry:

```json
"onsiteGyms": [
  {
    "id": 650123,
    "startTime": "2026-10-17T12:00:00+02:00",
    "displayName": "ONSITE 1",
    "problemSources": [
      {"contestId": 2170, "problem": "A"},
      {"contestId": 2170, "problem": "B"},
      {"contestId": 2169, "problem": "C"},
      null
    ]
  }
]
```

- `id` is the Gym ID.
- `startTime` is an ISO-8601 timestamp with a timezone. `Z` may be used for UTC.
- `displayName` is the table column name.
- `problemSources` follows the exact Gym problem order. Each rated problem maps
  to its original Codeforces contest and problem index; use `null` for an
  unrated problem.

The fixed scoring rule uses the Gym standings only for each contestant's solved
set. Each problem is normalized inside its original contest, counting only
parties that solved at least one problem, and the mapped problem scores are then
summed. Onsite scores are multiplied by two in the final ranking.

Private Gym access uses the Codeforces API. Put the API key on the first line
and the API secret on the second line of `.codeforces_api_config.txt`.

## Contribution
Please feel free to contribute to the project by creating a pull request.
