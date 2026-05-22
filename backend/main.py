import os
from fractions import Fraction

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router
from pydantic import BaseModel

ALLOW_ORIGINS = os.environ.get("ALLOW_ORIGINS", "http://localhost:4200,http://localhost")
middleware_config = {
    "allow_origins": ALLOW_ORIGINS.split(","),
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

# https://github.com/pydantic/pydantic/issues/8426
BaseModel.model_config["json_encoders"] = {Fraction: lambda obj: {'__fraction__': True, 'as_str': str((obj.numerator, obj.denominator))}}

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    **middleware_config
)

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
