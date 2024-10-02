import os
import hashlib
import json
import requests
import importlib
from log import writeLog
import bencodepy
import qbittorrentapi
import transmission_rpc
import deluge_client

logger = writeLog('my_logger', 'log/reseed.log')

MAX_RETRIES = 5

def reload_config():
    """Reloads the site and downloader configuration."""
    config_module = importlib.import_module('config.site_config')
    importlib.reload(config_module)
    return config_module.sites, config_module.downloaders

def connect_to_downloader(downloader_config, retry_count=0):
    """Connects to the specified downloader with retries."""
    logger.info(f"尝试连接到下载器: {downloader_config['name']}")

    try:
        client = None
        if downloader_config['type'] == 'qbittorrent':
            client = qbittorrentapi.Client(**downloader_config['connection_info'])
            client.auth_log_in()
        elif downloader_config['type'] == 'transmission':
            client = transmission_rpc.Client(**downloader_config['connection_info'])
        elif downloader_config['type'] == 'deluge':
            client = deluge_client.DelugeRPCClient(**downloader_config['connection_info'])
            client.connect()
        else:
            logger.error(f"不支持的下载器类型: {downloader_config['type']}")
            return None
        return client
    except Exception as e:
        logger.error(f"连接到下载器 {downloader_config['name']} 失败: {e}")

        if retry_count < MAX_RETRIES:
            logger.info(f"重试第 {retry_count + 1} 次...")
            return connect_to_downloader(downloader_config, retry_count + 1)
        else:
            logger.error(f"连接失败次数达到最大限制 {MAX_RETRIES} 次，跳过该下载器。")
            return None

def get_torrent_info(client, downloader_type, info_hash):
    """Retrieves torrent information from the specified downloader."""
    try:
        torrent_info = None
        if downloader_type == 'qbittorrent':
            torrent_info = client.torrents_info(torrent_hashes=info_hash)
        elif downloader_type == 'transmission':
            torrent_info = client.get_torrent(info_hash)
        elif downloader_type == 'deluge':
            torrent_info = client.core.get_torrent_status(info_hash, ['save_path', 'state'])
        
        if not torrent_info:
            return {'exists': False}

        # Build info_data based on downloader type
        if downloader_type == 'qbittorrent':
            return {
                'hash': torrent_info[0].hash,
                'save_path': torrent_info[0].save_path,
                'state': torrent_info[0].state,
                'exists': True
            }
        elif downloader_type == 'transmission':
            return {
                'hash': torrent_info.hashString,
                'save_path': torrent_info.download_dir,
                'state': torrent_info.status,
                'exists': True
            }
        elif downloader_type == 'deluge':
            return {
                'hash': info_hash,
                'save_path': torrent_info['save_path'],
                'state': torrent_info['state'],
                'exists': True
            }
    except Exception as e:
        logger.error(f"获取种子信息出错 ({info_hash}): {e}")
        return None

def get_local_torrent_hashes(torrent_folder):
    """Retrieves local torrent hashes from the specified folder."""
    local_hashes = set()
    for filename in os.listdir(torrent_folder):
        if filename.endswith('.torrent'):
            local_hashes.add(filename[:-8])  # Remove '.torrent' from the filename
    return local_hashes

def download_torrent(client, downloader_type, torrent_info, torrent_folder):
    """Downloads the specified torrent if it doesn't already exist locally."""
    file_path = os.path.join(torrent_folder, f"{torrent_info['hash']}.torrent")
    if not os.path.exists(file_path):
        if downloader_type == 'qbittorrent':
            torrent_data = client.torrents_export(torrent_info['hash'])
        elif downloader_type == 'transmission':
            torrent_data = client.get_torrent(torrent_info['id']).torrent_file()
        elif downloader_type == 'deluge':
            torrent_data = client.core.get_torrent_status(torrent_info['hash'], ['torrent_file'])['torrent_file']

        if torrent_data:
            with open(file_path, 'wb') as f:
                f.write(torrent_data)
            logger.info(f"下载种子: {torrent_info['name']}, 保存至 {file_path}")
            return file_path
        else:
            logger.error(f"未找到种子数据: {torrent_info['name']}")
    else:
        logger.info(f"种子已存在: {torrent_info['name']}")
    return None

