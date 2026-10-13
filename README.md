# Google Calendar MCP Server

A small MCP (Model Context Protocol) server that lets Claude read and schedule events on my Google Calendar. I built it because scheduling one thing meant opening the calendar, scanning for a free spot by eye, and clicking through several screens. Now I can tell Claude how long something takes and how urgent it is, and it finds a slot and books it.

Built with Python, [FastMCP](https://github.com/jlowin/fastmcp), and the Google Calendar API.

## How it works

Claude never talks to Google directly. It picks a tool and fills in the arguments, and this server makes the actual Calendar API call.

```
You -> Claude (MCP client) -> this server (FastMCP) -> Google Calendar API
```

The server runs locally over stdio. The MCP client (for example Claude Desktop) launches it as a subprocess, so there's no web server or deployment involved.

## Tools

| Tool | What it does |
|---|---|
| `list_calendars` | Lists your calendars with their names and IDs |
| `list_event` | Lists events on a date (`YYYY-MM-DD`, defaults to today) |
| `create_calendar_event` | Creates an event with a title, start/end time, and optional description |
| `find_free_slot` | Finds gaps in a day that fit a given duration (default 30 min) |
| `schedule_task_with_priority` | Finds a free slot and books the task based on priority |

### Priority scheduling

| Priority | Where the task goes |
|---|---|
| `high` | The earliest free slot |
| `low` | The latest free slot |
| `medium` (default) | The first free slot inside working hours (9:00-17:00) |

It's a simple rule, not an optimizer. The point is that I only have to say how urgent something is instead of picking a time myself.

## Setup

**Requirements:** Python 3.10+ and a Google account.

### 1. Install dependencies

```bash
pip install fastmcp google-api-python-client google-auth-oauthlib
```

### 2. Get Google credentials

1. In the [Google Cloud Console](https://console.cloud.google.com/), create a project.
2. Enable the **Google Calendar API** for it.
3. Set up the OAuth consent screen. If the app is in testing mode, add your own Google account as a test user.
4. Create an **OAuth client ID** of type **Desktop app**.
5. Download the JSON and save it as `credentials.json` in the same folder as the server script.

### 3. First run

```bash
python server.py
```

The first time a tool needs Google access, a browser window opens so you can approve access. The server then saves the result to `token.json` next to the script and reuses it, refreshing it automatically when it expires.

### 4. Connect it to Claude Desktop

Add the server to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "google-calendar": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

Use the Python interpreter that has the dependencies installed, and restart Claude Desktop afterward.

## Example prompts

- "What's on my calendar tomorrow?"
- "Find a 45 minute slot on Thursday."
- "Schedule a 1 hour task called 'Write report', high priority, for Friday."

When creating events directly, times should be ISO 8601 with a UTC offset, for example `2026-10-14T15:00:00-04:00`.

## Gotchas I ran into

- **OAuth scopes.** Google's quickstart uses the read-only calendar scope. This server creates events, so it uses the full `https://www.googleapis.com/auth/calendar` scope. If you change scopes, the token you already saved still has the old permissions, so **delete `token.json`** and authorize again.
- **stdout is reserved.** With the stdio transport, stdout carries the protocol messages between client and server, so a stray `print()` can break it. Debug output goes to `stderr`.

## Known limitations

- **Time zones.** Day boundaries and working hours are calculated in UTC, not the calendar's time zone.
- **All-day events.** They're returned as dates rather than datetimes and aren't handled separately yet.
- **No tests yet.** I want to add unit tests for the free-slot logic and a small set of scenarios to measure how often Claude picks the right tool with the right arguments.
- **Local only.** It runs over stdio on my machine. There's no remote deployment, so there's also no rate limiting or endpoint authentication.

## Keep secrets out of git

`credentials.json` and `token.json` contain secrets. Add them to `.gitignore` before your first commit:

```
credentials.json
token.json
```

If either was ever committed, remove it from the history and create new credentials in the Google Cloud Console.
