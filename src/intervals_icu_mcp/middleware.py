"""Middleware for Intervals.icu MCP server.

This module provides middleware components that run before tool execution.
"""

from collections.abc import Callable
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers, get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext

from .auth import apply_header_credentials, load_config, validate_credentials


def get_http_query_params() -> dict[str, str]:
    """Return the current request's query params, or ``{}`` when there is none.

    Mirrors ``get_http_headers()``: safe to call on non-HTTP transports (e.g.
    stdio), where ``get_http_request()`` raises ``RuntimeError`` and we return an
    empty dict so the env-var path is preserved.
    """
    try:
        return dict(get_http_request().query_params)
    except RuntimeError:
        return {}


class ConfigMiddleware(Middleware):
    """Middleware that loads and validates Intervals.icu configuration for all tool calls.

    This middleware:
    1. Loads the ICU config from environment variables
    2. Overrides credentials from per-request query params / HTTP headers (multi-tenant)
    3. Validates that credentials are properly configured
    4. Injects the config into the context state for tools to access via ctx.get_state("config")
    5. Raises ToolError if authentication is not configured
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next: Callable[..., Any]):
        """Resolve and validate config before every tool call.

        Credentials are resolved per request, priority: query params
        (``api_key`` / ``athlete_id``) > headers (``X-Intervals-Api-Key`` /
        ``X-Intervals-Athlete-Id``) > env vars. The header / query-param accessors
        return empty for non-HTTP transports (e.g. stdio), so the env-var path is
        preserved unchanged.
        """
        # Load env config, then apply per-request query-param / header overrides
        config = apply_header_credentials(
            load_config(), get_http_headers(), get_http_query_params()
        )

        # Validate credentials are properly configured
        if not validate_credentials(config):
            raise ToolError(
                "Intervals.icu credentials not configured. Provide credentials via "
                "the api_key / athlete_id query params, the X-Intervals-Api-Key / "
                "X-Intervals-Athlete-Id headers, or run 'icu-mcp-auth' to set up "
                "environment credentials."
            )

        # Inject config into context state for tools to access
        if context.fastmcp_context:
            await context.fastmcp_context.set_state("config", config, serializable=False)

        # Continue to the tool execution
        return await call_next(context)
