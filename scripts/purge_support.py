"""Delete locally stored ticket data after configured retention period.

Run daily with OS cron / Task Scheduler. Do not run against a shared dataset
unless the data ownership and deletion policy authorize it.
"""
import argparse
import os
from app.support.store import TicketStore


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--days',type=int,default=14)
    parser.add_argument('--db',default=os.getenv('GRAND_DB_PATH','data/support.sqlite3'))
    args=parser.parse_args()
    if args.days<1:parser.error('--days must be positive')
    print('Deleted tickets:',TicketStore(args.db).purge(args.days))


if __name__=='__main__':main()
