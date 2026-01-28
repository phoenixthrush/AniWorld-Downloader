"""
Networking module for HTTP connection pooling and session management.

This module provides optimized session factories with connection pooling
to improve performance across all API requests in the application.
"""

from .pool import create_pooled_session, get_http_adapter, get_retry_strategy

__all__ = ["create_pooled_session", "get_http_adapter", "get_retry_strategy"]
