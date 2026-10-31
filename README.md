# Adventure workbench

Extract the complete ZIP to a writable folder on a Windows x64 computer. Double-click **SETUP.cmd** once using your normal account. The supplied Python and Pillow files work offline; you do not need to install Python or configure PowerShell. Wait for the window check and successful setup message.

Then double-click **START.cmd**, or open **main.py** in your IDE and use Run with no arguments. Select this project's `.venv\Scripts\python.exe` interpreter if your IDE asks.

On Linux, use the project-local interpreter instead. Create the environment with Python 3.12 (with tkinter) and install the runtime wheel, then launch through the added Linux entry point:

```bash
python3.12 -m venv .venv
.venv/bin/pip install pillow==12.3.0
./start.sh
```

Or run the GUI directly with `.venv/bin/python -X utf8 -B run_linux.py`.

On macOS, the same procedure applies: create the environment with Python 3.12 (with tkinter), install Pillow, then run `./start.sh` or `.venv/bin/python -X utf8 -B run_linux.py`.

Start learning with the [seven-case guide](GUIDE.html). A [Markdown copy](GUIDE.md) and the separate [API reference](docs/guide/api-reference.html) are included. The workbench's **Help** opens the guide and the actual rules for your selected scenario.

Choose **Straight path**, then **Run solution**. An unfinished-code message is expected: all six student components start as TODOs. **Watch example** shows a supplied recording; it does not complete or replace your code. Save edits before using **Run again**.

See [Setup and repair](SETUP.md) for moving the project and support. Keep your work in `src/student` and retain the complete project folder, including `.setup-payload`, its art and public examples. Saved attempts are managed automatically in `practice`.

This is a private DEVELOPMENT practice package. Its points are practice feedback, not a course grade. Classroom release and art redistribution are not approved.
