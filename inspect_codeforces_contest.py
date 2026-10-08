"""Inspect one Codeforces contest's standings and one configured user's submissions.

Usage:
    python3 inspect_codeforces_contest.py 2275
    python3 inspect_codeforces_contest.py 2275 --user Kirill

The standings request intentionally contains only contestId. Codeforces only
allows anonymous users to make that exact request for non-Gym contests.
"""

import argparse
import json
from pathlib import Path

import codeforcesApi as cf_api


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"


def load_handle(user_name):
    with CONFIG_PATH.open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    try:
        return config["users"][user_name]["codeforces-handle"]
    except KeyError as error:
        raise SystemExit(f"No Codeforces handle configured for user {user_name!r}") from error


def find_standing_rows(rows, handle):
    folded_handle = handle.casefold()
    all_member_matches = []
    first_member_matches = []

    for row in rows:
        members = row.get("party", {}).get("members", [])
        matching_members = [
            member.get("handle")
            for member in members
            if member.get("handle", "").casefold() == folded_handle
        ]
        if matching_members:
            all_member_matches.append((row, matching_members))
        if members and members[0].get("handle", "").casefold() == folded_handle:
            first_member_matches.append(row)

    return all_member_matches, first_member_matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contest_id", type=int, help="Codeforces contest ID")
    parser.add_argument("--user", default="Kirill", help="Name in config.json (default: Kirill)")
    parser.add_argument(
        "--output",
        type=Path,
        help="Path for the raw standings JSON (default: contest_<id>_standings.json beside this script)",
    )
    args = parser.parse_args()

    handle = load_handle(args.user)
    print(f"Configured user: {args.user} ({handle})")
    print(f"Fetching contest {args.contest_id} standings...")

    standings = cf_api.request("contest.standings", {"contestId": args.contest_id})
    if standings is False:
        raise SystemExit("Could not fetch standings; see the Codeforces API error above.")

    output_path = args.output or ROOT / f"contest_{args.contest_id}_standings.json"
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(standings, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    print(f"Raw standings JSON saved to: {output_path}")

    contest = standings.get("contest", {})
    rows = standings.get("rows", [])
    matches, first_member_matches = find_standing_rows(rows, handle)
    print(f"Contest: {contest.get('name', '(name unavailable)')}")
    print(f"Phase: {contest.get('phase', '(unknown)')}")
    print(f"Standings rows returned: {len(rows)}")
    if rows:
        print(f"First returned rank: {rows[0].get('rank')}")
        print(f"Last returned rank: {rows[-1].get('rank')}")
    print(f"Rows containing {handle} in any team member position: {len(matches)}")
    print(f"Rows the current code would match (first member only): {len(first_member_matches)}")

    for row, matching_members in matches:
        party = row.get("party", {})
        print("Standing match:")
        print(f"  rank: {row.get('rank')}")
        print(f"  points: {row.get('points')}")
        print(f"  members: {[m.get('handle') for m in party.get('members', [])]}")
        print(f"  matched handles: {matching_members}")
        print(f"  participantType: {party.get('participantType')}")
        print(f"  problem results: {[p.get('points') for p in row.get('problemResults', [])]}")

    # Public regular-contest standings cannot be filtered or paged for
    # anonymous callers. Rated contests expose a separate per-handle endpoint
    # that includes the official rank, even when a handle is absent from the
    # standings response above.
    print(f"Fetching rating changes for contest {args.contest_id}...")
    rating_changes = cf_api.request(
        "contest.ratingChanges",
        {"contestId": args.contest_id},
    )
    if rating_changes is False:
        print("Could not fetch rating changes; see the Codeforces API error above.")
    else:
        rating_matches = [
            change
            for change in rating_changes
            if change.get("handle", "").casefold() == handle.casefold()
        ]
        print(f"Rating changes returned: {len(rating_changes)}")
        if rating_matches:
            change = rating_matches[0]
            print(f"Official rank from contest.ratingChanges: {change.get('rank')}")
            print(f"Rating: {change.get('oldRating')} -> {change.get('newRating')}")
        else:
            print(f"No rating-change record for {handle} in this contest.")

    print(f"Fetching recent submissions for {handle}...")
    submissions = cf_api.request(
        "user.status",
        {"handle": handle, "from": 1, "count": 1000},
    )
    if submissions is False:
        print("Could not fetch submissions; see the Codeforces API error above.")
        return

    contest_submissions = [s for s in submissions if s.get("contestId") == args.contest_id]
    print(f"Recent submissions returned: {len(submissions)}")
    print(f"Submissions for contest {args.contest_id} in that response: {len(contest_submissions)}")
    for submission in contest_submissions:
        problem = submission.get("problem", {})
        author = submission.get("author", {})
        print(
            "  "
            f"problem={problem.get('index', '?')} "
            f"verdict={submission.get('verdict', '?')} "
            f"participantType={author.get('participantType', '?')} "
            f"participantId={author.get('participantId', '?')} "
            f"time={submission.get('creationTimeSeconds', '?')}"
        )

    accepted = sorted({
        s.get("problem", {}).get("index")
        for s in contest_submissions
        if s.get("verdict") == "OK" and s.get("problem", {}).get("index")
    })
    print(f"Accepted problem indices in recent submissions: {accepted}")
    if contest_submissions and not matches:
        print("DIAGNOSIS: submissions exist, but this standings response has no row for the configured handle.")
    elif matches and not first_member_matches:
        print("DIAGNOSIS: the handle appears in the standings, but not as the first team member.")
    elif matches:
        print("DIAGNOSIS: the handle appears in the standings and is matchable by the current first-member lookup.")
    elif not contest_submissions:
        print("DIAGNOSIS: neither the returned standings nor the recent submissions show this contest.")


if __name__ == "__main__":
    main()
