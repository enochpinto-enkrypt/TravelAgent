"""Wrapper to Google Maps Places API."""

import os
from typing import Dict, List, Any, Optional
import time

from google.adk.tools import ToolContext
import requests
from newsletter.shared_libraries import ai_logging


class PlacesService:
    """Wrapper to Placees API."""

    def _check_key(self):
        if (
            not hasattr(self, "places_api_key") or not self.places_api_key
        ):  # Either it doesn't exist or is None.
            # https://developers.google.com/maps/documentation/places/web-service/get-api-key
            self.places_api_key = os.getenv("GOOGLE_PLACES_API_KEY")

    def find_place_from_text(self, query: str) -> Dict[str, Any]:
        """
        Find a place using a text query via Google Places API.

        Args:
            query: The search query (e.g., "Eiffel Tower Paris").

        Returns:
            A dictionary with place_id, place_name, place_address, photos (list), map_url, lat, lng.
            If no place is found, returns {'error': ...}
        """
        self._check_key()
        places_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        params = {
            "input": query,
            "inputtype": "textquery",
            "fields": "place_id,formatted_address,name,photos,geometry",
            "key": self.places_api_key,
        }

        max_attempts = 5
        attempt = 0
        backoff = 1.0
        last_error: Optional[Exception] = None
        start_time = time.time()
        # Log the outgoing places query as AI-related context (prompt-like)
        try:
            ai_logging.log_ai_call(
                event="places.find_place.start",
                model=None,
                prompt=query,
                extra={"url": places_url},
            )
        except Exception:
            pass

        while attempt < max_attempts:
            try:
                response = requests.get(places_url, params=params, timeout=10)
                # Successful response
                if response.status_code == 200:
                    place_data = response.json()

                    # No candidates found
                    if not place_data.get("candidates"):
                        try:
                            ai_logging.log_ai_call(
                                event="places.find_place.end",
                                model=None,
                                prompt=query,
                                response={"status_code": response.status_code, "candidate_count": 0},
                                start_time=start_time,
                                extra={"url": places_url},
                            )
                        except Exception:
                            pass
                        return {"error": "No places found."}

                    # Extract data for the first candidate
                    place_details = place_data["candidates"][0]
                    place_id = place_details.get("place_id")
                    place_name = place_details.get("name")
                    place_address = place_details.get("formatted_address")
                    photos = self.get_photo_urls(place_details.get("photos", []), maxwidth=400)
                    map_url = self.get_map_url(place_id) if place_id else None
                    location = place_details.get("geometry", {}).get("location", {})
                    lat = str(location.get("lat")) if "lat" in location else None
                    lng = str(location.get("lng")) if "lng" in location else None

                    result = {
                        "place_id": place_id,
                        "place_name": place_name,
                        "place_address": place_address,
                        "photos": photos,
                        "map_url": map_url,
                        "lat": lat,
                        "lng": lng,
                    }

                    # Log successful end before returning
                    try:
                        ai_logging.log_ai_call(
                            event="places.find_place.end",
                            model=None,
                            prompt=query,
                            response={"status_code": response.status_code, "candidate_count": len(place_data.get("candidates", []))},
                            start_time=start_time,
                            extra={"url": places_url},
                        )
                    except Exception:
                        pass

                    return result

                # Handle quota / throttling responses as retryable
                retryable_statuses = {429, 503}
                if response.status_code in retryable_statuses or response.status_code == 403:
                    # Prefer `Retry-After` header if present
                    retry_after = response.headers.get("Retry-After")
                    delay = None
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except Exception:
                            delay = None

                    # Try to parse Google RPC RetryInfo from body
                    if delay is None:
                        try:
                            body = response.json()
                            details = []
                            if isinstance(body, dict):
                                # Some errors live under `error.details` or top-level `details`
                                details = body.get("error", {}).get("details", []) or body.get("details", []) or []
                            for d in details:
                                if isinstance(d, dict) and d.get("@type", "").endswith("RetryInfo"):
                                    rd = d.get("retryDelay")
                                    if rd and rd.endswith("s"):
                                        try:
                                            delay = float(rd[:-1])
                                            break
                                        except Exception:
                                            pass
                        except ValueError:
                            pass

                    if delay is None:
                        delay = backoff

                    time.sleep(delay)
                    backoff = min(backoff * 2, 60)
                    attempt += 1
                    continue

                # Non-retryable HTTP error
                response.raise_for_status()

            except requests.exceptions.RequestException as e:
                last_error = e
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                attempt += 1
                try:
                    ai_logging.log_ai_call(
                        event="places.find_place.error",
                        model=None,
                        prompt=query,
                        response={"error": str(e)},
                        start_time=start_time,
                        extra={"attempt": attempt},
                    )
                except Exception:
                    pass
                continue

        return {"error": f"Error fetching place data after {max_attempts} attempts: {last_error}"}

    def get_photo_urls(self, photos: List[Dict[str, Any]], maxwidth: int = 400) -> List[str]:
        """Helper to build photo URLs from Google Places API photo references."""
        if not photos:
            return []
        base_url = "https://maps.googleapis.com/maps/api/place/photo"
        return [
            f"{base_url}?maxwidth={maxwidth}&photoreference={photo['photo_reference']}&key={self.places_api_key}"
            for photo in photos
        ]

    def get_map_url(self, place_id: str) -> str:
        """Helper to build a Google Maps URL for a place."""
        return f"https://www.google.com/maps/place/?q=place_id:{place_id}"


