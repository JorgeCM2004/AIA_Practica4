from typing import Annotated

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict


class AgentState(TypedDict):
	messages: Annotated[list, add_messages]


class Tools_Graph_Agent:
	def __init__(self, searcher, model_name="llama3"):
		self.searcher = searcher

		@tool
		def search_local_db(query: str) -> str:
			"""Search the official clinical medical database. Always use this tool first for any medical inquiry."""
			top_k = self.searcher.search(query, top_k=3)
			return "\n\n".join(top_k["documents"][0])

		@tool
		def search_internet(query: str) -> str:
			"""Search the internet for general information. Use this only if the 'search_local_db' tool has not returned useful information or has failed."""
			ddg = DuckDuckGoSearchRun()
			return ddg.invoke(query)

		self.tools = [search_local_db, search_internet]

		self.llm = ChatOllama(model=model_name, temperature=0).bind_tools(self.tools)

		self.app = self._build_graph()

	def agent_node(self, state: AgentState):
		sys_msg = SystemMessage(
			content="""You are a professional maternity assistant.
        Strict rules:
        1. ALWAYS use the local database tool first to look up symptoms.
        2. If the local database doesn’t help, use the online tool.
        3. If the final answer comes from the internet, you MUST add a disclaimer stating that it is unverified web information.
        4. Always recommend consulting an obstetrician."""
		)

		messages_to_process = [sys_msg] + state["messages"]

		response = self.llm.invoke(messages_to_process)

		return {"messages": [response]}

	def _build_graph(self):
		workflow = StateGraph(AgentState)

		workflow.add_node("agent", self.agent_node)

		workflow.add_node("tools", ToolNode(self.tools))

		workflow.add_edge(START, "agent")

		workflow.add_conditional_edges("agent", tools_condition)

		workflow.add_edge("tools", "agent")

		return workflow.compile()

	def run(self, query: str):
		inputs = {"messages": [("user", query)]}

		final_state = self.app.invoke(inputs)

		return final_state["messages"][-1].content
