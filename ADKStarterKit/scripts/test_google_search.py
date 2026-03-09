import json
import traceback

from google.adk.tools.google_search_tool import google_search


def run_test():
    query = "What's the weather in Paris today?"
    try:
        result = google_search(query)
        print(json.dumps({"ok": True, "result": result}, default=str, indent=2))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        traceback.print_exc()


if __name__ == "__main__":
    run_test()
