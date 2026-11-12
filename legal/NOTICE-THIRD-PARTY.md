# Third-party Content

dittoctl is distributed as a Python package without bundled dependencies: the packages below are installed
from PyPI next to it. Versions are the ones dittoctl is currently tested with; `pyproject.toml` declares the
accepted ranges of the direct dependencies.

## click (8.5.0)

* PyPI: `click==8.5.0`
* License: [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html)
* Project: https://palletsprojects.com/p/click/
* Sources: https://github.com/pallets/click

## httpx (0.28.1)

* PyPI: `httpx==0.28.1`
* License: [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html)
* Project: https://www.python-httpx.org/
* Sources: https://github.com/encode/httpx

## httpcore (1.0.9)

* PyPI: `httpcore==1.0.9`
* License: [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html)
* Project: https://www.encode.io/httpcore/
* Sources: https://github.com/encode/httpcore

## h11 (0.16.0)

* PyPI: `h11==0.16.0`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Sources: https://github.com/python-hyper/h11

## anyio (4.16.0)

* PyPI: `anyio==4.16.0`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Project: https://anyio.readthedocs.io/
* Sources: https://github.com/agronholm/anyio

## idna (3.20)

* PyPI: `idna==3.20`
* License: [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html)
* Sources: https://github.com/kjd/idna

## certifi (2026.10.23)

* PyPI: `certifi==2026.10.23`
* License: [MPL-2.0](https://spdx.org/licenses/MPL-2.0.html)
* Sources: https://github.com/certifi/python-certifi

## keyring (25.7.0)

* PyPI: `keyring==25.7.0`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Sources: https://github.com/jaraco/keyring

## jaraco.classes (3.4.0)

* PyPI: `jaraco.classes==3.4.0`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Sources: https://github.com/jaraco/jaraco.classes

## jaraco.context (6.1.2)

* PyPI: `jaraco.context==6.1.2`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Sources: https://github.com/jaraco/jaraco.context

## jaraco.functools (4.6.0)

* PyPI: `jaraco.functools==4.6.0`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Sources: https://github.com/jaraco/jaraco.functools

## more-itertools (11.2.1)

* PyPI: `more-itertools==11.2.1`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Sources: https://github.com/more-itertools/more-itertools

## rich (15.0.0)

* PyPI: `rich==15.0.0`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Project: https://rich.readthedocs.io/
* Sources: https://github.com/Textualize/rich

## markdown-it-py (4.2.0)

* PyPI: `markdown-it-py==4.2.0`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Sources: https://github.com/executablebooks/markdown-it-py

## mdurl (0.1.2)

* PyPI: `mdurl==0.1.2`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Sources: https://github.com/executablebooks/mdurl

## Pygments (2.21.0)

* PyPI: `Pygments==2.21.0`
* License: [BSD-2-Clause](https://spdx.org/licenses/BSD-2-Clause.html)
* Project: https://pygments.org/
* Sources: https://github.com/pygments/pygments

## tomli-w (1.2.0)

* PyPI: `tomli-w==1.2.0`
* License: [MIT](https://spdx.org/licenses/MIT.html)
* Sources: https://github.com/hukkin/tomli-w

# Platform-specific dependencies

Installed only on some platforms or Python versions; versions are resolved at install time.

## Linux: SecretStorage, jeepney, cryptography, cffi, pycparser (keyring backend)

* SecretStorage: [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html), https://github.com/mitya57/secretstorage
* jeepney: [MIT](https://spdx.org/licenses/MIT.html), https://gitlab.com/takluyver/jeepney
* cryptography: [Apache-2.0](https://spdx.org/licenses/Apache-2.0.html) OR [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html), https://github.com/pyca/cryptography
* cffi: [MIT](https://spdx.org/licenses/MIT.html), https://github.com/python-cffi/cffi
* pycparser: [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html), https://github.com/eliben/pycparser

## Windows: pywin32-ctypes (keyring backend)

* License: [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html)
* Sources: https://github.com/enthought/pywin32-ctypes

## Python < 3.12: importlib-metadata, zipp (keyring)

* importlib-metadata: [Apache-2.0](https://spdx.org/licenses/Apache-2.0.html), https://github.com/python/importlib_metadata
* zipp: [MIT](https://spdx.org/licenses/MIT.html), https://github.com/jaraco/zipp

## Python < 3.13: typing-extensions (anyio)

* License: [PSF-2.0](https://spdx.org/licenses/PSF-2.0.html)
* Sources: https://github.com/python/typing_extensions
