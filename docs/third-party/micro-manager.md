# Micro-Manager provenance and lifecycle

Micro-Manager is preinstalled in the AllieOS live ISO and is installed by the optional `pathology-lab` profile on an existing Ubuntu system. Upstream does not publish a Linux binary, so AllieOS builds it from source inside the live-image chroot.

| Field | Value |
| --- | --- |
| Upstream | `https://github.com/micro-manager/micro-manager` |
| Version | 2.0.3 |
| Git revision | `bba80619603cf8974a0666c06c60ec68111d14b2` |
| Third-party SVN revision | 227 (the revision declared by the pinned Git source) |
| UI license | BSD-style |
| MMCore license | LGPL |
| Installer | `scripts/install-micromanager.sh` |
| Update owner | AllieOS maintainers |

The installer also builds SWIG 3.0.12 from its HTTPS source archive after checking SHA-256 `5d9f84a99bd4593be487c94301c44c5070a5bc66fa448f965d31103d6f5b5294`. The Micro-Manager Git checkout and its submodules are pinned by commit, and the external class library is pinned by SVN revision.

The application is installed version-by-version under `/opt/micro-manager`, with `/usr/local/bin/micromanager` pointing to the selected version and a desktop entry in `/usr/local/share/applications`. It is not sandboxed because microscope and camera control requires direct hardware access. Only users authorized to operate the attached instrument should receive the necessary device permissions.

To remove this version, remove `/usr/local/bin/micromanager` if it points to the directory above, remove `/usr/local/share/applications/org.micro-manager.MicroManager.desktop`, then remove `/opt/micro-manager/2.0.3-bba80619603c`. Build dependencies are intentionally left installed because APT cannot safely determine whether another development workflow needs them.

Micro-Manager and hardware-specific drivers must be validated with the exact microscope configuration before use. It is not approved for diagnostic use merely by being included in AllieOS.
