from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    prox_api_token: str
    prox_host: str

    model_config = {"env_file": "examples/.env"}
