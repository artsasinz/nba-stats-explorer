"""
NBA Stats Explorer (Streamlit app)
====================================================================
How this file is organized:
    1. SETTINGS     page setup, team names, colors
    2. DATABASE     functions that ask DuckDB for data
    3. HELPERS      small tools (logo link, player headshot picture, etc.)
    4. CHARTS       functions that build ONE chart each
    5. PAGE PARTS   functions that draw ONE section of a page
    6. MAIN         the sidebar, and deciding which page to show
"""

import duckdb
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from nba_api.stats.static import teams as nba_teams


# =====================================================================
# 1. SETTINGS
# =====================================================================

# Database Path (we'll use .duckdb)
DB_PATH = "./nba_analytics.duckdb"

# This must be the first Streamlit command in the file.
st.set_page_config(page_title="NBA Stats Explorer", layout="wide")

# Make the page be flexible to vary sizes.
st.markdown(
    "<style>[data-testid='stMetricValue'] { font-size: clamp(1.3rem, 2vw, 2.2rem) !important; text-overflow: clip !important; }</style>",
    unsafe_allow_html=True,
)

# Team abbreviation -> full name
TEAM_NAMES = {
    "ATL": "Atlanta Hawks",
    "BOS": "Boston Celtics",
    "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls",
    "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors",
    "HOU": "Houston Rockets",
    "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers",
    "LAL": "Los Angeles Lakers",
    "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks",
    "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans",
    "NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers",
    "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers",
    "SAC": "Sacramento Kings",
    "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz",
    "WAS": "Washington Wizards",
}

# Colors (change them here and every chart updates)
GREEN = "#27D547"        # made shots
GRAY = "#A9A5A49D"       # missed shots
BLUE = "#75AAE3"         # steals
GOLD = "#EDBF53"         # blocks
RED = "#FF4B4B"          # the selected team
LINE_RED = "#E714147C"   # rolling-average line (attempts)
LINE_GREEN = "#27D54776" # rolling-average line (makes)

# Text for the four corners of the quadrant chart
EFFICIENCY_LABELS = {
    "top_right": "High Volume, High Efficiency",
    "top_left": "Low Volume, High Efficiency",
    "bottom_right": "High Volume, Low Efficiency",
    "bottom_left": "Low Volume, Low Efficiency",
}

# The radar chart axes: (column in the profile table, label on the chart, is a higher number better?)
TEAM_RADAR = [
    ("PPG",     "Points",        True),
    ("FG_PCT",  "FG%",           True),
    ("FG3_PCT", "3P%",           True),
    ("REB_PG",  "Rebounds",      True),
    ("STL_PG",  "Steals",        True),
    ("BLK_PG",  "Blocks",        True),
    ("TOV_PG",  "Ball security", False),   # fewer turnovers is better
    ("WIN_PCT", "Win %",         True),
]
PLAYER_RADAR = [
    ("PPG",     "Points",        True),
    ("FG_PCT",  "FG%",           True),
    ("FG3_PCT", "3P%",           True),
    ("FT_PCT",  "FT%",           True),
    ("REB_PG",  "Rebounds",      True),
    ("STL_PG",  "Steals",        True),
    ("BLK_PG",  "Blocks",        True),
    ("TOV_PG",  "Ball security", False),   # fewer turnovers is better
]

# Shot Types
SHOT_TYPES = ["Rim", "Paint (non-rim)", "Mid-range", "Corner 3", "Above-the-break 3"]
SHOT_COLORS = [GREEN, GOLD, "#B388FF", "#75AAE3", "#4A7FC1"]


# =====================================================================
# 2. DATABASE
# Every function below asks DuckDB one question and returns a table.
# =====================================================================

@st.cache_data
def query(sql, params=None):
    """Run one SQL query and return the result as a pandas table.
    @st.cache_data remembers the answer, so the same query is only run once."""
    connection = duckdb.connect(DB_PATH, read_only=True)
    try:
        return connection.execute(sql, params or []).df()
    finally:
        connection.close()


def get_season_list():
    table = query("""
        SELECT DISTINCT SEASON FROM player_games
        ORDER BY SEASON DESC
    """)
    return table["SEASON"].tolist()


def get_team_list():
    table = query("""
                  SELECT DISTINCT TEAM_ABBREVIATION 
                  FROM player_games
                  WHERE SEASON = ?
                  ORDER BY 1
                  """,
                  [selected_szn],
                  )
    return table["TEAM_ABBREVIATION"].tolist()


def get_player_list(team=None):
    if team is None:
        table = query("""
                      SELECT DISTINCT PLAYER_NAME FROM player_games
                      WHERE SEASON = ?
                      ORDER BY 1
                      """,
                      [selected_szn],
                      )
    else:
        table = query("""
                      SELECT DISTINCT PLAYER_NAME FROM player_games
                      WHERE SEASON = ? AND TEAM_ABBREVIATION = ? 
                      ORDER BY 1
                      """,
                      [selected_szn, team],
                      )
    return table["PLAYER_NAME"].tolist()


def get_player_id(player):
    result = query(
        """
        SELECT PLAYER_ID
        FROM player_games
        WHERE SEASON = ? AND PLAYER_NAME = ?
        LIMIT 1
        """,
        [selected_szn, player],
    )

    if result.empty:
        return None

    return int(result["PLAYER_ID"].iloc[0])


def get_player_games(player):
    games = query(
            """
            SELECT GAME_DATE,
                   TEAM_ABBREVIATION,
                   MAX(WL)      AS WL,
                   SUM(PTS)     AS PTS,
                   SUM(REB)     AS REB,
                   SUM(AST)     AS AST,
                   SUM(FGM)     AS FGM,
                   SUM(FGA)     AS FGA,
                   SUM(FTM)     AS FTM,
                   SUM(FTA)     AS FTA,
                   SUM(FG3M)    AS FG3M,
                   SUM(FG3A)    AS FG3A,
                   SUM(STL)     AS STL,
                   SUM(BLK)     AS BLK
            FROM player_games
            WHERE SEASON = ? AND PLAYER_NAME = ?
            GROUP BY GAME_ID, GAME_DATE, TEAM_ABBREVIATION
            ORDER BY GAME_DATE
            """,
            [selected_szn, player],
        )
    
    # Extra columns we need for the charts (easy to read in pandas)
    games["FGMissed"] = games["FGA"] - games["FGM"]
    games["FG3Missed"] = games["FG3A"] - games["FG3M"]
    games["STL_BLK"] = games["STL"] + games["BLK"]

    # 5-game rolling averages -> columns named ROLLING_5G_FGA, ROLLING_5G_FGM, ...
    return add_rolling_average(games, ["FGA", "FGM", "FG3A", "FG3M", "STL_BLK"])


