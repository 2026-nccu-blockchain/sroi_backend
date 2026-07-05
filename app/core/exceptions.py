from fastapi import HTTPException

class APIException(HTTPException):
    def __init__(self, http_status: int, status_code: str, message: str):
        super().__init__(status_code=http_status, detail=message)
        self.status_code_str = status_code
        self.message = message