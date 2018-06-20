# Android Things Factory Tool (ATFT)

--------------------------------------------------------------------------------

This repository contains codes for Android Things Factory Tool.

# What is it?

The Google Android Things Factory Tool (ATFT) helps factory partners with key
provisioning and security related operations. It provides a user interface to
issue commands between a product device and an Android Things Factory Appliance
(ATFA). For detail please refer to [user
guide](https://support.google.com/androidpartners_things/answer/9023873?hl=en&ref_topic=7394193).

# Build and Run

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

1.  Goto the 'AThings-Factory-Tool/at-factory-tool' folder.

1.  Create a text file called GIT\_COMMIT, fill its content with the git commit
    number to keep track of which commit you checked out.

    You could use the following command to get the commit number, run under the
    checked out repo directory: `git log`

1.  Edit 'config.json' using your text editor. (Notepad would not show the
    format correctly, use sublime or notepad++ or other advanced text editors
    instead)

    Change the value for "LOG\_DIR" to a directory that you want to store the
    log file. You need to change this because default value '/tmp/atft\_log'
    would not exist and could not be created on Windows.

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

# License Information

This package contains the following open source software:

*   Android Things Factory Tool 2.0 -
    https://android.googlesource.com/platform/system/iot/attestation/+/master/NOTICE

*   Python 2.7.13 - https://www.python.org/download/releases/2.7/license/

*   Python Packages:

    *   wxPython 4.0.2 - https://www.wxpython.org/pages/license/
    *   PyInstaller 3.2.1 - http://www.pyinstaller.org/license.html
    *   sh 1.12.14 - https://github.com/amoffat/sh/blob/master/LICENSE.txt
    *   six 1.11.0 - https://github.com/benjaminp/six/blob/master/LICENSE
    *   future 0.16.0 - http://python-future.org/credits.html#licence
    *   pypiwin32 219 -
        https://github.com/mhammond/pywin32/blob/master/win32/License.txt
    *   passlib 1.7.1 - https://pythonhosted.org/passlib/copyright.html

This package contains the following Microsoft Visual C++ redistributable files:

*   msvcr90.dll
*   msvcp90.dll
*   msvcm90.dll

For more information on Microsoft Visual C++ redistributable files, see:

*   https://msdn.microsoft.com/en-us/library/ms235299(v=vs.90).aspx
*   https://msdn.microsoft.com/en-us/library/8kche8ah(v=vs.90).aspx

The package uses tcl/tk8.5, see:

*   https://www.tcl.tk/software/tcltk/license.html