def get_player_ts_by_szn(player):
    player_id = get_player_id(player)
    
    league = query(
             """
             SELECT SEASON,
                    SUM(PTS) * 100.0 / (2 * (SUM(FGA) + 0.44 * SUM(FTA))) AS LEAGUE_TS
             FROM player_games
             WHERE SEASON <= ?
             GROUP BY SEASON
             ORDER BY SEASON
             """,
             [selected_szn],
             ).tail(5)

    mine = query(
             """
             SELECT SEASON,
                    COUNT(DISTINCT GAME_ID) AS Games,
                    SUM(PTS) * 100.0 / NULLIF(2 * (SUM(FGA) + 0.44 * SUM(FTA)), 0) AS PLAYER_TS
             FROM player_games
             WHERE PLAYER_ID = ? AND SEASON <= ?
             GROUP BY SEASON
             """,
            [player_id, selected_szn],
            )
    return league.merge(mine, on="SEASON", how="left")
    

def get_team_games(team):
    """One row per game for one team (the players' numbers added together)."""
    games = query("""
                  SELECT GAME_DATE,
                    MAX(WL)      AS WL,
                    SUM(PTS)     AS PTS,
                    SUM(FGM)     AS FGM,
                    SUM(FGA)     AS FGA,
                    SUM(FG3M)    AS FG3M,
                    SUM(FTM)     AS FTM,
                    SUM(FTA)     AS FTA,
                    SUM(FG3A)    AS FG3A,
                    SUM(STL)     AS STL,
                    SUM(BLK)     AS BLK
                  FROM player_games
                  WHERE SEASON = ? AND TEAM_ABBREVIATION = ?
                  GROUP BY GAME_ID, GAME_DATE
                  ORDER BY GAME_DATE
                  """,
                  [selected_szn, team],
                 )

    # Extra columns we need for the charts (easy to read in pandas)
    games["FGMissed"] = games["FGA"] - games["FGM"]
    games["FG3Missed"] = games["FG3A"] - games["FG3M"]
    games["STL_BLK"] = games["STL"] + games["BLK"]

    # 5-game rolling averages -> columns named ROLLING_5G_FGA, ROLLING_5G_FGM, ...
    return add_rolling_average(games, ["FGA", "FGM", "FG3A", "FG3M", "STL_BLK"])


def get_team_three_point_shooters(team):
    return query(
        """
        SELECT PLAYER_NAME AS Player,
               ROUND(AVG(FG3M), 1)              AS "3PM per game",
               ROUND(AVG(FG3A), 1)              AS "3PA per game",
               ROUND(AVG(FG3A) - AVG(FG3M), 1)  AS Missed
        FROM player_games
        WHERE SEASON = ? AND TEAM_ABBREVIATION = ?
        GROUP BY PLAYER_NAME
        HAVING COUNT(*) >= 10
        ORDER BY AVG(FG3M) DESC
        LIMIT 5
        """,
        [selected_szn, team],
    )


def get_team_defenders(team):
    return query(
        """
        SELECT PLAYER_NAME AS Player,
               ROUND(AVG(STL), 1)       AS Steals,
               ROUND(AVG(BLK), 1)       AS Blocks,
               ROUND(AVG(STL + BLK), 1) AS "Steals + Blocks"
        FROM player_games
        WHERE SEASON = ? AND TEAM_ABBREVIATION = ?
        GROUP BY PLAYER_NAME
        HAVING COUNT(*) >= 10
        ORDER BY AVG(STL + BLK) DESC
        LIMIT 5
        """,
        [selected_szn, team],
    )


def get_league_efficiency():
    """One row per team: 3PA per game and eFG% (for the quadrant chart)."""
    return query(
        """
        SELECT TEAM_ABBREVIATION AS Team,
               ROUND(SUM(FG3A) * 1.0 / COUNT(DISTINCT GAME_ID), 1) AS FG3A_PG,
               ROUND((SUM(FGM) + 0.5 * SUM(FG3M)) * 100.0 / SUM(FGA), 1) AS EFG_PCT
        FROM player_games
        WHERE SEASON = ?
        GROUP BY TEAM_ABBREVIATION
        """,
        [selected_szn],
    )


def get_league_profile():
    profile = query(
        """
        SELECT TEAM_ABBREVIATION AS Team,
               SUM(PTS)  * 1.0 / COUNT(DISTINCT GAME_ID) AS PPG,
               SUM(FGA)  * 1.0 / COUNT(DISTINCT GAME_ID) AS FGA_PG,
               SUM(FGM)  * 1.0 / COUNT(DISTINCT GAME_ID) AS FGM_PG,
               SUM(FG3A) * 1.0 / COUNT(DISTINCT GAME_ID) AS FG3A_PG,
               SUM(FG3M) * 1.0 / COUNT(DISTINCT GAME_ID) AS FG3M_PG,
               SUM(REB)  * 1.0 / COUNT(DISTINCT GAME_ID) AS REB_PG,
               SUM(AST)  * 1.0 / COUNT(DISTINCT GAME_ID) AS AST_PG,
               SUM(STL)  * 1.0 / COUNT(DISTINCT GAME_ID) AS STL_PG,
               SUM(BLK)  * 1.0 / COUNT(DISTINCT GAME_ID) AS BLK_PG,
               SUM(TOV)  * 1.0 / COUNT(DISTINCT GAME_ID) AS TOV_PG,
               SUM(FGM)  * 100.0 / SUM(FGA)  AS FG_PCT,
               SUM(FG3M) * 100.0 / SUM(FG3A) AS FG3_PCT,
               SUM(FG3A) * 100.0 / SUM(FGA)  AS FG3A_RATE,
               COUNT(DISTINCT CASE WHEN WL = 'W' THEN GAME_ID END) AS WINS,
               COUNT(DISTINCT CASE WHEN WL = 'L' THEN GAME_ID END) AS LOSSES,
               COUNT(DISTINCT CASE WHEN WL = 'W' THEN GAME_ID END) * 100.0
                   / COUNT(DISTINCT GAME_ID) AS WIN_PCT
        FROM player_games
        WHERE SEASON = ? 
        GROUP BY TEAM_ABBREVIATION
        """,
        [selected_szn],
    )

    opponent_points = query(
        """
        WITH team_game AS (
            SELECT GAME_ID, TEAM_ABBREVIATION AS Team, SUM(PTS) AS PTS
            FROM player_games
            WHERE SEASON = ?
            GROUP BY GAME_ID, TEAM_ABBREVIATION
        )
        SELECT mine.Team, AVG(other.PTS) AS OPP_PPG
        FROM team_game AS mine
        JOIN team_game AS other
          ON other.GAME_ID = mine.GAME_ID AND other.Team <> mine.Team
        GROUP BY mine.Team
        """,
        [selected_szn],
    )

    return profile.merge(opponent_points, on="Team")


