from langchain_openai import AzureChatOpenAI
from flatland_agent.models import AgentState
import os
import httpx


class IncidentAgent:

    def __init__(self) -> None:
        self.llm = AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_ENDPOINT"],
            api_key=os.environ["OPENAI_API_KEY"],
            api_version=os.environ["API_VERSION"],
            model=os.environ["MODEL_NAME"],
            http_client=httpx.Client(verify=os.environ["CERTIFICATE_PATH"]),
        )

    def process(self, state: AgentState) -> AgentState:
        """Process the request using the LLM."""
        # TODO: this is so far only a placeholder prompt for preview purposes.
        prompt = """
            As a dispatcher, you must compare the timetable variants in case of deviations and find the best solution variant.
            As input, the system provides you with the route for n train journeys as a sequence of code points with
            passing times and arrival times. In addition, for each train journey, the latest arrival time is given,
            which must not be exceeded. If the train arrives later than the latest arrival time,
            that is not good. Arriving too early is also not acceptable. Too early is anything that arrives before the latest arrival time.
            The goal must be to arrive as precisely as possible. Being late is not a solution and is very unfavorable.
            If the train never arrives at the target - the solution must be marked as unsolvable and must not be used.

            The following train journeys exist:
            A, B, C

            There are three solution variants:
            V1 and V2

            Here is the data for V1:

            A: [ (Location C1, Time: 10), (Location C2, Time: 11), (Location C2, Time: 12), Target: C2, latest arrival: 14]
            B: [ (Location C0, Time: 8), (Location C2, Time: 9), (Location C2, Time: 10), Target: C2, latest arrival: 10]
            C: [ (Location C0, Time: 10), (Location C0, Time: 11), (Location C0, Time: 12), (Location C0, Time: 13), (Location C3, Time: 14), Target: C3, latest arrival: 13]

            Here is the data for V2:

            A: [ (Location C1, Time: 10), (Location C3, Time: 11), (Location C3, Time: 12), Target: C2, latest arrival: 14]
            B: [ (Location C0, Time: 8), (Location C1, Time: 9), (Location C2, Time: 10), Target: C2, latest arrival: 10]
            C: [ (Location C0, Time: 10), (Location C3, Time: 11), (Location C4, Time: 12), (Location C3, Time: 13), Target: C3, latest arrival: 13]

            The numbers are to be interpreted as minutes.

            Consider the following rules for your response:

            - Mark the variants in which at least one train does not arrive with ❌ | Mark the best variant with ✔️ | mark the remaining variants with ➤  } - the icon must be displayed before the variant.

            - Rate the trains as follows: too early as icon ⇠ with calculated minute deviation | on time as icon ✔ | too late as ⚠️ with calculated minute deviation | not arrived with ❌ }

            - Keep your output as short as possible.
        """
        response = self.llm.invoke(prompt)
        state.response = response.content if response else "No response from LLM"
        return state
