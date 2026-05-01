from pydantic import BaseModel


class UploadedKeyResponse(BaseModel):
    original_filename: str
    stored_filename: str
    private_key_path: str
