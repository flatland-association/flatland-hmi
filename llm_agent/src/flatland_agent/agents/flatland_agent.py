from langchain_openai import AzureChatOpenAI
from flatland_agent.models import AgentState, FlatlandResponse
import os
import httpx


class FlatlandAgent:

    def __init__(self) -> None:
        self.llm = AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_ENDPOINT"],
            api_key=os.environ["OPENAI_API_KEY"],
            api_version=os.environ["API_VERSION"],
            model=os.environ["MODEL_NAME"],
            http_client=httpx.Client(verify=os.environ["CERTIFICATE_PATH"]),
        ).with_structured_output(FlatlandResponse, method="json_schema", strict=True)

    def process(self, state: AgentState) -> AgentState:
        prompt = f"""Return only the ID of the variant that should be used for the Flatland API request.
        The selection of the variant should be based on the following prompt and the conversation context.

        ### Main Request\n
        {state.prompt}\n\n
        ### Conversation History\n
        "{state.context}\n
        """
        response = self.llm.invoke(prompt)
        state.variant_id = response.variant_id
        state.response = f"The selected variant {response.variant_id} will be forwarded to the operators."
        return state
