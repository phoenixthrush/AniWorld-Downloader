import importlib
import inspect
import pkgutil
from pathlib import Path

provider_functions = {}

provider_path = Path(__path__[0]) / "provider"

for _, module_name, _ in pkgutil.iter_modules([str(provider_path)]):
    mod = importlib.import_module(f".provider.{module_name}", __name__)
    for name, obj in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith(("get_direct_link_from_", "get_preview_image_link_from_")):
            provider_functions[name] = obj

# Example usage:
# provider_functions["get_direct_link_from_voe"](url)
