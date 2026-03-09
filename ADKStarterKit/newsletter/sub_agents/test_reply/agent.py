"""Simple test reply agent for manual testing."""

from google.adk.agents import Agent


REPLY_AGENT_INSTR = """
You are a test reply agent. When given a user's message, reply concisely in one sentence,
acknowledging and restating the user's request. Keep the response neutral and helpful.
Do not call external tools or sub-agents—this agent is for quick reply testing only.
"""


reply_test_agent = Agent(
    model="gemini-2.0-flash-lite",
    name="reply_test_agent",
    description="Simple agent that replies to user messages for quick manual testing.",
    instruction=REPLY_AGENT_INSTR,
)
