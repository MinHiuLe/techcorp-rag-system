import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    GROQ_API_KEY: str = Field(default=..., env="GROQ_API_KEY")
    COHERE_API_KEY: str = Field(default=..., env="COHERE_API_KEY")
    GOOGLE_API_KEY: str = Field(default="", env="GOOGLE_API_KEY")

    QDRANT_URL: str = Field(default="http://localhost:6333", env="QDRANT_URL")
    MINIO_ENDPOINT: str = Field(default="localhost:9000", env="MINIO_ENDPOINT")
    MINIO_ACCESS_KEY: str = Field(env="MINIO_ACCESS_KEY") 
    MINIO_SECRET_KEY: str = Field(env="MINIO_SECRET_KEY")

    LANGCHAIN_TRACING_V2: str = Field(default="true", env="LANGCHAIN_TRACING_V2")
    LANGCHAIN_API_KEY: str = Field(default="", env="LANGCHAIN_API_KEY")
    LANGCHAIN_PROJECT: str = Field(default="TechCorp-RAG-Prod", env="LANGCHAIN_PROJECT")

    LLM_MODEL: str = "llama-3.3-70b-versatile"
    UTILITY_MODEL: str = "llama-3.1-8b-instant"
    COLLECTION_NAME: str = "techcorp_knowledge"
    MAX_CONTEXT_LENGTH: int = 15000

    EVAL_MODE: bool = Field(default=False, env="EVAL_MODE")
    
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    API_KEYS: str = Field(default="", env="API_KEYS") # Comma-separated keys

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()