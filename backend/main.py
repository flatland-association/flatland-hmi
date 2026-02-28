import os
import typing
from fractions import Fraction

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic.json import ENCODERS_BY_TYPE

from app.routes import router

ALLOW_ORIGINS = os.environ.get("ALLOW_ORIGINS", "http://localhost:4200,http://localhost")
middleware_config = {
    "allow_origins": ALLOW_ORIGINS.split(","),
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}


def fraction_encoder(obj: Fraction) -> typing.Any:
    return {'__fraction__': True, 'as_str': str((obj.numerator, obj.denominator))}


ENCODERS_BY_TYPE[Fraction] = fraction_encoder

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    **middleware_config
)

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
