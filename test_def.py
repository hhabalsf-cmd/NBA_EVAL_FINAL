import concurrent.futures
from dotenv import load_dotenv; load_dotenv(".env", override=True)
from bdl_client import get_bdl_client

bdl = get_bdl_client()

def fetch_advanced():
    return bdl.get_team_season_averages("general", "advanced", 2025)

def fetch_base():
    return bdl.get_team_season_averages("general", "base", 2025)

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    f_advanced = pool.submit(fetch_advanced)
    f_base = pool.submit(fetch_base)
    print("Advanced Exception:", f_advanced.exception())
    print("Base Exception:", f_base.exception())
