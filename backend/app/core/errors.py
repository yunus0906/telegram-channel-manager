from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """业务异常：`code` 是稳定的机器可读标识，`detail` 携带排查线索。

    `detail` 只放异常类名一类的非敏感信息，禁止放验证码、密码、API Hash、
    session 文件内容或消息正文。
    """

    def __init__(self, status_code: int, code: str, message: str, detail: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    error: dict[str, str] = {"code": exc.code, "message": exc.message}
    if exc.detail:
        error["detail"] = exc.detail
    return JSONResponse(status_code=exc.status_code, content={"error": error})
