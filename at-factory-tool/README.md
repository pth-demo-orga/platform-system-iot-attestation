# Android Things Factory Tool (ATFT)

--------------------------------------------------------------------------------

This repository contains codes for Android Things Factory Tool.

# What is it?

The Google Android Things Factory Tool (ATFT) helps factory partners with key
provisioning and security related operations. It provides a user interface to
issue commands between a product device and an Android Things Factory Appliance
(ATFA). For detail please refer to [user
guide](https://support.google.com/androidpartners_things/answer/9023873?hl=en&ref_topic=7394193).

# How to Run

If you already have a prebuilt version of the tool.

## Windows

1.  Download Microsoft Visual C++ Compiler for Python 2.7 from [this link]
(https://www.microsoft.com/en-us/download/details.aspx?id=44266).

1.  Install the Microsoft Visual C++ Compiler for Python 2.7 following the
instruction on the link.

1.  Execute the exe file 'atft.exe' under 'AThings-Factory-Tool' folder.

## Linux

1.  Execute the file 'atft' under 'AThings-Factory-Tool' folder. Run:

    `cd AThings-Factory-Tool; ./atft`

# How to Build and Run From Source Code

## Windows

1.  Make sure you have python 2.7 installed. (The tool is not compatible with
    python 3.0)

1.  Install the following python packages:

    *   wxPython 4.0.0 or above
    *   passlib 1.7.1

1.  Checkout this git repo to a temporary directory.

1.  Create a working folder named 'AThings-Factory-Tool'

1.  Copy the whole 'repo/at-factory-tool' folder to the 'AThings-Factory-Tool'
    directory.

1.  Copy the license files to the 'AThings-Factory-Tool' directory:

    *   repo/NOTICE
    *   repo/MODULE\_LICENSE\_APACHE2
    *   repo/LICENSE

1.  Goto the 'AThings-Factory-Tool/at-factory-tool' folder.

1.  Create a text file called GIT\_COMMIT, fill its content with the git commit
    number to keep track of which commit you checked out.

    You could use the following command to get the commit number, run under the
    checked out repo directory: `git log`

1.  Edit 'config.json' using your text editor. (Notepad would not show the
    format correctly, use sublime or notepad++ or other advanced text editors
    instead)

    Change the value for "LOG\_DIR" to a directory to store the log file.
    This default needs to be changed because '/tmp/atfa\_log' does not exist
    on Windows.

    Change the value for "AUDIT\_DIR" to a directory to store the audit file.
    This default needs to be changed because '/tmp/atfa\_audit' does not exist
    on Windows.

1.  Open a command line, run

    `python atft.py`

    Make sure the program runs without error.

1.  If you want to create a bundled executable file that includes all the
    dependencies, make sure you have python package **PyInstaller** installed.

    You could use the following command:

    `pip install pyinstaller`

    to install.

1.  In a command line window, run

    `cd [the AThings-Factory-Tool/at-factory-tool folder]`

    `pyinstaller --noconsole atft.py`

    This would create a folder containing all the dependencies and the
    executable file. The '--noconsole' tells the bundled binary not showing a
    command line window, so if you want to print out any debug message in you
    own modification, you could remove this flag.

    The built binary is under folder
    'AThings-Factory-Tool/at-factory-tool/dist/atft'

1.  Copy everything from 'AThings-Factory-Tool/at-factory-tool/dist/atft/*' to
    'AThings-Factory-Tool/'

1.  Delete folder 'AThings-Factory-Tool/at-factory-tool/dist' and
    'AThings-Factory-Tool/at-factory-tool/build'

1.  Copy all the following files from folder
    'AThings-Factory-Tool/at-factory-tool/' to 'AThings-Factory-Tool/'

    *   All image files (*.png)
    *   config.json
    *   NOTICE
    *   MODULE\_LICENSE\_APACHE2
    *   README.md (if exists)
    *   fastboot.exe
    *   AdbWinApi.dll
    *   AdbWinUsbApi.dll
    *   operation\_start\_p256.bin
    *   operation\_start\_x25519.bin

1.  Now just copy the 'AThings-Factory-Tool' folder to the workstation you want
    to use it. To use the tool, execute the exe file 'atft.exe' under
    'AThings-Factory-Tool' folder.

## Linux

1.  Make sure you have python 2.7 installed. (The tool is not compatible with
    python 3.0)

1.  Install the following python packages:

    *   wxPython 4.0.0 or above
    *   passlib 1.7.1
    *   sh

1.  Checkout this git repo to a temporary directory.

1.  Create a working folder named 'AThings-Factory-Tool'

1.  Copy the whole 'repo/at-factory-tool' folder to the 'AThings-Factory-Tool'
    directory.

1.  Copy the license files to the 'AThings-Factory-Tool' directory:

    *   repo/NOTICE
    *   repo/MODULE\_LICENSE\_APACHE2
    *   repo/LICENSE

1.  Goto the 'AThings-Factory-Tool/at-factory-tool' folder.

1.  Create a text file called GIT_COMMIT, fill its content with the git commit
    number to keep track of which commit you checked out.

1.  Open a command line, run

    `python atft.py`

    Make sure the program runs without error.

1.  If you want to create a bundled executable file that includes all the
    dependencies, make sure you have python package **PyInstaller** installed.

    You could use the following command:

    `pip install pyinstaller`

    to install.

1.  In a command line window, run

    `cd [the AThings-Factory-Tool/at-factory-tool folder]`

    `pyinstaller --noconsole atft.py`

    This would create a folder containing all the dependencies and the
    executable file. The '--noconsole' tells the bundled binary not showing a
    command line window, so if you want to print out any debug message in you
    own modification, you could remove this flag.

    The built binary is under folder
    'AThings-Factory-Tool/at-factory-tool/dist/atft'

1.  Copy everything from 'AThings-Factory-Tool/at-factory-tool/dist/atft/*' to
    'AThings-Factory-Tool/'

1.  Delete folder 'AThings-Factory-Tool/at-factory-tool/dist' and
    'AThings-Factory-Tool/at-factory-tool/build'

1.  Copy all the following files from folder
    'AThings-Factory-Tool/at-factory-tool/' to 'AThings-Factory-Tool/'

    *   All image files (*.png)
    *   config.json
    *   NOTICE
    *   MODULE\_LICENSE\_APACHE2
    *   README.md (if exists)
    *   fastboot
    *   operation\_start\_p256.bin
    *   operation\_start\_x25519.bin

1.  Now just copy the 'AThings-Factory-Tool' folder to the workstation you want
    to use it. To use the tool, execute the file 'atft' under
    'AThings-Factory-Tool' folder. Run:

    `cd AThings-Factory-Tool; ./atft`
