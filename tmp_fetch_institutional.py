import requests
import datetime
import json

stock = '1503'
today = datetime.date.today().strftime('%Y%m%d')
url = 'https://www.twse.com.tw/rwd/zh/fund/BFI82'
params = {'response': 'json', 'date': today, 'stockNo': stock}
print('URL:', url)
print('PARAMS:', params)
resp = requests.get(url, params=params, timeout=15)
print('STATUS:', resp.status_code)
try:
    data = resp.json()
except Exception as exc:
    print('JSON ERROR', exc)
    print(resp.text[:2000])
    raise
print('KEYS:', list(data.keys()))
print('fields:', data.get('fields'))
print('data count:', len(data.get('data', [])))
print('first row:', data.get('data', [])[0] if data.get('data') else None)
print('payload snippet:')
print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
