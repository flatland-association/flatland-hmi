from langchain_openai import AzureChatOpenAI
from flatland_agent.models import AgentState
import os
import httpx


class LanguageAgent:

    def __init__(self) -> None:
        """Initialize the SQLAgent with an AzureChatOpenAI instance and a workflow graph."""
        self.llm = AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_ENDPOINT"],
            api_key=os.environ["OPENAI_API_KEY"],
            api_version=os.environ["API_VERSION"],
            model=os.environ["MODEL_NAME"],
            http_client=httpx.Client(verify=os.environ["CERTIFICATE_PATH"]),
        )

    def process(self, state: AgentState) -> AgentState:
        """Process the request using the LLM."""
        prompt = f"""Answer the following request in natural language, and keep your answer very short:
        {state.prompt}.

        Use the information from previous conversations:
        {state.context}
        """
        response = self.llm.invoke(prompt)
        state.response = response.content if response else "No response from LLM"
        return state
