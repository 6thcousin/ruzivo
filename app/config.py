from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    whatsapp_token:           str
    whatsapp_phone_number_id: str
    verify_token:             str
    flow_id:                  str
    flow_mode:                str = "draft"       # "draft" or "published"
    catalog_id:               str = ""            # Meta Commerce Catalog ID
    base_url:                 str = "http://localhost:8000"
    api_version:              str = "v19.0"

    @property
    def whatsapp_api_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}/{self.whatsapp_phone_number_id}/messages"

    @property
    def whatsapp_media_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}/{self.whatsapp_phone_number_id}/media"

    class Config:
        env_file = ".env"


settings = Settings()
