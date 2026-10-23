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

AtCoder requires a logged-in session to fetch the rankings. Provide valid login credentials in `.atcoder_config.txt`: the username on the first line and the password on the second. If automated login is blocked by Cloudflare, log in manually and copy the session cookie into `.atcoder_cookies.txt`. The code accepts either `REVEL_SESSION=...` or the raw cookie value on a single line.

## Selection period and scoring

`startDate` and `endDate` in `config.json` are interpreted in `Europe/Berlin`.
All eligible Codeforces and AtCoder contests whose start times fall within this
inclusive period are baseline contests; the list is not limited to the last 12.
Codeforces eligibility keeps the existing name and simultaneous-start filters;
AtCoder includes ABC and ARC contests. Onsite contests are configured separately
and are excluded from the baseline list.

The final score is the sum of the best four baseline scores plus twice the sum
of the best two onsite scores. Upcoming contests are scored only once started.

## Onsite contest configuration

All onsite information is configured in `config.json` under `onsiteGyms`.
The field includes both ordinary Codeforces rounds and Gym/group contests.
For each selection cycle, update the selection dates and onsite entries in
`config.json`. Use `ONSITE 1`, `ONSITE 2`, and so on as the display names.
Use an empty list while no onsite contest has been scheduled:

```json
"onsiteGyms": []
```

Once a Gym is known, add one entry. The IDs and timestamp below are examples;
replace them with the actual contest details:

```json
"onsiteGyms": [
  {
    "id": 650123,
    "startTime": "2000-01-01T12:00:00Z",
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
- For a regular Codeforces round used as an onsite contest, set `type` to
  `"codeforces"` and omit `problemSources`. Its score receives the same onsite
  multiplier of two, and the round is excluded from baseline contests.
- `startTime` is an ISO-8601 timestamp with a timezone. `Z` may be used for UTC.
- `displayName` is the table column name.
- `enabled` defaults to `true`. Set it to `false` for a pending contest; it is
  omitted from the schedule, ranking columns and API requests until configured
  and enabled. A disabled entry may omit its ID, time and problem sources.
- For a group contest, set `groupCode` to the code in its URL:
  `https://codeforces.com/group/<groupCode>/contest/<contestId>`.
  It is included in authenticated standings requests.
- `problemSources` follows the exact Gym problem order. Each rated problem maps
  to its original Codeforces contest and problem index; use `null` for an
  unrated problem.

The fixed scoring rule uses the Gym standings only for each contestant's solved
set. Each problem is normalized inside its original contest, counting only
parties that solved at least one problem, and the mapped problem scores are then
summed. Onsite scores are multiplied by two in the final ranking.

For a source contest, let `N` be the number of standings parties with at least
one accepted problem, and `n_j` the number solving problem `j`. Its raw weight is
`r_j = 1 - ln(n_j / N)`, with weight zero if `n_j = 0`. Its normalized weight is
`w_j = r_j / sum_k[(n_k / N) * r_k]`, where the denominator includes all source
contest problems. A Gym score is the sum of `w_j` for the mapped, rated problems
the contestant solved; it is not normalized again using the Gym participants.

To enable a pending onsite contest, fill in its `id`, timezone-aware
`startTime`, and `groupCode` if applicable. For a Gym, also populate
`problemSources` in the API problem order. Verify authenticated standings
access, then set `enabled` to `true`. Choose the timestamp's UTC offset for the
actual contest date, accounting for daylight saving time when applicable.

Private Gym access uses the Codeforces API. Put the API key on the first line
and the API secret on the second line of `.codeforces_api_config.txt`.

## Contribution
Please feel free to contribute to the project by creating a pull request.
