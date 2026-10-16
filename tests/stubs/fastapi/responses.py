class Response:
    def __init__(self, content=None, status_code: int = 200, media_type=None, headers=None, **kw):
        self.body = content
        self.status_code = status_code
        self.media_type = media_type
        self.headers = dict(headers or {})
        self._cookies = {}

    def set_cookie(self, key, value="", **kwargs):
        self._cookies[key] = value

    def delete_cookie(self, key, **kwargs):
        self._cookies.pop(key, None)


class HTMLResponse(Response):
    pass


class JSONResponse(Response):
    pass


class PlainTextResponse(Response):
    pass


class RedirectResponse(Response):
    def __init__(self, url="", status_code: int = 307, **kw):
        super().__init__(content=None, status_code=status_code, **kw)
        self.url = url


class StreamingResponse(Response):
    def __init__(self, content=None, status_code: int = 200, media_type=None, headers=None, **kw):
        super().__init__(content=content, status_code=status_code, media_type=media_type, headers=headers)


class FileResponse(Response):
    def __init__(self, path=None, status_code: int = 200, media_type=None, headers=None, **kw):
        super().__init__(content=path, status_code=status_code, media_type=media_type, headers=headers)