def get_torrents_from_client(client, downloader_type, downloader_config):
    """Retrieves torrents from the downloader client."""
    torrents = []
    torrent_folder = downloader_config['torrent_folder']
    os.makedirs(torrent_folder, exist_ok=True)

    local_hashes = get_local_torrent_hashes(torrent_folder)

    try:
        if downloader_type == 'qbittorrent':
            torrents_info = client.torrents_info()
            torrents = [download_torrent(client, downloader_type, torrent, torrent_folder) for torrent in torrents_info if torrent['hash'] not in local_hashes]
        elif downloader_type == 'transmission':
            torrents_info = client.get_torrents()
            torrents = [download_torrent(client, downloader_type, torrent, torrent_folder) for torrent in torrents_info if torrent.hashString not in local_hashes]
        elif downloader_type == 'deluge':
            torrents_info = client.core.get_torrents_status({}, ['name', 'hash'])
            torrents = [download_torrent(client, downloader_type, {'hash': torrent_hash, 'name': torrent_info['name']}, torrent_folder) for torrent_hash, torrent_info in torrents_info.items() if torrent_hash not in local_hashes]

    except Exception as e:
        logger.error(f"获取种子时出错: {e}")
    
    return torrents

def process_local_torrents(torrents):
    """Processes local torrent files to extract information."""
    info_hash_topieces = {}
    torrent_name_topieces = {}

    for file_path in torrents:
        try:
            with open(file_path, 'rb') as f:
                torrent_data = f.read()
                torrent = bencodepy.decode(torrent_data)
                info = torrent[b'info']
                info_sha1 = hashlib.sha1(bencodepy.encode(info)).hexdigest()
                pieces_sha1 = hashlib.sha1(info[b'pieces']).hexdigest()
                info_hash_topieces[pieces_sha1] = info_sha1
                torrent_name_topieces[pieces_sha1] = os.path.basename(file_path)

        except Exception as e:
            logger.error(f"处理种子文件时出错 {file_path}: {e}")

    return info_hash_topieces, torrent_name_topieces

def add_torrent(client, downloader_type, url, save_path):
    """Adds a torrent to the specified downloader."""
    try:
        if downloader_type == 'qbittorrent':
            return client.torrents_add(urls=url, save_path=save_path) == "Ok."
        elif downloader_type == 'transmission':
            torrent = client.add_torrent(url, download_dir=save_path)
            return torrent is not None
        elif downloader_type == 'deluge':
            return client.core.add_torrent_url(url, {'download_location': save_path})
    except Exception as e:
        logger.error(f"添加种子失败 ({url}): {e}")
    return False

def seed():
    """Main seeding function."""
    logger.info('辅种脚本启动')
    sites, downloaders = reload_config()

    if not downloaders:
        logger.warning("没有检测到下载器配置，程序将退出。")
        return
    
    fz_array = []
    info_hash_topieces = {}
    torrent_name_topieces = {}
    added_hashes = set()  # 用于存储已添加的种子哈希值

    for downloader_config in downloaders:
        client = connect_to_downloader(downloader_config)
        if not client:
            logger.error(f"连接失败 {downloader_config['name']}")
            continue

        try:
            torrents = get_torrents_from_client(client, downloader_config['type'], downloader_config)
            info_hash_topieces, torrent_name_topieces = process_local_torrents(torrents)
        except Exception as e:
            logger.error(f"处理种子时出错 {downloader_config['name']}: {e}")

    logger.info("当前种子库：%d 个种子", len(info_hash_topieces))

    for site in filter(lambda x: x['passkey'], sites):
        pieces_hash_groups = [list(info_hash_topieces.keys())[i:i + 100] for i in range(0, len(info_hash_topieces), 100)]
        
        for group_list in pieces_hash_groups:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Reseed-Puppy"
            }
            data = {
                "passkey": site['passkey'],
                "pieces_hash": group_list
            }
            url = site['apiUrl']
            try:
                response = requests.post(url, headers=headers, json=data, timeout=10)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.warning('站点请求失败：%s - %s', site['siteName'], e)
                continue

            response_json = response.json()
            if isinstance(response_json.get('data'), dict):
                for value in response_json['data']:
                    torrent_info = client.torrents_info(torrent_hashes=info_hash_topieces[value])

                    if torrent_info:
                        save_path = torrent_info[0]['save_path']
                        state = torrent_info[0]['state']
                        hash = torrent_info[0]['hash']
                        
                        if hash in added_hashes:
                            logger.info("%s 已在下载器中，跳过添加", torrent_name_topieces[value])
                            continue

                        if state in ["downloading", "seeding"]:
                            logger.info("%s 处于 %s 状态，跳过添加", torrent_name_topieces[value], state)
                            added_hashes.add(hash)
                            continue

                        # 添加种子
                        if add_torrent(client, downloader_config['type'], 
                                       f"{site['siteUrl']}download.php?id={response_json['data'][value]}&passkey={site['passkey']}", 
                                       save_path):
                            logger.info("种子pieces_info:%s", value)
                            logger.info("%s ：正在添加到下载器中", torrent_name_topieces[value])
                            fz_array.append(f"{site['siteUrl']}download.php?id={response_json['data'][value]}&passkey={site['passkey']}")
                            added_hashes.add(hash)

    logger.info("可辅种数：%d 个种子", len(fz_array))
    logger.info("辅种 URL 列表: %s", fz_array)
    logger.info("辅种结束")