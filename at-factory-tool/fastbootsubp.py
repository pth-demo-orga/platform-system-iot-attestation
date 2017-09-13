# !/usr/bin/python
"""Fastboot Interface Implementation using subprocess library.

"""
import subprocess
import fastboot_exceptions

CREATE_NO_WINDOW = 0x08000000


class FastbootDevice(object):
  """An abstracted fastboot device object.

  Attributes:
    serial_number: The serial number of the fastboot device.
  """

  @staticmethod
  def ListDevices():
    """List all fastboot devices.

    Returns:
      A list of serial numbers for all the fastboot devices.
    """
    try:
      out = subprocess.check_output(['fastboot', 'devices'],
                                    creationflags=CREATE_NO_WINDOW)
      device_serial_numbers = (out.replace('\tfastboot', '')
                               .rstrip().splitlines())
      # filter out empty string
      return filter(None, device_serial_numbers)
    except subprocess.CalledProcessError as e:
      raise fastboot_exceptions.FastbootFailure(e.output)

  def __init__(self, serial_number):
    """Initiate the fastboot device object.

    Args:
      serial_number: The serial number of the fastboot device.
    """
    self.serial_number = serial_number

  def Oem(self, oem_command, err_to_out):
    """"Run an OEM command.

    Args:
      oem_command: The OEM command to run.
      err_to_out: Whether to redirect stderr to stdout.
    Returns:
      The result message for the OEM command.
    Raises:
      FastbootFailure: If failure happens during the command.
    """
    try:
      if err_to_out:
        return subprocess.check_output(['fastboot', '-s', self.serial_number,
                                        'oem', oem_command],
                                       stderr=subprocess.STDOUT,
                                       creationflags=CREATE_NO_WINDOW)
      else:
        return subprocess.check_output(['fastboot', '-s', self.serial_number,
                                        'oem', oem_command],
                                       creationflags=CREATE_NO_WINDOW)
    except subprocess.CalledProcessError as e:
      raise fastboot_exceptions.FastbootFailure(e.output)

  def Upload(self, file_path):
    """Pulls a file from the fastboot device to the local file system.

    Args:
      file_path: The file path of the file system
        that the remote file would be pulled to.
    Returns:
      The output for the fastboot command required.
    Raises:
      FastbootFailure: If failure happens during the command.
    """
    try:
      return subprocess.check_output(['fastboot', '-s', self.serial_number,
                                      'get_staged', file_path],
                                     creationflags=CREATE_NO_WINDOW)
    except subprocess.CalledProcessError as e:
      raise fastboot_exceptions.FastbootFailure(e.output)

  def Download(self, file_path):
    """Push a file from the file system to the fastboot device.

    Args:
      file_path: The file path of the file on the local file system
        that would be pushed to fastboot device.
    Returns:
      The output for the fastboot command required.
    Raises:
      FastbootFailure: If failure happens during the command.
    """
    try:
      return subprocess.check_output(['fastboot', '-s', self.serial_number,
                                      'stage', file_path],
                                     creationflags=CREATE_NO_WINDOW)
    except subprocess.CalledProcessError as e:
      raise fastboot_exceptions.FastbootFailure(e.output)

  def GetVar(self, var):
    """Get a variable from the device.

    Note that the return value is in stderr instead of stdout.
    Args:
      var: The name of the variable.
    Returns:
      The value for the variable.
    Raises:
      FastbootFailure: If failure happens during the command.
    """
    try:
      # Fastboot getvar command's output would be in stderr instead of stdout.
      # Need to redirect stderr to stdout.

      # Need the shell=True flag for windows, otherwise it hangs.
      out = subprocess.check_output(['fastboot', '-s', self.serial_number,
                                     'getvar', var],
                                    stderr=subprocess.STDOUT,
                                    shell=True,
                                    creationflags=CREATE_NO_WINDOW)
      lines = out.splitlines()
      for line in lines:
        if line.startswith(var + ': '):
          value = line.replace(var + ': ', '').replace('\r', '')
      return value
    except subprocess.CalledProcessError as e:
      # Since we redirected stderr, we should print stdout here.
      raise fastboot_exceptions.FastbootFailure(e.output)

  def Disconnect(self):
    """Disconnect from the fastboot device."""
    pass

  def __del__(self):
    self.Disconnect()
