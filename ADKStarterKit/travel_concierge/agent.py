from google.adk.agents import Agent

from travel_concierge.sub_agents.inspiration.agent import inspiration_agent

# Example 1: Simple built-in tool
# google_search_tool = FunctionTool(func=google_search)

# Example 2: Agent as a tool
from travel_concierge.tools.search import (
    search_available_hotels,
    search_flights_to_destination,
)

# Example 3: Function tool
from google.adk.tools import FunctionTool
hotels_tool = FunctionTool(func=search_available_hotels)
flights_tool = FunctionTool(func=search_flights_to_destination)
from travel_concierge.prompt import ROOT_AGENT_INSTR

from travel_concierge.sub_agents.inspiration.agent import place_agent, news_agent
root_agent = Agent(
    model="gemini-2.5-flash",
    name="root_agent",
    description="A Travel concierge",
    instruction=ROOT_AGENT_INSTR,
    tools=[hotels_tool, flights_tool],
    sub_agents=[
        inspiration_agent
    ]
    # tools = [google_search_tool]
    # tools = [google_search_grounding],
    # tools=[places_tool]
    # sub_agents=[
    #     inspiration_agent
    # ]
)