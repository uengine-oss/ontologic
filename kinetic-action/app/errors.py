"""계약 §3 오류 형식 `{error:{code, message}}`."""

from __future__ import annotations

_STATUS = {
    "unauthenticated": 401,
    "forbidden": 403,
    "not_plan_owner": 403,
    "not_found": 404,
    "invalid_filter": 422,
    "invalid_params": 422,
    "too_many_targets": 422,
    "not_executable": 422,
    "not_readonly": 422,
    "plan_expired": 409,
    "approval_required": 409,
    "conflict": 409,
    "nothing_to_execute": 409,
    "bad_gateway": 502,
}


class KineticError(Exception):
    """REST·MCP 공통 오류. code 가 HTTP 상태를 정한다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = _STATUS.get(code, 400)

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}
