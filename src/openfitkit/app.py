"""A small local HTTP boundary around the replaceable coaching service."""

from contextlib import contextmanager
from pathlib import Path
import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException

from . import __version__
from .models import ChatRequest, Profile, ResetRequest
from .providers import Provider, ProviderError, build_provider
from .service import FitnessService, ServiceError
from .settings import Settings
from .storage import Store, StoreError


MAX_BODY_BYTES = 32 * 1024
STATIC_DIR = Path(__file__).with_name("static")


def create_app(settings: Settings | None = None, provider: Provider | None = None) -> FastAPI:
    """Create one local app; injected settings/providers keep tests fully offline."""
    settings = settings or Settings.from_env()
    service = FitnessService(Store(settings.data_dir), provider or build_provider(settings))
    token = secrets.token_urlsafe(32)
    hosts = {f"127.0.0.1:{settings.port}", f"localhost:{settings.port}"}
    if settings.port == 80:
        hosts.update({"127.0.0.1", "localhost"})
    origins = {f"http://{host}" for host in hosts}
    app = FastAPI(title="OpenFitKit", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service, app.state.settings = service, settings

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.headers.get("host", "").lower() not in hosts:
            response = JSONResponse({"error": "OpenFitKit accepts local browser requests only."}, status_code=403)
        elif request.headers.get("origin") and request.headers["origin"] not in origins:
            response = JSONResponse({"error": "OpenFitKit accepts requests from its own page only."}, status_code=403)
        elif request.url.path.startswith("/api/") and not secrets.compare_digest(
            request.headers.get("x-openfitkit-token", "").encode(), token.encode()
        ):
            response = JSONResponse({"error": "Reload OpenFitKit in your local browser and try again."}, status_code=403)
        else:
            response = None
            if request.url.path.startswith("/api/"):
                try:
                    content_length = int(request.headers.get("content-length", "0"))
                    if content_length < 0:
                        raise ValueError
                except ValueError:
                    response = JSONResponse({"error": "Invalid request length."}, status_code=400)
                else:
                    if content_length > MAX_BODY_BYTES:
                        response = JSONResponse({"error": "The request is too large."}, status_code=413)
                    else:
                        # Count actual bytes as well: chunked clients need not send Content-Length.
                        body = bytearray()
                        async for chunk in request.stream():
                            if len(body) + len(chunk) > MAX_BODY_BYTES:
                                response = JSONResponse({"error": "The request is too large."}, status_code=413)
                                break
                            body.extend(chunk)
                        if response is None:
                            request._body = bytes(body)
            if response is None:
                try:
                    response = await call_next(request)
                except Exception:
                    response = JSONResponse({"error": "OpenFitKit could not complete this action."}, status_code=500)
        response.headers.update({
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                "img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            ),
        })
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error):
        # FastAPI's default includes the raw submitted input, which may be private.
        return JSONResponse({"error": "Check the request fields and try again."}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(_request, error):
        message = "Another action is in progress. Try again when it finishes." if error.status_code == 409 else "That page or action is unavailable."
        return JSONResponse({"error": message}, status_code=error.status_code)

    @app.exception_handler(ProviderError)
    async def provider_error(_request, error):
        return JSONResponse({"error": str(error)}, status_code=502)

    @app.exception_handler(ServiceError)
    @app.exception_handler(StoreError)
    async def service_error(_request, error):
        return JSONResponse({"error": str(error)}, status_code=400)

    @app.exception_handler(Exception)
    async def unexpected_error(_request, _error):
        return JSONResponse({"error": "OpenFitKit could not complete this action."}, status_code=500)

    @contextmanager
    def available_service():
        # One generation or mutation at a time: never charge for duplicate overlapping sends.
        if not service.lock.acquire(blocking=False):
            raise HTTPException(status_code=409)
        try:
            yield
        finally:
            service.lock.release()

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse((STATIC_DIR / "index.html").read_text().replace("{{CSRF_TOKEN}}", token))

    @app.get("/app.js")
    def script():
        return FileResponse(STATIC_DIR / "app.js", media_type="text/javascript")

    @app.get("/styles.css")
    def styles():
        return FileResponse(STATIC_DIR / "styles.css", media_type="text/css")

    @app.get("/api/state")
    def state():
        with available_service():
            provider_state = settings.public()
            provider_state.update({
                "provider": service.provider.name,
                "model": service.provider.model,
                "demo": bool(getattr(service.provider, "demo", service.provider.name == "demo")),
            })
            if provider is not None:
                provider_state["configured"] = True
            return {
                "name": "OpenFitKit", "version": __version__,
                "provider": provider_state, **service.state(),
            }

    @app.get("/api/conversations/{conversation_id}")
    def conversation(conversation_id: str):
        with available_service():
            return service.conversation(conversation_id)

    @app.post("/api/chat")
    def chat(request: ChatRequest):
        with available_service():
            return service.reply(request)

    @app.put("/api/profile")
    def profile(request: Profile):
        with available_service():
            return {"profile": service.store.save_profile(request).model_dump()}

    @app.post("/api/memory/reset")
    def reset(request: ResetRequest):
        with available_service():
            service.reset(request.scope)
            return {"cleared": request.scope}

    return app
