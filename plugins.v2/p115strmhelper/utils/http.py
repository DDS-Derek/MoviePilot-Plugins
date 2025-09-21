import httpx

def check_response(
    resp: httpx.Response,
) -> httpx.Response:
    """
    检查 HTTP 响应，如果状态码 ≥ 400 则抛出 httpx.HTTPStatusError
    """
    if resp.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"HTTP Error {resp.status_code}: {resp.reason_phrase}",
            request=resp.request,
            response=resp,
        )
    return resp
