import datetime
import feedparser
import requests

STOCK_DAY_API = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
MI_INDEX_API = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
INSTITUTIONAL_T86_API = "https://www.twse.com.tw/rwd/zh/fund/T86"
INSTITUTIONAL_CACHE = None
INSTITUTIONAL_DATA_DATE = None


def get_month_strings(months=2):
    today = datetime.date.today()
    result = []
    for _ in range(months):
        result.append(today.strftime("%Y%m"))
        first_day = today.replace(day=1)
        today = first_day - datetime.timedelta(days=1)
    return result


def parse_int(value):
    try:
        return int(str(value).replace(',', '').replace('X', '').strip())
    except Exception:
        return 0


def parse_float(value):
    try:
        return float(str(value).replace(',', '').replace('X', '').strip())
    except Exception:
        return 0.0


def fetch_top_stocks_by_market_cap(limit=150):
    """取得市值前 N 大的股票清單。

    TWSE 公開資料中並無提供「個股市值」欄位（T86 僅有法人買賣超、
    BWIBBU_d 僅有股價淨值比、MI_INDEX 僅有大盤統計，皆無股本/市值），
    因此改用「成交金額」作為市值的替代指標進行排序——
    成交金額高的個股通常是大型權值股（如台積電、聯發科、鴻海等），
    與市值排名高度相關。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        api_url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL"
        today = datetime.date.today()
        params = {
            "response": "json",
            "date": today.strftime("%Y%m%d"),
        }

        response = requests.get(api_url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()

        if payload.get("stat") == "OK":
            rows = payload.get("data", [])
            candidates = []
            for row in rows:
                if len(row) < 4:
                    continue
                stock_id = row[0].strip()
                stock_name = row[1].strip()
                if not (stock_id.isdigit() and len(stock_id) == 4 and not stock_id.startswith('0')):
                    continue
                turnover = parse_float(row[3])
                candidates.append((turnover, {"id": stock_id, "name": stock_name}))

            candidates.sort(key=lambda item: item[0], reverse=True)
            stocks = [item[1] for item in candidates[:limit]]

            if stocks:
                return stocks

        raise RuntimeError("無法從 TWSE API 取得足夠的股票資料")

    except Exception as exc:
        print(f"警告：{exc}")
        print("將使用常見股票清單作為備用方案...")
        return fetch_popular_stocks(limit)


def fetch_taiex_index():
    """取得今日加權股價指數（發行量加權股價指數）的收盤點位與漲跌幅。
    使用 TWSE MI_INDEX API（type=IND，僅取價格指數表），若當日無資料則往前回溯查詢。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    base_date = datetime.date.today()

    for offset in range(7):
        query_date = (base_date - datetime.timedelta(days=offset)).strftime("%Y%m%d")
        params = {
            "response": "json",
            "date": query_date,
            "type": "IND",
        }

        try:
            response = requests.get(MI_INDEX_API, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            payload = response.json()

            if payload.get("stat") != "OK":
                continue

            for table in payload.get("tables", []):
                for row in table.get("data", []):
                    if not row or row[0] != "發行量加權股價指數":
                        continue

                    points = parse_float(row[1])
                    change_points = abs(parse_float(row[3]))
                    change_pct = parse_float(row[4])
                    if change_pct < 0:
                        change_points = -change_points

                    return {
                        "date": query_date,
                        "points": points,
                        "change": change_points,
                        "change_pct": change_pct,
                    }
        except Exception:
            continue

    return None


def fetch_popular_stocks(limit=150):
    """備用方案：取得常見的台灣股票清單"""
    popular_stocks_data = {
        "2330": "台積電",
        "2317": "鴻海",
        "2454": "聯發科",
        "2412": "中華電",
        "2308": "台達電",
        "2881": "富邦金",
        "2882": "國泰金",
        "2891": "中信金",
        "2892": "第一金",
        "2887": "台新金",
        "2885": "元大金",
        "1303": "台塑",
        "1301": "台塑化",
        "2409": "友達",
        "2435": "奇力新",
        "3711": "日月光",
        "2498": "宏達電",
        "2357": "瑞昱",
        "2382": "廣達",
        "2880": "華南金",
        "2301": "光磊",
        "2327": "微星",
        "2355": "華碩",
        "2379": "瑞昱",
        "2390": "互盛",
        "2408": "南科",
        "2411": "高通",
        "2420": "新磊",
        "2425": "互盛",
        "2441": "超豐",
        "2448": "晶體",
        "2451": "創意",
        "2458": "義隆",
        "2474": "緯穎",
        "2492": "華新科",
        "2501": "國巨",
        "2535": "宏普",
        "2542": "興勤",
        "2603": "長榮",
        "2609": "陽明",
        "2615": "萬海",
        "2618": "浩鼎",
        "2633": "台灣高鐵",
        "2701": "南港",
        "2702": "華碩",
        "2801": "彩晶",
        "2823": "中環",
        "2826": "交通銀行",
        "2832": "台產",
        "2833": "台險",
        "2834": "臺灣銀行",
        "2836": "和泰",
        "2845": "遠傳",
        "2847": "台塑",
        "2849": "首信",
        "2850": "世界",
        "2851": "中信",
        "2852": "國泰",
        "2880": "華南金",
        "2881": "富邦金",
        "2882": "國泰金",
        "2883": "開發金",
        "2884": "玉山金",
        "2885": "元大金",
        "2886": "兆豐金",
        "2887": "台新金",
        "2888": "新光金",
        "2889": "國票金",
        "2890": "永豐金",
        "2891": "中信金",
        "2892": "第一金",
        "3008": "大立光",
        "3017": "奇美",
        "3019": "亞光",
        "3034": "聯詠",
        "3037": "欣興",
        "3045": "尖點",
        "3047": "銘異",
        "3050": "鈺寶科",
        "3054": "立萬歲",
        "3055": "蔚華科",
        "3057": "喜鴻",
        "3064": "銘異",
        "3066": "瑞磁",
        "3078": "僑威",
        "3105": "正達",
        "3149": "陽光",
        "3229": "晶鑫",
        "3231": "緯創",
        "3289": "宏科",
        "3437": "榮瑋",
        "3443": "創意",
        "3501": "鑫禾",
        "3533": "嘉澤",
        "3545": "同欣電",
        "3557": "嘉澤",
        "3579": "尖點",
        "3682": "亞光",
        "3711": "日月光",
        "3713": "力旺",
        "3714": "富采",
        "3721": "磊晶",
        "3722": "台積電",
        "3764": "老虎",
        "4904": "遠傳",
        "4938": "和泰",
        "5269": "祥碩",
        "5521": "工業技術研究院",
        "5607": "遠端",
        "5608": "顥天",
        "5854": "愛普",
        "6005": "群益證",
        "6024": "群益期",
        "6066": "王磊",
        "6116": "相紙",
        "6121": "新普",
        "6125": "瑞磁",
        "6147": "力晶",
        "6176": "瑞昱",
        "6239": "力積電",
        "6269": "台郡",
        "6415": "矽格",
        "6442": "光磊",
        "6505": "台塑化",
        "6525": "捷敏",
        "6669": "緯軟",
        "8016": "矽創",
        "8028": "鉅祥",
        "8081": "致新",
        "8367": "光寶",
        "8454": "富邦媒",
        "9910": "豐泰",
        "9914": "美利達",
        "9917": "中美矽晶",
        "9921": "巨大",
        "9926": "新光紡",
        "9927": "中視",
        "9928": "中視",
        "9929": "華碩",
        "9933": "中華電",
        "9938": "百和",
        "9941": "裕融",
        "9942": "茂迪",
        "9945": "潤泰全",
        "9950": "股神",
    }

    stocks = [{"id": stock_id, "name": name} for stock_id, name in popular_stocks_data.items()]
    return stocks[:limit]


def fetch_stock_history(stock_id, days=30):
    """抓取股票近 N 個交易日的歷史價格資料"""
    months = get_month_strings(3)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    all_rows = []

    for month in reversed(months):
        params = {
            "response": "json",
            "date": month,
            "stockNo": stock_id,
        }
        try:
            response = requests.get(STOCK_DAY_API, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
            if payload.get("stat") != "OK":
                continue

            rows = payload.get("data", [])
            if rows:
                all_rows.extend(rows)
        except Exception:
            continue

    if not all_rows:
        return []

    history = []
    for row in all_rows:
        if len(row) < 7:
            continue

        close_price = parse_float(row[6])
        if close_price <= 0:
            continue

        history.append({
            "date": row[0],
            "volume": parse_int(row[1]),
            "open": parse_float(row[3]),
            "high": parse_float(row[4]),
            "low": parse_float(row[5]),
            "close": close_price,
            "change": str(row[7]).strip(),
        })

    history.sort(key=lambda x: x["date"])
    return history[-days:]


def fetch_latest_price(stock_id):
    """抓取單一股票的今日收盤價和漲跌幅"""
    history = fetch_stock_history(stock_id, days=30)
    if not history:
        return None

    latest = history[-1]
    close_price = f"{latest['close']:.2f}"
    price_change = latest["change"]

    try:
        change_float = float(str(price_change).replace(',', '').replace('+', '').strip())
    except ValueError:
        change_float = 0.0

    return {
        "stock_id": stock_id,
        "stock_name": "",
        "date": latest["date"],
        "close": close_price,
        "change": price_change,
        "change_float": change_float,
        "volume": latest["volume"],
        "history": history,
    }


def _load_institutional_data():
    global INSTITUTIONAL_CACHE, INSTITUTIONAL_DATA_DATE
    if INSTITUTIONAL_CACHE is not None:
        return INSTITUTIONAL_CACHE

    base_date = datetime.date.today()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    for offset in range(7):
        query_date = (base_date - datetime.timedelta(days=offset)).strftime("%Y%m%d")
        params = {
            "response": "json",
            "date": query_date,
            "selectType": "ALL",
        }

        try:
            response = requests.get(INSTITUTIONAL_T86_API, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            payload = response.json()

            if payload.get("stat") != "OK":
                continue

            rows = payload.get("data", [])
            if not rows:
                continue

            inst_data = {}
            for row in rows:
                if not isinstance(row, list) or len(row) < 19:
                    continue
                stock_code = str(row[0]).strip()
                inst_data[stock_code] = row

            INSTITUTIONAL_CACHE = inst_data
            INSTITUTIONAL_DATA_DATE = query_date
            return inst_data
        except Exception:
            continue

    INSTITUTIONAL_CACHE = {}
    INSTITUTIONAL_DATA_DATE = None
    return INSTITUTIONAL_CACHE


def fetch_institutional(stock_code):
    """從 TWSE 取得法人買賣超（外資、投信、自營商）。
    若資料日期距今超過 2 天（非最近 2 個交易日內）則視為過舊，回傳 None。"""
    data_rows = _load_institutional_data()
    result_date = INSTITUTIONAL_DATA_DATE or datetime.date.today().strftime("%Y%m%d")

    try:
        data_date = datetime.datetime.strptime(result_date, "%Y%m%d").date()
        days_old = (datetime.date.today() - data_date).days
        if days_old > 2:
            print(f"⚠️ {stock_code} 法人資料過舊（資料日期 {result_date}，距今已 {days_old} 天），視為無效")
            return None
    except ValueError:
        pass

    result = {
        "foreign_net": 0,
        "investment_trust_net": 0,
        "dealer_net": 0,
        "three_major_net": 0,
        "source": "TWSE 法人買賣超",
        "date": result_date,
    }

    row = data_rows.get(str(stock_code).strip())
    if not row:
        return result

    result["foreign_net"] = parse_int(row[4]).__int__()
    result["investment_trust_net"] = parse_int(row[10]).__int__()
    result["dealer_net"] = parse_int(row[14]).__int__()
    result["three_major_net"] = parse_int(row[18]).__int__()
    return result


def fetch_news(stock_code, stock_name):
    """從鉅亨網與 Google News RSS 抓取近 3 日新聞，最多 5 則"""
    urls = [
        f"https://www.cnyes.com/rss/cat/tw_stock",
        f"https://news.google.com/rss/search?q={stock_name}+股票&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        f"https://news.google.com/rss/search?q={stock_code}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    ]
    now = datetime.datetime.now(datetime.timezone.utc)
    recent_news = []

    for url in urls:
        try:
            feed = feedparser.parse(url)
            if not getattr(feed, "entries", None):
                continue

            for entry in feed.entries:
                published = None
                if getattr(entry, "published_parsed", None):
                    published = datetime.datetime(*entry.published_parsed[:6], tzinfo=datetime.timezone.utc)
                elif getattr(entry, "updated_parsed", None):
                    published = datetime.datetime(*entry.updated_parsed[:6], tzinfo=datetime.timezone.utc)

                if published is None:
                    continue

                age = now - published
                if age.days > 3:
                    continue

                recent_news.append({
                    "title": entry.get("title", "無標題"),
                    "link": entry.get("link", ""),
                    "published": published.strftime("%Y-%m-%d"),
                })

                if len(recent_news) >= 5:
                    break
            
            if len(recent_news) >= 5:
                break
        except Exception:
            continue

    return recent_news