def get_league_summary(season):
    """League-wide numbers for ONE season. 
    Per team per game = total / (games x 2),
    because every game has two teams."""
    return query(
        """
        SELECT COUNT(DISTINCT TEAM_ABBREVIATION) AS Teams,
               COUNT(DISTINCT GAME_ID) AS Games,
               SUM(PTS)  * 1.0 / (COUNT(DISTINCT GAME_ID) * 2) AS PPG,
               SUM(FG3A) * 1.0 / (COUNT(DISTINCT GAME_ID) * 2) AS FG3A_PG,
               SUM(FG3M) * 100.0 / SUM(FG3A) AS FG3_PCT,
               (SUM(FGM) + 0.5 * SUM(FG3M)) * 100.0 / SUM(FGA) AS EFG_PCT,
               SUM(PTS) * 100.0 / (2 * (SUM(FGA) + 0.44 * SUM(FTA))) AS TS_PCT
        FROM player_games
        WHERE SEASON = ?
        """,
        [season],
    )


def get_player_profile():
    return query(
        """
        SELECT
            PLAYER_ID,
            PLAYER_NAME AS Player,
            MODE(TEAM_ABBREVIATION) AS Team,
            COUNT(DISTINCT GAME_ID) AS Games,

            SUM(PTS) * 1.0 / COUNT(DISTINCT GAME_ID) AS PPG,
            
            SUM(FGM) * 1.0 / COUNT(DISTINCT GAME_ID) AS FGM_PG,
            SUM(FGA) * 1.0 / COUNT(DISTINCT GAME_ID) AS FGA_PG,
            CASE WHEN SUM(FGA) >= 30 THEN SUM(FGM) * 100.0 / SUM(FGA) END AS FG_PCT,
            
            SUM(FG3M) * 1.0 / COUNT(DISTINCT GAME_ID) AS FG3M_PG,
            SUM(FG3A) * 1.0 / COUNT(DISTINCT GAME_ID) AS FG3A_PG,
            CASE WHEN SUM(FG3A) >= 30 THEN SUM(FG3M) * 100.0 / SUM(FG3A) END AS FG3_PCT,
            
            SUM(FTM) * 1.0 / COUNT(DISTINCT GAME_ID) AS FTM_PG,
            SUM(FTA) * 1.0 / COUNT(DISTINCT GAME_ID) AS FTA_PG,
            CASE WHEN SUM(FTA) >= 15 THEN SUM(FTM) * 100.0 / SUM(FTA) END AS FT_PCT,
            
            SUM(REB) * 1.0 / COUNT(DISTINCT GAME_ID) AS REB_PG,
            SUM(AST) * 1.0 / COUNT(DISTINCT GAME_ID) AS AST_PG,
            SUM(STL) * 1.0 / COUNT(DISTINCT GAME_ID) AS STL_PG,
            SUM(BLK) * 1.0 / COUNT(DISTINCT GAME_ID) AS BLK_PG,
            SUM(STL + BLK) * 1.0 / COUNT(DISTINCT GAME_ID) AS STOCKS_PG,
            SUM(FG3A) * 100.0 / SUM(FGA)             AS FG3A_RATE,

        FROM player_games
        WHERE SEASON = ?
        GROUP BY PLAYER_ID, PLAYER_NAME
        HAVING COUNT(DISTINCT GAME_ID) >= 8
        """,
        [selected_szn],
    )


def get_league_shot_types():
    return query("""
                SELECT SHOT_TYPE, SUM(FGA) AS FGA
                FROM team_shot_zones
                WHERE SEASON = ?
                GROUP BY SHOT_TYPE
                """,
                [selected_szn],
                )
    
    
def get_all_team_shot_types():
    return query("""
                SELECT TEAM_ABBREVIATION AS Team, SHOT_TYPE, SUM(FGA) AS FGA
                FROM team_shot_zones
                WHERE SEASON = ?
                GROUP BY TEAM_ABBREVIATION, SHOT_TYPE
                """,
                [selected_szn],
                )


def get_team_shot_types():
    return query("""
                SELECT SHOT_TYPE, SUM(FGA) AS FGA
                FROM team_shot_zones
                WHERE SEASON = ? AND TEAM_ABBREVIATION = ?
                GROUP BY SHOT_TYPE
                """,
                [selected_szn, team],
                )


def get_player_shot_types(player):
    return query("""
                 SELECT SHOT_TYPE, SUM(FGA) AS FGA
                 FROM player_shot_zones
                 WHERE SEASON = ? AND PLAYER_ID = ?
                 GROUP BY SHOT_TYPE
                 """,
                 [selected_szn, get_player_id(player)],
                )
    

# =====================================================================
# 3. HELPERS
# =====================================================================

def is_compact_layout():
    """True on phones, or when the link ends with ?compact=1 in pc testing."""
    if st.query_params.get("compact") == "1":
        return True
    try:
        agent = st.context.headers.get("User-Agent", "")
    except Exception:
        return False
    return any(word in agent for word in ("Mobi", "iPhone", "Android"))


def as_list(value):
    """None -> [],  "abc" -> ["abc"],  ["a", "b"] -> ["a", "b"]"""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def add_rolling_average(table, columns, window=5):
    """For each column, add a 5-game rolling average column named ROLLING_5G_<column>."""
    for column in columns:
        average = table[column].astype(float).rolling(window, min_periods=1).mean()
        table["ROLLING_5G_" + column] = average.round(2)
    return table


def team_logo_url(team):
    team_id = nba_teams.find_team_by_abbreviation(team)["id"]
    try:
        variant = "D" if st.context.theme.type == "dark" else "L"
    except Exception:
        variant = "D"
    return f"https://cdn.nba.com/logos/nba/{team_id}/global/{variant}/logo.svg"


def player_headshot_url(player):
    player_id = get_player_id(player)
    if player_id is None:
        return None
    return f"https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"


def nba_logo_url():
    return f"https://cdn.nba.com/logos/leagues/logo-nba.svg"


def team_rank(profile, column, team, higher_is_better=True):
    """Rank the team's stats compare with others, taken from the profile table."""
    
    ranks = profile[column].rank(ascending=not higher_is_better, method="min")
    return int(ranks[profile["Team"] == team].iloc[0])


def player_rank(profile, column, player, higher_is_better=True):
    """Rank the player's stats compare with others, taken from the profile table."""
    
    ranked = profile.dropna(subset=[column]).copy()
    ranked["rank"] = ranked[column].rank(ascending=not higher_is_better, method="min")
    row = ranked[ranked["Player"] == player]
    if row.empty:
        return None, len(ranked)
    return int(row["rank"].iloc[0]), len(ranked)


def profile_value(profile, team, column):
    """The value of one stat for one team, taken from the profile table."""
    
    return profile.loc[profile["Team"] == team, column].iloc[0]


def team_metric_rank(box, label, value, rank_column, profile, team, higher_is_better=True):
    """A Streamlit metric card with 'Rank X of 30' written under it."""
    
    box.metric(label, value)
    rank = team_rank(profile, rank_column, team, higher_is_better)
    box.caption(f"Rank {rank} of {len(profile)}")
    
    
def player_metric_rank(box, label, value, rank_column, profile, player, higher_is_better=True):
    """A Streamlit metric card with 'Rank X of N' written under it."""
    
    box.metric(label, value)
    rank, total = player_rank(profile, rank_column, player, higher_is_better)
    
    if rank is not None:
        box.caption(f"Rank {rank} of {total}")
    elif player not in profile["Player"].values:
        box.caption(f"Rank unavailable (>=8 game played)")
    else:
        box.caption(f"Not enough attempts")


