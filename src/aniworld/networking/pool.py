"""
HTTP connection pooling and session factory.

Provides optimized HTTP/HTTPS adapters with connection pooling
for efficient connection reuse across the application.
"""

from niquests import Session
from niquests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Global pool configuration constants
DEFAULT_POOL_CONNECTIONS = 10  # Number of connection pools to cache
DEFAULT_POOL_MAXSIZE = 20      # Maximum connections per pool
DEFAULT_MAX_RETRIES = 0        # Retries handled at application level
DEFAULT_TIMEOUT = 30           # Default request timeout in seconds


def get_retry_strategy(
    retries: int = 3,
    backoff_factor: float = 0.3,
    status_forcelist: list = None,
) -> Retry:
    """
    Create a urllib3 Retry strategy for automatic request retries.

    Args:
        retries: Maximum number of retries
        backoff_factor: Backoff factor for exponential delay (e.g., 0.3 = 0.3s, 0.6s, 1.2s)
        status_forcelist: HTTP status codes to retry on (default: 429, 500, 502, 503, 504)

    Returns:
        Retry: Configured retry strategy
    """
    if status_forcelist is None:
        status_forcelist = [429, 500, 502, 503, 504]

    return Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
    )


def get_http_adapter(
    pool_connections: int = DEFAULT_POOL_CONNECTIONS,
    pool_maxsize: int = DEFAULT_POOL_MAXSIZE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_strategy: Retry = None,
) -> HTTPAdapter:
    """
    Create an optimized HTTP adapter with connection pooling.

    Args:
        pool_connections: Number of connection pools to cache (default: 10)
        pool_maxsize: Maximum connections to keep in each pool (default: 20)
        max_retries: Maximum retries for failed connections (default: 0)
        retry_strategy: Optional urllib3 Retry strategy object

    Returns:
        HTTPAdapter: Configured adapter with pooling enabled
    """
    # Use provided retry strategy or fall back to max_retries parameter
    if retry_strategy is not None:
        return HTTPAdapter(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            max_retries=retry_strategy,
        )
    
    return HTTPAdapter(
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        max_retries=max_retries,
    )


def create_pooled_session(
    base_headers: dict = None,
    resolver: list = None,
    pool_connections: int = DEFAULT_POOL_CONNECTIONS,
    pool_maxsize: int = DEFAULT_POOL_MAXSIZE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_strategy: Retry = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Session:
    """
    Create a niquests Session with optimized HTTP connection pooling.

    Connection pooling reuses TCP connections across requests to the same host,
    reducing handshake overhead and improving throughput.

    Args:
        base_headers: Optional dict of headers to set on the session
        resolver: Optional list of DNS resolvers (e.g., ["doh+google://"])
        pool_connections: Number of connection pools to cache (default: 10)
        pool_maxsize: Maximum connections per pool (default: 20)
        max_retries: Maximum retries for connections (default: 0)
        retry_strategy: Optional urllib3 Retry strategy object for advanced retry config
        timeout: Default timeout for all requests in seconds (default: 30)

    Returns:
        Session: A niquests Session with pooling configured for HTTP/HTTPS

    Example:
        >>> session = create_pooled_session(
        ...     base_headers={"User-Agent": "MyApp/1.0"},
        ...     resolver=["doh+google://"],
        ...     pool_maxsize=30
        ... )
        >>> response = session.get("https://api.example.com/data")
    """
    # Create session with optional resolver
    kwargs = {}
    if resolver:
        kwargs["resolver"] = resolver
    if base_headers:
        kwargs["headers"] = base_headers

    session = Session(**kwargs)

    # Create adapter with specified pool settings and retry strategy
    adapter = get_http_adapter(
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        max_retries=max_retries,
        retry_strategy=retry_strategy,
    )

    # Mount adapter for both HTTP and HTTPS
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Set default timeout for the session
    if timeout:
        session.timeout = timeout

    return session
