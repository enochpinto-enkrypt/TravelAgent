import json, urllib.request, urllib.error

data = {
    "session_id": "test-session",
    "itinerary_text": "# Trip to Rome\nDay 1: Arrival\n- Breakfast: Cafe\n- Visit: Colosseum\nDay 2: Explore\n- Lunch: Trattoria\n",
    "title": "Rome Trip",
}

req = urllib.request.Request(
    url="http://localhost:8000/itinerary/pdf",
    data=json.dumps(data).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        print(resp.status)
        print(body)
except urllib.error.HTTPError as e:
    print('HTTPError', e.code)
    try:
        print(e.read().decode())
    except Exception:
        pass
except Exception as e:
    print('Error', e)