def show_chart(fig, shrink=True):
    """Draw a plotly chart at the full width of its column."""
    
    config = {}
    if COMPACT:
        fig.update_xaxes(fixedrange=True)
        fig.update_yaxes(fixedrange=True)
        fig.update_layout(font=dict(size=11), legend=dict(font=dict(size=10)))
        if shrink:
            fig.update_layout(height=min(fig.layout.height or 450, 380))
        config = {"displayModeBar": False} 
    st.plotly_chart(fig, width= 'stretch', config=config)


def shot_shares(table):
    """Turns a table (SHOT_TYPE, FGA) into {shot type: % of all shots}."""
    
    total = table["FGA"].sum()
    shares = {shot_type: 0.0 for shot_type in SHOT_TYPES}
    for _, row in table.iterrows():
        shares[row["SHOT_TYPE"]] = row["FGA"] / total * 100 if total else 0.0
    return shares


def get_previous_season():
    """The season before the selected one, or None for the oldest season."""
    
    seasons = get_season_list()
    position = seasons.index(selected_szn)
    return seasons[position + 1] if position + 1 < len(seasons) else None


# =====================================================================
# 4. CHARTS
# Each function receives data and returns a plotly figure.
# =====================================================================

def rolling_chart(df, bar_col, line_col, y_title, height=500):
    """Bars for each game + a line for the 5-game average."""
    
    fig = go.Figure()
    fig.add_bar(x=df["GAME_DATE"], y=df[bar_col], name="Per game", opacity=0.5)
    fig.add_scatter(x=df["GAME_DATE"], y=df[line_col], mode="lines",
                    name="5-game average", line=dict(width=3))
    fig.update_layout(yaxis_title=y_title, height=height,
                      legend=dict(orientation="h", y=1.1))
    return fig


def stack_chart(df, x_col, stack_cols, names=None, colors=None,
                line_col=None, line_name=None, line_colors=None,
                y_title=None, barmode="stack", height=550):
    """
    Stacked bars (one segment per column) with optional lines on top.

    x_col        column for the x axis, e.g. "GAME_DATE"
    stack_cols   columns to stack, bottom to top, e.g. ["FGM", "FGMissed"]
    names        legend names for the bars (same order as stack_cols)
    colors       colors for the bars
    line_col     columns drawn as lines, e.g. ["ROLLING_5G_FGA"]
    line_name    legend names for the lines (same order as line_col)
    line_colors  colors for the lines
    """
    
    stack_cols = as_list(stack_cols)
    line_cols = as_list(line_col)
    names = as_list(names) or stack_cols
    line_names = as_list(line_name) or line_cols
    colors = colors or [GREEN, GRAY, BLUE, GOLD]
    line_colors = line_colors or [LINE_RED, LINE_GREEN, "#B388FF"]

    # Rename the columns to the legend names, so plotly uses them as the legend text
    data = df[[x_col] + stack_cols].rename(columns=dict(zip(stack_cols, names)))

    fig = px.bar(data, x=x_col, y=names, color_discrete_sequence=colors,
                 labels={"value": y_title or "", "variable": "", x_col: ""})
    fig.update_traces(opacity=0.75)   # do this BEFORE adding lines, so lines stay solid

    for i, (column, label) in enumerate(zip(line_cols, line_names)):
        fig.add_scatter(x=df[x_col], y=df[column], mode="lines", name=label,
                        line=dict(width=3, color=line_colors[i % len(line_colors)]))

    fig.update_layout(barmode=barmode, height=height, hovermode="x unified",
                      legend=dict(orientation="h", y=1.1))
    return fig


def ts_chart(df, name, height=450):
    fig = go.Figure()

    fig.add_scatter(x=df["SEASON"], y=df["LEAGUE_TS"], mode="lines",
                    name="League average",
                    line=dict(width=2, color="#9AA0A6", dash="dash"),
                    hovertemplate="League: %{y:.1f}%<extra></extra>")

    fig.add_scatter(x=df["SEASON"], y=df["PLAYER_TS"], mode="lines+markers",
                    name=name, line=dict(width=2.5, color=RED), marker=dict(size=10),
                    customdata=df["Games"],
                    hovertemplate="%{fullData.name}: %{y:.1f}% (%{customdata} games)<extra></extra>")

    fig.update_xaxes(type="category")       # make the season year as 'text' not 'date'
    fig.update_layout(height=height, yaxis_title="True shooting %",
                      hovermode="x unified", legend=dict(orientation="h", y=1.1))
    return fig


