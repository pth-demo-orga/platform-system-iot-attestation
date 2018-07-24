#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2017 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""AT-Factory-Tool manager module.

This module provides the logical implementation of the graphical tool for
managing the ATFA and AT communication.
"""
import base64
from datetime import datetime
import json
import os
import re
import struct
import sys
import tempfile
import threading
import uuid

from fastboot_exceptions import DeviceCreationException
from fastboot_exceptions import DeviceNotFoundException
from fastboot_exceptions import FastbootFailure
from fastboot_exceptions import NoAlgorithmAvailableException
from fastboot_exceptions import OsVersionNotAvailableException
from fastboot_exceptions import OsVersionNotCompatibleException
from fastboot_exceptions import ProductAttributesFileFormatError
from fastboot_exceptions import ProductNotSpecifiedException


BOOTLOADER_STRING = '(bootloader) '
_ECDH_KEY_LEN = 33
_VAR_LEN = 4
_HEADER_LEN = 8
_GCM_IV_LEN = 12
_GCM_TAG_LEN = 16
_HASH_LEN = 32
_HKDF_HASH_LEN = 16
_OPERATIONS = {'ISSUE': 2, 'ISSUE_ENC': 3, 'ISSUE_SOM': 4, 'ISSUE_ENC_SOM': 5}


def _GetCurrentPath():
  if getattr(sys, 'frozen', False):
    # we are running in a bundle
    path = sys._MEIPASS  # pylint: disable=protected-access
  else:
    # we are running in a normal Python environment
    path = os.path.dirname(os.path.abspath(__file__))
  return path


def _GetVarLen(data, index):
  """Reads the 4 byte little endian unsigned integer at data[index].

  Args:
    data: Start of bytearray
    index: Offset that indicates where the integer begins

  Returns:
    Little endian unsigned integer at data[index]
  """
  return struct.unpack('<I', data[index:index + 4])[0]


class EncryptionAlgorithm(object):
  """The support encryption algorithm constant."""
  ALGORITHM_P256 = 1
  ALGORITHM_CURVE25519 = 2


class ProvisionStatus(object):
  """The provision status constant."""
  _PROCESSING           = 0
  _SUCCESS              = 1
  _FAILED               = 2

  IDLE                  = 0
  WAITING               = 1
  FUSEVBOOT_ING         = (10 + _PROCESSING)
  FUSEVBOOT_SUCCESS     = (10 + _SUCCESS)
  FUSEVBOOT_FAILED      = (10 + _FAILED)
  REBOOT_ING            = (20 + _PROCESSING)
  REBOOT_SUCCESS        = (20 + _SUCCESS)
  REBOOT_FAILED         = (20 + _FAILED)
  FUSEATTR_ING          = (30 + _PROCESSING)
  FUSEATTR_SUCCESS      = (30 + _SUCCESS)
  FUSEATTR_FAILED       = (30 + _FAILED)
  LOCKAVB_ING           = (40 + _PROCESSING)
  LOCKAVB_SUCCESS       = (40 + _SUCCESS)
  LOCKAVB_FAILED        = (40 + _FAILED)
  PROVISION_ING         = (50 + _PROCESSING)
  PROVISION_SUCCESS     = (50 + _SUCCESS)
  PROVISION_FAILED      = (50 + _FAILED)
  UNLOCKAVB_ING         = (60 + _PROCESSING)
  UNLOCKAVB_SUCCESS     = (60 + _SUCCESS)
  UNLOCKAVB_FAILED      = (60 + _FAILED)
  SOM_PROVISION_ING     = (70 + _PROCESSING)
  SOM_PROVISION_SUCCESS = (70 + _SUCCESS)
  SOM_PROVISION_FAILED  = (70 + _FAILED)

  STRING_MAP = {
    IDLE                  : ['Idle', '初始'],
    WAITING               : ['Waiting', '等待'],
    FUSEVBOOT_ING         : ['Fusing VbootKey...', '烧录引导密钥中...'],
    FUSEVBOOT_SUCCESS     : ['Bootloader Locked', '已烧录引导密钥'],
    FUSEVBOOT_FAILED      : ['Lock Vboot Failed', '烧录引导密钥失败'],
    REBOOT_ING            : ['Rebooting...', '重启设备中...'],
    REBOOT_SUCCESS        : ['Rebooted', '已重启设备'],
    REBOOT_FAILED         : ['Reboot Failed', '重启设备失败'],
    FUSEATTR_ING          : ['Fusing PermAttr', '烧录产品信息中...'],
    FUSEATTR_SUCCESS      : ['PermAttr Fused', '已烧录产品信息'],
    FUSEATTR_FAILED       : ['Fuse PermAttr Failed', '烧录产品信息失败'],
    LOCKAVB_ING           : ['Locking AVB', '锁定AVB中...'],
    LOCKAVB_SUCCESS       : ['AVB Locked', '已锁定AVB'],
    LOCKAVB_FAILED        : ['Lock AVB Failed', '锁定AVB失败'],
    PROVISION_ING         : ['Giving Key', '传输密钥中...'],
    PROVISION_SUCCESS     : ['Success', '成功!'],
    PROVISION_FAILED      : ['Provision Failed', '传输密钥失败'],
    UNLOCKAVB_ING         : ['Unlocking AVB', '解锁AVB中...'],
    UNLOCKAVB_SUCCESS     : ['AVB Unlocked', '已解锁AVB'],
    UNLOCKAVB_FAILED      : ['Unlock AVB Failed', '解锁AVB失败'],
    SOM_PROVISION_ING     : ['Giving SoMKey', '传输SoM密钥中...'],
    SOM_PROVISION_SUCCESS : ['SoM Key Stored', 'SoM密钥已传输!'],
    SOM_PROVISION_FAILED  : ['SoM Key Failed', '传输SoM密钥失败']

  }

  @staticmethod
  def ToString(provision_status, language_index):
    return ProvisionStatus.STRING_MAP[provision_status][language_index]

  @staticmethod
  def isSuccess(provision_status):
    return provision_status % 10 == ProvisionStatus._SUCCESS

  @staticmethod
  def isProcessing(provision_status):
    return provision_status % 10 == ProvisionStatus._PROCESSING

  @staticmethod
  def isFailed(provision_status):
    return provision_status % 10 == ProvisionStatus._FAILED


class ProvisionState(object):
  """The provision state of the target device.

  Attributes:
    bootloader_locked: Whether bootloader is locked.
    avb_perm_attr_set: Whether permanent attribute is set.
    avb_locked: Whether avb is locked.
    provisioned: Whether the device has product key provisioned.
  """
  bootloader_locked = False
  avb_perm_attr_set = False
  avb_locked = False
  product_provisioned = False
  som_provisioned = False

  def __eq__(self, other):
    return (self.bootloader_locked == other.bootloader_locked and
            self.avb_perm_attr_set == other.avb_perm_attr_set and
            self.avb_locked == other.avb_locked and
            self.product_provisioned == other.product_provisioned and
            self.som_provisioned == other.som_provisioned)

  def __ne__(self, other):
    return not self.__eq__(other)


class ProductInfo(object):
  """The information about a product.

  Attributes:
    product_id: The id for the product.
    product_name: The name for the product.
    product_attributes: The byte array of the product permanent attributes.
  """

  def __init__(self, product_id, product_name, product_attributes, vboot_key):
    self.product_id = product_id
    self.product_name = product_name
    self.product_attributes = product_attributes
    self.vboot_key = vboot_key


class SomInfo(object):
  """The information about a SoM.

  Attributes:
    som_id: The id for the som.
    som_name: The name for the som.
  """

  def __init__(self, som_id, som_name, vboot_key):
    self.som_id = som_id
    self.som_name = som_name
    self.vboot_key = vboot_key


class DeviceInfo(object):
  """The class to wrap the information about a fastboot device.

  Attributes:
    serial_number: The serial number for the device.
    location: The physical USB location for the device.
  """

  def __init__(self, _fastboot_device_controller, serial_number,
               location=None, provision_status=ProvisionStatus.IDLE,
               provision_state=ProvisionState()):
    self._fastboot_device_controller = _fastboot_device_controller
    self.serial_number = serial_number
    self.location = location
    # The provision status and provision state is only meaningful for target
    # device.
    self.provision_status = provision_status
    self.provision_state = provision_state
    # The number of attestation keys left for the selected product. This
    # attribute is only meaning for ATFA device.
    self.keys_left = None
    # Only one operation is allowed on one device at one time.
    self.operation_lock = threading.Lock()
    # Current operation.
    self.operation = None
    # The at-attest-uuid for the provisioned key in this device.
    self.at_attest_uuid = None

  def Copy(self):
    return DeviceInfo(None, self.serial_number, self.location,
                      self.provision_status, self.provision_state)

  def Reboot(self):
    return self._fastboot_device_controller.Reboot()

  def Oem(self, oem_command, err_to_out=False):
    return self._fastboot_device_controller.Oem(oem_command, err_to_out)

  def Flash(self, partition, file_path):
    return self._fastboot_device_controller.Flash(partition, file_path)

  def Upload(self, file_path):
    return self._fastboot_device_controller.Upload(file_path)

  def Download(self, file_path):
    return self._fastboot_device_controller.Download(file_path)

  def GetVar(self, var):
    return self._fastboot_device_controller.GetVar(var)

  def __eq__(self, other):
    return (self.serial_number == other.serial_number and
            self.location == other.location and
            self.provision_status == other.provision_status and
            self.provision_state == other.provision_state)

  def __ne__(self, other):
    return not self.__eq__(other)

  def __str__(self):
    if self.location:
      return self.serial_number + ' at location: ' + self.location
    else:
      return self.serial_number


class RebootCallback(object):
  """The class to handle reboot success and timeout callbacks."""

  def __init__(
      self, timeout, success_callback, timeout_callback):
    """Initiate a reboot callback handler class.

    Args:
      timeout: How much time to wait for the device to reappear.
      success_callback: The callback to be called if the device reappear
        before timeout.
      timeout_callback: The callback to be called if the device doesn't reappear
        before timeout.
    """
    self.success = success_callback
    self.fail = timeout_callback
    # Lock to make sure only one callback is called. (either success or timeout)
    # This lock can only be obtained once.
    self.lock = threading.Lock()
    self.timer = threading.Timer(timeout, self._TimeoutCallback)
    self.timer.start()

  def _TimeoutCallback(self):
    """The function to handle timeout callback.

    Call the timeout_callback that is registered.
    """
    if self.lock and self.lock.acquire(False):
      self.fail()

  def Release(self):
    lock = self.lock
    timer = self.timer
    self.lock = None
    self.timer = None
    lock.release()
    timer.cancel()


class _AtapSessionParameters(object):
  """Atap session parameters.

  Modified from the same structure in provision-test.py.

  Attributes:
    private_key: The key exchange private key.
    public_key: The key exchange public key.
    device_pub_key: The public key sent from the device.
    shared_key: The computed shared key.
  """

  def __init__(self):
    self.private_key = bytes()
    self.public_key = bytes()
    self.device_pub_key = bytes()
    self.shared_key = bytes()


class AtftManager(object):
  """The manager to implement ATFA tasks.

  Attributes:
    atfa_dev: A FastbootDevice object identifying the detected ATFA device.
    target_dev: A FastbootDevice object identifying the AT device
      to be provisioned.
  """
  SORT_BY_SERIAL = 0
  SORT_BY_LOCATION = 1
  # The length of the permanent attribute should be 1052.
  EXPECTED_ATTRIBUTE_LENGTH = 1052

  # The Permanent Attribute File JSON Key Names:
  JSON_PRODUCT_NAME = 'productName'
  JSON_PRODUCT_ATTRIBUTE = 'productPermanentAttribute'
  JSON_PRODUCT_ATTRIBUTE = 'productPermanentAttribute'
  JSON_VBOOT_KEY = 'bootloaderPublicKey'
  JSON_SOM_ID = 'somId'

  def __init__(self, fastboot_device_controller, serial_mapper, configs):
    """Initialize attributes and store the supplied fastboot_device_controller.

    Args:
      fastboot_device_controller:
        The interface to interact with a fastboot device.
      serial_mapper:
        The interface to get the USB physical location to serial number map.
      configs:
        The additional configurations. Need to contain 'ATFA_REBOOT_TIMEOUT'.
    """
    # The timeout period for ATFA device reboot.
    self.ATFA_REBOOT_TIMEOUT = 30
    self.UNLOCK_CREDENTIAL = None
    if configs:
      if 'ATFA_REBOOT_TIMEOUT' in configs:
        try:
          self.ATFA_REBOOT_TIMEOUT = float(configs['ATFA_REBOOT_TIMEOUT'])
        except ValueError:
          pass

      if 'COMPATIBLE_ATFA_VERSION' in configs:
        try:
          self.COMPATIBLE_ATFA_VERSION = int(configs['COMPATIBLE_ATFA_VERSION'])
        except ValueError:
          pass

      if 'UNLOCK_CREDENTIAL' in configs:
        self.UNLOCK_CREDENTIAL = configs['UNLOCK_CREDENTIAL']

    # The serial numbers for the devices that are at least seen twice.
    self.stable_serials = []
    # The serail numbers for the devices that are only seen once.
    self.pending_serials = []
    # The atfa device DeviceInfo object.
    self.atfa_dev = None
    # The list of target devices DeviceInfo objects.
    self.target_devs = []
    # The product information for the selected product.
    self.product_info = None
    # The som information for the selected som.
    self.som_info = None
     # The atfa device manager.
    self._atfa_dev_manager = AtfaDeviceManager(self)
    # The fastboot controller.
    self._fastboot_device_controller = fastboot_device_controller
    # The map mapping serial number to USB location.
    self._serial_mapper = serial_mapper()
    # The map mapping rebooting device serial number to their reboot callback
    # objects.
    self._reboot_callbacks = {}

  def GetCachedATFAKeysLeft(self):
    if not self.atfa_dev:
      return None
    return self.atfa_dev.keys_left

  def UpdateATFAKeysLeft(self, is_som_key):
    return self._atfa_dev_manager.UpdateKeysLeft(is_som_key)

  def RebootATFA(self):
    return self._atfa_dev_manager.Reboot()

  def ShutdownATFA(self):
    return self._atfa_dev_manager.Shutdown()

  def ProcessATFAKey(self):
    return self._atfa_dev_manager.ProcessKey()

  def UpdateATFA(self):
    return self._atfa_dev_manager.Update()

  def PurgeATFAKey(self, is_som_key):
    return self._atfa_dev_manager.PurgeKey(is_som_key)

  def PrepareFile(self, file_type):
    return self._atfa_dev_manager.PrepareFile(file_type)

  def GetATFASerial(self):
    return self._atfa_dev_manager.GetSerial()

  def ListDevices(self, sort_by=SORT_BY_LOCATION):
    """Get device list.

    Get the serial number of the ATFA device and the target device. If the
    device does not exist, the returned serial number would be None.

    Args:
      sort_by: The field to sort by.
    """
    # ListDevices returns a list of USBHandles
    device_serials = self._fastboot_device_controller.ListDevices()
    self.UpdateDevices(device_serials)
    self._HandleRebootCallbacks()
    self._SortTargetDevices(sort_by)

  def UpdateDevices(self, device_serials):
    """Update device list.

    Args:
      device_serials: The device serial numbers.
    """
    self._UpdateSerials(device_serials)
    self._HandleSerials()

  @staticmethod
  def _SerialAsKey(device):
    return device.serial_number

  @staticmethod
  def _LocationAsKey(device):
    if device.location is None:
      return ''
    return device.location

  def _SortTargetDevices(self, sort_by):
    """Sort the target device list according to sort_by field.

    Args:
      sort_by: The field to sort by, possible values are:
        self.SORT_BY_LOCATION and self.SORT_BY_SERIAL.
    """
    if sort_by == self.SORT_BY_LOCATION:
      self.target_devs.sort(key=AtftManager._LocationAsKey)
    elif sort_by == self.SORT_BY_SERIAL:
      self.target_devs.sort(key=AtftManager._SerialAsKey)

  def _UpdateSerials(self, device_serials):
    """Update the stored pending_serials and stable_serials.

    Note that we cannot check status as soon as the fastboot device is found
    since the device may not be ready yet. So we put the new devices into the
    pending state. Once we see the device again in the next refresh, we add that
    device. If that device is not seen in the next refresh, we remove it from
    pending. This makes sure that the device would have a refresh interval time
    after it's recognized as a fastboot device until it's issued command.

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
      self._AddNewAtfa(atfa_serial)

    # Remove those devices that are not in new targets and not rebooting.
    self.target_devs = [
        device for device in self.target_devs
        if (device.serial_number in new_targets or
            device.provision_status == ProvisionStatus.REBOOT_ING)
    ]

    common_serials = [device.serial_number for device in self.target_devs]

    # Create new device object for newly added devices.
    self._serial_mapper.refresh_serial_map()
    for serial in new_targets:
      if serial not in common_serials:
        self.target_devs.append(self._CreateNewTargetDevice(serial))

  def _CreateNewTargetDevice(self, serial, check_status=True):
    """Create a new target device object.

    Args:
      serial: The serial number for the new target device.
      check_status: Whether to check provision status for the target device.
    Returns:
      The created new target device.
    Raises:
      DeviceCreationException: When error happens when creating device.
    """
    try:
      controller = self._fastboot_device_controller(serial)
      location = self._serial_mapper.get_location(serial)

      new_target_dev = DeviceInfo(controller, serial, location)
      if check_status:
        self.CheckProvisionStatus(new_target_dev)
      return new_target_dev
    except FastbootFailure as e:
      self.stable_serials.remove(serial)
      raise DeviceCreationException(e.msg, new_target_dev)

  def _AddNewAtfa(self, atfa_serial):
    """Create a new ATFA device object.

    If the OS variable on the ATFA device is not the same as the host OS
    version, we would use set the correct OS version.

    Args:
      atfa_serial: The serial number of the ATFA device to be added.
    Raises:
      FastbootFailure: When fastboot command fails.
      OsVersionNotAvailableException: When we cannot get the atfa version.
      OsVersionNotCompatibleException: When the atfa version is not compatible.
    """
    self._serial_mapper.refresh_serial_map()
    controller = self._fastboot_device_controller(atfa_serial)
    location = self._serial_mapper.get_location(atfa_serial)
    atfa_dev = DeviceInfo(controller, atfa_serial, location)
    try:
      # Issue a command that basically do nothing to see if the ATFA is indeed
      # booted up to prevent further fastboot failure.
      # This command actually returns the fastboot version but we ignore it.
      atfa_dev.GetVar('version')
    except FastbootFailure:
      return
    self.atfa_dev = atfa_dev
    if self.COMPATIBLE_ATFA_VERSION:
      try:
        atfa_version = int(atfa_dev.GetVar('os-version'))
        required_version = self.COMPATIBLE_ATFA_VERSION
        if atfa_version < required_version:
          raise OsVersionNotCompatibleException(atfa_dev, atfa_version)
      except FastbootFailure as e:
        raise OsVersionNotAvailableException(atfa_dev)

  def _HandleRebootCallbacks(self):
    """Handle the callback functions after the reboot."""
    success_serials = []
    for serial in self._reboot_callbacks:
      if serial in self.stable_serials:
        callback_lock = self._reboot_callbacks[serial].lock
        # Make sure the timeout callback would not be called at the same time.
        if callback_lock and callback_lock.acquire(False):
          success_serials.append(serial)

    for serial in success_serials:
      self._reboot_callbacks[serial].success()

  def _ParseStateString(self, state_string):
    """Parse the string returned by 'at-vboot-state' to a key-value map.

    Args:
      state_string: The string returned by oem at-vboot-state command.

    Returns:
      A key-value map.
    """
    state_map = {}
    lines = state_string.splitlines()
    for line in lines:
      if line.startswith(BOOTLOADER_STRING):
        key_value = re.split(r':[\s]*|=', line.replace(BOOTLOADER_STRING, ''))
        if len(key_value) == 2:
          state_map[key_value[0]] = key_value[1]
    return state_map

  def CheckProvisionStatus(self, target_dev):
    """Check whether the target device has been provisioned.

    Args:
      target_dev: The target device (DeviceInfo).
    Raises:
      FastbootFailure: When fastboot command fails.
    """
    state_string = target_dev.GetVar('at-vboot-state')

    target_dev.provision_status = ProvisionStatus.IDLE
    target_dev.provision_state = ProvisionState()

    status_set = False

    try:
      at_attest_uuid = target_dev.GetVar('at-attest-uuid')
      # TODO(shanyu): We only need empty string here
      # NOT_PROVISIONED is for test purpose.
      if at_attest_uuid and at_attest_uuid != 'NOT_PROVISIONED':
        target_dev.at_attest_uuid = at_attest_uuid
        target_dev.provision_status = ProvisionStatus.PROVISION_SUCCESS
        status_set = True
        target_dev.provision_state.product_provisioned = True
    except FastbootFailure:
      # Some board might gives error if at-attest-uuid is not set.
      pass

    # state_string should be in format:
    # (bootloader) bootloader-locked: 1
    # (bootloader) bootloader-min-versions: -1,0,3
    # (bootloader) avb-perm-attr-set: 1
    # (bootloader) avb-locked: 0
    # (bootloader) avb-unlock-disabled: 0
    # (bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2
    if not state_string:
      return
    state_map = self._ParseStateString(state_string)
    if state_map.get('avb-locked') and state_map['avb-locked'] == '1':
      if not status_set:
        target_dev.provision_status = ProvisionStatus.LOCKAVB_SUCCESS
        status_set = True
      target_dev.provision_state.avb_locked = True

    status_set = self.CheckSomKeyStatus(target_dev, status_set)

    if (state_map.get('avb-perm-attr-set') and
        state_map['avb-perm-attr-set'] == '1'):
      if not status_set:
        target_dev.provision_status = ProvisionStatus.FUSEATTR_SUCCESS
        status_set = True
      target_dev.provision_state.avb_perm_attr_set = True

    if (state_map.get('bootloader-locked') and
        state_map['bootloader-locked'] == '1'):
      if not status_set:
        target_dev.provision_status = ProvisionStatus.FUSEVBOOT_SUCCESS
      target_dev.provision_state.bootloader_locked = True

  def CheckSomKeyStatus(self, target_dev, status_set):
    """Checks whether the target device has som key.

    Args:
      target_dev: The target device (DeviceInfo).
      status_set: Whether a successful status has already been set.
    Return: Whether contains som key.
    """

    tmp_file = tempfile.NamedTemporaryFile(delete=False)
    tmp_file.close()
    ca_request_file = tmp_file.name
    try:
      algorithm_list = self._GetAlgorithmList(target_dev)
      algorithm = self._ChooseAlgorithm(algorithm_list)
      if algorithm == EncryptionAlgorithm.ALGORITHM_CURVE25519:
        op_start_file = os.path.join(
            _GetCurrentPath(), 'operation_start_x25519.bin')
      else:
        op_start_file = os.path.join(
            _GetCurrentPath(), 'operation_start_p256.bin')
      target_dev.Download(op_start_file)
      target_dev.Oem('at-get-ca-request')
      target_dev.Upload(ca_request_file)
    except (FastbootFailure, NoAlgorithmAvailableException):
      # If some command fail while trying to check som key status, we assume
      # som key is not there
      os.unlink(ca_request_file)
      return status_set

    try:
      file_size = os.path.getsize(ca_request_file)
    except os.error:
      os.unlink(ca_request_file)
      return status_set
    os.unlink(ca_request_file)
    # cleartext header                            8
    # cleartext device ephemeral public key       33
    # cleartext GCM IV                            12
    # cleartext inner ca request length           4
    # encrypted header                            8
    # encrypted SOM key certificate chain         variable
    # encrypted SOM key authentication signature  variable
    # encrypted product ID SHA256 hash            32
    # encrypted RSA public key                    variable
    # encrypted ECDSA public key                  variable
    # encrypted edDSA public key                  variable
    # cleartext GCM tag                           16
    min_message_length = (
        _HEADER_LEN + _ECDH_KEY_LEN + _GCM_IV_LEN + _VAR_LEN + _HEADER_LEN +
        _VAR_LEN + _VAR_LEN + _HASH_LEN + _VAR_LEN + _VAR_LEN +
        _VAR_LEN + _GCM_TAG_LEN)
    # TODO: We only check response size here. Need to add more robust check.
    # If size is larger than minimum size, something is in the key cert field.
    if file_size > min_message_length:
      target_dev.provision_state.som_provisioned = True
      if not status_set:
        target_dev.provision_status = ProvisionStatus.SOM_PROVISION_SUCCESS
      return True
    else:
      return status_set

  def TransferContent(self, src, dst):
    """Transfer content from a device to another device.

    Download file from one device and store it into a tmp file. Upload file from
    the tmp file onto another device.

    Args:
      src: The source device to be copied from.
      dst: The destination device to be copied to.
    Raises:
      FastbootFailure: When fastboot command fails.
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
      The DeviceInfo object for the device. None if not exists.
    """
    for device in self.target_devs:
      if device.serial_number == serial:
        return device

    return None

  def Provision(self, target, is_som_key):
    """Provision the key to the target device.

    1. Get supported encryption algorithm
    2. Send start-provisioning message to ATFA
    3. Transfer content from ATFA to target
    4. Send at-get-ca-request to target
    5. Transfer content from target to ATFA
    6. Send finish-provisioning message to ATFA
    7. Transfer content from ATFA to target
    8. Send at-set-ca-response message to target

    Args:
      target: The target device to be provisioned to.
      is_som_key: Whether provision som key (or product key).
    Raises:
      DeviceNotFoundException: When a device is not available.
      FastbootFailure: When fastboot command fails.
    """
    try:
      if not is_som_key:
        target.provision_status = ProvisionStatus.PROVISION_ING
      else:
        target.ProvisionStatus = ProvisionStatus.SOM_PROVISION_ING
      atfa = self.atfa_dev
      AtftManager.CheckDevice(atfa)
      # Set the ATFA's time first.
      self._atfa_dev_manager.SetTime()
      algorithm_list = self._GetAlgorithmList(target)
      algorithm = self._ChooseAlgorithm(algorithm_list)
      # First half of the DH key exchange
      if not is_som_key:
        atfa.Oem('start-provisioning ' + str(algorithm))
      else:
        atfa.Oem('start-provisioning ' + str(algorithm) +
                 ' ' + str(_OPERATIONS['ISSUE_SOM']))
      self.TransferContent(atfa, target)
      # Second half of the DH key exchange
      target.Oem('at-get-ca-request')
      self.TransferContent(target, atfa)
      # Encrypt and transfer key bundle
      atfa.Oem('finish-provisioning')
      self.TransferContent(atfa, target)
      # Provision the key on device
      target.Oem('at-set-ca-response')

      # After a success provision, the status should be updated.
      self.CheckProvisionStatus(target)
      if not is_som_key and not target.provision_state.product_provisioned:
        raise FastbootFailure('Status not updated.')
      if is_som_key and not target.provision_state.som_provisioned:
        raise FastbootFailure('Status not updated.')
    except (FastbootFailure, DeviceNotFoundException) as e:
      if not is_som_key:
        target.provision_status = ProvisionStatus.PROVISION_FAILED
      else:
        target.provision_status = ProvisionStatus.SOM_PROVISION_FAILED
      raise e

  def FuseVbootKey(self, target):
    """Fuse the verified boot key to the target device.

    Args:
      target: The target device.
    Raises:
      FastbootFailure: When fastboot command fails.
      ProductNotSpecified Exception: When product is not specified.
    """
    if self.product_info:
      vboot_key = self.product_info.vboot_key
    elif self.som_info:
      vboot_key = self.som_info.vboot_key
    else:
      target.provision_status = ProvisionStatus.FUSEVBOOT_FAILED
      raise ProductNotSpecifiedException

    # Create a temporary file to store the vboot key.
    target.provision_status = ProvisionStatus.FUSEVBOOT_ING
    try:
      temp_file = tempfile.NamedTemporaryFile(delete=False)
      temp_file.write(vboot_key)
      temp_file.close()
      temp_file_name = temp_file.name
      target.Download(temp_file_name)
      # Delete the temporary file.
      os.remove(temp_file_name)
      target.Oem('fuse at-bootloader-vboot-key')

    except FastbootFailure as e:
      target.provision_status = ProvisionStatus.FUSEVBOOT_FAILED
      raise e

  def FusePermAttr(self, target):
    """Fuse the permanent attributes to the target device.

    Args:
      target: The target device.
    Raises:
      FastbootFailure: When fastboot command fails.
      ProductNotSpecified Exception: When product is not specified.
    """
    if not self.product_info:
      target.provision_status = ProvisionStatus.FUSEATTR_FAILED
      raise ProductNotSpecifiedException
    try:
      target.provision_status = ProvisionStatus.FUSEATTR_ING
      temp_file = tempfile.NamedTemporaryFile(delete=False)
      temp_file.write(self.product_info.product_attributes)
      temp_file.close()
      temp_file_name = temp_file.name
      target.Download(temp_file_name)
      os.remove(temp_file_name)
      target.Oem('fuse at-perm-attr')

      self.CheckProvisionStatus(target)
      if not target.provision_state.avb_perm_attr_set:
        raise FastbootFailure('Status not updated')

    except FastbootFailure as e:
      target.provision_status = ProvisionStatus.FUSEATTR_FAILED
      raise e

  def LockAvb(self, target):
    """Lock the android verified boot for the target.

    Args:
      target: The target device.
    Raises:
      FastbootFailure: When fastboot command fails.
    """
    try:
      target.provision_status = ProvisionStatus.LOCKAVB_ING
      target.Oem('at-lock-vboot')
      self.CheckProvisionStatus(target)
      if not target.provision_state.avb_locked:
        raise FastbootFailure('Status not updated')
    except FastbootFailure as e:
      target.provision_status = ProvisionStatus.LOCKAVB_FAILED
      raise e

  def UnlockAvb(self, target):
    """Unlock the android verified boot for the target.

    Args:
      target: The target device.
    Raises:
      FastbootFailure: When fastboot command fails.
    """
    try:
      target.provision_status = ProvisionStatus.UNLOCKAVB_ING
      unlock_command = 'at-unlock-vboot'
      if self.UNLOCK_CREDENTIAL:
        unlock_command += ' ' + self.UNLOCK_CREDENTIAL
      target.Oem(unlock_command)
      self.CheckProvisionStatus(target)
      if target.provision_state.avb_locked:
        raise FastbootFailure('Status not updated')
    except FastbootFailure as e:
      target.provision_status = ProvisionStatus.UNLOCKAVB_FAILED
      raise e

  def Reboot(self, target, timeout, success_callback, timeout_callback):
    """Reboot the target device.

    Args:
      target: The target device.
      timeout: The time out value.
      success_callback: The callback function called when the device reboots
        successfully.
      timeout_callback: The callback function called when the device reboots
        timeout.
    Raises:
      FastbootFailure: When fastboot command fails.

    The device would disappear from the list after reboot.
    If we see the device again within timeout, call the success_callback,
    otherwise call the timeout_callback.
    """
    try:
      target.Reboot()
      serial = target.serial_number
      location = target.location
      # We assume after the reboot the device would disappear
      self.target_devs.remove(target)
      del target
      self.stable_serials.remove(serial)
      # Create a rebooting target device that only contains serial and location.
      rebooting_target = DeviceInfo(None, serial, location)
      rebooting_target.provision_status = ProvisionStatus.REBOOT_ING
      self.target_devs.append(rebooting_target)

      reboot_callback = RebootCallback(
          timeout,
          self.RebootCallbackWrapper(success_callback, serial, True),
          self.RebootCallbackWrapper(timeout_callback, serial, False))
      self._reboot_callbacks[serial] = reboot_callback

    except FastbootFailure as e:
      target.provision_status = ProvisionStatus.REBOOT_FAILED
      raise e

  def RebootCallbackWrapper(self, callback, serial, success):
    """This wrapper function wraps the original callback function.

    Some clean up operations are added. We need to remove the handler if
    callback is called. We need to release the resource the handler requires.
    We also needs to remove the rebooting device from the target list since a
    new device would be created if the device reboot successfully.

    Args:
      callback: The original callback function.
      serial: The serial number for the device.
      success: Whether this is the success callback.
    Returns:
      An extended callback function.
    Raises:
      FastbootFailure: When fastboot command fails.
    """
    def RebootCallbackFunc(callback=callback, serial=serial, success=success):
      try:
        if success:
          self._serial_mapper.refresh_serial_map()
          new_target_device = self._CreateNewTargetDevice(serial, True)
          self.DeleteRebootingDevice(serial)
          self.target_devs.append(new_target_device)
          self.GetTargetDevice(serial).provision_status = (
              ProvisionStatus.REBOOT_SUCCESS)
        else:
          # If failed, we remove the rebooting device.
          self.DeleteRebootingDevice(serial)

        callback()
        self._reboot_callbacks[serial].Release()
        del self._reboot_callbacks[serial]
      except (DeviceCreationException, FastbootFailure) as e:
        # Release the lock so that it can be obtained again.
        self._reboot_callbacks[serial].lock.release()
        # This exception would be bubbled up to the ListDevices function.
        raise e

    return RebootCallbackFunc

  def DeleteRebootingDevice(self, serial):
    """Delete the rebooting target device from target device list.

    Args:
      serial: The serial number for the rebooting device.
    """
    rebooting_dev = self.GetTargetDevice(serial)
    if rebooting_dev:
      # We only remove the rebooting device if a new device is created
      # successfully.
      self.target_devs.remove(rebooting_dev)
      del rebooting_dev

  def _GetAlgorithmList(self, target):
    """Get the supported algorithm list.

    Get the available algorithm list using getvar at-attest-dh
    at_attest_dh should be in format 1:p256,2:curve25519
    or 1:p256
    or 2:curve25519.

    Args:
      target: The target device to check for supported algorithm.
    Returns:
      A list of available algorithms.
      Options are ALGORITHM_P256 or ALGORITHM_CURVE25519
    """
    at_attest_dh = target.GetVar('at-attest-dh')
    if not at_attest_dh:
      return []
    algorithm_strings = at_attest_dh.split(',')
    algorithm_list = []
    for algorithm_string in algorithm_strings:
      algorithm_list.append(int(algorithm_string.split(':')[0]))
    return algorithm_list

  def _ChooseAlgorithm(self, algorithm_list):
    """Choose the encryption algorithm to use for key provisioning.

    We favor ALGORITHM_CURVE25519 over ALGORITHM_P256

    Args:
      algorithm_list: The list containing all available algorithms.
    Returns:
      The selected available algorithm
    Raises:
      NoAlgorithmAvailableException:
        When there's no available valid algorithm to use.
    """
    if not algorithm_list:
      raise NoAlgorithmAvailableException()
    if EncryptionAlgorithm.ALGORITHM_CURVE25519 in algorithm_list:
      return EncryptionAlgorithm.ALGORITHM_CURVE25519
    elif EncryptionAlgorithm.ALGORITHM_P256 in algorithm_list:
      return EncryptionAlgorithm.ALGORITHM_P256

    raise NoAlgorithmAvailableException()

  def ProcessAttributesFile(self, content):
    """Process the product/som attributes file.

    The product file should follow the following JSON format:
      {
        "productName": "",
        "productDescription": "",
        "productConsoleId": "",
        "productPermanentAttribute": "",
        "bootloaderPublicKey": "",
        "creationTime": ""
      }

    The som file should follow the following JSON format:
      {
        "productName": "",
        "productDescription": "",
        "productConsoleId": "",
        "somId": "",
        "creationTime": ""
      }

    Args:
      content: The content of the product attributes file.
    Raises:
      ProductAttributesFileFormatError: When the file format is wrong.
    """
    try:
      file_object = json.loads(content)
    except ValueError:
      raise ProductAttributesFileFormatError(
          'Wrong JSON format!')
    product_name = file_object.get(self.JSON_PRODUCT_NAME)
    attribute_string = file_object.get(self.JSON_PRODUCT_ATTRIBUTE)
    vboot_key_string = file_object.get(self.JSON_VBOOT_KEY)
    som_id_string = file_object.get(self.JSON_SOM_ID)
    if (not product_name or
        (not attribute_string and not som_id_string) or not vboot_key_string):
      raise ProductAttributesFileFormatError(
          'Essential field missing!')
    try:
      vboot_key_array = bytearray(base64.standard_b64decode(vboot_key_string))
    except TypeError:
        raise ProductAttributesFileFormatError(
            'Incorrect Base64 encoding for verified boot key')

    # Clear previous information.
    self.product_info = None
    self.som_info = None
    if attribute_string:
      # This is a product attribute file.
      try:
        attribute = base64.standard_b64decode(attribute_string)
        attribute_array = bytearray(attribute)
        if self.EXPECTED_ATTRIBUTE_LENGTH != len(attribute_array):
          raise ProductAttributesFileFormatError(
              'Incorrect permanent product attributes length')

        # We only need the last 16 byte for product ID
        # We store the hex representation of the product ID
        product_id = self._ByteToHex(attribute_array[-16:])

      except TypeError:
        raise ProductAttributesFileFormatError(
            'Incorrect Base64 encoding for permanent product attributes')

      self.product_info = ProductInfo(product_id, product_name, attribute_array,
                                      vboot_key_array)
    else:
      # This is a som attribute file
      self.som_info = SomInfo(som_id_string, product_name, vboot_key_array)


  def _ByteToHex(self, byte_array):
    """Transform a byte array into a hex string."""
    return ''.join('{:02x}'.format(x) for x in byte_array)

  @staticmethod
  def CheckDevice(device):
    """Check if the device is a connected fastboot device.

    Args:
      device: The device to be checked.
    Raises:
      DeviceNotFoundException: When the device is not found
    """
    if device is None:
      raise DeviceNotFoundException()


