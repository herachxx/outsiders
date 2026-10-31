"""Opt-in synthetic examples for UI evaluation. Never use real player data."""
import argparse
import os
from app.core import TriageService
from app.rules import RuleIndex
from app.support.store import TicketStore

FAKE_RULES={'rules':[{'id':30,'category':'DEMO ONLY — not official game rules','points':[
    {'ref':'2.1','text':'Запрещены оскорбления игроков.'},
    {'ref':'5.2','text':'Запрещено использовать читы.'}]}]}
CASES=[
 ('complaint','Игрок Kairat_B оскорблял меня в чате около 15:30, прикладываю скриншоты.','Сервер 01','Kairat_B',2,'2.1'),
 ('report','Оплатил 500 Grand Coins, деньги списались, но на мой аккаунт валюта не поступила.','Сервер 03',None,1,None),
 ('complaint','Игрок летал на машине и стрелял сквозь стены. Прошу проверить запись.','Сервер 02','XPlayer_20',1,'5.2'),
 ('report','Как устроиться на работу механиком? Я на первом сервере.','Сервер 01',None,0,None),
 ('report','Игра вылетает после загрузки. Выдаёт ошибку соединения.','Сервер 05',None,0,None)
]

def main():
    parser=argparse.ArgumentParser(description='Add five completely synthetic tickets to a local SQLite DB')
    parser.add_argument('--db',default=os.environ.get('GRAND_DB_PATH','data/dev-support.sqlite3'))
    args=parser.parse_args()
    store=TicketStore(args.db)
    service=TriageService(RuleIndex.from_data(FAKE_RULES))
    existing={item['request']['messages'][0]['text'] for item in store.list(limit=200)['items']}
    count=0
    for kind,message,region,nick,images,rule in CASES:
        if message in existing:continue
        request={'kind':kind,'messages':[{'role':'player','text':message}],
                 'region':region,'reported_nick':nick,'images_count':images,'rule_refs_raw':rule}
        result=service.triage(request)
        if kind=='complaint' or result['category'] in ('report.payment','report.account'):result['needs_human']=True
        store.create(request,result,source='synthetic-demo')
        count+=1
    print(f'Created {count} SYNTHETIC tickets in {args.db}. Rules are illustrative only.')


if __name__=='__main__':main()
