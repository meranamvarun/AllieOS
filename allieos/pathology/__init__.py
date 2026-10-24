"""Local-first anatomic pathology workflow service.

This package manages clinical workflow metadata and report revisions. Whole-slide
pixels remain in an external image archive and are referenced by DICOM UIDs.
"""

from .store import PathologyError, PathologyStore

__all__ = ["PathologyError", "PathologyStore"]
