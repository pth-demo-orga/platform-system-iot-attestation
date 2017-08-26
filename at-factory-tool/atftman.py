#!/usr/bin/python
"""At-Factory-Tool manager module.

This module provides the logical implementation of the graphical tool
for managing the ATFA and AT communication.
"""
import os
import tempfile
import uuid

import fastboot_exceptions


class EncryptionAlgorithm(object):
  ALGORITHM_P256 = 1
  ALGORITHM_CURVE25519 = 2


class AtftManager(object):
  """The manager to implement ATFA tasks.

  TODO(shan): Support multiple target devices.
  The target_dev attribute can be extended to a list

  Attributes:
    atfa_dev: A FastbootDevice object identifying the detected ATFA device.
    target_dev: A FastbootDevice object identifying the AT device
      to be provisioned.
    atfa_dev_manager: An interface to do operation on ATFA device.
  """

  def __init__(self, fastboot_device_controller):
    """Initialize attributes and store the supplied fastboot_device_controller.

    Args:
      fastboot_device_controller:
        The interface to interact with a fastboot device.
    """
    self.atfa_dev = None
    self.target_dev = None
    self.atfa_dev_manager = None
    self._fastboot_device_controller = fastboot_device_controller

  def FormatException(self, e):
    """Format the exception. Concatenate the exception type with the message.

    Args:
      e: The exception to be printed.
    Returns:
      The exception message.
    """
    return '{0}: {1}'.format(e.__class__.__name__, e)

  def ListDevices(self):
    """Get device list.

    Get the serial number of the ATFA device and the target device.
    If the device does not exist, the returned serial number would be None.

    Returns:
      A dictionary of
      {'atfa_dev': ATFA device serial number,
      'target_dev': target device serial number}
    Raises:
      DeviceNotFoundException: When no device is found.
    """
    # ListDevices returns a list of USBHandles
    device_serials = self._fastboot_device_controller.ListDevices()

    if not device_serials:
      self.atfa_dev = None
      self.target_dev = None
      raise fastboot_exceptions.DeviceNotFoundException()
    else:
      for found_dev_serial in device_serials:
        if found_dev_serial.startswith('ATFA'):
          self.atfa_dev = self._fastboot_device_controller(found_dev_serial)
          self.atfa_dev_manager = AtfaDeviceManager(self.atfa_dev)
        elif found_dev_serial:
          self.target_dev = self._fastboot_device_controller(found_dev_serial)
    if self.atfa_dev is None:
      atfa_dev_serial = None
    else:
      atfa_dev_serial = self.atfa_dev.serial_number
    if self.target_dev is None:
      target_dev_serial = None
    else:
      target_dev_serial = self.target_dev.serial_number
    return {'atfa_dev': atfa_dev_serial, 'target_dev': target_dev_serial}

  def GetAtfaSerial(self):
    """Get the serial number for the ATFA device.

    Returns:
      The serial number for the ATFA device
    Raises:
      DeviceNotFoundException: When the device is not found
    """
    self._CheckDevice(self.atfa_dev)
    return self.atfa_dev.serial_number

  def TransferContent(self, src, dst):
    """Transfer content from a device to another device.

    Download file from one device and store it into a tmp file.
    Upload file from the tmp file onto another device.

    Args:
      src: The source device to be copied from.
      dst: The destination device to be copied to.
    """
    # create a tmp folder
    tmp_folder = tempfile.mkdtemp()
    # temperate file name is a UUID based on host ID and current time.
    tmp_file_name = str(uuid.uuid1())
    file_path = os.path.join(tmp_folder, tmp_file_name)
    # pull file to local fs
    src.Upload(file_path)
    # push file to fastboot device
    dst.Download(file_path)
    # delete the temperate file afterwards
    if os.path.exists(file_path):
      os.remove(file_path)
    # delete the temperate folder afterwards
    if os.path.exists(tmp_folder):
      os.rmdir(tmp_folder)

  def _CheckDevice(self, device):
    """Check if the device is a connected fastboot device.

    Args:
      device: The device to be checked.
    Raises:
      DeviceNotFoundException: When the device is not found
    """
    if device is None:
      raise fastboot_exceptions.DeviceNotFoundException()


class AtfaDeviceManager(object):
  """The class to manager ATFA device related operations.

  """

  def __init__(self, atfa_dev):
    self.atfa_dev = atfa_dev

  def GetSerial(self):
    """Issue fastboot command to get serial number for the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found.
    """
    self._CheckDevice(self.atfa_dev)
    self.atfa_dev.Oem('serial')

  def SwitchNormal(self):
    """Switch the ATFA device to normal mode.

    TODO(matta): Find a way to find and nicely unmount drive from Windows.
    TODO(matta): Have ATFA detect unmount and switch back to g_ser mode.

    Raises:
      DeviceNotFoundException: When the device is not found
    """
    self._CheckDevice(self.atfa_dev)

  def SwitchStorage(self):
    """Switch the ATFA device to storage mode.

    Returns:
      The result for the fastboot command.
    Raises:
      DeviceNotFoundException: When the device is not found
    """
    self._CheckDevice(self.atfa_dev)
    return self.atfa_dev.Oem('storage')

  def Reboot(self):
    """Reboot the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found
    """
    self._CheckDevice(self.atfa_dev)
    self.atfa_dev.Oem('reboot')

  def Shutdown(self):
    """Shutdown the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found
    """
    self._CheckDevice(self.atfa_dev)
    self.atfa_dev.Oem('shutdown')

  def GetLogs(self):
    # TODO(matta): Add Fastboot command to copy logs to storage device and
    # switch to mass storage mode
    self._CheckDevice(self.atfa_dev)
