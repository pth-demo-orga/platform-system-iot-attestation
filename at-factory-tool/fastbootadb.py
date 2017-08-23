# !/usr/bin/python
"""Fastboot Interface Implementation using python adb library.

"""
from adb import fastboot
from adb import usb_exceptions

import fastboot_exceptions


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
    device_serial_numbers = []
    try:
      for device in fastboot.FastbootCommands.Devices():
        device_serial_numbers.append(device.serial_number)
    except usb_exceptions.FormatMessageWithArgumentsException as e:
      raise fastboot_exceptions.FastbootFailure(str(e))

    return device_serial_numbers

  def __init__(self, serial_number):
    """Initiate the fastboot device object.

    Args:
      serial_number: The serial number of the fastboot device.
    Raises:
      FastbootFailure: If failure happens for fastboot commands.
    """
    try:
      self.serial_number = serial_number
      self._fastboot_commands = (fastboot.FastbootCommands.ConnectDevice(
          serial=serial_number))
    except usb_exceptions.FormatMessageWithArgumentsException as e:
      raise fastboot_exceptions.FastbootFailure(str(e))

  def Oem(self, oem_command):
    """Run an OEM command.

    Args:
      oem_command: The OEM command to run.
    Returns:
      The result message for the OEM command.
    Raises:
      FastbootFailure: If failure happens during the command.
    """
    try:
      return self._fastboot_commands.Oem(oem_command)
    except usb_exceptions.FormatMessageWithArgumentsException as e:
      raise fastboot_exceptions.FastbootFailure(str(e))

  def Upload(self, file_path):
    """Pulls a file from the fastboot device to the local file system.

    TODO: To be implemented. Currently adb library does not support
    the stage and get_staged command.

    Args:
      file_path: The file path of the file system
        that the remote file would be pulled to.
    """
    pass

  def Download(self, file_path):
    """Push a file from the file system to the fastboot device.

    TODO: To be implemented. Currently adb library does not support
    the stage and get_staged command.

    Args:
      file_path: The file path of the file on the local file system
        that would be pushed to fastboot device.
    """
    pass

  def Disconnect(self):
    """Disconnect from the fastboot device."""
    self._fastboot_commands.Close()

  def __del__(self):
    self.Disconnect()
