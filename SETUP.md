# Setup and repair

## First setup

1. Extract the complete ZIP into an ordinary writable folder on Windows x64. Do not run files inside the ZIP viewer. Keep the supplied `.setup-payload` folder with the project.
2. Double-click **SETUP.cmd** using your normal account. It checks the supplied files, prepares the project's environment, and opens a short graphical window check.
3. Wait for **Setup complete**. Failed or interrupted setup is not ready to launch. Press a key to close the setup console.
4. Double-click **START.cmd** to open the workbench. Alternatively, open the extracted folder in PyCharm or VS Code, choose `.venv\Scripts\python.exe`, open **main.py**, and press Run with no arguments.

You do not need internet, an installed Python, a PowerShell setting, administrator privileges, scenario commands, or an output-folder selection. Real IDE Run-button and separate clean-machine acceptance remain untested for this DEVELOPMENT candidate; the interpreter configuration above is the intended route.

## Supplied environment

This candidate contains the exact pinned Astral CPython **3.12.14** runtime for Windows x64 with **Tk 8.6**, plus the local **Pillow 12.3.0** wheel. Setup always checks every supplied runtime and wheel file, including on repeat runs, and installs the wheel without a package index. `runtime-lock.json` records the publisher artifact identities. [Third-party notices](THIRD_PARTY_NOTICES.md) and `THIRD_PARTY_PROVENANCE.json` preserve notice coverage and source hashes. Local hashes check consistency; they are not a publisher signature.

The runtime is supplied as runnable files under `.setup-payload/python`. Setup builds an owned `.venv` on your computer, with its records and verified wheel cache under `.setup`. It leaves global Python installations, packages, PATH, security policy and editor configuration alone. Setup and the workbench accept both standard and administrator Windows sessions; administrator privileges are not required.

The old `setup_windows.ps1` is retained unchanged solely for compatibility with historical workbench source identities. SETUP.cmd, START.cmd and main.py do not call it. Use SETUP.cmd for this offline package.

## Retry, move and repair

Close the workbench before setup or repair. Keep the entire project together. After moving it, rerun **SETUP.cmd** at its new location: the environment is tied to a location and setup repairs only environments it owns. Student files and saved `practice` history stay in place. Setup refuses to replace an unidentified `.venv` or a linked environment folder; ask your instructor to check it.

For missing or damaged supplied files, obtain and extract the complete original ZIP again. Keep a copy of your edited `src/student` files and saved `practice` folder when replacing setup files. There is no download fallback. If the folder is read-only, extract into a writable ordinary folder. If setup is interrupted, close it and retry. A failed Pillow or graphical check withholds readiness.

If Windows or institutional policy blocks the supplied `.cmd` or interpreter, ask your institution's IT team for approval. Keep its security policy in place. Setup does not change execution policy, disable protection or add exclusions. The Help menu offers **Setup & repair** and **Support details**; diagnostic export is an explicit action.

## Verification limits

The acceptance report distinguishes genuine current-host Windows checks from unavailable lanes. This package is internal DEVELOPMENT only. Its first-use journey on a separate clean offline Windows computer and native PyCharm/VS Code Run-button interaction still require genuine destination-machine acceptance. Administrator-session refusal is no longer part of the workbench policy.

The local environment uses exact native interpreter and support DLL copies from the verified bundle. This keeps worker process identity stable on Windows. Setup repairs only its owned environment; launch verifies these copies and asks for setup if they changed.
