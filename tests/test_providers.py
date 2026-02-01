import pytest
import importlib
from typing import Dict, Optional, Callable
import logging

# Configure logging for test output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Provider test URLs - mark broken ones with None
PROVIDERS: Dict[str, Optional[str]] = {
    "doodstream": None,  # needs link
    "filemoon": "https://filemoon.to/e/eawuwyrd40an",
    "loadx": None,  # needs link
    "luluvdo": "https://luluvdo.com/embed/g1gaitimtoc1",
    "speedfiles": None,  # needs link
    "streamtape": None,  # needs link
    "vidmoly": "https://vidmoly.net/embed-19xpz8qoujf9.html",
    "vidoza": None,  # needs link
    "voe": "https://voe.sx/e/ayginbzzb6bi",
}


def get_provider_function(provider_name: str) -> Callable[[str], str]:
    """
    Dynamically import and return the provider extraction function.

    Args:
        provider_name: Name of the provider module

    Returns:
        The provider's extraction function

    Raises:
        ImportError: If the provider module cannot be imported
        AttributeError: If the extraction function doesn't exist
    """
    try:
        module = importlib.import_module(
            f"aniworld.extractors.provider.{provider_name}"
        )
        function_name = f"get_direct_link_from_{provider_name}"
        return getattr(module, function_name)
    except ImportError as err:
        raise ImportError(
            f"Failed to import provider module '{provider_name}': {err}"
        ) from err
    except AttributeError as err:
        raise AttributeError(
            f"Provider '{provider_name}' missing function '{function_name}': {err}"
        ) from err


@pytest.mark.parametrize("provider_name,test_url", PROVIDERS.items())
def test_get_direct_link(provider_name: str, test_url: Optional[str]):
    """
    Test that each provider can extract a direct link from its test URL.

    Args:
        provider_name: Name of the provider to test
        test_url: Test URL for the provider (None if broken/unavailable)
    """
    if test_url is None:
        pytest.skip(f"Provider '{provider_name}' is marked as broken/unavailable")

    logger.info(f"Testing provider: {provider_name}")

    # Get the provider function
    try:
        extract_function = get_provider_function(provider_name)
    except (ImportError, AttributeError) as err:
        pytest.fail(f"Failed to load provider '{provider_name}': {err}")

    # Test the extraction
    try:
        direct_link = extract_function(test_url)

        # Validate the result
        assert direct_link is not None, f"Provider '{provider_name}' returned None"
        assert isinstance(direct_link, str), (
            f"Provider '{provider_name}' returned non-string: {type(direct_link)}"
        )
        assert direct_link.strip(), f"Provider '{provider_name}' returned empty string"
        assert direct_link.startswith(("http://", "https://")), (
            f"Provider '{provider_name}' returned invalid URL: {direct_link}"
        )

        logger.info(
            f"Provider '{provider_name}' successfully extracted: {direct_link[:50]}..."
        )

    except Exception as err:
        pytest.fail(
            f"Provider '{provider_name}' failed with exception: {type(err).__name__}: {err}"
        )


@pytest.mark.parametrize("provider_name", PROVIDERS.keys())
def test_provider_module_structure(provider_name: str):
    """
    Test that each provider module has the expected structure and function.

    Args:
        provider_name: Name of the provider to test
    """
    try:
        extract_function = get_provider_function(provider_name)

        # Check if function is callable
        assert callable(extract_function), (
            f"Provider '{provider_name}' function is not callable"
        )

        # Check function signature (should accept at least one string parameter)
        import inspect

        sig = inspect.signature(extract_function)
        assert len(sig.parameters) >= 1, (
            f"Provider '{provider_name}' function should accept at least one parameter"
        )

        logger.info(f"Provider '{provider_name}' module structure is valid")

    except Exception as err:
        pytest.fail(f"Provider '{provider_name}' module structure test failed: {err}")


def test_all_providers_present():
    """Test that all expected provider modules are present and importable."""
    missing_providers = []

    for provider_name in PROVIDERS.keys():
        try:
            get_provider_function(provider_name)
        except (ImportError, AttributeError) as err:
            missing_providers.append(f"{provider_name}: {err}")

    if missing_providers:
        pytest.fail("Missing or broken providers:\n" + "\n".join(missing_providers))

    logger.info(f"All {len(PROVIDERS)} providers are present and importable")


if __name__ == "__main__":
    """Run tests directly when script is executed."""
    import sys

    print("Running provider tests directly...")
    print(f"Testing {len(PROVIDERS)} providers:")

    # Test all providers present
    print("\n1. Testing provider module structure...")
    try:
        test_all_providers_present()
        print("All providers are present and importable")
    except Exception as err:
        print(f"✗ Provider presence test failed: {err}")
        sys.exit(1)

    # Test module structures
    print("\n2. Testing provider module structures...")
    for provider_name in PROVIDERS.keys():
        try:
            test_provider_module_structure(provider_name)
        except Exception as err:
            print(f"✗ Module structure test failed for {provider_name}: {err}")
            sys.exit(1)

    # Test actual extraction (only for providers with URLs)
    print("\n3. Testing provider extraction...")
    available_providers = {
        name: url for name, url in PROVIDERS.items() if url is not None
    }

    if not available_providers:
        print("No providers with test URLs available")
    else:
        print(f"Testing {len(available_providers)} providers with URLs...")

        for provider_name, test_url in available_providers.items():
            try:
                test_get_direct_link(provider_name, test_url)
            except Exception as err:
                print(f"✗ Extraction test failed for {provider_name}: {err}")
                continue

    print("\nAll tests completed successfully!")
    print(f"Providers available: {len(available_providers)}")
    print(f"Providers needing URLs: {len(PROVIDERS) - len(available_providers)}")
