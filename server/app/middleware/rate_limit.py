import time
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging

from app.core.valkey import valkey_client

logger = logging.getLogger(__name__)

# Max requests per minute per IP
RATE_LIMIT = 60
# Window size in seconds
WINDOW_SIZE = 60

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow requests to pass through if Valkey is not configured or offline
        if not valkey_client:
            return await call_next(request)

        # Skip rate limiting for non-API routes if desired, but we'll apply it everywhere for now.
        if request.url.path.startswith("/docs") or request.url.path.startswith("/openapi"):
            return await call_next(request)

        # Get client IP
        client_ip = request.client.host if request.client else "127.0.0.1"
        
        # We use a fixed window strategy: key is tied to the current minute
        current_minute = int(time.time() // WINDOW_SIZE)
        key = f"rate_limit:{client_ip}:{current_minute}"

        try:
            # Use pipeline to increment and set expire atomically
            async with valkey_client.pipeline(transaction=True) as pipe:
                await pipe.incr(key)
                await pipe.expire(key, WINDOW_SIZE)
                results = await pipe.execute()
                
            request_count = results[0]

            if request_count > RATE_LIMIT:
                logger.warning(f"Rate limit exceeded for IP {client_ip}")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many requests. Please try again later."}
                )
        except Exception as e:
            # If Valkey throws an error, fail open (allow the request) rather than breaking the API
            logger.error(f"Rate limit check failed: {e}")

        # Continue processing the request
        return await call_next(request)
