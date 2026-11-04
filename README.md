# NBA Stats Explorer

An interactive NBA dashboard built with Python, DuckDB and Streamlit. It covers the league, every team and every player, and lets you switch between seasons (2020-21 to 2025-26).

## Working with an AI assistant

You can ask questions and get answers without changing any project files. Files are edited only when you explicitly ask for an edit or other file change.

**Live app:** <paste your Streamlit link here>

![League overview](images/league.png)

## What you can explore

**League overview**
- League averages (points, 3PA, 3P%, eFG%, TS%) compared with the previous season
- Team leaders: best record, best offense, best defense, most 3PA, best 3P%
- Quadrant chart of all 30 teams: 3-point volume against shooting efficiency (eFG%)
- Shot type mix of every team: rim, paint (non-rim), mid-range, corner 3 and above-the-break 3

**Team page**
- Record and stat cards, each with the team's rank out of 30
- Radar chart showing where the team stands in the league
- Game-by-game shooting charts with 5-game rolling averages (field goals and 3-pointers)
- Steals, blocks and points allowed
- Shot type mix compared with the league

**Player page**
- Headshot, per-game stats with league rank, and the full game log
- Game-by-game shooting charts
- True shooting % (TS%) by season compared with the league average
- Shot type mix compared with the league

![Team page](images/team.png)
![Player page](images/player.png)

## How it works

```
NBA API (nba_api)  ->  pipeline.py (pandas)  ->  DuckDB file  ->  app.py (Streamlit + Plotly)
```

1. `pipeline.py` downloads the game logs and shot-zone data for each season with `nba_api`, cleans them with pandas, and loads them into `nba_analytics.duckdb`. Each season is replaced as a whole (delete, then insert), so the script can be run again safely.
2. `app.py` asks DuckDB for exactly the numbers each page needs with SQL, calculates the rest in pandas (rolling averages, ranks) and draws the charts with Plotly.

**Tables in the database**

| Table | What is in it |
|---|---|
| `player_games` | One row per player per game: points, shots, rebounds, steals, minutes and more |
| `player_shot_zones` | Shot attempts and makes per player, season and court zone |
| `team_shot_zones` | The same, per team |

**Stat definitions**
- **eFG%** = (FGM + 0.5 x 3PM) / FGA
- **TS%** = PTS / (2 x (FGA + 0.44 x FTA))
- **Rank** = position among all teams (or all qualifying players) for that season. Players need a minimum number of games, and percentages need a minimum number of attempts.

## Run it on your computer

```bash
git clone https://github.com/<your-username>/nba-stats-explorer.git
cd nba-stats-explorer

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
streamlit run app.py
```

The database file is included in the repo, so the app works right away.

**Refresh the data** (needs an internet connection; stop the app first):

```bash
python pipeline.py
```

Change the `SEASONS` list at the top of `pipeline.py` to load other seasons.

## Project structure

```
app.py                  # the Streamlit app
pipeline.py             # downloads, cleans and loads the data
nba_analytics.duckdb    # the database
requirements.txt        # Python packages
images/                 # screenshots used in this README
```

## Tech stack

Python, pandas, DuckDB, Streamlit, Plotly, nba_api

## Notes

- The NBA API often blocks requests from cloud servers, so the data is refreshed on a local computer and the database file is committed to the repo.
- Rim shots come from the "Restricted Area" zone, which includes layups, dunks and tip-ins.

## Credits

Data comes from NBA.com through the unofficial [`nba_api`](https://github.com/swar/nba_api) package. Team logos and player photos belong to the NBA and are loaded from its website, not stored in this repo. This project is for learning and is not affiliated with the NBA.
