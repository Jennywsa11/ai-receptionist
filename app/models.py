from pydantic import BaseModel, HttpUrl


class ScrapeRequest(BaseModel):
    url: HttpUrl


class ChatStartRequest(BaseModel):
    session_id: str
    url: HttpUrl


class ChatRequest(BaseModel):
    session_id: str
    url: HttpUrl
    question: str


class ChatResponse(BaseModel):
    answer: str
