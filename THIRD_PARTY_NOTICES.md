# Third-party notices — internal DEVELOPMENT candidate

The complete supplied runtime tree and Pillow wheel retain every upstream byte and embedded notice. No Python, Tcl/Tk, DLL, pip, vendor or wheel member was modified or removed. The artifact identities are in `runtime-lock.json`; the full extracted-file mapping is in `.setup-payload/manifest.json`. `THIRD_PARTY_PROVENANCE.json` lists notice source URLs, sizes and hashes. This inventory is technical evidence; institutional, classroom and art redistribution approvals remain pending.

## Runtime and dependency notices

Python's combined notice is retained at `.setup-payload/python/LICENSE.txt` and copied under `licenses`. It includes the PSF/history notices and incorporated-component terms, including the Microsoft VC runtime conditions. Tcl/Tk and Tix supplemental notices, Tk's supplied `license.terms`, bzip2, libffi, liblzma, zlib, OpenSSL 3, exact-version Expat, SQLite provenance, CPython's bundled libmpdec and HACL notices are included under `licenses` where the install-only artifact omits the supplemental notice directory.

The CPython 3.12 build uses bundled libmpdec 2.5.1; the unrelated libmpdec 4 build-tool pin is not claimed as its binary version. Pip 26.2.1 and its complete vendor notice tree remain in the exact runtime. The unchanged ensurepip wheel supplies pip 25.0.1 to the local environment. Its older vendor notices are mapped in THIRD_PARTY_PROVENANCE.json; identical notices reuse the retained pip 26 tree, while the differing idna and urllib3 notices and typing_extensions notice are supplied under licenses/pip25-vendor. Pillow's combined 12.3.0 license is retained inside the supplied wheel and copied under `licenses/Pillow-12.3.0-LICENSE`.

Pillow and its native libraries include work from the FreeType Project, the Independent JPEG Group and libjpeg-turbo contributors. FreeType credit: portions of this software are copyright by The FreeType Project (www.freetype.org), all rights reserved. JPEG credit: this software is based in part on the work of the Independent JPEG Group. TIFF credit: this software includes material copyright by the University of California, Berkeley and its contributors. Complete copyright, attribution and conditions remain in the combined Pillow notice, including the TIFF disclaimer and other native dependency notices.

The included Astral build-tooling MPL 2.0 notice describes the standalone project's build tooling; it is not presented as the license of every runtime binary. No endorsement by Astral, Python, Microsoft or dependency authors is implied. No bundled runtime source was changed.

## Project material

Adventure artwork, public course code, guide and student placeholders preserve the previous package bytes. Practice points are not certified grades. This candidate is not approved for classroom release, external sharing, grading conversion or art redistribution.
