import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PACIFIC = timezone(timedelta(hours=-7))  # PDT; switches to -8 in winter (handled by system tz)


def _utc_to_pt(utc_str: str) -> str:
    """Convert ESPN UTC date string to Pacific Time display string."""
    try:
        dt_utc = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        dt_pt = dt_utc.astimezone(PACIFIC)
        return dt_pt.strftime("%-I:%M %p PT")
    except Exception:
        return utc_str


def _pt_dates_for_day(date_str: str) -> list[str]:
    """Return the two UTC date strings that cover a full PT calendar day.
    e.g. May 13 PT spans 20260513 and 20260514 in UTC."""
    dt = datetime.strptime(date_str, "%Y%m%d")
    next_day = dt + timedelta(days=1)
    return [date_str, next_day.strftime("%Y%m%d")]


def _fetch_espn(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _fetch_pt_day(base_url: str, date_str: str, team_filter: str = None, label: str = "") -> list[dict]:
    """Fetch events across both UTC dates that cover a PT calendar day, filter to PT day, optionally filter by team."""
    seen, events = set(), []
    for d in _pt_dates_for_day(date_str):
        sep = "&" if "?" in base_url else "?"
        url = f"{base_url}{sep}dates={d}"
        try:
            data = _fetch_espn(url)
            for e in data.get("events", []):
                if e["id"] in seen:
                    continue
                raw_date = e.get("date", "")
                try:
                    dt_utc = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    if dt_utc.astimezone(PACIFIC).strftime("%Y%m%d") != date_str:
                        continue
                except Exception:
                    pass
                if team_filter:
                    competitors = e.get("competitions", [{}])[0].get("competitors", [])
                    if not any(team_filter in c["team"]["displayName"] for c in competitors):
                        continue
                seen.add(e["id"])
                events.append(e)
        except Exception as ex:
            print(f"{label} fetch error: {ex}")
    return events


def get_nhl_games(date_str: str) -> list[dict]:
    return _fetch_pt_day("https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard", date_str, label="NHL")


def get_nfl_games(date_str: str) -> list[dict]:
    return _fetch_pt_day("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard", date_str, team_filter="Seattle Seahawks", label="NFL")


def get_mls_games(date_str: str) -> list[dict]:
    return _fetch_pt_day("https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard", date_str, team_filter="Seattle Sounders", label="MLS")


def get_mlb_games(date_str: str) -> list[dict]:
    return _fetch_pt_day("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard", date_str, team_filter="Seattle Mariners", label="MLB")


def get_ncaa_football_games(date_str: str) -> list[dict]:
    return _fetch_pt_day("https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80", date_str, team_filter="Washington State", label="NCAA")


def get_pga_leaderboard(date_str: str) -> list[dict]:
    dt = datetime.strptime(date_str, "%Y%m%d")
    if dt.weekday() not in (5, 6):  # 5=Saturday, 6=Sunday
        return []
    try:
        scoreboard = _fetch_espn(f"https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates={date_str}")
        events = scoreboard.get("events", [])
        results = []
        for event in events:
            event_id = event.get("id")
            detail = _fetch_espn(f"https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard/{event_id}")
            competitors = detail.get("competitions", [{}])[0].get("competitors", [])
            top3 = sorted(competitors, key=lambda c: c.get("order", 999))[:3]
            results.append({
                "name": event.get("name"),
                "top3": [{"player": c["athlete"]["fullName"], "score": c["score"], "position": c["order"]} for c in top3]
            })
        return results
    except Exception as e:
        print(f"PGA fetch error: {e}")
        return []


def get_f1_events(date_str: str) -> list[dict]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/racing/f1/scoreboard?dates={date_str}"
    try:
        data = _fetch_espn(url)
        return data.get("events", [])
    except Exception as e:
        print(f"F1 fetch error: {e}")
        return []


def _slim_event(e: dict) -> dict:
    comp = e.get("competitions", [{}])[0]
    teams = [c["team"]["displayName"] for c in comp.get("competitors", [])]
    broadcasts = [b["names"][0] for b in comp.get("broadcasts", []) if b.get("names")]
    geo = [g["media"]["shortName"] for g in comp.get("geoBroadcasts", []) if g.get("media")]
    tv = broadcasts or geo
    return {
        "name": e.get("name"),
        "time_pt": _utc_to_pt(e.get("date", "")),
        "teams": teams,
        "tv": tv,
        "status": comp.get("status", {}).get("type", {}).get("description", ""),
    }


def build_raw_summary(date_str: str) -> str:
    nhl = get_nhl_games(date_str)
    pga = get_pga_leaderboard(date_str)
    f1 = get_f1_events(date_str)
    mlb = get_mlb_games(date_str)
    nfl = get_nfl_games(date_str)
    mls = get_mls_games(date_str)
    ncaa = get_ncaa_football_games(date_str)

    sections = []

    def fmt_game_events(label, events):
        if not events:
            return
        lines = [f"## {label}"]
        for e in events:
            lines.append(json.dumps(_slim_event(e), default=str))
        sections.append("\n".join(lines))

    def fmt_pga(events):
        if not events:
            return
        lines = ["## PGA Golf"]
        for e in events:
            lines.append(json.dumps(e, default=str))
        sections.append("\n".join(lines))

    fmt_game_events("NHL", nhl)
    fmt_pga(pga)
    fmt_game_events("Formula 1", f1)
    fmt_game_events("MLB - Mariners", mlb)
    fmt_game_events("NFL - Seahawks", nfl)
    fmt_game_events("MLS - Sounders", mls)
    fmt_game_events("NCAA Football - WSU Cougars", ncaa)

    return "\n\n".join(sections) if sections else "NO_EVENTS"


def get_sports_digest(date_str: str = None) -> str:
    if date_str is None:
        date_str = datetime.now(PACIFIC).strftime("%Y%m%d")

    raw = build_raw_summary(date_str)

    if raw == "NO_EVENTS":
        return "No sporting events today across your tracked sports."

    display_date = datetime.strptime(date_str, "%Y%m%d").strftime("%A, %B %-d")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""You are formatting a daily sports digest for a personal Telegram notification.

Date: {display_date}
Timezone: Pacific Time

Below is raw ESPN API data for today's events. Extract and format ONLY the following:
For most sports:
- Game/event time is already provided in Pacific Time in the `time_pt` field — use it as-is
- Matchup (Team A vs Team B, or event name for F1)
- TV network/channel

For PGA Golf (only shown on Saturday/Sunday):
- Tournament name
- Top 3 on the leaderboard: position, player name, score (e.g. -15)
- Format each player on its own line: `1. Player Name — -15`

Output format — use this exact structure, with sports in this priority order:
1. NHL
2. PGA Golf
3. Formula 1
4. Seattle Seahawks
5. Seattle Sounders
6. WSU Cougars

Use Telegram Markdown formatting:
- Bold the date header: *Sports for {display_date}*
- Bold each sport section header
- One line per event: `TIME — Matchup — TV`
- If a TV channel is unknown, write "TBD"
- Omit any sport with no events today

Sports priority order:
1. NHL
2. PGA Golf
3. Formula 1
4. Seattle Mariners
5. Seattle Seahawks
6. Seattle Sounders
7. WSU Cougars

Raw data:
{raw}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text


if __name__ == "__main__":
    print(get_sports_digest())