# Google Places API
places_service = PlacesService()


def map_tool(key: str, tool_context: ToolContext):
    """
    This is going to inspect the pois stored under the specified key in the state.
    One by one it will retrieve the accurate Lat/Lon from the Map API, if the Map API is available for use.

    Args:
        key: The key under which the POIs are stored.
        tool_context: The ADK tool context.
        
    Returns:
        The updated state with the full JSON object under the key.
    """
    if key not in tool_context.state:
        tool_context.state[key] = {}

    # The pydantic object types.POISuggestions
    if "places" not in tool_context.state[key]:
        tool_context.state[key]["places"] = []

    pois = tool_context.state[key]["places"]
    for poi in pois:  # The pydantic object types.POI
        location = poi["place_name"] + ", " + poi["address"]
        # Log a short context snapshot for this map lookup
        try:
            ai_logging.log_ai_call(
                event="map_tool.lookup",
                model=None,
                prompt=location,
                extra={"key": key, "place_name": poi.get("place_name")},
            )
        except Exception:
            pass

        result = places_service.find_place_from_text(location)
        # Fill the place holders with verified information.
        poi["place_id"] = result["place_id"] if "place_id" in result else None
        poi["map_url"] = result["map_url"] if "map_url" in result else None
        if "lat" in result and "lng" in result:
            poi["lat"] = result["lat"]
            poi["long"] = result["lng"]

    return {"places": pois}  # Return the updated pois


# """Wrapper to Google Maps Places API."""

# import os
# from typing import Dict, List, Any, Optional

# from google.adk.tools import ToolContext
# import requests


# class PlacesService:
#     """Wrapper to Placees API."""

#     def _check_key(self):
#         if (
#             not hasattr(self, "places_api_key") or not self.places_api_key
#         ):  # Either it doesn't exist or is None.
#             # https://developers.google.com/maps/documentation/places/web-service/get-api-key
#             self.places_api_key = os.getenv("GOOGLE_PLACES_API_KEY")

#     def find_place_from_text(self, query: str) -> Dict[str, Any]:
#         """
#         Find a place using a text query via Google Places API.

#         Args:
#             query: The search query (e.g., "Eiffel Tower Paris").

#         Returns:
#             A dictionary with place_id, place_name, place_address, photos (list), map_url, lat, lng.
#             If no place is found, returns {'error': ...}
#         """
#         self._check_key()
#         places_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
#         params = {
#             "input": query,
#             "inputtype": "textquery",
#             "fields": "place_id,formatted_address,name,photos,geometry",
#             "key": self.places_api_key,
#         }

#         try:
#             response = requests.get(places_url, params=params)
#             response.raise_for_status()
#             place_data = response.json()

#             if not place_data.get("candidates"):
#                 return {"error": "No places found."}

#             # Extract data for the first candidate
#             place_details = place_data["candidates"][0]
#             place_id = place_details["place_id"]
#             place_name = place_details["name"]
#             place_address = place_details["formatted_address"]
#             location = place_details["geometry"]["location"]
#             lat = str(location["lat"])
#             lng = str(location["lng"])

#             return {
#                 "place_id": place_id,
#                 "place_name": place_name,
#                 "place_address": place_address,
#                 "lat": lat,
#                 "lng": lng,
#             }

#         except requests.exceptions.RequestException as e:
#             return {"error": f"Error fetching place data: {e}"}

# # Google Places API
# places_service = PlacesService()