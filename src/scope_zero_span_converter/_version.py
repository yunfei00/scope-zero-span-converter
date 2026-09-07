"""Single source of truth for the application version.

On the main branch this is the next development version. The release workflow
replaces this value with the pushed Git tag before packaging, so the EXE,
package metadata and exported conversion metadata all report the same version.
"""

__version__ = "0.8.0.dev0"
