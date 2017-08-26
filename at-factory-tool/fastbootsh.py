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
    out = sh.fastboot('devices')
    if out.startswith('FAIL'):
      raise fastboot_exceptions.FastbootFailure(out)

    device_serial_numbers = out.replace('\tfastboot', '').rstrip().split('\n')
    # filter out empty string
    return filter(None, device_serial_numbers)

  def __init__(self, serial_number):
    """Initiate the fastboot device object.

    Args:
      serial_number: The serial number of the fastboot device.
    """
    self.serial_number = serial_number

  def Oem(self, oem_command):
    """Run an OEM command.

    Args:
      oem_command: The OEM command to run.
    Returns:
      The result message for the OEM command.
    Raises:
      FastbootFailure: If failure happens during the command.
    """
    out = sh.fastboot('-s', self.serial_number, 'oem', oem_command)
    if out.startswith('FAIL'):
      raise fastboot_exceptions.FastbootFailure(out)
    return out

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
    out = sh.fastboot('-s', self.serial_number, 'get_staged', file_path)
    if out.startswith('FAIL'):
      raise fastboot_exceptions.FastbootFailure(out)
    return out

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
    out = sh.fastboot('-s', self.serial_number, 'stage', file_path)
    if out.startswith('FAIL'):
      raise fastboot_exceptions.FastbootFailure(out)
    return out

  def Disconnect(self):
    """Disconnect from the fastboot device."""
    pass

  def __del__(self):
    self.Disconnect()
