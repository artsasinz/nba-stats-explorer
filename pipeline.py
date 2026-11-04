import time
import duckdb
import pandas as pd
from nba_api.stats.static import teams as nba_teams
from nba_api.stats.endpoints import (playergamelogs,
                                     leaguedashplayershotlocations,
                                     leaguedashteamshotlocations)


# ======== CHANGE THE SEASON HERE! ========
SEASONS = ["2014-15", "2015-16", "2016-17",
           "2017-18", "2018-19", "2019-20",
           "2020-21", "2021-22", "2022-23", 
           "2023-24", "2024-25", "2025-26",
           "2026-27"]

# =====================================================================
#           TEAM AND PLAYER STATS columns to extract
# =====================================================================

ID_COLS = ['PLAYER_ID', 
           'PLAYER_NAME', 
           'TEAM_ABBREVIATION',
           'GAME_ID', 
           'GAME_DATE', 
           'WL', 
           'MIN']
STAT_COLS = ['FGM', 'FGA', 'FG3M', 'FG3A', 
             'FTM', 'FTA', 
             'PTS', 'OREB', 'DREB', 'REB', 'AST',
             'BLK', 'STL', 'PF', 'TOV', 
             'PLUS_MINUS']


# =====================================================================
#           SHOT LOCATION/ZONE columns to extract
# =====================================================================

API_ZONE_ORDER = ["Restricted Area", "In The Paint (Non-RA)", "Mid-Range",
                  "Left Corner 3", "Right Corner 3", "Above the Break 3",
                  "Backcourt", "Corner 3"]
ZONE_TO_SHOT_TYPE = {
    "Restricted Area":       "Rim",
    "In The Paint (Non-RA)": "Paint (non-rim)",
    "Mid-Range":             "Mid-range",
    "Left Corner 3":         "Corner 3",
    "Right Corner 3":        "Corner 3",
    "Above the Break 3":     "Above-the-break 3",
}
ABBR_BY_ID = {team["id"]: team["abbreviation"] for team in nba_teams.get_teams()}

# =====================================================================


def extract_logs(szn, retry=3):
    for attempt in range(retry):
        try:
            logs = playergamelogs.PlayerGameLogs(
                season_nullable=szn,
                season_type_nullable="Regular Season",
                timeout=60,
            )
            return logs.get_data_frames()[0]
        except Exception as error:
            if attempt == retry - 1:
                raise error
            print(f"Timeout on {szn} load failed, retrying: ({attempt+1})...")
            time.sleep(5)
            

def transform(df, szn):
    df = df[ID_COLS + STAT_COLS].copy()
    df["SEASON"] = szn
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df = df.sort_values(by=['PLAYER_ID', 'GAME_DATE']).reset_index(drop=True)
    return df


def select_season(szn=None):
    """ 'All' for all SEASONS.
        If no parameter entered, run only newest season """
        
    if szn == "All":
        season = SEASONS
    elif szn is None:
        season = [SEASONS[-1]]
    elif isinstance(szn, str):
        season = [szn]
        
    return season


def load(df, szn, db_path="nba_analytics.duckdb"):
    con = duckdb.connect(db_path)
    
    con.execute("CREATE TABLE IF NOT EXISTS player_games AS SELECT * FROM df LIMIT 0")
    
    # re-running a szn it replace when we change the season year
    con.execute("DELETE FROM player_games WHERE SEASON = ?", [szn])     # deleting existing data
    con.execute("INSERT INTO player_games BY NAME SELECT * FROM df")    # inserting updated one
    
    con.close()


def run_pipeline(seasons):
    for szn in seasons:
        try:
            df = extract_logs(szn)
            df = transform(df,szn)
            load(df, szn)
            print(f"Loaded {len(df)} rows from: {szn} season. [Data]")
            time.sleep(2)
        except Exception as error:
            print(f"{szn} data load failed: {error}")
        time.sleep(2)


# =====================================================================

# =====================================================================


def extract_zones(szn, type, retry=3):
    if type == "player":
        endpoint = leaguedashplayershotlocations.LeagueDashPlayerShotLocations
    else:
        endpoint = leaguedashteamshotlocations.LeagueDashTeamShotLocations
    
    for attempt in range(retry):
        try:
            result = endpoint(season=szn, 
                            season_type_all_star="Regular Season",
                            distance_range="By Zone", 
                            per_mode_detailed="Totals",
                            timeout=60,
                    )
            return result.get_data_frames()[0]
        except Exception as error:
            if attempt == retry - 1:
                raise error
            print(f"Timeout on {szn}, retrying ({attempt + 1}...")
            time.sleep(5)


def transform_zones(raw, szn, id_cols):
    names = [c[-1] if isinstance(c, tuple) else c for c in raw.columns]
    first_stat = names.index("FGM")
    if len(names) - first_stat != 3 * len(API_ZONE_ORDER):
        raise ValueError(f"Unexpected column layout, please check: {names}")

    ids = raw.iloc[:, :first_stat].copy()
    ids.columns = names[:first_stat]

    pieces = []
    for k, zone in enumerate(API_ZONE_ORDER):
        if zone not in ZONE_TO_SHOT_TYPE:
            continue
        piece = ids[id_cols].copy()
        piece["SEASON"] = szn
        piece["ZONE"] = zone
        piece["SHOT_TYPE"] = ZONE_TO_SHOT_TYPE[zone]
        piece["FGM"] = raw.iloc[:, first_stat + 3 * k].values
        piece["FGA"] = raw.iloc[:, first_stat + 3 * k + 1].values
        pieces.append(piece)
    return pd.concat(pieces, ignore_index=True)


def load_table(df, szn, table, db_path="nba_analytics.duckdb"):
    con = duckdb.connect(db_path)
    try:
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM df LIMIT 0")
        con.execute("BEGIN TRANSACTION")
        con.execute(f"DELETE FROM {table} WHERE SEASON = ?", [szn])
        con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM df")
        con.execute("COMMIT")
    finally:
        con.close()


def run_shot_zone_pipeline(seasons):
    for szn in seasons:
        try:
            players = transform_zones(extract_zones(szn, "player"), szn,
                                      ["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"])
            load_table(players, szn, "player_shot_zones")
            time.sleep(2)

            team_zones = transform_zones(extract_zones(szn, "team"), szn, ["TEAM_ID"])
            team_zones["TEAM_ABBREVIATION"] = team_zones["TEAM_ID"].map(ABBR_BY_ID)
            load_table(team_zones, szn, "team_shot_zones")
            print(f"Loaded {len(team_zones)} rows from: {szn} season. [Shot Zones]")
        except Exception as error:
            print(f"{szn} shot zones load failed: {error}")
        time.sleep(2) 
    

# =====================================================================


if __name__ == "__main__":
    """ Default: Run the only newest season only.
        Change the 'season = select_season(...) to change the excuted result """
    # no parameter = newest season only
    season = select_season()
    run_pipeline(seasons= season)
    run_shot_zone_pipeline(seasons= season)
    
    with duckdb.connect("nba_analytics.duckdb") as con:
        con.execute("VACUUM")