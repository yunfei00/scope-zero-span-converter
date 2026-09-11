# Third-party notices

Scope Zero Span Converter uses third-party software. This document records the
release build inputs and upstream license information; it is not a legal opinion
or a declaration that organizational compliance review is complete.

项目采用的第三方依赖及许可证说明，正式商业分发前应根据组织的法律/合规要求复核。
Application licensing is separate; this document does not assign an open-source
license to Scope Zero Span Converter itself.

## Release dependencies

Versions below match `packaging/requirements-windows.txt`. The build also collects
the actual installed distribution metadata and original license/notice files into
`_internal/licenses/`, including bundled numerical libraries and font notices.
`dependency-inventory.json` records all build-environment distributions; that list
is broader than the set of runtime modules selected by PyInstaller.

| Component | Release input | License / source |
|---|---|---|
| Python | 3.11.15 | Python Software Foundation License; runtime `LICENSE.txt` included |
| PySide6 / Shiboken / Qt | 6.9.3 | Wheel metadata: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; commercial licensing is a separate option. [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html) |
| NumPy | 2.4.6 | BSD-3-Clause; this wheel's aggregate expression also includes 0BSD, MIT, Zlib, CC0-1.0. Preserve all bundled-library notices. [NumPy license](https://numpy.org/doc/stable/license.html) |
| pandas | 3.0.3 | BSD 3-Clause, as recorded in the installed wheel metadata. [Upstream license](https://github.com/pandas-dev/pandas/blob/v3.0.3/LICENSE) |
| Matplotlib | 3.11.0 | Matplotlib's PSF-style license plus bundled component/font licenses. [License text](https://matplotlib.org/stable/project/license.html) |
| PyInstaller | 6.21.0 | GPLv2-or-later with the distribution exception; selected files Apache-2.0. The exception permits proprietary bundles subject to dependency licenses. [PyInstaller license](https://pyinstaller.org/en/stable/license.html) |
| Inno Setup | 6.4.3 | Inno Setup License; upstream copyright notices are retained. [Versioned license](https://github.com/jrsoftware/issrc/blob/is-6_4_3/license.txt) |

Transitive dependencies (including Pillow, contourpy, fonttools, python-dateutil,
tzdata, packaging, and build hooks) are locked and represented in the generated
inventory. Original upstream texts, not this summary, control their terms.
Windows system fonts such as Microsoft YaHei are used if present and are not
copied from the build machine into the product.

## Qt / LGPL distribution considerations

The package uses dynamically loaded Qt libraries in the PyInstaller onedir layout;
it does not statically link Qt. This layout keeps DLLs available for replacement.
The LGPL and its referenced GPLv3 text are included, fetched from versioned Qt
sources with checked SHA256 hashes (some PySide6 wheels only ship a commercial
license-reference file).

The owner must review the exact Qt modules and plugins shipped, preserve notices,
provide the corresponding library source or a compliant source offer, and ensure
users can replace/relink and run modified LGPL libraries. Any EULA must preserve
applicable reverse-engineering rights for debugging such modifications. Selecting
onedir alone does not establish compliance. See [Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations).

Matching source locations: [Qt 6.9.3 archives](https://download.qt.io/archive/qt/6.9/6.9.3/),
[PySide/Shiboken 6.9.3 source](https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.9.3).
These references identify upstream source; the distributor must decide and maintain
the appropriate source-delivery/offer mechanism before commercial distribution.

The original icon is generated in-repository by `assets/generate_icon.py`; no
third-party artwork or trademarks are used.
