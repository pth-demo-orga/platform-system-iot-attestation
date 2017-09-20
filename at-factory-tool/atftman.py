#!/usr/bin/python
"""AT-Factory-Tool manager module.

This module provides the logical implementation of the graphical tool for
managing the ATFA and AT communication.
"""
import datetime
import os
import tempfile
import uuid

import fastboot_exceptions


class EncryptionAlgorithm(object):
  ALGORITHM_P256 = 1
  ALGORITHM_CURVE25519 = 2


class ProvisionStatus(object):
  IDLE = 'Idle'
  WAITING = 'Waiting'
  PROVISIONING = 'Provisioning'
  PROVISIONED = 'Provisioned'
  FAILED = 'Provision Failed'


class DeviceInfo(object):
  """The class to wrap the information about a fastboot device.

  Attributes:
    serial_number: The serial number for the device.
    location: The physical USB location for the device.
  """

  def __init__(self,
               _fastboot_device_controller,
               serial_number,
               location=None,
               provision_status=ProvisionStatus.IDLE):
    self._fastboot_device_controller = _fastboot_device_controller
    self.serial_number = serial_number
    self.location = location
    self.provision_status = provision_status

  def Oem(self, oem_command, err_to_out=False):
    return self._fastboot_device_controller.Oem(oem_command, err_to_out)

  def Upload(self, file_path):
    return self._fastboot_device_controller.Upload(file_path)

  def Download(self, file_path):
    return self._fastboot_device_controller.Download(file_path)

  def GetVar(self, var):
    return self._fastboot_device_controller.GetVar(var)

  def __eq__(self, other):
    return (self.serial_number == other.serial_number and
            self.location == other.location and
            self.provision_status == other.provision_status)

  def __ne__(self, other):
    return not self.__eq__(other)

  def __str__(self):
    if self.location:
      return self.serial_number + ' at location: ' + self.location
    else:
      return self.serial_number


