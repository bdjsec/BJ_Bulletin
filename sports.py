import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta
import anthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PACIFIC = timezone(timedelta(hours=-7))  # PDT; switches to -8 in winter (handled by system tz)


def _fetch_espn(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get_nhl_games(date_str: str) -> list[dict]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates={date_str}"
    try:
        data = _fetch_espn(url)
        return data.get("events", [])
    except Exception as e:
        print(f"NHL fetch error: {e}")
        return []


def get_nfl_games(date_str: str) -> list[dict]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={date_str}"
    try:
        data = _fetch_espn(url)
        return [e for e in data.get("events", [])
                if any("Seattle Seahawks" in c["team"]["displayName"]
                       for c in e.get("competitions", [{}])[0].get("competitors", []))]
    except Exception as e:
        print(f"NFL fetch error: {e}")
        return []


def get_mls_games(date_str: str) -> list[dict]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard?dates={date_str}"
    try:
        data = _fetch_espn(url)
        return [e for e in data.get("events", [])
                if any("Seattle Sounders" in c["team"]["displayName"]
                       for c in e.get("competitions", [{}])[0].get("competitors", []))]
    except Exception as e:
        print(f"MLS fetch error: {e}")
        return []


def get_mlb_games(date_str: str) -> list[dict]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={date_str}"
    try:
        data = _fetch_espn(url)
        return [e for e in data.get("events", [])
                if any("Seattle Mariners" in c["team"]["displayName"]
                       for c in e.get("competitions", [{}])[0].get("competitors", []))]
    except Exception as e:
        print(f"MLB fetch error: {e}")
        return []


def get_ncaa_football_games(date_str: str) -> list[dict]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates={date_str}&groups=80"
    try:
        data = _fetch_espn(url)
        return [e for e in data.get("events", [])
                if any("Washington State" in c["team"]["displayName"]
                       for c in e.get("competitions", [{}])[0].get("competitors", []))]
    except Exception as e:
        print(f"NCAA football fetch error: {e}")
        return []


def get_pga_events(date_str: str) -> list[dict]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates={date_str}"
    try:
        data = _fetch_espn(url)
        return data.get("events", [])
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


def build_raw_summary(date_str: str) -> str:
    nhl = get_nhl_games(date_str)
    pga = get_pga_events(date_str)
    f1 = get_f1_events(date_str)
    mlb = get_mlb_games(date_str)
    nfl = get_nfl_games(date_str)
    mls = get_mls_games(date_str)
    ncaa = get_ncaa_football_games(date_str)

    sections = []

    def fmt_events(label, events):
        if not events:
            return
        lines = [f"## {label}"]
        for e in events:
            lines.append(json.dumps(e, default=str))
        sections.append("\n".join(lines))

    fmt_events("NHL", nhl)
    fmt_events("PGA Golf", pga)
    fmt_events("Formula 1", f1)
    fmt_events("MLB - Mariners", mlb)
    fmt_events("NFL - Seahawks", nfl)
    fmt_events("MLS - Sounders", mls)
    fmt_events("NCAA Football - WSU Cougars", ncaa)

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
- Game/event time in Pacific Time (convert from UTC if needed)
- Matchup (Team A vs Team B, or event name for golf/F1)
- TV network/channel

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
        model="claude-opus-4-7",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text


if __name__ == "__main__":
    print(get_sports_digest())
