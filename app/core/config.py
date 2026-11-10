import truststore
truststore.inject_into_ssl()

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List


class Settings(BaseSettings):
    """
    Application Settings configured via environment variables.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # Project Info
    PROJECT_NAME: str = "Mazaji AI"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    API_SECRET_KEY: str = "mazaji_ai_secure_prod_key_9f82d1c4b7e"

    # Database Settings
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "mazaji_db"

    # Connection Pool Settings
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 30
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800  # 30 minutes

    # Security & Rate Limiting Settings
    RATE_LIMIT_PER_MINUTE: int = 60
    CORS_ORIGINS: List[str] = ["*"]

    @property
    def async_database_url(self) -> str:
        """
        Constructs the async MySQL connection string for SQLAlchemy using aiomysql.
        """
        auth = f"{self.DB_USER}:{self.DB_PASSWORD}" if self.DB_PASSWORD else self.DB_USER
        return f"mysql+aiomysql://{auth}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    # Vector Storage Settings (Qdrant)
    QDRANT_PATH: str = "./qdrant_storage"
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None

    # Cache & Session Management (Redis)
    REDIS_URL: Optional[str] = None
    SESSION_TTL_SECONDS: int = 86400  # 24 hours
    MAX_SESSION_HISTORY: int = 10

    # Media & Image Base URL
    MEDIA_BASE_URL: str = "https://booking.najaz.in/storage"

    # AI & Embeddings Settings (Google Gemini)
    EMBEDDING_PROVIDER: str = "gemini"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    CHAT_MODEL: str = "gemini-3.5-flash"
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_API_KEYS: List[str] = []

    @property
    def all_gemini_keys(self) -> List[str]:
        """
        تجميع كافة مفاتيح جوجل المتاحة (الأساسية والاحتياطية) في قائمة موحدة خالية من التكرار
        سواء تم تمريرها كمفتاح واحد أو مفاتيح مفصولة بفواصل أو قائمة.
        """
        keys: List[str] = []
        if self.GEMINI_API_KEY:
            for k in self.GEMINI_API_KEY.split(","):
                k_clean = k.strip()
                if k_clean and k_clean not in keys:
                    keys.append(k_clean)
        for k in self.GEMINI_API_KEYS:
            k_clean = k.strip()
            if k_clean and k_clean not in keys:
                keys.append(k_clean)
        return keys


settings = Settings()
