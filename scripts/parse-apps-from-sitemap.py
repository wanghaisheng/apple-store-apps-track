import requests
import gzip
import xml.etree.ElementTree as ET
from io import BytesIO
import logging
from datetime import datetime
from dotenv import load_dotenv
import hashlib
import os
import concurrent.futures

from save_app_profile import *

load_dotenv()

# Constants for D1 Database
D1_DATABASE_ID = os.getenv('D1_APP_DATABASE_ID')
CLOUDFLARE_ACCOUNT_ID = os.getenv('CLOUDFLARE_ACCOUNT_ID')
CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')

CLOUDFLARE_BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/d1/database/{D1_DATABASE_ID}"

# Set up logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app_profiles.log"),
        logging.StreamHandler()
    ]
)

def calculate_row_hash(url, lastmodify):
    """
    Generate a row hash using the URL and lastmodify timestamp.
    Using lastmodify ensures that the hash only changes if the content changes.
    """
    hash_input = f"{url}{lastmodify}"
    return hashlib.sha256(hash_input.encode()).hexdigest()

def extract_links_from_xml(xml_root, tag="loc"):
    """
    Extract links or other elements from the given XML root using the specified tag.
    """
    namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}  # Define the correct namespace
    return [element.text for element in xml_root.findall(f".//ns:{tag}", namespaces)]


def fetch_and_parse_sitemap(url):
    """
    Fetch the Sitemap XML file and parse it to get all <loc> links.
    """
    try:
        logging.debug(f"Fetching sitemap from URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        logging.info(f"Successfully fetched sitemap from {url}")
        sitemap_xml = response.text

        # Parse XML to extract all <loc> links using extract_links_from_xml
        tree = ET.ElementTree(ET.fromstring(sitemap_xml))
        root = tree.getroot()
        loc_tags = extract_links_from_xml(root, tag="loc")
        
        logging.debug(f"Extracted {len(loc_tags)} <loc> links from sitemap.")
        return loc_tags
    except requests.RequestException as e:
        logging.error(f"Failed to fetch sitemap: {e} - URL: {url}")
        return []
    except ET.ParseError as e:
        logging.error(f"XML parsing error for sitemap at URL {url}: {e}")
        return []

def fetch_and_parse_gzip_stream(url, process_function=None, batch_size=100, max_workers=4):
    """
    流式解析GZipped XML文件，逐个处理<url>节点，支持多线程/多进程并行处理和分批存储。
    """
    try:
        logging.debug(f"Fetching GZipped sitemap from URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        with gzip.GzipFile(fileobj=BytesIO(response.content)) as f:
            context = ET.iterparse(f, events=("end",))
            batch = []
            results = []
            # 线程池/进程池
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for event, elem in context:
                    if elem.tag.endswith('url'):
                        loc = elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                        lastmod = elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod')
                        if loc is not None and lastmod is not None:
                            batch.append({"url": loc.text, "lastmodify": lastmod.text})
                        if len(batch) >= batch_size:
                            if process_function:
                                # 异步提交批处理任务
                                futures.append(executor.submit(process_function, batch.copy()))
                            results.extend(batch)
                            batch.clear()
                    elem.clear()
                # 处理剩余未满batch的部分
                if batch:
                    if process_function:
                        futures.append(executor.submit(process_function, batch.copy()))
                    results.extend(batch)
                # 等待所有任务完成
                for future in futures:
                    future.result()
            logging.debug(f"[stream] Extracted {len(results)} app data entries from GZipped sitemap.")
            return results
    except requests.RequestException as e:
        logging.error(f"Failed to fetch or parse GZipped sitemap: {e} - URL: {url}")
        return []
    except ET.ParseError as e:
        logging.error(f"XML parsing error for GZipped sitemap at URL {url}: {e}")
        return []

def extract_app_id_from_url(url):
    """
    从app url中提取id（如id1273216352），未匹配返回None。
    """
    import re
    match = re.search(r'id(\d+)', url)
    return match.group(0) if match else None


def save_id_list_to_file(id_list, file_path):
    """
    保存id列表到文本文件，每行一个id。
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        for app_id in id_list:
            f.write(f"{app_id}\n")


def load_id_list_from_file(file_path):
    """
    从文本文件读取id列表。
    """
    if not os.path.exists(file_path):
        return set()
    with open(file_path, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())


def compare_new_ids(today_ids, history_ids):
    """
    对比今日id集合与历史id集合，返回新增id集合。
    """
    return today_ids - history_ids


def analyze_and_report_new_apps(today_id_file, history_id_file, report_file):
    """
    对比今日与历史id，输出新增app报告。
    """
    today_ids = load_id_list_from_file(today_id_file)
    history_ids = load_id_list_from_file(history_id_file)
    new_ids = compare_new_ids(today_ids, history_ids)
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"今日新增app数量: {len(new_ids)}\n")
        for app_id in sorted(new_ids):
            f.write(f"{app_id}\n")
    print(f"今日新增app数量: {len(new_ids)}，详情见: {report_file}")


def process_sitemaps_and_save_profiles():
    """
    Process the sitemaps and save app profiles.
    """
    sitemap_url = "https://apps.apple.com/sitemaps_apps_index_app_1.xml"
    loc_urls = fetch_and_parse_sitemap(sitemap_url)
    print('gz count',len(loc_urls))
    for loc_url in loc_urls[:1]:
        print(f'processing sitemap:{loc_url}')
        app_data_list = fetch_and_parse_gzip_stream(loc_url, process_function=lambda batch: batch_process_in_chunks(batch, process_function=batch_process_initial_app_profiles), batch_size=100, max_workers=4)
        print('app_data_list count',len(app_data_list))
        print(app_data_list[:2])
        batch_process_in_chunks(app_data_list[:2], process_function=batch_process_initial_app_profiles)
        # 新增：提取id并保存
        today = datetime.now().strftime('%Y-%m-%d')
        id_list = [extract_app_id_from_url(app['url']) for app in app_data_list if extract_app_id_from_url(app['url'])]
        id_file = f"app_ids_{today}.txt"
        save_id_list_to_file(id_list, id_file)
        # 新增：对比历史id并输出今日新增app报告
        history_id_file = "app_ids_history.txt"
        report_file = f"new_apps_{today}.txt"
        # // analyze_and_report_new_apps(id_file, history_id_file, report_file)
        # 可选：更新历史id文件（追加或合并）
        all_ids = load_id_list_from_file(history_id_file).union(set(id_list))
        save_id_list_to_file(sorted(all_ids), history_id_file)

# Start the process
process_sitemaps_and_save_profiles()