class AtftManager(object):
  """The manager to implement ATFA tasks.

  Attributes:
    atfa_dev: A FastbootDevice object identifying the detected ATFA device.
    target_dev: A FastbootDevice object identifying the AT device
      to be provisioned.
    atfa_dev_manager: An interface to do operation on ATFA device.
  """
  SORT_BY_SERIAL = 0
  SORT_BY_LOCATION = 1
  DEFAULT_KEY_THRESHOLD = 100

  def __init__(self, fastboot_device_controller, serial_mapper):
    """Initialize attributes and store the supplied fastboot_device_controller.

    Args:
      fastboot_device_controller:
        The interface to interact with a fastboot device.
      serial_mapper:
        The interface to get the USB physical location to serial number map.
    """
    self.stable_serials = []
    self.pending_serials = []
    self.atfa_dev = None
    self.atfa_dev_manager = AtfaDeviceManager(self)
    self.target_devs = []
    self.product_id = '00000000000000000000000000000000'
    self.key_threshold = self.DEFAULT_KEY_THRESHOLD
    self._fastboot_device_controller = fastboot_device_controller
    self._serial_mapper = serial_mapper()

  def ListDevices(self, sort_by=SORT_BY_LOCATION):
    """Get device list.

    Get the serial number of the ATFA device and the target device.
    If the device does not exist, the returned serial number would be None.

    Args:
      sort_by: The field to sort by.
    """
    # ListDevices returns a list of USBHandles
    device_serials = self._fastboot_device_controller.ListDevices()
    self._UpdateSerials(device_serials)
    if not self.stable_serials:
      self.target_devs = []
      self.atfa_dev = None
      return
    self._HandleSerials()
    self._SortTargetDevices(sort_by)

  @staticmethod
  def _SerialAsKey(device):
    return device.serial_number

  @staticmethod
  def _LocationAsKey(device):
    if device.location is None:
      return ''
    return device.location

  def _SortTargetDevices(self, sort_by):
    if sort_by == self.SORT_BY_LOCATION:
      self.target_devs.sort(key=AtftManager._LocationAsKey)
    elif sort_by == self.SORT_BY_SERIAL:
      self.target_devs.sort(key=AtftManager._SerialAsKey)

  def _UpdateSerials(self, device_serials):
    """Update the stored pending_serials and stable_serials.

    Note that we cannot check status once the fastboot device is found since the
    device may not be ready yet. So we put the new devices into the pending
    state. Once we see the device again in the next refresh, we add that device.
    If that device is not seen in the next refresh, we remove it from pending.
    This makes sure that the device would have a refresh interval time after
    it's recognized as a fastboot device until it's issued command.

    Args:
      device_serials: The list of serial numbers of the fastboot devices.
    """
    stable_serials_copy = self.stable_serials[:]
    pending_serials_copy = self.pending_serials[:]
    self.stable_serials = []
    self.pending_serials = []
    for serial in device_serials:
      if serial in stable_serials_copy or serial in pending_serials_copy:
        # Was in stable or pending state, seen twice, add to stable state.
        self.stable_serials.append(serial)
      else:
        # First seen, add to pending state.
        self.pending_serials.append(serial)

  def _HandleSerials(self):
    """Create new devices and remove old devices.

    Add device location information and target device provision status.
    """
    device_serials = self.stable_serials
    serial_location_map = self._serial_mapper.get_serial_map()
    new_targets = []
    atfa_serial = None
    for serial in device_serials:
      if not serial:
        continue

      if serial.startswith('ATFA'):
        atfa_serial = serial
      else:
        new_targets.append(serial)

    if atfa_serial is None:
      # No ATFA device found.
      self.atfa_dev = None
    elif self.atfa_dev is None or self.atfa_dev.serial_number != atfa_serial:
      # Not the same ATFA device.
      controller = self._fastboot_device_controller(atfa_serial)
      location = None
      if atfa_serial in serial_location_map:
        location = serial_location_map[atfa_serial]
      self.atfa_dev = DeviceInfo(controller, atfa_serial, location)

    # Remove those devices that are not in new targets.
    self.target_devs = [
        device for device in self.target_devs
        if device.serial_number in new_targets
    ]

    common_serials = [device.serial_number for device in self.target_devs]

    # Create new device object for newly added devices.
    for serial in new_targets:
      if serial not in common_serials:
        controller = self._fastboot_device_controller(serial)
        location = None
        if serial in serial_location_map:
          location = serial_location_map[serial]

        new_target_dev = DeviceInfo(controller, serial, location)
        self.CheckProvisionStatus(new_target_dev)
        self.target_devs.append(new_target_dev)

  def CheckProvisionStatus(self, target_dev):
    """Check whether the target device has been provisioned.

    Args:
      target_dev: The target device (DeviceInfo).
    """
    at_attest_uuid = target_dev.GetVar('at-attest-uuid')
    # TODO(shan): We only need empty string here
    # NOT_PROVISIONED is for test purpose.
    if at_attest_uuid and at_attest_uuid != 'NOT_PROVISIONED':
      target_dev.provision_status = ProvisionStatus.PROVISIONED

  def GetAtfaSerial(self):
    """Get the serial number for the ATFA device.

    Returns:
      The serial number for the ATFA device
    Raises:
      DeviceNotFoundException: When the device is not found
    """
    self.CheckDevice(self.atfa_dev)
    return self.atfa_dev.serial_number

  def TransferContent(self, src, dst):
    """Transfer content from a device to another device.

    Download file from one device and store it into a tmp file. Upload file from
    the tmp file onto another device.

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

  def GetTargetDevice(self, serial):
    """Get the target DeviceInfo object according to the serial number.

    Args:
      serial: The serial number for the device object.
    Returns:
      The DeviceInfo object for the device.
    """
    for target_dev in self.target_devs:
      if target_dev.serial_number == serial:
        return target_dev
    return None

  @staticmethod
  def CheckDevice(device):
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

  def __init__(self, atft_manager):
    self.atft_manager = atft_manager

  def GetSerial(self):
    """Issue fastboot command to get serial number for the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found.
    """
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    self.atft_manager.atfa_dev.Oem('serial')

  def SwitchNormal(self):
    """Switch the ATFA device to normal mode.

    Raises:
      DeviceNotFoundException: When the device is not found
    """
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)

  def SwitchStorage(self):
    """Switch the ATFA device to storage mode.

    Raises:
      DeviceNotFoundException: When the device is not found
    """
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    self.atft_manager.atfa_dev.Oem('storage')

  def ProcessKey(self):
    """Ask the ATFA device to process the stored key bundle.

    Raises:
      DeviceNotFoundException: When the device is not found
    """
    # Need to set time first so that certificates would validate.
    self.SetTime()
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    self.atft_manager.atfa_dev.Oem('process-keybundle')

  def Reboot(self):
    """Reboot the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found
    """
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    self.atft_manager.atfa_dev.Oem('reboot')

  def Shutdown(self):
    """Shutdown the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found
    """
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    self.atft_manager.atfa_dev.Oem('shutdown')

  def GetLogs(self):
    # switch to mass storage mode
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)

  def CheckStatus(self):
    """Return the number of available AT keys for the current product.

    Returns:
      The number of attestation keys left for the current product.
    Raises:
      FastbootFailure: If error happens with the fastboot oem command.
    """
    if not self.atft_manager.product_id:
      raise fastboot_exceptions.ProductNotSpecifiedException()

    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    out = self.atft_manager.atfa_dev.Oem(
        'num-keys ' + self.atft_manager.product_id, True)
    # Note: use splitlines instead of split('\n') to prevent '\r\n' problem on
    # windows.
    for line in out.splitlines():
      if line.startswith('(bootloader) '):
        try:
          return int(line.replace('(bootloader) ', ''))
        except ValueError:
          raise fastboot_exceptions.FastbootFailure(
              'ATFA device response has invalid format')

    raise fastboot_exceptions.FastbootFailure(
        'ATFA device response has invalid format')

  def SetTime(self):
    """Inject the host time into the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found
    """
    time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)

    self.atft_manager.atfa_dev.Oem('set-date ' + time)
