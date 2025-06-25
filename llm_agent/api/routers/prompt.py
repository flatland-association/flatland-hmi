"""This module provides the API router for handling prompt requests to the coordinator agent.

It defines the endpoint for invoking the coordinator agent with a prompt and optional responses.
"""  # noqa: INP001

import logging

from fastapi import APIRouter, HTTPException

from flatland_agent.agents.coordinator_agent import CoordinatorAgent
from flatland_agent.models import PromptRequest

router = APIRouter(tags=["prompt"])

logger = logging.getLogger("flatland")
logger.setLevel(logging.INFO)


@router.post("/prompt")
async def prompt(request: PromptRequest) -> dict:
    """Invoke the coordinator agent with a prompt and optional responses.

    Parameters
    ----------
    request : PromptRequest
        The request object containing the prompt string, optional responses, and context.

    Returns:
    -------
    dict: A dictionary containing the response from the coordinator agent.

    Raises:
    ------
    HTTPException: If the prompt is empty (400) or if an internal error occurs (500).
    """
    coordinator = CoordinatorAgent()
    if not request.prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    try:
        return await coordinator.process(prompt=request.prompt, context=request.context)
    except Exception as err:
        logger.exception("Error occurred while processing the request.")
        raise HTTPException(status_code=500, detail="An internal error occurred") from err