def quadrant_chart(df, x_col, y_col, label_col, highlight=None,
                          x_title=None, y_title=None, quadrant_labels=None,
                          split="mean", invert_x=False, invert_y=False,
                          show_labels=True, use_logos=True, height=500):
    """
    Scatter plot split into 4 quadrants by two dashed lines.

    label_col        column with the names (shown on the dots and on hover)
    highlight        name (or list of names) to show in red; the others fade
    quadrant_labels  dict with keys top_right, top_left, bottom_right, bottom_left
    split            "mean" or "median": where the dashed lines go
    invert_x/y       True if a LOWER number is better on that axis
    show_labels      False when there are too many dots (e.g. all players)

    - When highlight is empty (League view) and use_logos=True: all points are team logos.
    - When highlight is set (Team view) and use_logos=True: selected team is a logo, others are faded grey dots.
    """
    
    highlight = as_list(highlight)
    x_title = x_title or x_col
    y_title = y_title or y_col

    if split == "median":
        x_line, y_line = df[x_col].median(), df[y_col].median()
    else:
        x_line, y_line = df[x_col].mean(), df[y_col].mean()

    is_highlighted = df[label_col].isin(highlight)
    others = df[~is_highlighted]
    picked = df[is_highlighted]

    fade = len(highlight) > 0
    # True in League view (no team highlighted), 
    # False in Team view (one team highlighted)
    all_logos = use_logos and not fade

    hover_text = ("%{hovertext}<br>" + x_title + ": %{x}<br>"
                  + y_title + ": %{y}<extra></extra>")

    fig = go.Figure()

    # "Others" trace:
    #   - League View (all_logos=True): invisible markers so hovering on logos works
    #   - Team View (all_logos=False, fade=True): faded labels and grey dots
    fig.add_scatter(
        x=others[x_col], y=others[y_col],
        mode="markers" if all_logos else ("markers+text" if show_labels else "markers"),
        text=None if all_logos else (others[label_col] if show_labels else None),
        textposition="top center",
        textfont=dict(color="rgba(250,250,250,0.35)" if fade else "rgba(250,250,250,0.95)"),
        hovertext=others[label_col], hovertemplate=hover_text,
        marker=dict(
            size=28 if all_logos else 10,
            color="#9AA0A6",
            opacity=0 if all_logos else (0.25 if fade else 0.95),
        ),
        showlegend=not all_logos,
        name="Others",
    )

    # 'Selected Team' in Team view
    if not picked.empty:
        fig.add_scatter(
            x=picked[x_col], y=picked[y_col],
            mode="markers" if use_logos else "markers+text",
            text=None if use_logos else picked[label_col],
            textposition="top center",
            hovertext=picked[label_col], hovertemplate=hover_text,
            marker=dict(
                size=35 if use_logos else 20,
                color=RED,
                opacity=0 if use_logos else 0.95,
            ),
            name=", ".join(highlight),
        )

    # Draw Logo (League view: all 30 teams, Team view: 'Selected Team')
    if use_logos:
        x_span = (df[x_col].max() - df[x_col].min()) or 1.0
        y_span = (df[y_col].max() - df[y_col].min()) or 1.0

        x_range = [df[x_col].min() - x_span * 0.08, df[x_col].max() + x_span * 0.08]
        y_range = [df[y_col].min() - y_span * 0.08, df[y_col].max() + y_span * 0.08]
        
        fig.update_xaxes(range=x_range[::-1] if invert_x else x_range)
        fig.update_yaxes(range=y_range[::-1] if invert_y else y_range)

        logo_rows = picked if fade else df
        scale = 0.11 if fade else 0.075

        for _, row in logo_rows.iterrows():
            fig.add_layout_image(
                dict(
                    source=team_logo_url(row[label_col]),
                    xref="x",
                    yref="y",
                    x=row[x_col],
                    y=row[y_col],
                    sizex=x_span * scale,
                    sizey=y_span * scale,
                    xanchor="center",
                    yanchor="middle",
                    opacity=1.0,
                    layer="above",
                )
            )

    # Dividing Lines
    fig.add_vline(x=x_line, line_dash="dash", line_color=RED, opacity=0.35)
    fig.add_hline(y=y_line, line_dash="dash", line_color=RED, opacity=0.35)

    corners = {
        "top_right":    (0.99, 0.99, "right", "top"),
        "top_left":     (0.01, 0.99, "left",  "top"),
        "bottom_right": (0.99, 0.01, "right", "bottom"),
        "bottom_left":  (0.01, 0.01, "left",  "bottom"),
    }
    for key, text in (quadrant_labels or {}).items():
        x, y, x_anchor, y_anchor = corners[key]
        fig.add_annotation(xref="paper", yref="paper", 
                           x=x, y=y, text=text,
                           showarrow=False, 
                           xanchor=x_anchor, yanchor=y_anchor,
                           opacity=0.6)

    if invert_x:
        fig.update_xaxes(autorange="reversed")
    if invert_y:
        fig.update_yaxes(autorange="reversed")

    fig.update_layout(height=height, 
                      xaxis_title=x_title, 
                      yaxis_title=y_title,
                      legend=dict(orientation="h", y=1.1))
    return fig


def radar_chart(df, metrics, label_col, team, height=450):
    is_selected = df[label_col] == team
    n_teams = len(df)

    labels, scores, values, ranks = [], [], [], []
    for column, label, higher_is_better in metrics:
        score = df[column].rank(pct=True, ascending=higher_is_better) * 100     # league score
        rank = df[column].rank(ascending=not higher_is_better, method="min")

        labels.append(label)
        scores.append(score[is_selected].iloc[0])
        values.append(df.loc[is_selected, column].iloc[0])
        ranks.append(int(rank[is_selected].iloc[0]))

    labels = labels + labels[:1]
    scores = scores + scores[:1]
    details = list(zip(values + values[:1], ranks + ranks[:1]))

    fig = go.Figure()
    fig.add_scatterpolar(r=[50] * len(labels), theta=labels, mode="lines",
                         name="League median", hoverinfo="skip",
                         line=dict(color="#9AA0A6", dash="dash"))
    fig.add_scatterpolar(r=scores, theta=labels, fill="toself", name=team,
                         line=dict(color="rgba(255,75,75,0.9)"),
                         fillcolor="rgba(255,75,75,0.3)",
                         customdata=details,
                         hovertemplate="%{theta}<br>Value: %{customdata[0]:.1f}"
                                       "<br>Rank: %{customdata[1]} of " + str(n_teams)
                                       + "<extra></extra>")
    fig.update_layout(
        height=height,
        margin=dict(l=70, r=70, t=30, b=50),    # room so the labels are not cut off
        polar=dict(bgcolor="rgba(0,0,0,0)",
                   radialaxis=dict(range=[0, 100], tickvals=[25, 50, 75, 100],
                                   showticklabels=False)),
        legend=dict(orientation="h", y=-0.1),
    )
    return fig


def player_bar_chart(df, x_cols, colors=None, total_col=None, total_label="",
                     height=350):
    """
    Horizontal stacked bars, one bar per player.

    x_cols       columns to stack, e.g. ["3PM per game", "Missed"]
    total_col    optional column written as text at the end of each bar
    total_label  text after that number, e.g. "3PA"
    """
    
    colors = colors or [GREEN, GRAY]

    fig = go.Figure()
    for i, column in enumerate(x_cols):
        fig.add_bar(y=df["Player"], x=df[column], name=column, orientation="h",
                    marker_color=colors[i % len(colors)])

    if total_col:
        fig.add_scatter(x=df[total_col], y=df["Player"], mode="text",
                        text=[f"{value:.1f} {total_label}" for value in df[total_col]],
                        textposition="middle right", showlegend=False, hoverinfo="skip")
        fig.update_xaxes(range=[0, df[total_col].max() * 1.45])     # room for the text

    fig.update_layout(barmode="stack", height=height,
                      yaxis=dict(autorange="reversed"),         # best player on the top
                      legend=dict(orientation="h", y=1.2),
                      margin=dict(t=10, b=10, l=10, r=10))
    return fig


def shot_type_chart(rows, use_logos, row_height=60):
    """100% horizontal stacked bar. rows = {row label: {shot type: percent}}."""
    labels = list(rows.keys())
    n = len(labels)
    def row_logo(label): 
        if label in TEAM_NAMES:
            return team_logo_url(label)
        if label == "League":
            return nba_logo_url()
        return None

    has_logos = [use_logos and row_logo(label) is not None for label in labels]
    
    fig = go.Figure()
    for shot_type, color in zip(SHOT_TYPES, SHOT_COLORS):
        values = [rows[label][shot_type] for label in labels]
        fig.add_bar(y=labels, x=values, 
                    name=shot_type, 
                    orientation="h",
                    marker_color=color,
                    text=[f"{v:.0f}%" if v >= 4 else "" for v in values],
                    textposition="inside", 
                    insidetextanchor="middle",
                    hovertemplate="%{y}<br>" + shot_type + ": %{x:.1f}%<extra></extra>"
                    )
        
    fig.update_layout(barmode="stack", 
                      height=90 + row_height * len(labels),
                      bargap=0.15,
                      xaxis=dict(range=[0, 100], ticksuffix="%"),
                      yaxis=dict(type="category", range=[n - 0.5, -0.5],
                                 showticklabels= not any(has_logos)),
                      legend=dict(orientation="h",
                                  xanchor="left", x=0,
                                  yanchor="bottom", y=1.0),
                      margin=dict(t=50, b=30, l=60, r=10),
                      )   
    
    for i, label in enumerate(labels):
        if has_logos[i]:
            fig.add_layout_image(dict(
                source=row_logo(label),
                xref="paper", yref="paper",
                x=-0.005, xanchor="right",
                y=1 - (i + 0.5) / n, yanchor="middle",
                sizex=0.035, sizey=0.85 / n,
                layer="above",
            ))
            
    return fig


