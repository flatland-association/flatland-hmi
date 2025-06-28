"""Main entrypoint for the FastAPI application in the Flatland agent API.

This module sets up the FastAPI app, includes routers, and configures the Mangum handler so it is also deployable on aws lambda.
"""

from importlib.metadata import PackageNotFoundError, version

from routers import prompt, invoke
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

import uvicorn


TITLE = "FLATLAND"
DESCRIPTION = __doc__
try:
    VERSION = version("flatland")
except PackageNotFoundError:
    VERSION = "0.0.1"

app = FastAPI(title=TITLE, description=DESCRIPTION, version=VERSION)
app.include_router(prompt.router)
app.include_router(invoke.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mangum_handler = Mangum(app, lifespan="off")

uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")