class AtfaDeviceManager(object):
  """The class to manager ATFA device related operations."""

  def __init__(self, atft_manager):
    """Initiate the atfa device manager using the at-factory-tool manager.

    Args:
      atft_manager: The at-factory-tool manager that
        includes this atfa device manager.
    """
    self.atft_manager = atft_manager

  def GetSerial(self):
    """Issue fastboot command to get serial number for the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found.
      FastbootFailure: When fastboot command fails.
    """
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    return self.atft_manager.atfa_dev.GetVar('serial')

  def ProcessKey(self):
    """Ask the ATFA device to process the stored key bundle.

    Raises:
      DeviceNotFoundException: When the device is not found.
      FastbootFailure: When fastboot command fails.
    """
    # Need to set time first so that certificates would validate.
    # Set time would check atfa_dev device.
    self.SetTime()
    self.atft_manager.atfa_dev.Oem('keybundle')

  def Update(self):
    """Update the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found.
      FastbootFailure: When fastboot command fails.
    """
    # Set time would check atfa_dev device.
    self.SetTime()
    self.atft_manager.atfa_dev.Oem('update')

  def Reboot(self):
    """Reboot the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found.
      FastbootFailure: When fastboot command fails.
    """
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    self.atft_manager.atfa_dev.Oem('reboot')

  def Shutdown(self):
    """Shutdown the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found.
      FastbootFailure: When fastboot command fails.
    """
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    self.atft_manager.atfa_dev.Oem('shutdown')

  def UpdateKeysLeft(self, is_som_key):
    """Update the number of available AT keys for the current product.

    Need to use GetCachedATFAKeysLeft() function to get the number of keys left.
    If some error happens, keys_left would be set to -1 to prevent checking
    again.

    Args:
      is_som_key: Whether checking number of som keys (or product keys).
    Raises:
      FastbootFailure: When fastboot command fails.
      ProductNotSpecifiedException: When product is not specified.
    """
    if not is_som_key and self.atft_manager.product_info:
      product_som_id = self.atft_manager.product_info.product_id
      command = 'num-keys '
    elif is_som_key and self.atft_manager.som_info:
      product_som_id = self.atft_manager.som_info.som_id
      command = 'num-som-keys '
    else:
      raise ProductNotSpecifiedException()

    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    try:
      out = self.atft_manager.atfa_dev.Oem(command + product_som_id, True)
      # Note: use splitlines instead of split('\n') to prevent '\r\n' problem on
      # windows.
      for line in out.splitlines():
        if line.startswith('(bootloader) '):
          try:
            self.atft_manager.atfa_dev.keys_left = int(
                line.replace('(bootloader) ', ''))
            return
          except ValueError:
            raise FastbootFailure(
                'ATFA device response has invalid format')

      raise FastbootFailure('ATFA device response has invalid format')
    except FastbootFailure as e:
      if ('No matching available products' in e.msg or
          'No matching available SoMs' in e.msg):
        # If there's no matching product key, we set keys left to 0.
        self.atft_manager.atfa_dev.keys_left = 0
        return
      else:
        # -1 means some error happens.
        self.atft_manager.atfa_dev.keys_left = -1
        raise e

  def PurgeKey(self, is_som_key):
    """Purge the key for the product

    Args:
      is_som_key: Whether to purge som key (or product key).
    Raises:
      DeviceNotFoundException: When the device is not found.
      FastbootFailure: When fastboot command fails.
      ProductNotSpecifiedException: When product is not specified.
    """
    if not is_som_key and self.atft_manager.product_info:
      product_som_id = self.atft_manager.product_info.product_id
      command = 'purge '
    elif is_som_key and self.atft_manager.som_info:
      product_som_id = self.atft_manager.som_info.som_id
      command = 'purge-som '
    else:
      raise ProductNotSpecifiedException()
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    self.atft_manager.atfa_dev.Oem(command + product_som_id)

  def SetTime(self):
    """Inject the host time into the ATFA device.

    Raises:
      DeviceNotFoundException: When the device is not found.
      FastbootFailure: When fastboot command fails.
    """
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    self.atft_manager.atfa_dev.Oem('set-date ' + time)

  def PrepareFile(self, file_type):
    """Prepare a file for download.

    Args:
      file_type: the type of the file to prepare. Now supports 'reg'/'audit'.
    Raises:
      DeviceNotFoundException: When the device is not found.
      FastbootFailure: When fastboot command fails.
    """
    AtftManager.CheckDevice(self.atft_manager.atfa_dev)
    self.atft_manager.atfa_dev.Oem(file_type)
