from pydantic import BaseModel, Field


class HTTPErrorResponse(BaseModel):
    detail: str = Field(description="Description of the error.")
