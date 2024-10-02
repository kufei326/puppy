from sanic import Sanic
from config.site_config import sites, credentials, downloaders
from log import writeLog
from seed import seed
from sanic.response import html, redirect, json, text
import jinja2, os
from sanic.log import logger
import asyncio
from functools import wraps
import re

app = Sanic(__name__)
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))
app.static('/static', './static')
config_file_path = 'config/site_config.py'


def update_config_list(config_file_path, list_name, new_list):
    """
    更新配置文件中的指定列表。

    :param config_file_path: 配置文件的路径
    :param list_name: 要更新的列表名称（如 'sites', 'downloaders'）
    :param new_list: 新的列表内容
    """
    with open(config_file_path, 'r', encoding='utf-8') as f:
        config_content = f.read()
    new_list_str = f"{list_name} = {new_list!r}"
    pattern = re.compile(rf"{list_name}\s*=\s*\[.*?\]", re.DOTALL)
    updated_content = pattern.sub(new_list_str, config_content)

    with open(config_file_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)

from sanic import Sanic, response

@app.route('/logs', methods=['GET', 'POST'])
async def handle_logs(request):
    log_file_path = 'log/reseed.log'

    if request.method == 'POST':
        if 'clear_logs' in request.form:
            try:
                logger.info("Attempting to clear log file...")
                if os.path.exists(log_file_path):
                    with open(log_file_path, 'w') as log_file:
                        log_file.write('')  # 清空文件内容
                    logger.info("Log file cleared successfully.")
                else:
                    logger.warning(f"Log file not found at {log_file_path}")
                return response.json({"status": "success"})
            except Exception as e:
                logger.error(f"Error clearing log file: {str(e)}")
                return response.json({"status": "error", "message": str(e)})

    log_content = await get_log_content(log_file_path)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # 这是一个 AJAX 请求，只返回日志内容
        return response.text(log_content)
    else:
        # 这是一个常规请求，返回完整的 HTML 页面
        template = jinja_env.get_template('logo.html')
        html_content = template.render(log_content=log_content)
        return response.html(html_content)

async def get_log_content(log_file_path):
    try:
        if os.path.exists(log_file_path):
            with open(log_file_path, 'r', encoding='utf-8') as log_file:
                log_content = log_file.readlines()
                log_content.reverse()
                return ''.join(log_content)
        else:
            return "Log file not found"
    except Exception as e:
        logger.error(f"Error reading log file: {str(e)}")
        return f"Error reading log file: {str(e)}"

@app.route('/downloader')
async def downloader(request):
    existing_downloaders = [d for d in downloaders if d['name'] != '']
    template = jinja_env.get_template('downloader.html')
    html_content = template.render(downloaders=downloaders, existing_downloaders=existing_downloaders)
    return html(html_content)

@app.route('/login')
async def login(request):
    template = jinja_env.get_template('login.html')
    html_content = template.render()
    return html(html_content)

@app.route('/')
async def index(request):
    existing_sites = [s for s in sites if s['passkey'] != '']
    template = jinja_env.get_template('index.html')
    html_content = template.render(sites=sites, existing_sites=existing_sites)
    return html(html_content)

async def reseed():
    while True:
        seed()
        await asyncio.sleep(60)

@app.route('/submit', methods=['POST'])
async def submit(request):
    # 获取表单数据
    site_id = request.form.get('site') 
    site_name = request.form.get('siteName') 
    site_url = request.form.get('siteUrl')  
    passkey = request.form.get('passkey')  

    try:
        # 尝试将 site_id 转换为整数
        site_id = int(site_id) if site_id else None
    except ValueError:
        site_id = None

    if site_id is not None and passkey is not None and not (site_name or site_url):
        site_found = False
        for i, site in enumerate(sites):
            if site['id'] == site_id:
                sites[i]['passkey'] = passkey  # 更新 passkey
                site_found = True
                break

        if not site_found:
            return redirect('/')

        update_config_list(config_file_path, 'sites', sites)
        return redirect('/')

    api_url = f"{site_url}api/pieces-hash" if site_url else None

    new_site = {
        'id': site_id if site_id is not None else max((site['id'] for site in sites), default=-1) + 1,
        'siteName': site_name,
        'siteUrl': site_url,
        'apiUrl': api_url,
        'passkey': passkey
    }

    if site_id is not None:
        for i, site in enumerate(sites):
            if site['id'] == site_id:
                sites[i] = new_site  # 更新现有站点
                break
    else:
        sites.append(new_site)  # 添加新站点

    update_config_list(config_file_path, 'sites', sites)
    
    return redirect('/')

@app.route('/submit_downloader', methods=['POST'])
async def submit_downloader(request):
    downloader_id = request.form.get('id')
    
    if downloader_id:
        downloader_id = int(downloader_id)
    else:
        downloader_id = None 

    downloader_name = request.form.get('name')
    downloader_type = request.form.get('type')
    host = request.form.get('host')
    port = request.form.get('port')
    username = request.form.get('username')
    password = request.form.get('password')
    torrent_folder = request.form.get('torrent_folder')

    new_id = max([d['id'] for d in downloaders] + [-1]) + 1

    new_downloader = {
        'id': downloader_id if downloader_id is not None else new_id,
        'name': downloader_name,
        'type': downloader_type,
        'connection_info': {
            'host': host,
            'port': int(port),
            'username': username,
            'password': password
        },
        'torrent_folder': torrent_folder
    }

    downloader_found = False
    if downloader_id is not None:
        for i, downloader in enumerate(downloaders):
            if downloader['id'] == downloader_id:
                downloaders[i] = new_downloader 
                downloader_found = True
                break

    if not downloader_found:
        downloaders.append(new_downloader)

    update_config_list(config_file_path, 'downloaders', downloaders)

    return redirect('/downloader')

@app.route('/delete_downloader/<downloader_id>', methods=['POST'])
async def delete_downloader(request, downloader_id):
    global downloaders

    downloaders = [d for d in downloaders if d['id'] != int(downloader_id)]

    try:
        update_config_list(config_file_path, 'downloaders', downloaders)
    except Exception as e:
        print(f"Error writing to config file: {e}")

    return json({"message": "下载器已成功删除"})


@app.route('/delete_sites/<site_id>', methods=['POST'])
async def delete_site(request, site_id):
    global sites

    sites = [d for d in sites if d['id'] != int(site_id)]

    try:
        update_config_list(config_file_path, 'sites', sites)
    except Exception as e:
        print(f"Error writing to config file: {e}")

    return json({"message": "站点已成功删除"})

@app.middleware('request')
async def redirect_to_login(request):
    protected_routes = ['/', '/downloader', '/logs']
    if request.path in protected_routes and not request.cookies.getlist('user'):
        return redirect('/login')

@app.route('/login', methods=['POST'])
async def handle_login(request):
    username = request.form.get('username')
    password = request.form.get('password')
    
    if username == credentials['username'] and password == credentials['password']:
        response = redirect('/')
        response.cookies.add_cookie('user', 'username', httponly=True, max_age=3600, samesite='Lax', secure=False)
        return response
    else:
        return html("<h1>Login Failed</h1><a href='/login'>Try Again</a>")

app.add_task(reseed())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4532)
