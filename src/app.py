from flask import Flask, render_template, request
import requests
import concurrent.futures
import urllib.parse
import time

app = Flask(__name__)

# 基础请求头
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
}

def format_size(size):
    try:
        size = int(size)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024: return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    except: return str(size)

# === 源 1: APIBay (海盗湾) - 核心主力 ===
# 这是一个纯 API，不经过 Cloudflare 验证，VPS 99% 能连上
def search_apibay(kw):
    url = "https://apibay.org/q.php"
    # cat=0 代表所有类别
    params = {'q': kw, 'cat': ''}
    try:
        print(f"[APIBay] 请求中: {kw}")
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        
        # APIBay 如果没结果会返回 id=0
        if data and data[0].get('id') == '0':
            return []
            
        results = []
        for i in data:
            if i.get('name') == 'No results returned': continue
            
            # 构造磁力链
            magnet = f"magnet:?xt=urn:btih:{i['info_hash']}&dn={urllib.parse.quote(i['name'])}"
            
            results.append({
                'engine': 'ThePirateBay',
                'name': i['name'],
                'size': format_size(i['size']),
                'date': "Unknown", # APIBay 不返回具体日期，只返回时间戳，这里简化处理
                'magnet': magnet,
                'seeders': i['seeders'],
                'leechers': i['leechers']
            })
        print(f"[APIBay] 找到 {len(results)} 个结果")
        return results
    except Exception as e:
        print(f"[APIBay] Error: {e}")
        return []

# === 源 2: YTS (官方 API) - 电影主力 ===
# 官方提供给开发者的，绝对稳
def search_yts(kw):
    url = "https://yts.mx/api/v2/list_movies.json"
    params = {"query_term": kw, "limit": 20}
    try:
        print(f"[YTS] 请求中: {kw}")
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        results = []
        if data.get('status') == 'ok' and data['data'].get('movie_count') > 0:
            for m in data['data']['movies']:
                for t in m.get('torrents', []):
                    magnet = f"magnet:?xt=urn:btih:{t['hash']}&dn={urllib.parse.quote(m['title'])}"
                    results.append({
                        'engine': 'YTS',
                        'name': f"{m['title_long']} ({t['quality']})",
                        'size': t['size'],
                        'date': str(m['year']),
                        'magnet': magnet,
                        'seeders': str(t['seeds']),
                        'leechers': str(t['peers'])
                    })
        print(f"[YTS] 找到 {len(results)} 个结果")
        return results
    except Exception as e:
        print(f"[YTS] Error: {e}")
        return []

# === 源 3: BT4G (备用) ===
# 尝试直接请求
def search_bt4g(kw):
    try:
        url = f"https://bt4gprx.com/search?q={urllib.parse.quote(kw)}"
        # BT4G 有时候需要更像浏览器的 Header
        h = HEADERS.copy()
        h['Referer'] = 'https://bt4gprx.com/'
        
        resp = requests.get(url, headers=h, timeout=8)
        if resp.status_code != 200: return []
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        
        for item in soup.select('div.row.marketing div.card'):
            try:
                title = item.select_one('h5.card-title a').get_text(strip=True)
                link = item.select_one('a[href^="magnet:"]')['href']
                # 简单提取，不纠结详细信息，保证能拿到链接
                results.append({
                    'engine': 'BT4G',
                    'name': title,
                    'size': 'N/A',
                    'date': 'Unknown',
                    'magnet': link,
                    'seeders': '?',
                    'leechers': '?'
                })
            except: continue
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
            # 并发请求
            with concurrent.futures.ThreadPoolExecutor() as executor:
                f1 = executor.submit(search_apibay, kw)
                f2 = executor.submit(search_yts, kw)
                f3 = executor.submit(search_bt4g, kw)
                
                # 优先显示 APIBay 和 YTS 的结果，因为它们最准
                results = f1.result() + f2.result() + f3.result()
            
            duration = round(time.time() - start_t, 2)
            if not results:
                error = f"未找到资源 (耗时 {duration}s)。可能关键词无结果，或 VPS IP 被所有源站屏蔽。"
            else:
                # 简单的磁力链去重
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
