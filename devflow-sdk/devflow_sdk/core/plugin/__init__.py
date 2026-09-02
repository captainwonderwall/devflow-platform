import warnings
from devflow_sdk.plugin import *          # noqa: F401,F403
from devflow_sdk.plugin import __all__    # noqa: F401

warnings.warn(
    "devflow_sdk.core.plugin is deprecated; import from devflow_sdk.plugin instead.",
    DeprecationWarning,
    stacklevel=2,
)
