from langchain_openai import AzureChatOpenAI
import os
import httpx
from dotenv import load_dotenv, find_dotenv
from flatland_agent.models import PromptRequest, Context
from flatland_agent.agents.language_agent import LanguageAgent
from flatland_agent.agents.flatland_agent import FlatlandAgent
from flatland_agent.agents.incident_agent import IncidentAgent  # Placeholder for incident management agent
from langgraph.graph import END, StateGraph
from flatland_agent.models import AgentState, CoordinatorResponse
from flatland_agent.utils import context_to_markdown


dotenv_path = find_dotenv()
load_dotenv(dotenv_path)


class CoordinatorAgent:

    def __init__(self) -> None:
        """Initialize the CoordinatorAgent with LLM."""
        self.llm = AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_ENDPOINT"],
            api_key=os.environ["OPENAI_API_KEY"],
            api_version=os.environ["API_VERSION"],
            model=os.environ["MODEL_NAME"],
            http_client=httpx.Client(verify=os.environ["CERTIFICATE_PATH"]),
        ).with_structured_output(CoordinatorResponse, method="json_schema", strict=True)

        self.language_agent = LanguageAgent()
        self.flatland_agent = FlatlandAgent()
        self.incident_agent = IncidentAgent()

        workflow = StateGraph(AgentState)
        workflow.add_node("determine_intent", self._determine_intent)
        workflow.add_node("process_request", self._process_request)
        workflow.add_node("process_simulation", self._process_simulation)
        workflow.add_node("process_incident", self._process_incident)
        workflow.add_conditional_edges(
            "determine_intent",
            self._route_after_intent,
            {
                "flatland_agent": "process_simulation",
                "language_agent": "process_request",
                "incident_agent": "process_incident",
             },
        )
        workflow.set_entry_point("determine_intent")
        self.graph = workflow.compile()

    async def process(self, prompt: str, context: Context=None) -> dict:
        """Process a user request and return the response.

        Parameters
        ----------
        prompt : str
            The user's prompt to be processed.
        context : Context
            The context for the request, if any.

        Returns:
        -------
        dict
            A dictionary containing the reponse.
        """
        initial_state = AgentState(
            prompt=prompt,
            context=context_to_markdown(context) if context else "",
        )

        response = await self.graph.ainvoke(initial_state)
        return {
            "response": {
                "text": response["response"],
            },
        }

    def _determine_intent(self, state: AgentState) -> AgentState:
        prompt = (
            "## Analysis of the Main Request and Conversation History\n\n"
            "**Instructions:**\n"
            "- Analyze the following **main request** and the **conversation history**.\n"
            "- The conversation history is presented in Markdown format, with each line starting with the role followed by the respective text.\n"
            "- Note: Newer conversation history appears at the end and is more relevant than older context.\n"
            "- In your answer, almost always return **'Language Agent'**.\n"
            "- Only return **'Flatland Agent'** if the request explicitly and unambiguously instructs to continue with a specific Variant (e.g., 'Continue with Variant 1').\n"
            "- Do NOT return **'Flatland Agent'** for questions, suggestions, or vague references to variants.\n"
            "- If the request clearly requires language input or processing, return **'Language Agent'**.\n"
            "- If the request clearly asks for information about the duckdog incident, return **'Incident Agent'**.\n"
            "- If the request is not clear, return **'Language Agent'**.\n\n"
            "### Request\n"
            f"{state.prompt}\n\n"
            "### Conversation History\n"
            f"{state.context}\n"
        )

        response = self.llm.invoke(prompt)
        state.intent = response.intent
        return state

    def _route_after_intent(self, state: AgentState) -> str:
        if "Flatland Agent" in state.intent:
            return "flatland_agent"
        elif "Incident Agent" in state.intent:
            return "incident_agent"
        return "language_agent"

    def _process_request(self, state: AgentState) -> AgentState:
        return self.language_agent.process(state)

    def _process_simulation(self, state: AgentState) -> AgentState:
        return self.flatland_agent.process(state)

    def _process_incident(self, state: AgentState) -> AgentState:
        return self.incident_agent.process(state)
