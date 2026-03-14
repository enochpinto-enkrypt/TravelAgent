"""Wrapper to Google Search Grounding with custom prompt and travel helpers.

Exports AgentTool wrappers that use the `google_search` tool to ground
answers and to perform high-level flights/hotels searches (via web search).
"""

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

from google.adk.tools.google_search_tool import google_search
from newsletter.shared_libraries import ai_logging


_search_agent = Agent(
    model="gemini-2.5-flash",
    name="google_search_grounding",
    description="An agent providing Google-search grounding capability",
    instruction="""
    Answer the user's question directly using google_search grounding tool; Provide a brief but concise response.
    Rather than a detailed response, provide the immediate actionable item for a tourist or traveler, in a single sentence.
    Do not ask the user to check or look up information for themselves; that's your role.
    IMPORTANT:
    - Always return your response in bullet points
    - Specify why it matters to the user
    - Add a light, relevant joke at the end of your response
    """,
    tools=[google_search],
)


google_search_grounding = AgentTool(agent=_search_agent)


# Flight search agent: uses web search to find current flight options, carriers,
# approximate prices and booking links for the requested route and dates.
_flight_agent = Agent(
    model="gemini-2.5-flash",
    name="google_flight_search",
    description="Find flight options and booking links using web search",
    instruction="""
    You are a travel assistant. Use the `google_search` tool to find current
    flight options for the given origin, destination and dates. Return a
    short list of top options with carrier, approximate price, departure/arrival
    times, and a booking link. If exact prices are unavailable, indicate ranges.
    Return results as bullet points; include why each option might matter to the traveler.
    """,
    tools=[google_search],
)

google_flight_search = AgentTool(agent=_flight_agent)


# Hotel search agent: uses web search to find nearby hotels with price ranges,
# ratings and booking links for the specified location and dates.
_hotel_agent = Agent(
    model="gemini-2.5-flash",
    name="google_hotel_search",
    description="Find hotels near a location using web search",
    instruction="""
    You are a travel assistant. Use the `google_search` tool to locate hotels
    around the specified location for the requested dates. Return a shortlist of
    hotels with star rating, approximate nightly price, distance to requested
    point of interest, and a booking link. Present as bullet points and include
    one sentence on suitability (e.g., family-friendly, business travelers).
    """,
    tools=[google_search],
)

google_hotel_search = AgentTool(agent=_hotel_agent)