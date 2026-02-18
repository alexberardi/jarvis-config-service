"""Shared test helpers for jarvis-config-service tests."""

from unittest.mock import AsyncMock, MagicMock, patch


def mock_async_client(
    target="app.routes.service_registration.httpx.AsyncClient",
    get_response=None,
    post_response=None,
    get_side_effect=None,
    post_side_effect=None,
):
    """Create a mock httpx.AsyncClient context manager.

    Returns (patcher, mock_instance) where mock_instance has .get and .post.
    Use the target parameter to patch different modules.
    """
    mock_instance = AsyncMock()

    if get_side_effect:
        mock_instance.get.side_effect = get_side_effect
    elif get_response is not None:
        mock_instance.get.return_value = get_response

    if post_side_effect:
        mock_instance.post.side_effect = post_side_effect
    elif post_response is not None:
        mock_instance.post.return_value = post_response

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    patcher = patch(target, return_value=mock_ctx)
    return patcher, mock_instance
