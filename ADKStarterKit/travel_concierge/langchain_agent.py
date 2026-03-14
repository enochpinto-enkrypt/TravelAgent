import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv

# Import the existing PlacesService
from travel_concierge.tools.places import PlacesService

load_dotenv()

# 1. Initialize our free internet search tool
search_tool = DuckDuckGoSearchRun(
    name="internet_search",
    description="Search the internet for travel destinations, flights, weather, news, and inspiration."
)

# 2. Wrap the existing Google Places API into a LangChain tool
places_service = PlacesService()

@tool
def search_places_and_hotels(query: str) -> str:
    """
    Search for travel places, tourist attractions, and hotel recommendations.
    Use this tool whenever the user asks for hotels or specific real-world locations.
    Pass a descriptive query like "Best cheap hotels in Paris" or "Eiffel tower".
    """
    result = places_service.find_place_from_text(query)
    if "error" in result:
        return f"Could not find information: {result['error']}"
    
    # Format the result nicely for the LLM
    return (
        f"Name: {result.get('place_name')}\n"
        f"Address: {result.get('place_address')}\n"
        f"Google Maps URL: {result.get('map_url')}\n"
    )

tools = [search_tool, search_places_and_hotels]

# 3. Setup the Agent System Prompt
system_instruction = '''You are an exclusive travel concierge agent.
You help users to discover their dream holiday destination, find cheap hotels, and plan their entire vacation.
You have access to the internet to search for inspiration, flights, news, and weather.
You also have a Places API to find specific high-quality hotels and tourist attractions.

Follow these rules:
1. Always ask clarifying questions if the user hasn't specified a budget or timeframe.
2. Provide day-by-day itineraries when asked or when it makes sense.
3. Recommend specific hotels using your `search_places_and_hotels` tool.
4. If the user wants a cheap option, make sure to explicitly search for budget-friendly alternatives and free attractions.
'''

# 4. Initialize the cheap OpenAI model 
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7,
    api_key=os.getenv("OPENAI_API_KEY")
)

# 5. Create the Agent using langgraph
travel_concierge_executor = create_react_agent(
    model=llm,
    tools=tools,
    state_modifier=system_instruction
)