# =====================================================================
# 5. PAGE PARTS
# Each function draws one part of a page.
# =====================================================================

# ---------- League page ----------

def show_league_header():
    summary = get_league_summary(selected_szn).iloc[0]
    previous_season = get_previous_season()
    previous = get_league_summary(previous_season).iloc[0] if previous_season else None

    logo_box, title_box = st.columns([1, 3.5], gap="small", vertical_alignment="center")
    with logo_box:
        st.image(nba_logo_url(), width=100 if COMPACT else 200)      
    with title_box:
        st.header(f"{selected_szn} Season League overview")
        st.caption(f"See who's the leader of this season")
    
    # League average  
    averages = [
        ("Points per Team", "PPG",     "{:.1f}"),
        ("3PA per Team",    "FG3A_PG", "{:.1f}"),
        ("3P%",             "FG3_PCT", "{:.1f}%"),
        ("eFG%",            "EFG_PCT", "{:.1f}%"),
        ("TS%",             "TS_PCT",  "{:.1f}%"),
    ]
    for box, (label, column, fmt) in zip(st.columns(len(averages)), averages):
        delta = None
        if previous is not None:
            delta = f"{summary[column] - previous[column]:+.1f} vs {previous_season}"
        box.metric(label, fmt.format(summary[column]), delta=delta, delta_color="normal")

    st.caption(" ")    
    
    # Team Leader
    l_profile = get_league_profile()
    l_leaders = [
        ("Best Record",  "WINS",    True,  "{:.0f} Games Win"),
        ("Best Offense", "PPG",     True,  "{:.1f} PPG"),
        ("Best Defense", "OPP_PPG", False, "{:.1f} PTS Allowed"),
        ("Most 3PA",     "FG3A_PG", True,  "{:.1f} per game"),
        ("Best 3P%",     "FG3_PCT", True,  "{:.1f}%"),
    ]
    for box, (label, column, highest, fmt) in zip(st.columns(len(l_leaders)), l_leaders):
        valid_teams = l_profile.dropna(subset=[column])
        if valid_teams.empty:
            with box:
                st.metric(label, "N/A")
            continue
        
        best = l_profile.loc[l_profile[column].idxmax() if highest else l_profile[column].idxmin()]
        abbr = best["Team"]
        
        with box:
            text_col, logo_col = st.columns([2, 1.5], gap="small", vertical_alignment="center")
            text_col.metric(label, abbr)
            logo_col.image(team_logo_url(abbr), width=60)
            st.caption(fmt.format(best[column]))   
    
    # Player Leader
    st.divider()
    st.subheader(f"{selected_szn} Season Player Leaders")
    
    p_profile = get_player_profile()
    p_profile.loc[p_profile["FG3M_PG"] * p_profile["Games"] < 82, "FG3_PCT"] = None     # official NBA rule
    p_leaders = [
        ("Scoring Leader",  "PPG",       True, "{:.1f} PPG"),
        ("Rebounds Leader", "REB_PG",    True, "{:.1f} RPG"),
        ("Assists Leader",  "AST_PG",    True, "{:.1f} APG"),
        ("Best 3P%",        "FG3_PCT",   True, "{:.1f}%"),
        ("Stocks Leader",   "STOCKS_PG", True, "{:.1f} STL+BLK"),
    ]
    for box, (label, column, highest, fmt) in zip(st.columns(len(p_leaders)), p_leaders):
        valid_players = p_profile.dropna(subset=[column])
        if valid_players.empty:
            with box:
                st.badge(label)
                st.markdown("**Too few games**")
                st.caption("Season just started")
            continue
        
        best = p_profile.loc[p_profile[column].idxmax() if highest else p_profile[column].idxmin()]
        player = best["Player"]
        team_abbr = best["Team"]
        
        with box:
            st.badge(label)
            st.markdown(f"**{player}**")
            st.caption(f"{fmt.format(best[column])} | ({team_abbr})")
            st.image(player_headshot_url(player), width=190)           
    

def show_league_efficiency_section():
    st.subheader(f"League-wide Efficiency Field Goal PCT (eFG%)")
    st.caption(f"""Dividing lines by league median. 
                Calculate from: eFG% = FGM + (0.5 × 3PM) / FGA""")

    fig = quadrant_chart(
        get_league_efficiency(), x_col="FG3A_PG", y_col="EFG_PCT", 
        label_col="Team",
        x_title="3PA per game", 
        y_title="eFG%",
        quadrant_labels=EFFICIENCY_LABELS, 
        split="median",
        use_logos=True,
        height=700
    )
    
    return show_chart(fig)


def show_league_shot_type():
    st.subheader("Shot Type Mix by Team")
    st.caption("Share of all field goal attempts by shot type")
    
    table = get_all_team_shot_types()
    rows = {"League": shot_shares(get_league_shot_types())}
    team_rows = {team: shot_shares(group) for team, group in table.groupby("Team")}
    for team in sorted(team_rows, key=lambda t: team_rows[t]["Rim"], reverse=True):
        rows[team] = team_rows[team]

    with st.expander("Click to Expand", expanded=not COMPACT):
        show_chart(shot_type_chart(rows, use_logos=not COMPACT, 
                                   row_height=40 if COMPACT else 50), shrink=False)


def show_league_view():
    
    show_league_header()
    st.divider()
    show_league_efficiency_section ()
    st.divider()
    show_league_shot_type()
    

# ---------- Team page ----------

def show_team_header(team, games, profile):
    wins = int((games["WL"] == "W").sum())
    losses = len(games) - wins
    three_point_pct = games["FG3M"].sum() / games["FG3A"].sum() * 100

    left, right = st.columns([2, 1], gap="small", vertical_alignment="center")

    with left:
        logo_box, title_box = st.columns([1, 3], gap="small", vertical_alignment="center")
        with logo_box:
            st.image(team_logo_url(team), width=150)
        with title_box:
            st.header(f"{TEAM_NAMES[team]} ({team})")
            st.caption(f"{len(games)} games | W-L: {wins}-{losses}")

        a, b, c = st.columns(3, gap="small")
        team_metric_rank(a, "Team FGA per game", f"{games['FGA'].mean():.1f}", "FGA_PG", profile, team)
        team_metric_rank(b, "Team FGM per game", f"{games['FGM'].mean():.1f}", "FGM_PG", profile, team)
        team_metric_rank(c, "Points per game",   f"{games['PTS'].mean():.1f}", "PPG",    profile, team)
        d, e, f = st.columns(3, gap="small")
        team_metric_rank(d, "Team 3PA per game", f"{games['FG3A'].mean():.1f}", "FG3A_PG", profile, team)
        team_metric_rank(e, "Team 3PM per game", f"{games['FG3M'].mean():.1f}", "FG3M_PG", profile, team)
        team_metric_rank(f, "Team 3P%",          f"{three_point_pct:.1f}%",     "FG3_PCT", profile, team)

    with right:
        show_chart(radar_chart(profile, TEAM_RADAR, "Team", team))


