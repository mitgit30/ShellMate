from pydantic import BaseModel


class UploadedKeyResponse(BaseModel):
    original_filename: str
    key_id: str
