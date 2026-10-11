from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

MACOS_BAMBU_STUDIO = Path("/Applications/BambuStudio.app")


class Settings(BaseSettings):
    """Configuração via variáveis de ambiente com prefixo FILAMENTOR_ (ou arquivo .env)."""

    model_config = SettingsConfigDict(env_prefix="FILAMENTOR_", env_file=".env", extra="ignore")

    # Pasta "profiles/BBL" do Bambu Studio. Em Linux/Docker, apontar explicitamente.
    profiles_dir: Path = MACOS_BAMBU_STUDIO / "Contents/Resources/profiles/BBL"
    # Executável do Bambu Studio usado pelo CLI (fases F5+).
    bambu_studio_bin: Path = MACOS_BAMBU_STUDIO / "Contents/MacOS/BambuStudio"


@lru_cache
def get_settings() -> Settings:
    return Settings()