def show_team_efficiency_section(team):
    st.subheader("Team Efficiency Field Goal (eFG%)")
    st.caption("Compare the team's eFG% with all other teams. Dividing lines by league median")

    fig = quadrant_chart(
        get_league_efficiency(), x_col="FG3A_PG", y_col="EFG_PCT", label_col="Team",
        x_title="3PA per game", y_title="eFG%",
        quadrant_labels=EFFICIENCY_LABELS, 
        split="median",
        use_logos=True,
        highlight=team,
        height=600
    )
    show_chart(fig)


def show_team_shooting_section(games):
    st.subheader("Team Shooting, game by game")
    st.caption("🟩Green for Made, ⬛Grey for Missed")

    fig = stack_chart(
        games, "GAME_DATE", ["FGM", "FGMissed"], 
        names=["Made", "Missed"],
        line_col=["ROLLING_5G_FGA", "ROLLING_5G_FGM"],
        line_name=["5-game avg attempts", "5-game avg makes"],
        y_title="Field goals",
    )
    show_chart(fig)


def show_team_shot_type(team):
    left, right = st.columns([1, 3], gap="medium", vertical_alignment="center")
    with left:
        st.subheader("Shot Types Taken")
        st.caption(f"Share of the {team} Field Goal Attempts by shot types")
    with right:
        table = get_team_shot_types()
        if table.empty:
            st.info("No shot-zone data for this team and season.")
            return
        
        rows = {TEAM_NAMES[team]: shot_shares(table)}
        
        show_chart(shot_type_chart(rows, use_logos=True, row_height=80))


def show_team_three_point_section(team, games, profile):
    left, right = st.columns([2, 1], gap="medium", vertical_alignment="center")

    with left:
        st.subheader("Team 3 Point Attempts")
        st.caption("Team 3PA, game by game")
        fig = stack_chart(
            games, "GAME_DATE", ["FG3M", "FG3Missed"], 
            names=["Made", "Missed"],
            line_col=["ROLLING_5G_FG3A", "ROLLING_5G_FG3M"],
            line_name=["5-game avg 3-pt attempts", "5-game avg 3-pt makes"],
            y_title="3-pointers",
        )
        show_chart(fig)

    with right:
        three_point_share = games["FG3A"].sum() / games["FGA"].sum() * 100

        a, b, c = st.columns(3, gap="small")
        team_metric_rank(a, "3PM per game", f"{games['FG3M'].mean():.1f}", "FG3M_PG", profile, team)
        team_metric_rank(b, "3PA per game", f"{games['FG3A'].mean():.1f}", "FG3A_PG", profile, team)
        team_metric_rank(c, "3PT share",    f"{three_point_share:.1f}%",   "FG3A_RATE", profile, team)

        st.caption(" ")
        st.caption("Top 5 3-Pointer Shooters")
        shooters = get_team_three_point_shooters(team)
        fig = player_bar_chart(shooters, ["3PM per game", "Missed"],
                               total_col="3PA per game", total_label="FG3A")
        show_chart(fig)


def show_team_defense_section(team, games, profile):
    left, right = st.columns([2, 1], gap="medium", vertical_alignment="center")

    with left:
        st.subheader("Team Defensive Stats")
        st.caption("🟦Steals and 🟨Blocks with 📉Averaging Line")
        fig = stack_chart(
            games, "GAME_DATE", ["STL", "BLK"], 
            names=["Steals", "Blocks"],
            colors=[BLUE, GOLD],
            line_col=["ROLLING_5G_STL_BLK"], 
            line_name=["5-game avg steals + blocks"],
            line_colors=[LINE_RED],
            y_title="Steals + blocks",
        )
        show_chart(fig)

    with right:
        points_allowed = profile_value(profile, team, "OPP_PPG")

        a, b, c = st.columns(3, gap="small")
        team_metric_rank(a, "Steals per game", f"{games['STL'].mean():.1f}", "STL_PG", profile, team)
        team_metric_rank(b, "Blocks per game", f"{games['BLK'].mean():.1f}", "BLK_PG", profile, team)
        team_metric_rank(c, "Points allowed",  f"{points_allowed:.1f}", "OPP_PPG", profile, team, higher_is_better=False)

        st.caption(" ")
        st.caption("Top 5 Defensive Playmakers")
        defenders = get_team_defenders(team)
        fig = player_bar_chart(defenders, ["Steals", "Blocks"], colors=[BLUE, GOLD],
                               total_col="Steals + Blocks", total_label="STOCKS")   
        show_chart(fig)


def show_team_view(team):
    games = get_team_games(team)
    profile = get_league_profile()

    show_team_header(team, games, profile)
    show_team_efficiency_section(team)
    st.divider()
    show_team_shooting_section(games)
    show_team_shot_type(team)
    st.divider()
    show_team_three_point_section(team, games, profile)
    st.divider()
    show_team_defense_section(team, games, profile)


# ---------- Player page ----------

def show_player_header(player, games, profile):
    headshot_url = player_headshot_url(player)
    
    left, right = st.columns([1.5, 3], gap="large", vertical_alignment="center")
    with left:
        teams = " / ".join(games["TEAM_ABBREVIATION"].dropna().unique())
        st.header(player)
        st.caption(f"{teams} | {len(games)} games played")
        if headshot_url:
            st.image(headshot_url, width= 250)
        else:
            st.caption("Unavailable Image")
        
    with right:
        st.subheader(f"{selected_szn} {player} Stats:")
        
        FG_attempts = games["FGA"].sum()
        FG_pct = f"{games['FGM'].sum() / games['FGA'].sum() * 100:.1f}%" if FG_attempts else "N/A"
        three_attempts = games["FG3A"].sum()
        three_point_pct = f"{games['FG3M'].sum() / games['FG3A'].sum() * 100:.1f}%" if three_attempts else "N/A"
        FT_attempts = games["FTA"].sum()
        FT_pct = f"{games['FTM'].sum() / games['FTA'].sum() * 100:.1f}%" if FT_attempts else "N/A"
        
        row1 = st.columns(3, gap="small")
        row2 = st.columns(3, gap="small")
        
        player_metric_rank(row1[0], "FG%", FG_pct, "FG_PCT", profile, player)
        player_metric_rank(row1[1], "3P%", three_point_pct, "FG3_PCT", profile, player)
        player_metric_rank(row1[2], "FT%", FT_pct, "FT_PCT", profile, player)
        player_metric_rank(row2[0], "PTS per game", f"{games['PTS'].mean():.1f}", "PPG", profile, player)
        player_metric_rank(row2[1], "REB per game", f"{games['REB'].mean():.1f}", "REB_PG", profile, player)
        player_metric_rank(row2[2], "AST per game", f"{games['AST'].mean():.1f}", "AST_PG", profile, player)
    
    st.subheader(f"{selected_szn} Season Game-by-Game Stats")
    st.dataframe(games, width="stretch", height=200, hide_index=True)


