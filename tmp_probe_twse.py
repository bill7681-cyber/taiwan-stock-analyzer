import requests
import datetime

stock='1503'
today=datetime.date.today().strftime('%Y%m%d')
urls=[
    'https://www.twse.com.tw/rwd/zh/fund/BFI82',
    'https://www.twse.com.tw/fund/BFI82',
    'https://www.twse.com.tw/exchangeReport/BFI82',
]
for url in urls:
    print('URL:', url)
    try:
        resp=requests.get(url, params={'response':'json','date':today,'stockNo':stock}, timeout=15)
        print(' status', resp.status_code, 'len', len(resp.text))
        if resp.status_code==200 and resp.text.strip().startswith('{'):
            print('json keys', resp.json().keys())
        else:
            print(resp.text[:400])
    except Exception as e:
        print('err', e)
    print('---')
