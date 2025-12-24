from fastmcp import FastMCP
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from datetime import datetime, timedelta, timezone
import os
import time
import logging
import sys

mcp = FastMCP()

SCOPES = ['https://www.googleapis.com/auth/calendar']

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(SCRIPT_DIR, 'token.json')
CREDENTIALS_PATH = os.path.join(SCRIPT_DIR, 'credentials.json')

def get_service():
    creds = None
    print("Processing request", file=sys.stderr)
    print(TOKEN_PATH, file=sys.stderr)

    if os.path.exists(TOKEN_PATH):
        print("token already exists", file=sys.stderr)
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        print("token doest exist and we are creating one", file=sys.stderr)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials = creds)

@mcp.tool
def list_calendars():
    print("listing calendar", file=sys.stderr)
    service = get_service()
    print("listing calendar got the service token", file=sys.stderr)

    calendars = service.calendarList().list().execute()
    return [
        {"name": c["summary"], "id": c["id"]}
        for c in calendars.get("items", [])
    ]

@mcp.tool
def list_event(calendar_id: str = "primary", date: str = None):
    """
    List all events on a given date(YYYY-MM-DD)
    """
    service = get_service()
    if date:
        start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        end = start+timedelta(days=1)
    else:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        end = start+timedelta(days=1)

    events = service.events().list(
        calendarId = calendar_id,
        timeMin = start.isoformat(),
        timeMax = end.isoformat(),
        singleEvents = True,
        orderBy = "startTime"
    ).execute()

    return [
        {
            "id": e["id"],
            "title": e.get("summary", ""),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "end": e["end"].get("dateTime", e["end"].get("date"))
        }
        for e in events.get("items", [])
    ]


@mcp.tool
def create_calendar_event(calendar_id: str, title: str, start_time: str, end_time: str, description: str = ""):
    """
    Create a new event on Google Calendar
    """
    service = get_service()
    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    result = service.events().insert(calendarId = calendar_id, body = event).execute()
    return {"status": "success", "event_id": result.get("id")}

@mcp.tool
def find_free_slot(calendar_id: str = "primary", date: str = None, duration_minutes: int = 30):
    """
    find free slot in calendar on a specific date
    """
    service = get_service()
    if date:
        start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    else:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)

    end = start + timedelta(days=1)

    result = service.events().list(
        calendarId=calendar_id,
        timeMin= start.isoformat(),
        timeMax= end.isoformat(),
        singleEvents = True,
        orderBy= "startTime"
    ).execute()

    events = result.get("items", [])

    busy_slots = []
    for e in events:
        start_str = e["start"].get("dateTime", e["start"].get("date"))
        end_str = e["end"].get("dateTime", e["end"].get("date"))

        busy_start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        busy_end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

        busy_slots.append((busy_start, busy_end))

    free_slots = []
    required_duration = timedelta(minutes=duration_minutes)

    current_time = start

    for busy_start, busy_end in busy_slots:
        if busy_start - current_time >= required_duration:
            free_slots.append({
                "start": current_time.isoformat(),
                "end": busy_start.isoformat()
            })

        current_time = max(current_time, end)

    if end - current_time >= required_duration:
        free_slots.append({
            "start": current_time.isoformat(),
            "end": end.isoformat()
        })

    return free_slots

WORK_START_HOUR = 9
WORK_END_HOUR = 17

def within_working_hours(slot_start, slot_end):
    return (
        WORK_START_HOUR <= slot_start.hour < WORK_END_HOUR and 
        WORK_START_HOUR < slot_end.hour <= WORK_END_HOUR
    )

@mcp.tool
def  schedule_task_with_priority(title: str, duration_minutes: int, priority: str = "medium", calendar_id: str = "primary", date: str = None, description: str = ""):
    """
    Schedule a task automatically based on priority.
    """
    service = get_service()
    duration = timedelta(minutes=duration_minutes)

    #find free slots
    free_slots = find_free_slot(
        calendar_id = calendar_id,
        date = date,
        duration_minutes = duration_minutes
    )

    if not free_slots:
        return {"status": "failed", "reason": "No available time slots"}
    
    #convert slot string into datetime
    parsed_slots = []
    for slot in free_slots:
        start = datetime.fromisoformat(slot["start"])
        end = datetime.fromisoformat(slot["end"])
        parsed_slots.append((start, end))

    #apply priority strategy
    priority = priority.lower()

    if priority == "high":
        chosen_start, chosen_end = parsed_slots[0]

    elif priority == "low":
        chosen_start, chosen_end = parsed_slots[-1]

    else:
        working_slots = [
            (s,e) for s,e in parsed_slots
            if within_working_hours(s,e)
        ]

        chosen_start, chosen_end = working_slots[0] if working_slots else parsed_slots[0]

    #trim slot to task duration
    event_start = chosen_start
    event_end = event_start+duration

    #create event
    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": event_start.isoformat()},
        "end": {"dateTime": event_end.isoformat()}
    }

    created = service.events().insert(
        calendarId = calendar_id,
        body = event
    ).execute()

    return {
        "status":"success",
        "title": title,
        "priority": priority,
        "start": event_start.isoformat(),
        "end": event_end.isoformat(),
        "event_id": created.get("id")
    }

if __name__ == "__main__":
    mcp.run()