def show_player_shooting_section(player, games):
    st.subheader(f"{player}'s Shooting, game by game")
    st.caption("🟩Green for Made, ⬛Grey for Missed")

    fig = stack_chart(
        games, "GAME_DATE", ["FGM", "FGMissed"], 
        names=["Made", "Missed"],
        line_col=["ROLLING_5G_FGA", "ROLLING_5G_FGM"],
        line_name=["5-game avg attempts", "5-game avg makes"],
        y_title="Field goals",
    )
    show_chart(fig)


def show_player_three_point_section(player, games, profile):
    left, right = st.columns([2, 1], gap="medium", vertical_alignment="center")
    
    with left:
        st.subheader(f"{player} 3-Point Shooting, game by game")
        st.caption("🟩Green for 3PT Made, ⬛Grey for 3PT Missed")
        fig = stack_chart(
            games, "GAME_DATE", ["FG3M", "FG3Missed"], 
            names=["Made", "Missed"],
            line_col=["ROLLING_5G_FG3A", "ROLLING_5G_FG3M"],
            line_name=["5-game avg 3-pt attempts", "5-game avg 3-pt makes"],
            y_title="3-pointers",
        )
        show_chart(fig)

    with right:
        three_point_share = games["FG3A"].sum() / games["FGA"].sum() * 100

        a, b, c = st.columns(3, gap="small")
        player_metric_rank(a, "3PM per game", f"{games['FG3M'].mean():.1f}", "FG3M_PG", profile, player)
        player_metric_rank(b, "3PA per game", f"{games['FG3A'].mean():.1f}", "FG3A_PG", profile, player)
        player_metric_rank(c, "3PT share",    f"{three_point_share:.1f}%",   "FG3A_RATE", profile, player)

        player_team = games["TEAM_ABBREVIATION"].iloc[-1] if team == "All teams" else team
        
        st.caption("")
        st.caption(f"{player_team} Top 5 3-Pointer Shooters")
        shooters = get_team_three_point_shooters(player_team)
        fig = player_bar_chart(shooters, ["3PM per game", "Missed"],
                                total_col="3PA per game", total_label="FG3A")
        show_chart(fig)
    return 


def show_player_defense_section(player, games, profile):
    left, right = st.columns([2, 1], gap="medium", vertical_alignment="center")
    
    with left:
        st.subheader(f"{player} Defensive Play, game by game")
        st.caption("🟦Steals and 🟨Blocks with 📉Averaging Line")
        fig = stack_chart(
            games, "GAME_DATE", ["STL", "BLK"], 
            names=["Steals", "Blocks"],
            colors=[BLUE, GOLD],
            line_col=["ROLLING_5G_STL_BLK"],
            line_name=["5-game avg steals + blocks"],
            line_colors=[LINE_RED],
            y_title="Steals + Blocks",
        )
        show_chart(fig)

    with right:
        a, b = st.columns(2, gap="small")
        player_metric_rank(a, "STL per game", f"{games['STL'].mean():.1f}", "STL_PG", profile, player)
        player_metric_rank(b, "BLK per game", f"{games['BLK'].mean():.1f}", "BLK_PG", profile, player)

        player_team = games["TEAM_ABBREVIATION"].iloc[-1] if team == "All teams" else team

        st.caption("")
        st.caption(f"{player_team} Top 5 Defensive Playmakers")
        defenders = get_team_defenders(player_team)
        fig = player_bar_chart(defenders, ["Steals", "Blocks"], colors=[BLUE, GOLD],
                                total_col="Steals + Blocks", total_label="stl+blk")
        show_chart(fig)
    return


def show_player_ts_section(player, games):
    left, right = st.columns([1.5, 1], gap="medium", vertical_alignment="center")
    with left:
        st.subheader(f"True Shooting PCT (TS%) by Season")
        st.caption(f"Measures a player's overall scoring efficiency")
        st.caption(f"Calculate from: TS% = PTS / ( 2 × (FGA + (0.44 × FTA)))")
        show_chart(ts_chart(get_player_ts_by_szn(player), player, height=500))
    with right:
        st.subheader("FTM vs FTA in each game")
        show_chart(px.scatter(games, x="FTA", y="FTM", hover_data=["GAME_DATE"], height=250))
        st.subheader("FGM vs FGA in each game")
        show_chart(px.scatter(games, x="FGA", y="FGM", hover_data=["GAME_DATE"], height=300))
    

def show_player_shot_type(player):
    left, right = st.columns([1, 3], gap="medium", vertical_alignment="center")
    with left:
        st.subheader("Shot Types Taken")
        st.caption(f"Share of {player}'s Field Goal Attempts by shot types")
    with right:
        table = get_player_shot_types(player)
        if table.empty:
            st.info("No shot-zone data for this player and season.")
            return
            
        rows = {player: shot_shares(table)}

        show_chart(shot_type_chart(rows, use_logos=True, row_height=80))


def show_player_view(player):
    
    games = get_player_games(player)
    profile = get_player_profile()
    
    show_player_header(player, games, profile)
    st.divider()
    show_player_shooting_section(player, games)
    show_player_shot_type(player)
    st.divider()
    show_player_three_point_section(player, games, profile)
    st.divider()
    show_player_defense_section(player, games, profile)
    st.divider()
    show_player_ts_section(player, games)
    

# =====================================================================
# 6. MAIN
# This is the part that runs every time you click something.
# =====================================================================

# --- Sidebar: choose a team first, then a player ---

# check if user device is phone
COMPACT = is_compact_layout()

picker = st.expander("Select the categories", expanded=True) if COMPACT else st.sidebar

selected_szn = picker.selectbox("Season", get_season_list())

team = picker.selectbox("Team", ["All teams"] + get_team_list())

if team == "All teams":
    player = picker.selectbox("Player", ["All players"] + get_player_list())
else:
    player = picker.selectbox("Player", ["Whole team"] + get_player_list(team))

if COMPACT:
    st.markdown("""
        <style>
        [data-testid="stMainBlockContainer"] { padding: 1rem 0.75rem 3rem; }
        [data-testid="stMetricValue"] { font-size: 1.6rem; }
        h1 { font-size: 1.8rem; } h2 { font-size: 1.5rem; } h3 { font-size: 1.2rem; }
        </style>
        """, unsafe_allow_html=True)

if team == "All teams" and player == "All players":
    page = "league"
elif team != "All teams" and player == "Whole team":
    page = "team"
else:
    page = "player"

if page == "league":
    show_league_view()
elif page == "team":
    show_team_view(team)
else:
    show_player_view(player)