from datetime import datetime

from ranking import Ranking
import util
from util import Table, readConfigOffline
from contestDates import ContestDates

if __name__ == '__main__':
  config = readConfigOffline()

  contestDates = ContestDates(config)
  newContestDates = contestDates.getDates()
  for contestDate in newContestDates:
    contestDate = {
      'date': datetime.fromtimestamp(contestDate['time']),
      **contestDate
    }
    print(contestDate)

  ranking = Ranking(config)
  table = ranking.getTable()
  print("\nSTANDINGS:\n ")
  print(table.toStr(width=80))
  print(">> Contestants marked with * are ineligible <<")
