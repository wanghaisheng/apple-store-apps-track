import os
import re
from datetime import datetime, timedelta

def get_id_files(result_dir, prefix="app_ids_", suffix=".txt"):
    files = []
    for fname in os.listdir(result_dir):
        if fname.startswith(prefix) and fname.endswith(suffix):
            files.append(fname)
    return sorted(files)

def extract_date_from_filename(filename, prefix="app_ids_", suffix=".txt"):
    date_str = filename[len(prefix):-len(suffix)]
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None

def load_ids_from_file(filepath):
    if not os.path.exists(filepath):
        return set()
    with open(filepath, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def analyze_period_ids(result_dir, period_days, today=None):
    if today is None:
        today = datetime.now()
    files = get_id_files(result_dir)
    period_start = today - timedelta(days=period_days)
    period_files = [f for f in files if extract_date_from_filename(f) and extract_date_from_filename(f) > period_start]
    all_ids = set()
    for fname in period_files:
        ids = load_ids_from_file(os.path.join(result_dir, fname))
        all_ids.update(ids)
    return all_ids, period_files

def generate_report(result_dir, period, period_days, report_prefix="report_"):
    today = datetime.now()
    ids, files = analyze_period_ids(result_dir, period_days, today)
    report_file = os.path.join(result_dir, f"{report_prefix}{period}_{today.strftime('%Y-%m-%d')}.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"{period} 新增app数量: {len(ids)}\n")
        for app_id in sorted(ids):
            f.write(f"{app_id}\n")
        f.write(f"涉及文件: {', '.join(files)}\n")
    print(f"{period}报告已生成: {report_file}")

def main():
    result_dir = os.path.dirname(__file__)
    # 日报
    generate_report(result_dir, "daily", 1)
    # 周报
    generate_report(result_dir, "weekly", 7)
    # 月报
    generate_report(result_dir, "monthly", 30)

if __name__ == "__main__":
    main()