import asyncio
import os
from typing import Dict, Any, List
import traceback

# --- LangChain Imports ---
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langchain.agents import create_agent
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_mcp_adapters.client import MultiServerMCPClient
# --- Configuration ---
# 1. SERVER URL: Must match the host and port you run your script.py server on (e.g., 127.0.0.1:8000)
# Assumes the FastMCP server is running at http://127.0.0.1:8000 on the default /mcp path
MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"
# 2. AZURE OPENAI CONFIGURATION
# IMPORTANT: These environment variables must be set for AzureChatOpenAI to work
# AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT_NAME
async def run_mcp_agent():
    """
    Initializes the MCP client, loads tools, and runs the LangChain Agent Executor.
    """
    print("--- 🚀 Initializing MCP-LangChain Agent ---")
    # 1. Initialize Azure OpenAI Model
    try:
        # AzureChatOpenAI automatically uses AZURE_OPENAI_API_KEY/ENDPOINT/DEPLOYMENT_NAME
        # The model name here should be your Azure deployment name.
        llm = AzureChatOpenAI(
                azure_deployment="gpt-4.1",  # or your deployment
                api_version="2025-03-01-preview",  # or your api version
                temperature=0,
                max_tokens=None,
                timeout=None,
                max_retries=2,
                # other params...
            )
        print(f"✅ Azure Model Initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Azure Model. Check environment variables: {e}")
        return
    # 2. Configure the MultiServerMCPClient to connect to your running server
    # We define a single server named 'weather_generator'
    server_config: Dict[str, Any] = {
        "weather_generator": {
            "transport": "streamable_http",
            "url": MCP_SERVER_URL,
        }
    }
    # Instantiate the client
    mcp_client = MultiServerMCPClient(server_config)
    # 3. Load MCP Tools and create a Client Session
    try:
        # The session must wrap the entire chat loop to prevent premature termination
        async with mcp_client.session("weather_generator") as session:
            # load_mcp_tools uses the session to fetch the mcp.json schema 
            tools: List[Any] = await load_mcp_tools(session)
            #print(f"✅ Tools Loaded Successfully: {[t.name for t in tools]}")
            for t in tools:
                print(f"🔧 Tool: {t.name} | Description: {t.description}")
            # --- 4. Build the LangChain Agent ---
            # System message guides the LLM on its role and when to use tools.
            system_prompt = SystemMessage(
                content="You are a helpful and powerful Weather and Document Agent. "
                        "Your purpose is to use the provided tools to answer user queries. "
                        "You must use the weather tools for data and the document tools for formatting or outputting files."
            )
            # Test the LLM directly
            messages = [
                (
                    "system",
                    "You are a helpful assistant that translates English to French. Translate the user sentence.",
                ),
                ("human", "I love programming."),
            ]
            ai_msg = llm.invoke(messages)
            print(ai_msg.content)
            # Create the Agent Executor with the loaded tools
            agent_executor = create_agent(
                llm,
                tools=tools,
                system_message=system_prompt,
                verbose=True
            )
            print("--- 💬 Agent Ready. Start chatting... ---")
            while True:
                user_input = await asyncio.to_thread(input, "\nUser: ")
                if user_input.lower() in ["quit", "exit"]:
                    print("Exiting agent.")
                    break
                try:
                    result = await agent_executor.ainvoke(
                        {"messages": [HumanMessage(content=user_input)]}
                    )
                    print(f"Agent: {result['messages'][-1].content}")
                except Exception as e:
                    print("❌ Agent execution failed:")
                    traceback.print_exc()
    except Exception as e:
        print(f"❌ An error occurred during agent execution or tool loading: {e}")
        traceback.print_exc()
        print("Ensure your FastMCP server is running at the specified URL.")
if __name__ == "__main__":
    # Ensure all required variables are present before starting
    required_vars = ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME"]
    os.environ["AZURE_OPENAI_API_KEY"] = ""
    os.environ["AZURE_OPENAI_ENDPOINT"] = ""
    os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"] = "gpt-4.1"
    if not all(os.environ.get(var) for var in required_vars):
        print("--- 🛑 SETUP ERROR ---")
        print("Please set the following environment variables to your Azure OpenAI credentials:")
        for var in required_vars:
            print(f"- {var}")
        print("---------------------")
    else:
        # LangChain's ainvoke requires an asynchronous context
        asyncio.run(run_mcp_agent())
