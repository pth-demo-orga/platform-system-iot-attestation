# !/usr/bin/python
"""Fastboot Interface Implementation using sh library.

"""
import fastboot_exceptions
import sh


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
      out = sh.fastboot('devices')
      device_serial_numbers = out.replace('\tfastboot', '').rstrip().split('\n')
      # filter out empty string
      return filter(None, device_serial_numbers)
    except sh.ErrorReturnCode as e:
      raise fastboot_exceptions.FastbootFailure(e.stderr)

  def __init__(self, serial_number):
    """Initiate the fastboot device object.

    Args:
      serial_number: The serial number of the fastboot device.
    """
    self.serial_number = serial_number

  def Oem(self, oem_command, err_to_out):
    """Run an OEM command.

    Args:
      oem_command: The OEM command to run.
      err_to_out: Whether to redirect stderr to stdout.
    Returns:
      The result message for the OEM command.
    Raises:
      FastbootFailure: If failure happens during the command.
    """
    try:
      out = sh.fastboot('-s', self.serial_number, 'oem', oem_command,
                        _err_to_out=err_to_out)
      return out
    except sh.ErrorReturnCode as e:
      if err_to_out:
        err = e.stdout
      else:
        err = e.stderr
      raise fastboot_exceptions.FastbootFailure(err)

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
      out = sh.fastboot('-s', self.serial_number, 'get_staged', file_path)
      return out
    except sh.ErrorReturnCode as e:
      raise fastboot_exceptions.FastbootFailure(e.stderr)

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
      out = sh.fastboot('-s', self.serial_number, 'stage', file_path)
      return out
    except sh.ErrorReturnCode as e:
      raise fastboot_exceptions.FastbootFailure(e.stderr)

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
      out = sh.fastboot('-s', self.serial_number, 'getvar', var,
                        _err_to_out=True)
      lines = out.split('\n')
      for line in lines:
        if line.startswith(var + ': '):
          value = line.replace(var + ': ', '')
      return value
    except sh.ErrorReturnCode as e:
      # Since we redirected stderr, we should print stdout here.
      raise fastboot_exceptions.FastbootFailure(e.stdout)

  def Disconnect(self):
    """Disconnect from the fastboot device."""
    pass

  def __del__(self):
    self.Disconnect()
