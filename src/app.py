from flask import Flask, render_template, request
import cloudscraper
import requests
import concurrent.futures
import time
from bs4 import BeautifulSoup
import urllib.parse

app = Flask(__name__)

# 使用 Cloudscraper 模拟桌面 Chrome 浏览器
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

def format_size(size):
    # 简单的格式化，如果在源站拿到的就是字符串则直接返回
    return str(size)

# === 引擎 1: BT4G (主力，抗封能力极强) ===
def search_bt4g(kw):
    try:
        # bt4gprx.com 是它的官方代理域名，比主域名更稳
        url = f"https://bt4gprx.com/search?q={urllib.parse.quote(kw)}"
        print(f"[BT4G] Searching: {url}")
        
        resp = scraper.get(url, timeout=15)
        
        if resp.status_code != 200:
            print(f"[BT4G] Failed: {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        
        # BT4G 的列表结构
        for item in soup.select('div.row.marketing div.card'):
            try:
                title_tag = item.select_one('h5.card-title a')
                if not title_tag: continue
                name = title_tag.get_text(strip=True)
                magnet = item.select_one('a[href^="magnet:"]')['href']
                
                # 提取信息
                stats = item.select('.card-body span')
                # 通常是: [Create Time, Size, Seeders, Leechers]
                size = "N/A"
                seeders = "0"
                leechers = "0"
                date = "Unknown"
                
                for stat in stats:
                    txt = stat.get_text(strip=True)
                    if 'Size:' in txt: size = txt.replace('Size:', '').strip()
                    if 'Seeds:' in txt: seeders = txt.replace('Seeds:', '').strip()
                    if 'Leechers:' in txt: leechers = txt.replace('Leechers:', '').strip()
                    if 'Create Time:' in txt: date = txt.replace('Create Time:', '').strip()

                results.append({
                    'engine': 'BT4G',
                    'name': name,
                    'size': size,
                    'date': date,
                    'magnet': magnet,
                    'seeders': seeders,
                    'leechers': leechers
                })
            except Exception as e:
                continue
        print(f"[BT4G] Found {len(results)} items")
        return results
    except Exception as e:
        print(f"[BT4G] Error: {e}")
        return []

# === 引擎 2: MagnetDL (纯静态，速度快) ===
def search_magnetdl(kw):
    try:
        # MagnetDL 必须处理关键词：空格转横杠
        clean_kw = kw.strip().lower().replace(" ", "-")
        url = f"https://www.magnetdl.com/{clean_kw[0]}/{clean_kw}/"
        print(f"[MagnetDL] Searching: {url}")
        
        resp = scraper.get(url, timeout=15)
        if resp.status_code != 200: return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        
        rows = soup.select('table.download tbody tr')
        for row in rows:
            try:
                cols = row.find_all('td')
                if len(cols) < 8: continue
                
                magnet_tag = cols[0].find('a', href=True)
                if not magnet_tag: continue
                
                results.append({
                    'engine': 'MagnetDL',
                    'name': cols[1].get_text(strip=True),
                    'size': cols[5].get_text(strip=True),
                    'date': cols[2].get_text(strip=True),
                    'magnet': magnet_tag['href'],
                    'seeders': cols[6].get_text(strip=True),
                    'leechers': cols[7].get_text(strip=True)
                })
            except: continue
        print(f"[MagnetDL] Found {len(results)} items")
        return results
    except Exception as e:
        print(f"[MagnetDL] Error: {e}")
        return []

# === 引擎 3: YTS (官方API，不用爬虫) ===
def search_yts(kw):
    url = "https://yts.mx/api/v2/list_movies.json"
    try:
        resp = requests.get(url, params={"query_term": kw, "limit": 10}, timeout=10)
        data = resp.json()
        results = []
        if data.get('status') == 'ok' and data['data'].get('movie_count') > 0:
            for m in data['data']['movies']:
                for t in m.get('torrents', []):
                    magnet = f"magnet:?xt=urn:btih:{t['hash']}&dn={urllib.parse.quote(m['title'])}"
                    results.append({
                        'engine': 'YTS',
                        'name': f"{m['title']} ({t['quality']})",
                        'size': t['size'],
                        'date': str(m['year']),
                        'magnet': magnet,
                        'seeders': str(t['seeds']),
                        'leechers': str(t['peers'])
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
            # 并发搜索
            with concurrent.futures.ThreadPoolExecutor() as executor:
                f1 = executor.submit(search_bt4g, kw)
                f2 = executor.submit(search_magnetdl, kw)
                f3 = executor.submit(search_yts, kw)
                
                results = f1.result() + f2.result() + f3.result()
            
            duration = round(time.time() - start_t, 2)
            if not results:
                # 打印到 Docker 日志，方便排查
                print("No results found. Sources might be blocking the IP.")
                error = f"未找到资源 (耗时 {duration}s) - 可能 VPS IP 被反爬拦截"
            else:
                # 简单的去重
                seen = set()
                unique = []
                for item in results:
                    if item['magnet'] not in seen:
                        unique.append(item)
                        seen.add(item['magnet'])
                results = unique

    return render_template('index.html', results=results, keyword=kw, error=error)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
