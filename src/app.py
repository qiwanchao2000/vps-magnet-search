from flask import Flask, render_template, request
import cloudscraper
import requests
import concurrent.futures
import time

app = Flask(__name__)

# 模拟浏览器 (防止被识别为爬虫)
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'linux', 'desktop': True}
)

def format_size(size):
    try:
        size = int(size)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024: return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    except: return str(size)

# === 引擎 1: SolidTorrents (API) ===
def search_solid(kw):
    url = "https://solidtorrents.to/api/v1/search"
    params = {"q": kw, "category": "all", "sort": "seeders"}
    try:
        resp = scraper.get(url, params=params, timeout=10)
        data = resp.json()
        results = []
        for i in data.get('hits', []):
            results.append({
                'engine': 'Solid',
                'name': i['title'],
                'size': format_size(i['size']),
                'date': i['imported'].split('T')[0],
                'magnet': i['magnet'],
                'seeders': i['swarm']['seeders'],
                'leechers': i['swarm']['leechers']
            })
        return results
    except Exception as e:
        print(f"[Solid Error] {e}")
        return []

# === 引擎 2: BitSearch (HTML) ===
def search_bit(kw):
    url = f"https://bitsearch.to/search?q={kw}"
    try:
        resp = scraper.get(url, timeout=10)
        if resp.status_code != 200: return []
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        for item in soup.select('li.search-result'):
            try:
                name = item.select_one('.info h5 a').get_text(strip=True)
                magnet = item.select_one('.links a.dl-magnet')['href']
                stats = item.select('.stats div')
                if len(stats) >= 5:
                    results.append({
                        'engine': 'Bit',
                        'name': name,
                        'size': stats[1].get_text(strip=True),
                        'date': stats[4].get_text(strip=True),
                        'magnet': magnet,
                        'seeders': stats[2].get_text(strip=True),
                        'leechers': stats[3].get_text(strip=True)
                    })
            except: continue
        return results
    except Exception as e:
        print(f"[Bit Error] {e}")
        return []

# === 引擎 3: YTS (API - 仅电影) ===
def search_yts(kw):
    url = "https://yts.mx/api/v2/list_movies.json"
    params = {"query_term": kw, "limit": 10}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        results = []
        if data.get('status') == 'ok' and data['data'].get('movie_count') > 0:
            for m in data['data']['movies']:
                for t in m.get('torrents', []):
                    magnet = f"magnet:?xt=urn:btih:{t['hash']}&dn={m['title']}"
                    results.append({
                        'engine': 'YTS',
                        'name': f"{m['title']} ({t['quality']})",
                        'size': t['size'],
                        'date': str(m['year']),
                        'magnet': magnet,
                        'seeders': t['seeds'],
                        'leechers': t['peers']
                    })
        return results
    except: return []

@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    kw = ""
    error = None

    if request.method == 'POST':
        kw = request.form.get('keyword')
        if kw:
            start_t = time.time()
            # 并发搜索，效率最大化
            with concurrent.futures.ThreadPoolExecutor() as executor:
                f1 = executor.submit(search_solid, kw)
                f2 = executor.submit(search_bit, kw)
                f3 = executor.submit(search_yts, kw)
                
                # 汇总结果
                results = f1.result() + f2.result() + f3.result()
            
            duration = round(time.time() - start_t, 2)
            if not results:
                error = f"未找到资源 (耗时 {duration}s)"
            else:
                # 简单的去重逻辑 (根据磁力链接)
                seen = set()
                unique_results = []
                for item in results:
                    if item['magnet'] not in seen:
                        unique_results.append(item)
                        seen.add(item['magnet'])
                results = unique_results

    return render_template('index.html', results=results, keyword=kw, error=error)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
