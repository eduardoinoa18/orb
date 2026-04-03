"""ORB 'platform' package.

Important compatibility note:
This repository keeps a local package named `platform` to match the build
prompt. Python also has a standard-library module named `platform`.

To reduce breakage for third-party libraries that do `import platform`, this
package re-exports symbols from stdlib `platform.py` while still exposing the
local `platform.api` and `platform.database` subpackages.
"""

from __future__ import annotations

import importlib.util
import sysconfig
from pathlib import Path


_stdlib_platform = Path(sysconfig.get_path("stdlib")) / "platform.py"
if _stdlib_platform.exists():
	spec = importlib.util.spec_from_file_location("_orb_stdlib_platform", str(_stdlib_platform))
	if spec and spec.loader:
		_module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(_module)
		for _name in dir(_module):
			if _name in {"__name__", "__loader__", "__package__", "__spec__", "__file__"}:
				continue
			globals().setdefault(_name, getattr(_module, _name))

