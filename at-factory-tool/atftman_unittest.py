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

"""Unit test for atft manager."""
import base64
import unittest

import atftman

from atftman import EncryptionAlgorithm
from atftman import ProductInfo
from atftman import ProvisionState
from atftman import ProvisionStatus
from atftman import SomInfo
from fastboot_exceptions import DeviceCreationException
from fastboot_exceptions import DeviceNotFoundException
from fastboot_exceptions import FastbootFailure
from fastboot_exceptions import NoAlgorithmAvailableException
from fastboot_exceptions import OsVersionNotAvailableException
from fastboot_exceptions import OsVersionNotCompatibleException
from fastboot_exceptions import ProductAttributesFileFormatError
from fastboot_exceptions import ProductNotSpecifiedException
from mock import call
from mock import MagicMock
from mock import patch
import os

files = []


class AtftManTest(unittest.TestCase):
  ATFA_TEST_SERIAL = 'ATFA_TEST_SERIAL'
  TEST_TMP_FOLDER = '/tmp/TMPTEST/'
  TEST_SERIAL = 'TEST_SERIAL'
  TEST_SERIAL2 = 'TEST_SERIAL2'
  TEST_SERIAL3 = 'TEST_SERIAL3'
  TEST_UUID = 'TEST-UUID'
  TEST_LOCATION = 'BUS1-PORT1'
  TEST_LOCATION2 = 'BUS2-PORT1'
  TEST_LOCATION3 = 'BUS1-PORT2'
  TEST_ID = '00000000000000000000000000000000'
  TEST_ID_ARRAY = bytearray.fromhex(TEST_ID)
  TEST_NAME = 'name'
  TEST_FILE_NAME = 'filename'
  TEST_ATTRIBUTE_ARRAY = bytearray(1052)
  TEST_VBOOT_KEY_ARRAY = bytearray(128)
  TEST_ATTRIBUTE_STRING = base64.standard_b64encode(TEST_ATTRIBUTE_ARRAY)
  TEST_VBOOT_KEY_STRING = base64.standard_b64encode(TEST_VBOOT_KEY_ARRAY)

  class FastbootDeviceTemplate(object):

    @staticmethod
    def ListDevices():
      pass

    def __init__(self, serial_number):
      self.serial_number = serial_number

    def Oem(self, oem_command, err_to_out):
      pass

    def Upload(self, file_path):
      pass

    def GetVar(self, var):
      pass

    def Download(self, file_path):
      pass

    def Disconnect(self):
      pass

    def GetHostOs(self):
      return 'Windows'

    def __del__(self):
      pass

  def MockInit(self, serial_number):
    mock_instance = MagicMock()
    mock_instance.serial_number = serial_number
    mock_instance.GetHostOs = MagicMock()
    mock_instance.GetHostOs.return_value = 'Windows'
    return mock_instance

  def setUp(self):
    self.mock_serial_mapper = MagicMock()
    self.mock_serial_instance = MagicMock()
    self.mock_serial_mapper.return_value = self.mock_serial_instance
    self.mock_serial_instance.get_serial_map.return_value = []
    self.status_map = {}
    self.mock_timer_instance = None
    self.configs = {}
    self.configs['ATFA_REBOOT_TIMEOUT'] = 30
    self.configs['DEFAULT_KEY_THRESHOLD'] = 100
    self.configs['COMPATIBLE_ATFA_VERSION'] = 10
    self.configs['UNLOCK_CREDENTIAL'] = None

  # Test ProvisionStatus
  def GetAllProvisionStatus(self):
    return [ProvisionStatus.IDLE,
            ProvisionStatus.WAITING,
            ProvisionStatus.FUSEVBOOT_IN_PROGRESS,
            ProvisionStatus.FUSEVBOOT_SUCCESS,
            ProvisionStatus.FUSEVBOOT_FAILED,
            ProvisionStatus.REBOOT_IN_PROGRESS,
            ProvisionStatus.REBOOT_SUCCESS,
            ProvisionStatus.REBOOT_FAILED,
            ProvisionStatus.FUSEATTR_IN_PROGRESS,
            ProvisionStatus.FUSEATTR_SUCCESS,
            ProvisionStatus.FUSEATTR_FAILED,
            ProvisionStatus.LOCKAVB_IN_PROGRESS,
            ProvisionStatus.LOCKAVB_SUCCESS,
            ProvisionStatus.LOCKAVB_FAILED,
            ProvisionStatus.PROVISION_IN_PROGRESS,
            ProvisionStatus.PROVISION_SUCCESS,
            ProvisionStatus.PROVISION_FAILED,
            ProvisionStatus.UNLOCKAVB_IN_PROGRESS,
            ProvisionStatus.UNLOCKAVB_SUCCESS,
            ProvisionStatus.UNLOCKAVB_FAILED]

  def testProvisionStatus(self):
    status_list = self.GetAllProvisionStatus()
    for status in status_list:
      self.assertNotEqual('', ProvisionStatus.ToString(status, 0))
      self.assertNotEqual('', ProvisionStatus.ToString(status, 1))
    self.assertEqual(
        True, ProvisionStatus.isSuccess(ProvisionStatus.LOCKAVB_SUCCESS))
    self.assertEqual(
        False, ProvisionStatus.isProcessing(ProvisionStatus.LOCKAVB_SUCCESS))
    self.assertEqual(
        False, ProvisionStatus.isFailed(ProvisionStatus.LOCKAVB_SUCCESS))
    self.assertEqual(
        False, ProvisionStatus.isSuccess(ProvisionStatus.FUSEATTR_IN_PROGRESS))
    self.assertEqual(
        True, ProvisionStatus.isProcessing(ProvisionStatus.FUSEATTR_IN_PROGRESS))
    self.assertEqual(
        False, ProvisionStatus.isFailed(ProvisionStatus.FUSEATTR_IN_PROGRESS))
    self.assertEqual(
        False, ProvisionStatus.isSuccess(ProvisionStatus.PROVISION_FAILED))
    self.assertEqual(
        False, ProvisionStatus.isProcessing(ProvisionStatus.PROVISION_FAILED))
    self.assertEqual(
        True, ProvisionStatus.isFailed(ProvisionStatus.PROVISION_FAILED))

  # Test AtftManager.ListDevices
  class MockInstantTimer(object):

    def __init__(self, timeout, callback):
      self.timeout = timeout
      self.callback = callback

    def start(self):
      self.callback()

  def MockCreateInstantTimer(self, timeout, callback):
    return self.MockInstantTimer(timeout, callback)

  def MockAddNewAtfa(self, serial, atft, mock_fastboot):
    mock_fastboot(self)
    atft._serial_mapper.refresh_serial_map()
    atft._atfa_dev_manager.SetATFADevice(atftman.DeviceInfo(
        MagicMock(), serial, atft._serial_mapper.get_location(serial)))

  @patch('threading.Timer')
  @patch('__main__.AtftManTest.FastbootDeviceTemplate.ListDevices')
  def testListDevicesNormal(self, mock_list_devices, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    # Mock creating a new atfa device.
    atft_manager._AddNewAtfa = (
        lambda serial, atft=atft_manager, mock_fastboot=MagicMock():
        self.MockAddNewAtfa(serial, atft_manager, mock_fastboot)
    )
    atft_manager.CheckProvisionStatus = MagicMock()
    mock_list_devices.return_value = [self.TEST_SERIAL, self.ATFA_TEST_SERIAL]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    # After adding a new target device, need to check its status.
    atft_manager.CheckProvisionStatus.assert_called_once()
    self.assertEqual(
        atft_manager.GetATFADevice().serial_number, self.ATFA_TEST_SERIAL)
    self.assertEqual(1, len(atft_manager.target_devs))
    self.assertEqual(atft_manager.target_devs[0].serial_number,
                     self.TEST_SERIAL)

  @patch('threading.Timer')
  @patch('__main__.AtftManTest.FastbootDeviceTemplate.ListDevices')
  def testListDevicesErrorCreation(self, mock_list_devices, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    # Mock creating a new atfa device.
    atft_manager._AddNewAtfa = (
        lambda serial, atft=atft_manager, mock_fastboot=MagicMock():
        self.MockAddNewAtfa(serial, atft_manager, mock_fastboot)
    )
    # While checking provision status, there is an error
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = FastbootFailure('')
    mock_list_devices.return_value = [self.TEST_SERIAL, self.ATFA_TEST_SERIAL]
    atft_manager.ListDevices()
    # Need to raise the DeviceCreationException.
    with self.assertRaises(DeviceCreationException):
      atft_manager.ListDevices()
    # After adding a new target device, need to check its status.
    atft_manager.CheckProvisionStatus.assert_called_once()
    self.assertEqual(
        atft_manager.GetATFADevice().serial_number, self.ATFA_TEST_SERIAL)
    self.assertEqual(0, len(atft_manager.target_devs))

  @patch('threading.Timer')
  @patch('__main__.AtftManTest.FastbootDeviceTemplate.ListDevices')
  def testListDevicesATFA(self, mock_list_devices, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    atft_manager._AddNewAtfa = (
        lambda serial, atft=atft_manager, mock_fastboot=MagicMock():
        self.MockAddNewAtfa(serial, atft_manager, mock_fastboot)
    )
    mock_list_devices.return_value = [self.ATFA_TEST_SERIAL]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    self.assertEqual(
        atft_manager.GetATFADevice().serial_number, self.ATFA_TEST_SERIAL)
    self.assertEqual(0, len(atft_manager.target_devs))

  @patch('threading.Timer')
  @patch('__main__.AtftManTest.FastbootDeviceTemplate.ListDevices')
  def testListDevicesTarget(self, mock_list_devices, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_list_devices.return_value = [self.TEST_SERIAL]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    self.assertEqual(
        atft_manager.GetATFADevice(), None)
    self.assertEqual(1, len(atft_manager.target_devs))
    self.assertEqual(atft_manager.target_devs[0].serial_number,
                     self.TEST_SERIAL)

  @patch('threading.Timer')
  @patch('__main__.AtftManTest.FastbootDeviceTemplate.ListDevices')
  def testListDevicesMultipleTargets(self, mock_list_devices, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_list_devices.return_value = [self.TEST_SERIAL, self.TEST_SERIAL2]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    self.assertEqual(atft_manager.GetATFADevice(), None)
    self.assertEqual(2, len(atft_manager.target_devs))
    self.assertEqual(atft_manager.target_devs[0].serial_number,
                     self.TEST_SERIAL)
    self.assertEqual(atft_manager.target_devs[1].serial_number,
                     self.TEST_SERIAL2)

  @patch('threading.Timer')
  def testListDevicesChangeNorm(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(mock_fastboot, self.mock_serial_mapper,
                                       self.configs)
    atft_manager._AddNewAtfa = (
        lambda serial, atft=atft_manager, mock_fastboot=mock_fastboot:
        self.MockAddNewAtfa(serial, atft_manager, mock_fastboot)
    )
    mock_fastboot.ListDevices.return_value = [self.ATFA_TEST_SERIAL]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    mock_fastboot.ListDevices.return_value = [self.TEST_SERIAL]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    self.assertEqual(atft_manager.GetATFADevice(), None)
    self.assertEqual(1, len(atft_manager.target_devs))
    self.assertEqual(atft_manager.target_devs[0].serial_number,
                     self.TEST_SERIAL)
    self.assertEqual(2, mock_fastboot.call_count)

  @patch('threading.Timer')
  def testListDevicesChangeAdd(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(
        mock_fastboot, self.mock_serial_mapper, self.configs)
    atft_manager._AddNewAtfa = (
        lambda serial, atft=atft_manager, mock_fastboot=mock_fastboot:
        self.MockAddNewAtfa(serial, atft_manager, mock_fastboot)
    )
    mock_fastboot.ListDevices.return_value = [self.ATFA_TEST_SERIAL]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    mock_fastboot.ListDevices.return_value = [
        self.ATFA_TEST_SERIAL, self.TEST_SERIAL
    ]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    self.assertEqual(
        atft_manager.GetATFADevice().serial_number, self.ATFA_TEST_SERIAL)
    self.assertEqual(1, len(atft_manager.target_devs))
    self.assertEqual(
        atft_manager.target_devs[0].serial_number, self.TEST_SERIAL)

  @patch('threading.Timer')
  def testListDevicesChangeAddATFA(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(
        mock_fastboot, self.mock_serial_mapper, self.configs)
    atft_manager._AddNewAtfa = (
        lambda serial, atft=atft_manager, mock_fastboot=mock_fastboot:
        self.MockAddNewAtfa(serial, atft_manager, mock_fastboot)
    )
    mock_fastboot.ListDevices.return_value = [self.TEST_SERIAL]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    mock_fastboot.ListDevices.return_value = [
        self.ATFA_TEST_SERIAL, self.TEST_SERIAL
    ]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    self.assertEqual(
        atft_manager.GetATFADevice().serial_number, self.ATFA_TEST_SERIAL)
    self.assertEqual(1, len(atft_manager.target_devs))
    self.assertEqual(
        atft_manager.target_devs[0].serial_number, self.TEST_SERIAL)

  @patch('threading.Timer')
  def testListDevicesChangeCommon(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(
        mock_fastboot, self.mock_serial_mapper, self.configs)
    atft_manager._AddNewAtfa = (
        lambda serial, atft=atft_manager, mock_fastboot=mock_fastboot:
        self.MockAddNewAtfa(serial, atft_manager, mock_fastboot)
    )
    mock_fastboot.ListDevices.return_value = [
        self.ATFA_TEST_SERIAL, self.TEST_SERIAL
    ]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    mock_fastboot.ListDevices.return_value = [
        self.TEST_SERIAL2, self.TEST_SERIAL
    ]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    self.assertEqual(atft_manager.GetATFADevice(), None)
    self.assertEqual(2, len(atft_manager.target_devs))
    self.assertEqual(
        atft_manager.target_devs[0].serial_number, self.TEST_SERIAL)
    self.assertEqual(
        atft_manager.target_devs[1].serial_number, self.TEST_SERIAL2)
    self.assertEqual(3, mock_fastboot.call_count)

  @patch('threading.Timer')
  def testListDevicesChangeCommonATFA(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(
        mock_fastboot, self.mock_serial_mapper, self.configs)
    atft_manager._AddNewAtfa = (
        lambda serial, atft=atft_manager, mock_fastboot=mock_fastboot:
        self.MockAddNewAtfa(serial, atft_manager, mock_fastboot)
    )
    mock_fastboot.ListDevices.return_value = [
        self.ATFA_TEST_SERIAL, self.TEST_SERIAL
    ]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    mock_fastboot.ListDevices.return_value = [
        self.ATFA_TEST_SERIAL, self.TEST_SERIAL2
    ]
    atft_manager.ListDevices()
    # First refresh, TEST_SERIAL should disappear
    self.assertEqual(0, len(atft_manager.target_devs))
    # Second refresh, TEST_SERIAL2 should be added
    atft_manager.ListDevices()
    self.assertEqual(
        self.ATFA_TEST_SERIAL, atft_manager.GetATFADevice().serial_number)
    self.assertEqual(1, len(atft_manager.target_devs))
    self.assertEqual(atft_manager.target_devs[0].serial_number,
                     self.TEST_SERIAL2)
    self.assertEqual(3, mock_fastboot.call_count)

  @patch('threading.Timer')
  def testListDevicesRemoveATFA(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(
        mock_fastboot, self.mock_serial_mapper, self.configs)
    atft_manager._AddNewAtfa = (
        lambda serial, atft=atft_manager, mock_fastboot=mock_fastboot:
        self.MockAddNewAtfa(serial, atft_manager, mock_fastboot)
    )
    mock_fastboot.ListDevices.return_value = [
        self.ATFA_TEST_SERIAL, self.TEST_SERIAL
    ]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    mock_fastboot.ListDevices.return_value = [self.TEST_SERIAL]
    atft_manager.ListDevices()
    self.assertEqual(None, atft_manager.GetATFADevice())
    self.assertEqual(2, mock_fastboot.call_count)
    self.assertEqual(atft_manager.target_devs[0].serial_number,
                     self.TEST_SERIAL)

  @patch('threading.Timer')
  def testListDevicesRemoveDevice(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(
        mock_fastboot, self.mock_serial_mapper, self.configs)
    atft_manager._AddNewAtfa = MagicMock()
    mock_fastboot.ListDevices.return_value = [
        self.ATFA_TEST_SERIAL, self.TEST_SERIAL
    ]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    atft_manager._AddNewAtfa.reset_mock()
    mock_fastboot.ListDevices.return_value = [self.ATFA_TEST_SERIAL]
    atft_manager.ListDevices()
    atft_manager._AddNewAtfa.assert_called_once_with(self.ATFA_TEST_SERIAL)
    self.assertEqual(0, len(atft_manager.target_devs))

  @patch('threading.Timer')
  def testListDevicesPendingRemove(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(mock_fastboot, self.mock_serial_mapper,
                                       self.configs)
    mock_fastboot.ListDevices.return_value = [self.TEST_SERIAL]
    atft_manager.ListDevices()
    # Just appear once, should not be in target device list.
    self.assertEqual(0, len(atft_manager.target_devs))

  @patch('threading.Timer')
  def testListDevicesPendingAdd(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(mock_fastboot, self.mock_serial_mapper,
                                       self.configs)
    mock_fastboot.ListDevices.return_value = [self.TEST_SERIAL]
    atft_manager.ListDevices()
    self.assertEqual(0, len(atft_manager.target_devs))
    mock_fastboot.ListDevices.return_value = [
        self.TEST_SERIAL, self.TEST_SERIAL2
    ]
    # TEST_SERIAL appears twice, should be in the list.
    # TEST_SERIAL2 just appears once, should not be in the list.
    atft_manager.ListDevices()
    self.assertEqual(1, len(atft_manager.target_devs))

  @patch('threading.Timer')
  def testListDevicesPendingTemp(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(mock_fastboot, self.mock_serial_mapper,
                                       self.configs)
    mock_fastboot.ListDevices.return_value = [self.TEST_SERIAL]
    atft_manager.ListDevices()
    self.assertEqual(0, len(atft_manager.target_devs))
    mock_fastboot.ListDevices.return_value = [self.TEST_SERIAL2]
    atft_manager.ListDevices()
    # Nothing appears twice.
    self.assertEqual(0, len(atft_manager.target_devs))

  def mockSetSerialMapper(self, serial_map):
    self.serial_map = {}
    for serial in serial_map:
      self.serial_map[serial.lower()] = serial_map[serial]

  def mockGetLocation(self, serial):
    serial_lower = serial.lower()
    if serial_lower in self.serial_map:
      return self.serial_map[serial_lower]
    return None

  @patch('threading.Timer')
  def testListDevicesLocation(self, mock_create_timer):
    mock_create_timer.side_effect = self.MockCreateInstantTimer
    mock_serial_mapper = MagicMock()
    smap = {
        self.ATFA_TEST_SERIAL: self.TEST_LOCATION,
        self.TEST_SERIAL: self.TEST_LOCATION2
    }
    mock_serial_instance = MagicMock()
    mock_serial_mapper.return_value = mock_serial_instance
    mock_serial_instance.refresh_serial_map.side_effect = (
        lambda serial_map=smap: self.mockSetSerialMapper(serial_map))
    mock_serial_instance.get_location.side_effect = self.mockGetLocation
    mock_fastboot = MagicMock()
    mock_fastboot.side_effect = self.MockInit
    atft_manager = atftman.AtftManager(
        mock_fastboot, mock_serial_mapper, self.configs)
    atft_manager._AddNewAtfa = (
        lambda serial, atft=atft_manager, mock_fastboot=mock_fastboot:
        self.MockAddNewAtfa(serial, atft_manager, mock_fastboot)
    )
    mock_fastboot.ListDevices.return_value = [
        self.ATFA_TEST_SERIAL, self.TEST_SERIAL
    ]
    atft_manager.ListDevices()
    atft_manager.ListDevices()
    self.assertEqual(
        atft_manager.GetATFADevice().location, self.TEST_LOCATION)
    self.assertEqual(atft_manager.target_devs[0].location, self.TEST_LOCATION2)

  # Test AtftManager.TransferContent

  @staticmethod
  def _AppendFile(file_path):
    files.append(file_path)

  @staticmethod
  def _CheckFile(file_path):
    assert file_path in files
    return True

  @staticmethod
  def _RemoveFile(file_path):
    assert file_path in files
    files.remove(file_path)

  @patch('os.rmdir')
  @patch('os.remove')
  @patch('os.path.exists')
  @patch('tempfile.mkdtemp')
  @patch('uuid.uuid1')
  @patch('__main__.AtftManTest.FastbootDeviceTemplate.Upload')
  @patch('__main__.AtftManTest.FastbootDeviceTemplate.Download')
  def testTransferContentNormal(self, mock_download, mock_upload, mock_uuid,
                                mock_create_folder, mock_exists, mock_remove,
                                mock_rmdir):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    # upload (to fs): create a temporary file
    mock_upload.side_effect = AtftManTest._AppendFile
    # download (from fs): check if the temporary file exists
    mock_download.side_effect = AtftManTest._CheckFile
    mock_exists.side_effect = AtftManTest._CheckFile
    # remove: remove the file
    mock_remove.side_effect = AtftManTest._RemoveFile
    mock_rmdir.side_effect = AtftManTest._RemoveFile
    mock_create_folder.return_value = self.TEST_TMP_FOLDER
    files.append(self.TEST_TMP_FOLDER)
    mock_uuid.return_value = self.TEST_UUID
    tmp_path = self.TEST_TMP_FOLDER + self.TEST_UUID
    src = self.FastbootDeviceTemplate(self.TEST_SERIAL)
    dst = self.FastbootDeviceTemplate(self.TEST_SERIAL)
    atft_manager.TransferContent(src, dst)
    src.Upload.assert_called_once_with(tmp_path)
    src.Download.assert_called_once_with(tmp_path)
    # we should have no temporary file at the end
    self.assertTrue(not files)

  # Test AtftManager._ChooseAlgorithm
  def testChooseAlgorithm(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    p256 = atftman.EncryptionAlgorithm.ALGORITHM_P256
    curve = atftman.EncryptionAlgorithm.ALGORITHM_CURVE25519
    algorithm = atft_manager._ChooseAlgorithm([p256, curve])
    self.assertEqual(curve, algorithm)

  def testChooseAlgorithmP256(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    p256 = atftman.EncryptionAlgorithm.ALGORITHM_P256
    algorithm = atft_manager._ChooseAlgorithm([p256])
    self.assertEqual(p256, algorithm)

  def testChooseAlgorithmCurve(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    curve = atftman.EncryptionAlgorithm.ALGORITHM_CURVE25519
    algorithm = atft_manager._ChooseAlgorithm([curve])
    self.assertEqual(curve, algorithm)

  def testChooseAlgorithmException(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    with self.assertRaises(NoAlgorithmAvailableException):
      atft_manager._ChooseAlgorithm([])

  def testChooseAlgorithmExceptionNoAvailable(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    with self.assertRaises(NoAlgorithmAvailableException):
      atft_manager._ChooseAlgorithm(['abcd'])

  # Test AtftManager._GetAlgorithmList
  def testGetAlgorithmList(self):
    mock_target = MagicMock()
    mock_target.GetVar.return_value = '1:p256,2:curve25519'
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    algorithm_list = atft_manager._GetAlgorithmList(mock_target)
    self.assertEqual(2, len(algorithm_list))
    self.assertEqual(1, algorithm_list[0])
    self.assertEqual(2, algorithm_list[1])

  # Test DeviceInfo.__eq__
  def testDeviceInfoEqual(self):
    test_device1 = atftman.DeviceInfo(None, self.TEST_SERIAL,
                                      self.TEST_LOCATION)
    test_device2 = atftman.DeviceInfo(None, self.TEST_SERIAL2,
                                      self.TEST_LOCATION2)
    test_device3 = atftman.DeviceInfo(None, self.TEST_SERIAL,
                                      self.TEST_LOCATION2)
    test_device4 = atftman.DeviceInfo(None, self.TEST_SERIAL2,
                                      self.TEST_LOCATION)
    test_device5 = atftman.DeviceInfo(None, self.TEST_SERIAL,
                                      self.TEST_LOCATION)
    self.assertEqual(test_device1, test_device5)
    self.assertNotEqual(test_device1, test_device2)
    self.assertNotEqual(test_device1, test_device3)
    self.assertNotEqual(test_device1, test_device4)

  # Test DeviceInfo.Copy
  def testDeviceInfoCopy(self):
    test_device1 = atftman.DeviceInfo(None, self.TEST_SERIAL,
                                      self.TEST_LOCATION)
    test_device2 = atftman.DeviceInfo(None, self.TEST_SERIAL2,
                                      self.TEST_LOCATION2)
    test_device3 = test_device1.Copy()
    self.assertEqual(test_device3, test_device1)
    self.assertNotEqual(test_device3, test_device2)

  # Test AtfaDeviceManager.UpdateKeysLeft
  def UpdateKeysLeft(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.product_info = MagicMock()
    atft_manager.product_info.product_id = self.TEST_ID
    mock_atfa_dev.Oem.return_value = 'TEST\n(bootloader) 100\nTEST'
    atft_manager.UpdateATFAKeysLeft(False)
    mock_atfa_dev.Oem.assert_called_once_with('num-keys ' + self.TEST_ID, True)
    self.assertEqual(100, atft_manager.GetCachedATFAKeysLeft())

  def UpdateKeysLeftSom(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.som_info = MagicMock()
    atft_manager.som_info.som_id = self.TEST_ID
    mock_atfa_dev.Oem.return_value = 'TEST\n(bootloader) 100\nTEST'
    atft_manager.UpdateATFAKeysLeft(True)
    mock_atfa_dev.Oem.assert_called_once_with('num-som-keys ' + self.TEST_ID,
                                              True)
    self.assertEqual(100, atft_manager.GetCachedATFAKeysLeft())

  def testUpdateKeysLeftCRLF(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.product_info = MagicMock()
    atft_manager.product_info.product_id = self.TEST_ID
    mock_atfa_dev.Oem.return_value = 'TEST\r\n(bootloader) 100\r\nTEST'
    atft_manager.UpdateATFAKeysLeft(False)
    mock_atfa_dev.Oem.assert_called_once_with('num-keys ' + self.TEST_ID, True)
    self.assertEqual(100, atft_manager.GetCachedATFAKeysLeft())

  def testUpdateKeysLeftNoProductId(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.product_info = None
    mock_atfa_dev.Oem.return_value = 'TEST\r\n(bootloader) 100\r\nTEST'
    with self.assertRaises(ProductNotSpecifiedException):
      atft_manager.UpdateATFAKeysLeft(False)

  def testUpdateKeysLeftNoATFA(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    atft_manager._atfa_dev_manager.SetATFADevice(None)
    atft_manager.product_info = MagicMock()
    atft_manager.product_info.product_id = self.TEST_ID
    with self.assertRaises(DeviceNotFoundException):
      atft_manager.UpdateATFAKeysLeft(False)

  def testUpdateKeysLeftInvalidFormat(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.product_info = MagicMock()
    atft_manager.product_info.product_id = self.TEST_ID
    mock_atfa_dev.Oem.return_value = 'TEST\nTEST'
    with self.assertRaises(FastbootFailure):
      atft_manager.UpdateATFAKeysLeft(False)

  def testUpdateKeysLeftInvalidNumber(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.product_info = MagicMock()
    atft_manager.product_info.product_id = self.TEST_ID
    mock_atfa_dev.Oem.return_value = 'TEST\n(bootloader) abcd\nTEST'
    with self.assertRaises(FastbootFailure):
      atft_manager.UpdateATFAKeysLeft(False)

  def testUpdateKeysLeftNoMatchingProduct(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.product_info = MagicMock()
    atft_manager.product_info.product_id = self.TEST_ID
    mock_atfa_dev.Oem.side_effect = FastbootFailure(
        'No matching available products')
    atft_manager.UpdateATFAKeysLeft(False)
    self.assertEqual(0, mock_atfa_dev.keys_left)

  def testUpdateKeysLeftNoMatchingSoM(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.som_info = MagicMock()
    atft_manager.som_info.som_id = self.TEST_ID
    mock_atfa_dev.Oem.side_effect = FastbootFailure(
        'No matching available SoMs')
    atft_manager.UpdateATFAKeysLeft(True)
    self.assertEqual(0, mock_atfa_dev.keys_left)

  # Test AtfaDeviceManager.PurgeKey
  def testPurgeKeyProduct(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.product_info = MagicMock()
    atft_manager.product_info.product_id = self.TEST_ID
    atft_manager.PurgeATFAKey(False)
    mock_atfa_dev.Oem.assert_called_once_with('purge ' + self.TEST_ID)

  def testPurgeKeySoM(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.som_info = MagicMock()
    atft_manager.som_info.som_id = self.TEST_ID
    atft_manager.PurgeATFAKey(True)
    mock_atfa_dev.Oem.assert_called_once_with('purge-som ' + self.TEST_ID)

  def testPurgeKeyProductNotSelected(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.product_info = None
    atft_manager.som_info = None
    with self.assertRaises(ProductNotSpecifiedException):
      atft_manager.PurgeATFAKey(False)
    mock_atfa_dev.Oem.assert_not_called()

  def testPurgeKeySoMNotSelected(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa_dev = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa_dev)
    atft_manager.product_info = None
    atft_manager.som_info = None
    with self.assertRaises(ProductNotSpecifiedException):
      atft_manager.PurgeATFAKey(True)
    mock_atfa_dev.Oem.assert_not_called()

  # Test AtftManager.CheckProvisionStatus
  def MockGetVar(self, variable):
    return self.status_map.get(variable)

  def testCheckProvisionStatus(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    # All initial state
    self.status_map = {}
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 0\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 0\n'
        '(bootloader) avb-locked: 0\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    mock_device = MagicMock()
    mock_device.GetVar.side_effect = self.MockGetVar
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(ProvisionStatus.IDLE, mock_device.provision_status)

    # Attestation key provisioned
    self.status_map['at-attest-uuid'] = self.TEST_UUID
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(ProvisionStatus.PROVISION_SUCCESS,
                     mock_device.provision_status)

    # AVB locked
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 0\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 0\n'
        '(bootloader) avb-locked: 1\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(ProvisionStatus.LOCKAVB_SUCCESS,
                     mock_device.provision_status)

    # Permanent attributes fused
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 0\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 1\n'
        '(bootloader) avb-locked: 0\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(ProvisionStatus.FUSEATTR_SUCCESS,
                     mock_device.provision_status)

    # Bootloader locked
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 1\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 0\n'
        '(bootloader) avb-locked: 0\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(ProvisionStatus.FUSEVBOOT_SUCCESS,
                     mock_device.provision_status)

  def testCheckProvisionStatusFormat(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    # All initial state
    self.status_map = {}
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked=1\n'
        '(bootloader) bootloader-min-versions=-1,0,3\n'
        '(bootloader) avb-perm-attr-set=0\n'
        '(bootloader) avb-locked=0\n'
        '(bootloader) avb-unlock-disabled=0\n'
        '(bootloader) avb-min-versions=0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    mock_device = MagicMock()
    mock_device.GetVar.side_effect = self.MockGetVar
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(
        ProvisionStatus.FUSEVBOOT_SUCCESS, mock_device.provision_status)
    self.assertEqual(True, mock_device.provision_state.bootloader_locked)

    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked:1\n'
        '(bootloader) bootloader-min-versions:-1,0,3\n'
        '(bootloader) avb-perm-attr-set:0\n'
        '(bootloader) avb-locked:0\n'
        '(bootloader) avb-unlock-disabled:0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    mock_device = MagicMock()
    mock_device.GetVar.side_effect = self.MockGetVar
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(
        ProvisionStatus.FUSEVBOOT_SUCCESS, mock_device.provision_status)
    self.assertEqual(True, mock_device.provision_state.bootloader_locked)

    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked:\t1\n'
        '(bootloader) bootloader-min-versions:\t-1,0,3\n'
        '(bootloader) avb-perm-attr-set:\t0\n'
        '(bootloader) avb-locked:\t0\n'
        '(bootloader) avb-unlock-disabled:\t0\n'
        '(bootloader) avb-min-versions:\t0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    mock_device = MagicMock()
    mock_device.GetVar.side_effect = self.MockGetVar
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(
        ProvisionStatus.FUSEVBOOT_SUCCESS, mock_device.provision_status)
    self.assertEqual(True, mock_device.provision_state.bootloader_locked)

  def testCheckProvisionState(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    # All initial state
    self.status_map = {}
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 0\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 0\n'
        '(bootloader) avb-locked: 0\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    mock_device = MagicMock()
    mock_device.GetVar.side_effect = self.MockGetVar
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(False, mock_device.provision_state.bootloader_locked)
    self.assertEqual(False, mock_device.provision_state.avb_perm_attr_set)
    self.assertEqual(False, mock_device.provision_state.avb_locked)
    self.assertEqual(False, mock_device.provision_state.product_provisioned)

    # Attestation key provisioned
    self.status_map['at-attest-uuid'] = self.TEST_UUID
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(False, mock_device.provision_state.bootloader_locked)
    self.assertEqual(False, mock_device.provision_state.avb_perm_attr_set)
    self.assertEqual(False, mock_device.provision_state.avb_locked)
    self.assertEqual(True, mock_device.provision_state.product_provisioned)

    # AVB locked and attestation key provisioned
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 0\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 0\n'
        '(bootloader) avb-locked: 1\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = self.TEST_UUID
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(False, mock_device.provision_state.bootloader_locked)
    self.assertEqual(False, mock_device.provision_state.avb_perm_attr_set)
    self.assertEqual(True, mock_device.provision_state.avb_locked)
    self.assertEqual(True, mock_device.provision_state.product_provisioned)
    self.assertEqual(ProvisionStatus.PROVISION_SUCCESS,
                     mock_device.provision_status)

    # Permanent attributes fused
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 0\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 1\n'
        '(bootloader) avb-locked: 0\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(False, mock_device.provision_state.bootloader_locked)
    self.assertEqual(True, mock_device.provision_state.avb_perm_attr_set)
    self.assertEqual(False, mock_device.provision_state.avb_locked)
    self.assertEqual(False, mock_device.provision_state.product_provisioned)

    # All status set
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 1\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 1\n'
        '(bootloader) avb-locked: 1\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = self.TEST_UUID
    atft_manager.CheckProvisionStatus(mock_device)
    self.assertEqual(True, mock_device.provision_state.bootloader_locked)
    self.assertEqual(True, mock_device.provision_state.avb_perm_attr_set)
    self.assertEqual(True, mock_device.provision_state.avb_locked)
    self.assertEqual(True, mock_device.provision_state.product_provisioned)
    self.assertEqual(ProvisionStatus.PROVISION_SUCCESS,
                     mock_device.provision_status)

  @patch('os.path.getsize')
  @patch('os.unlink')
  @patch('tempfile.NamedTemporaryFile')
  def testCheckSomStatusNotProvisioned(
      self, mock_create_temp_file, mock_delete_file, mock_get_size):
    self.status_map = {}
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 0\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 0\n'
        '(bootloader) avb-locked: 0\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    self.status_map['at-attest-dh'] = '1:p256;'
    mock_device = MagicMock()
    mock_device.GetVar.side_effect = self.MockGetVar
    mock_file = MagicMock()
    mock_create_temp_file.return_value = mock_file
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa = MagicMock()
    mock_device.provision_state = ProvisionState()
    mock_get_size.return_value = 133

    atft_manager.CheckProvisionStatus(mock_device)

    mock_create_temp_file.assert_called_once()
    mock_delete_file.assert_called_once_with(mock_file.name)
    mock_device.GetVar.assert_called()
    self.assertEqual(False, mock_device.provision_state.som_provisioned)

  @patch('os.path.getsize')
  @patch('os.unlink')
  @patch('tempfile.NamedTemporaryFile')
  def testCheckSomStatusProvisioned(
      self, mock_create_temp_file, mock_delete_file, mock_get_size):
    self.status_map = {}
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 1\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 1\n'
        '(bootloader) avb-locked: 0\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = ''
    self.status_map['at-attest-dh'] = '1:p256;'
    mock_device = MagicMock()
    mock_device.GetVar.side_effect = self.MockGetVar
    mock_file = MagicMock()
    mock_create_temp_file.return_value = mock_file
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa = MagicMock()
    mock_device.provision_state = ProvisionState()
    mock_get_size.return_value = 134

    atft_manager.CheckProvisionStatus(mock_device)

    mock_create_temp_file.assert_called_once()
    mock_delete_file.assert_called_once_with(mock_file.name)
    mock_device.GetVar.assert_called()
    self.assertEqual(True, mock_device.provision_state.som_provisioned)
    self.assertEqual(ProvisionStatus.SOM_PROVISION_SUCCESS,
                     mock_device.provision_status)

  @patch('os.path.getsize')
  @patch('os.unlink')
  @patch('tempfile.NamedTemporaryFile')
  def testCheckSomStatusProductProvisioned(
      self, mock_create_temp_file, mock_delete_file, mock_get_size):
    self.status_map = {}
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 0\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 0\n'
        '(bootloader) avb-locked: 0\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = self.TEST_UUID
    self.status_map['at-attest-dh'] = '1:p256;'
    mock_device = MagicMock()
    mock_device.GetVar.side_effect = self.MockGetVar
    mock_file = MagicMock()
    mock_create_temp_file.return_value = mock_file
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa = MagicMock()
    mock_device.provision_state = ProvisionState()
    mock_device.provision_status = ProvisionStatus.PROVISION_SUCCESS
    mock_get_size.return_value = 134

    atft_manager.CheckProvisionStatus(mock_device)

    mock_create_temp_file.assert_called_once()
    mock_delete_file.assert_called_once_with(mock_file.name)
    mock_device.GetVar.assert_called()
    self.assertEqual(True, mock_device.provision_state.som_provisioned)
    self.assertEqual(ProvisionStatus.PROVISION_SUCCESS,
                     mock_device.provision_status)

  @patch('os.path.getsize')
  @patch('os.unlink')
  @patch('tempfile.NamedTemporaryFile')
  def testCheckSomStatusFileNotExist(
      self, mock_create_temp_file, mock_delete_file, mock_get_size):
    self.status_map = {}
    self.status_map['at-vboot-state'] = (
        '(bootloader) bootloader-locked: 0\n'
        '(bootloader) bootloader-min-versions: -1,0,3\n'
        '(bootloader) avb-perm-attr-set: 0\n'
        '(bootloader) avb-locked: 0\n'
        '(bootloader) avb-unlock-disabled: 0\n'
        '(bootloader) avb-min-versions: 0:1,1:1,2:1,4097 :2,4098:2\n')
    self.status_map['at-attest-uuid'] = self.TEST_UUID
    self.status_map['at-attest-dh'] = ''
    mock_device = MagicMock()
    mock_device.GetVar.side_effect = self.MockGetVar
    mock_file = MagicMock()
    mock_create_temp_file.return_value = mock_file
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa = MagicMock()
    mock_device.provision_state = ProvisionState()
    mock_get_size.side_effect = os.error

    atft_manager.CheckProvisionStatus(mock_device)

    mock_create_temp_file.assert_called_once()
    mock_delete_file.assert_called_once_with(mock_file.name)
    self.assertEqual(False, mock_device.provision_state.som_provisioned)
    self.assertNotEqual(ProvisionStatus.SOM_PROVISION_SUCCESS,
                        mock_device.provision_status)

  # Test AtftManager.Provision
  def MockSetProvisionSuccess(self, target):
    target.provision_status = ProvisionStatus.PROVISION_SUCCESS
    target.provision_state = ProvisionState()
    target.provision_state.product_provisioned = True

  def MockSetProvisionFail(self, target):
    target.provision_status = ProvisionStatus.PROVISION_FAILED
    target.provision_state = ProvisionState()
    target.provision_state.product_provisioned = False

  def testProvision(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa = MagicMock()
    mock_target = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa)
    atft_manager._atfa_dev_manager.SetTime = MagicMock()
    atft_manager._GetAlgorithmList = MagicMock()
    atft_manager._GetAlgorithmList.return_value = [
        EncryptionAlgorithm.ALGORITHM_CURVE25519
    ]
    atft_manager.TransferContent = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetProvisionSuccess

    atft_manager.Provision(mock_target, False)

    # Make sure atfa.SetTime is called.
    atft_manager._atfa_dev_manager.SetTime.assert_called_once()
    # Transfer content should be ATFA->target, target->ATFA, ATFA->target
    transfer_content_calls = [
        call(mock_atfa, mock_target),
        call(mock_target, mock_atfa),
        call(mock_atfa, mock_target)
    ]
    atft_manager.TransferContent.assert_has_calls(transfer_content_calls)
    atfa_oem_calls = [
        call('start-provisioning ' +
             str(EncryptionAlgorithm.ALGORITHM_CURVE25519)),
        call('finish-provisioning')
    ]
    target_oem_calls = [
        call('at-get-ca-request'),
        call('at-set-ca-response')
    ]
    mock_atfa.Oem.assert_has_calls(atfa_oem_calls)
    mock_target.Oem.assert_has_calls(target_oem_calls)

  def testProvisionFailed(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa = MagicMock()
    mock_target = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa)
    atft_manager._GetAlgorithmList = MagicMock()
    atft_manager._GetAlgorithmList.return_value = [
        EncryptionAlgorithm.ALGORITHM_CURVE25519
    ]
    atft_manager.TransferContent = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetProvisionFail
    with self.assertRaises(FastbootFailure):
      atft_manager.Provision(mock_target, False)

  def MockSetProvisionSomSuccess(self, target):
    target.provision_status = ProvisionStatus.SOM_PROVISION_SUCCESS
    target.provision_state = ProvisionState()
    target.provision_state.som_provisioned = True

  def MockSetProvisionSomFail(self, target):
    target.provision_status = ProvisionStatus.SOM_PROVISION_FAILED
    target.provision_state = ProvisionState()
    target.provision_state.som_provisioned = False

  def testProvisionSom(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa = MagicMock()
    mock_target = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa)
    atft_manager._atfa_dev_manager.SetTime = MagicMock()
    atft_manager._GetAlgorithmList = MagicMock()
    atft_manager._GetAlgorithmList.return_value = [
        EncryptionAlgorithm.ALGORITHM_CURVE25519
    ]
    atft_manager.TransferContent = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = (
        self.MockSetProvisionSomSuccess)

    atft_manager.Provision(mock_target, True)

    # Make sure atfa.SetTime is called.
    atft_manager._atfa_dev_manager.SetTime.assert_called_once()
    # Transfer content should be ATFA->target, target->ATFA, ATFA->target
    transfer_content_calls = [
        call(mock_atfa, mock_target),
        call(mock_target, mock_atfa),
        call(mock_atfa, mock_target)
    ]
    atft_manager.TransferContent.assert_has_calls(transfer_content_calls)
    atfa_oem_calls = [
        call('start-provisioning ' +
             str(EncryptionAlgorithm.ALGORITHM_CURVE25519) + ' 4'),
        call('finish-provisioning')
    ]
    target_oem_calls = [
        call('at-get-ca-request'),
        call('at-set-ca-response')
    ]
    mock_atfa.Oem.assert_has_calls(atfa_oem_calls)
    mock_target.Oem.assert_has_calls(target_oem_calls)

  def testProvisionSomFailed(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_atfa = MagicMock()
    mock_target = MagicMock()
    atft_manager._atfa_dev_manager.SetATFADevice(mock_atfa)
    atft_manager._GetAlgorithmList = MagicMock()
    atft_manager._GetAlgorithmList.return_value = [
        EncryptionAlgorithm.ALGORITHM_CURVE25519
    ]
    atft_manager.TransferContent = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetProvisionSomFail
    with self.assertRaises(FastbootFailure):
      atft_manager.Provision(mock_target, True)

  def MockSetProvisionSomSuccess(self, target):
    target.provision_status = ProvisionStatus.PROVISION_SUCCESS
    target.provision_state = ProvisionState()
    target.provision_state.som_provisioned = True

  # Test AtftManager.FuseVbootKey
  def MockSetFuseVbootSuccess(self, target):
    target.provision_status = ProvisionStatus.FUSEVBOOT_SUCCESS
    target.provision_state = ProvisionState()
    target.provision_state.bootloader_locked = True

  def MockSetFuseVbootFail(self, target):
    target.provision_status = ProvisionStatus.FUSEVBOOT_FAILED
    target.provision_state = ProvisionState()
    target.provision_state.bootloader_locked = False

  @patch('os.remove')
  @patch('tempfile.NamedTemporaryFile')
  def testFuseVbootKey(self, mock_create_temp_file, mock_remove):
    mock_file = MagicMock()
    mock_create_temp_file.return_value = mock_file
    mock_file.name = self.TEST_FILE_NAME

    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    atft_manager.product_info = ProductInfo(
        self.TEST_ID, self.TEST_NAME, self.TEST_ATTRIBUTE_ARRAY,
        self.TEST_VBOOT_KEY_ARRAY)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetFuseVbootSuccess

    atft_manager.FuseVbootKey(mock_target)

    mock_file.write.assert_called_once_with(self.TEST_VBOOT_KEY_ARRAY)
    mock_target.Download.assert_called_once_with(self.TEST_FILE_NAME)
    mock_remove.assert_called_once_with(self.TEST_FILE_NAME)
    mock_target.Oem.assert_called_once_with('fuse at-bootloader-vboot-key')

  @patch('os.remove')
  @patch('tempfile.NamedTemporaryFile')
  def testFuseVbootKeySom(self, mock_create_temp_file, mock_remove):
    mock_file = MagicMock()
    mock_create_temp_file.return_value = mock_file
    mock_file.name = self.TEST_FILE_NAME

    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    atft_manager.som_info = SomInfo(
        self.TEST_ID, self.TEST_NAME, self.TEST_VBOOT_KEY_ARRAY)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetFuseVbootSuccess

    atft_manager.FuseVbootKey(mock_target)

    mock_file.write.assert_called_once_with(self.TEST_VBOOT_KEY_ARRAY)
    mock_target.Download.assert_called_once_with(self.TEST_FILE_NAME)
    mock_remove.assert_called_once_with(self.TEST_FILE_NAME)
    mock_target.Oem.assert_called_once_with('fuse at-bootloader-vboot-key')

  def testFuseVbootKeyNoProduct(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_target = MagicMock()
    atft_manager.product_info = None
    with self.assertRaises(ProductNotSpecifiedException):
      atft_manager.FuseVbootKey(mock_target)

  @patch('os.remove')
  @patch('tempfile.NamedTemporaryFile')
  def testFuseVbootKeyFastbootFailure(self, mock_create_temp_file, _):
    mock_file = MagicMock()
    mock_create_temp_file.return_value = mock_file
    mock_file.name = self.TEST_FILE_NAME

    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    atft_manager.product_info = ProductInfo(
        self.TEST_ID, self.TEST_NAME, self.TEST_ATTRIBUTE_ARRAY,
        self.TEST_VBOOT_KEY_ARRAY)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    mock_target.Oem.side_effect = FastbootFailure('')

    with self.assertRaises(FastbootFailure):
      atft_manager.FuseVbootKey(mock_target)
    self.assertEqual(
        ProvisionStatus.FUSEVBOOT_FAILED, mock_target.provision_status)

  # Test AtftManager.FusePermAttr
  def MockSetFuseAttrSuccess(self, target):
    target.provision_status = ProvisionStatus.FUSEATTR_SUCCESS
    target.provision_state = ProvisionState()
    target.provision_state.avb_perm_attr_set = True

  def MockSetFuseAttrFail(self, target):
    target.provision_status = ProvisionStatus.FUSEATTR_FAILED
    target.provision_state = ProvisionState()
    target.provision_state.avb_perm_attr_set = False

  @patch('os.remove')
  @patch('tempfile.NamedTemporaryFile')
  def testFusePermAttr(self, mock_create_temp_file, mock_remove):
    mock_file = MagicMock()
    mock_create_temp_file.return_value = mock_file
    mock_file.name = self.TEST_FILE_NAME

    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    atft_manager.product_info = ProductInfo(
        self.TEST_ID, self.TEST_NAME, self.TEST_ATTRIBUTE_ARRAY,
        self.TEST_VBOOT_KEY_ARRAY)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetFuseAttrSuccess

    atft_manager.FusePermAttr(mock_target)

    mock_file.write.assert_called_once_with(self.TEST_ATTRIBUTE_ARRAY)
    mock_target.Download.assert_called_once_with(self.TEST_FILE_NAME)
    mock_remove.assert_called_once_with(self.TEST_FILE_NAME)
    mock_target.Oem.assert_called_once_with('fuse at-perm-attr')

  @patch('os.remove')
  @patch('tempfile.NamedTemporaryFile')
  def testFusePermAttrFail(self, mock_create_temp_file, _):
    mock_file = MagicMock()
    mock_create_temp_file.return_value = mock_file
    mock_file.name = self.TEST_FILE_NAME

    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    atft_manager.product_info = ProductInfo(
        self.TEST_ID, self.TEST_NAME, self.TEST_ATTRIBUTE_ARRAY,
        self.TEST_VBOOT_KEY_ARRAY)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetFuseAttrFail
    with self.assertRaises(FastbootFailure):
      atft_manager.FusePermAttr(mock_target)

  def testFusePermAttrNoProduct(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_target = MagicMock()
    atft_manager.product_info = None
    with self.assertRaises(ProductNotSpecifiedException):
      atft_manager.FusePermAttr(mock_target)

  @patch('os.remove')
  @patch('tempfile.NamedTemporaryFile')
  def testFusePermAttrFastbootFailure(self, mock_create_temp_file, _):
    mock_file = MagicMock()
    mock_create_temp_file.return_value = mock_file
    mock_file.name = self.TEST_FILE_NAME

    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    atft_manager.product_info = ProductInfo(
        self.TEST_ID, self.TEST_NAME, self.TEST_ATTRIBUTE_ARRAY,
        self.TEST_VBOOT_KEY_ARRAY)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    mock_target.Oem.side_effect = FastbootFailure('')

    with self.assertRaises(FastbootFailure):
      atft_manager.FusePermAttr(mock_target)
    self.assertEqual(
        ProvisionStatus.FUSEATTR_FAILED, mock_target.provision_status)

  # Test AtftManager.LockAvb
  def MockSetLockAvbSuccess(self, target):
    target.provision_status = ProvisionStatus.LOCKAVB_SUCCESS
    target.provision_state = ProvisionState()
    target.provision_state.avb_locked = True

  def MockSetLockAvbFail(self, target):
    target.provision_status = ProvisionStatus.LOCKAVB_FAILED
    target.provision_state = ProvisionState()
    target.provision_state.avb_locked = False

  def testLockAvb(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetLockAvbSuccess
    atft_manager.LockAvb(mock_target)
    mock_target.Oem.assert_called_once_with('at-lock-vboot')
    self.assertEqual(
        ProvisionStatus.LOCKAVB_SUCCESS, mock_target.provision_status)

  def testLockAvbFail(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetLockAvbFail
    with self.assertRaises(FastbootFailure):
      atft_manager.LockAvb(mock_target)

  def testLockAvbFastbootFailure(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetLockAvbSuccess
    mock_target.Oem.side_effect = FastbootFailure('')
    with self.assertRaises(FastbootFailure):
      atft_manager.LockAvb(mock_target)
    self.assertEqual(
        ProvisionStatus.LOCKAVB_FAILED, mock_target.provision_status)

  # Test AtftManager.LockAvb
  def MockSetUnlockAvbSuccess(self, target):
    target.provision_status = ProvisionStatus.UNLOCKAVB_SUCCESS
    target.provision_state = ProvisionState()
    target.provision_state.avb_locked = False

  def MockSetUnlockAvbFail(self, target):
    target.provision_status = ProvisionStatus.UNLOCKAVB_FAILED
    target.provision_state = ProvisionState()
    target.provision_state.avb_locked = True

  def testUnlockAvb(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetUnlockAvbSuccess
    atft_manager.UnlockAvb(mock_target)
    mock_target.Oem.assert_called_once_with('at-unlock-vboot')
    self.assertEqual(
        ProvisionStatus.UNLOCKAVB_SUCCESS, mock_target.provision_status)

  def testUnlockAvbWithCredential(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetUnlockAvbSuccess
    atft_manager.UNLOCK_CREDENTIAL = 'test'
    atft_manager.UnlockAvb(mock_target)
    mock_target.Oem.assert_called_once_with('at-unlock-vboot test')
    self.assertEqual(
        ProvisionStatus.UNLOCKAVB_SUCCESS, mock_target.provision_status)

  def testUnlockAvbFail(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetUnlockAvbFail
    with self.assertRaises(FastbootFailure):
      atft_manager.UnlockAvb(mock_target)

  def testUnlockAvbFastbootFailure(self):
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    mock_target = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetUnlockAvbSuccess
    mock_target.Oem.side_effect = FastbootFailure('')
    with self.assertRaises(FastbootFailure):
      atft_manager.UnlockAvb(mock_target)
    self.assertEqual(
        ProvisionStatus.UNLOCKAVB_FAILED, mock_target.provision_status)

  # Test AtftManager.Reboot
  class MockTimer(object):
    def __init__(self, interval, callback):
      self.interval = interval
      self.callback = callback

    def start(self):
      pass

    def refresh(self):
      if self.callback:
        self.callback()

    def cancel(self):
      self.callback = None

  def mock_create_timer(self, interval, callback):
    self.mock_timer_instance = self.MockTimer(interval, callback)
    return self.mock_timer_instance

  @patch('threading.Timer')
  def testRebootSuccess(self, mock_timer):
    self.mock_timer_instance = None
    atft_manager = atftman.AtftManager(
      self.FastbootDeviceTemplate, self.mock_serial_mapper, self.configs)
    timeout = 1
    atft_manager.stable_serials = [self.TEST_SERIAL]
    mock_fastboot = MagicMock()
    test_device = atftman.DeviceInfo(
        mock_fastboot, self.TEST_SERIAL, self.TEST_LOCATION)

    atft_manager.target_devs.append(test_device)
    mock_success = MagicMock()
    mock_fail = MagicMock()
    mock_timer.side_effect = self.mock_create_timer

    atft_manager.Reboot(test_device, timeout, mock_success, mock_fail)

    # During the reboot, the status should be REBOOT_IN_PROGRESS.
    self.assertEqual(1, len(atft_manager.target_devs))
    self.assertEqual(
        ProvisionStatus.REBOOT_IN_PROGRESS,
        atft_manager.target_devs[0].provision_status)
    self.assertEqual(
        self.TEST_SERIAL, atft_manager.target_devs[0].serial_number)

    # After the device reappear, the status should be REBOOT_SUCCESS.
    atft_manager.stable_serials = [self.TEST_SERIAL]
    atft_manager._HandleRebootCallbacks()
    # mock timeout event.
    self.mock_timer_instance.refresh()

    self.assertEqual(1, len(atft_manager.target_devs))
    self.assertEqual(
        ProvisionStatus.REBOOT_SUCCESS,
        atft_manager.target_devs[0].provision_status)
    mock_fastboot.Reboot.assert_called_once()

    # Success should be called, fail should not.
    mock_success.assert_called_once()
    mock_fail.assert_not_called()

  @patch('threading.Timer')
  def testRebootTimeout(self, mock_timer):
    self.mock_timer_instance = None
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    timeout = 1
    atft_manager.stable_serials.append(self.TEST_SERIAL)
    mock_fastboot = MagicMock()
    test_device = atftman.DeviceInfo(
        mock_fastboot, self.TEST_SERIAL, self.TEST_LOCATION)
    atft_manager.target_devs.append(test_device)
    mock_success = MagicMock()
    mock_fail = MagicMock()
    # Status would be checked after reboot. We assume it's in FUSEVBOOT_SUCCESS
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetFuseVbootSuccess
    mock_timer.side_effect = self.mock_create_timer

    atft_manager.Reboot(test_device, timeout, mock_success, mock_fail)
    atft_manager.stable_serials = []

    atft_manager._HandleRebootCallbacks()

    # mock timeout event.
    self.mock_timer_instance.refresh()

    self.assertEqual(0, len(atft_manager.target_devs))
    mock_success.assert_not_called()
    mock_fail.assert_called_once()

  @patch('threading.Timer')
  def testRebootTimeoutBeforeRefresh(self, mock_timer):
    self.mock_timer_instance = None
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    timeout = 1
    atft_manager.stable_serials.append(self.TEST_SERIAL)
    mock_fastboot = MagicMock()
    test_device = atftman.DeviceInfo(
        mock_fastboot, self.TEST_SERIAL, self.TEST_LOCATION)
    atft_manager.target_devs.append(test_device)
    mock_success = MagicMock()
    mock_fail = MagicMock()
    # Status would be checked after reboot. We assume it's in FUSEVBOOT_SUCCESS
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetFuseVbootSuccess
    mock_timer.side_effect = self.mock_create_timer

    atft_manager.Reboot(test_device, timeout, mock_success, mock_fail)
    atft_manager.stable_serials = []
     # mock timeout event.
    self.mock_timer_instance.refresh()
    # mock refresh event.
    atft_manager._HandleRebootCallbacks()

    self.assertEqual(0, len(atft_manager.target_devs))
    mock_success.assert_not_called()
    mock_fail.assert_called_once()

  @patch('threading.Timer')
  def testRebootFailure(self, mock_timer):
    self.mock_timer_instance = None
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    timeout = 1
    atft_manager.stable_serials.append(self.TEST_SERIAL)
    test_device = atftman.DeviceInfo(None, self.TEST_SERIAL, self.TEST_LOCATION)
    atft_manager.target_devs.append(test_device)
    mock_success = MagicMock()
    mock_fail = MagicMock()
    # Status would be checked after reboot. We assume it's in FUSEVBOOT_SUCCESS
    atft_manager.CheckProvisionStatus = MagicMock()
    atft_manager.CheckProvisionStatus.side_effect = self.MockSetFuseVbootSuccess
    mock_timer.side_effect = self.mock_create_timer
    test_device.Reboot = MagicMock()
    test_device.Reboot.side_effect = FastbootFailure('')

    with self.assertRaises(FastbootFailure):
      atft_manager.Reboot(test_device, timeout, mock_success, mock_fail)

    # There should be no timeout timer.
    self.assertEqual(None, self.mock_timer_instance)
    # mock refresh event.
    atft_manager._HandleRebootCallbacks()
    mock_success.assert_not_called()
    mock_fail.assert_not_called()

  @patch('threading.Timer')
  def testRebootFailureAfterReboot(self, mock_timer):
    self.mock_timer_instance = None
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    timeout = 1
    atft_manager.stable_serials.append(self.TEST_SERIAL)
    mock_fastboot = MagicMock()
    test_device = atftman.DeviceInfo(
        mock_fastboot, self.TEST_SERIAL, self.TEST_LOCATION)
    atft_manager.target_devs.append(test_device)
    mock_success = MagicMock()
    mock_fail = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    # The check status failed after the reboot
    atft_manager.CheckProvisionStatus.side_effect = FastbootFailure('')
    mock_timer.side_effect = self.mock_create_timer

    atft_manager.Reboot(test_device, timeout, mock_success, mock_fail)

    mock_fastboot.Reboot.assert_called_once()

    # The timer should still be there.
    self.assertNotEqual(None, self.mock_timer_instance)
    # Put serial into stable serials.
    atft_manager.stable_serials = [self.TEST_SERIAL]
    # mock refresh event.
    with self.assertRaises(DeviceCreationException):
      atft_manager._HandleRebootCallbacks()

    # The timer should still be there.
    self.assertNotEqual(None, self.mock_timer_instance)
    # Success or fail should not be called.
    # We would treat this as we have not seen the device.
    mock_success.assert_not_called()
    mock_fail.assert_not_called()

  @patch('threading.Timer')
  def testRebootFailureAfterRebootMultipleDevice(self, mock_timer):
    self.mock_timer_instance = None
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    timeout = 1
    atft_manager.stable_serials = [self.TEST_SERIAL, self.TEST_SERIAL2]
    mock_fastboot = MagicMock()
    test_device_1 = atftman.DeviceInfo(
        mock_fastboot, self.TEST_SERIAL, self.TEST_LOCATION)
    test_device_2 = atftman.DeviceInfo(
        mock_fastboot, self.TEST_SERIAL2, self.TEST_LOCATION)
    atft_manager.target_devs = [test_device_1, test_device_2]
    mock_success = MagicMock()
    mock_fail = MagicMock()
    atft_manager.CheckProvisionStatus = MagicMock()
    # The check status failed after the reboot
    atft_manager.CheckProvisionStatus.side_effect = FastbootFailure('')
    mock_timer.side_effect = self.mock_create_timer

    atft_manager.Reboot(test_device_1, timeout, mock_success, mock_fail)
    atft_manager.Reboot(test_device_2, timeout, mock_success, mock_fail)

    mock_fastboot.Reboot.assert_called()

    # The timer should still be there.
    self.assertNotEqual(None, self.mock_timer_instance)
    # Put serial into stable serials.
    atft_manager.stable_serials = [self.TEST_SERIAL, self.TEST_SERIAL2]
    # mock refresh event.
    with self.assertRaises(DeviceCreationException) as cm:
      atft_manager._HandleRebootCallbacks()

    self.assertEqual(len(cm.exception.devices), 2)
    error_message = DeviceCreationException(str(FastbootFailure('')), []).msg
    self.assertEqual(error_message + '\n' + error_message, cm.exception.msg)
    self.assertEqual(
        True,
        atft_manager._reboot_callbacks[self.TEST_SERIAL].lock.acquire(False))
    self.assertEqual(
        True,
        atft_manager._reboot_callbacks[self.TEST_SERIAL2].lock.acquire(False))
    atft_manager._reboot_callbacks[self.TEST_SERIAL].Release()
    atft_manager._reboot_callbacks[self.TEST_SERIAL2].Release()

    # The timer should still be there.
    self.assertNotEqual(None, self.mock_timer_instance)
    # Success or fail should not be called.
    # We would treat this as we have not seen the device.
    mock_success.assert_not_called()
    mock_fail.assert_not_called()

  # Test AtftManager.ProcessAttributesFile
  def testProcessAttributesFile(self):
    test_content = (
        '{'
        '  "productName": "%s",'
        '  "productConsoleId": "%s",'
        '  "productPermanentAttribute": "%s",'
        '  "bootloaderPublicKey": "%s",'
        '  "creationTime": ""'
        '}') % (self.TEST_NAME, self.TEST_ID, self.TEST_ATTRIBUTE_STRING,
                self.TEST_VBOOT_KEY_STRING)
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    atft_manager.ProcessAttributesFile(test_content)
    self.assertEqual(self.TEST_NAME, atft_manager.product_info.product_name)
    self.assertEqual(self.TEST_ID, atft_manager.product_info.product_id)
    self.assertEqual(self.TEST_ATTRIBUTE_ARRAY,
                     atft_manager.product_info.product_attributes)
    self.assertEqual(self.TEST_VBOOT_KEY_ARRAY,
                     atft_manager.product_info.vboot_key)

  def testProcessAttributesFileSom(self):
    test_content = (
        '{'
        '  "productName": "%s",'
        '  "productConsoleId": "%s",'
        '  "somId": "%s",'
        '  "bootloaderPublicKey": "%s",'
        '  "creationTime": ""'
        '}') % (self.TEST_NAME, self.TEST_ID, self.TEST_ID,
                self.TEST_VBOOT_KEY_STRING)
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    atft_manager.ProcessAttributesFile(test_content)
    self.assertEqual(self.TEST_NAME, atft_manager.som_info.som_name)
    self.assertEqual(self.TEST_ID, atft_manager.som_info.som_id)
    self.assertEqual(self.TEST_VBOOT_KEY_ARRAY, atft_manager.som_info.vboot_key)

  def testProcessAttributesFileWrongJSON(self):
    test_content = (
        '{'
        '  "productName": "%s",'
        '  "productConsoleId": "%s",'
        '  "productPermanentAttribute": "%s",'
        '  "bootloaderPublicKey": "%s",'
        '  "creationTime": ""'
        '') % (self.TEST_NAME, self.TEST_ID, self.TEST_ATTRIBUTE_STRING,
               self.TEST_VBOOT_KEY_STRING)
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    with self.assertRaises(ProductAttributesFileFormatError):
      atft_manager.ProcessAttributesFile(test_content)

  def testProcessAttributesFileWrongJSONSomNoId(self):
    test_content = (
        '{'
        '  "productName": "%s",'
        '  "productConsoleId": "%s",'
        '  "bootloaderPublicKey": "%s",'
        '  "creationTime": ""'
        '}') % (self.TEST_NAME, self.TEST_ID, self.TEST_VBOOT_KEY_STRING)
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    with self.assertRaises(ProductAttributesFileFormatError):
      atft_manager.ProcessAttributesFile(test_content)

  def testProcessAttributesFileWrongJSONSomNoVbootKey(self):
    test_content = (
        '{'
        '  "productName": "%s",'
        '  "productConsoleId": "%s",'
        '  "somId": "%s",'
        '  "creationTime": ""'
        '}') % (self.TEST_NAME, self.TEST_ID, self.TEST_ID)
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    with self.assertRaises(ProductAttributesFileFormatError):
      atft_manager.ProcessAttributesFile(test_content)

  def testProcessAttributesFileMissingField(self):
    test_content = (
        '{'
        '  "productConsoleId": "%s",'
        '  "productPermanentAttribute": "%s",'
        '  "bootloaderPublicKey": "%s",'
        '  "creationTime": ""'
        '}') % (self.TEST_ID, self.TEST_ATTRIBUTE_STRING,
                self.TEST_VBOOT_KEY_STRING)
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    with self.assertRaises(ProductAttributesFileFormatError):
      atft_manager.ProcessAttributesFile(test_content)

  def testProcessAttributesFileWrongLength(self):
    test_content = (
        '{'
        '  "productName": "%s",'
        '  "productConsoleId": "%s",'
        '  "productPermanentAttribute": "%s",'
        '  "bootloaderPublicKey": "%s",'
        '  "creationTime": ""'
        '}') % (self.TEST_NAME, self.TEST_ID,
                base64.standard_b64encode(bytearray(1053)),
                self.TEST_VBOOT_KEY_STRING)
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    with self.assertRaises(ProductAttributesFileFormatError) as e:
      atft_manager.ProcessAttributesFile(test_content)

  def testProcessAttributesFileWrongBase64(self):
    test_content = (
        '{'
        '  "productName": "%s",'
        '  "productConsoleId": "%s",'
        '  "productPermanentAttribute": "%s",'
        '  "bootloaderPublicKey": "%s",'
        '  "creationTime": ""'
        '}') % (self.TEST_NAME, self.TEST_ID, self.TEST_ATTRIBUTE_STRING,
                '12')
    atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate,
                                       self.mock_serial_mapper, self.configs)
    with self.assertRaises(ProductAttributesFileFormatError):
      atft_manager.ProcessAttributesFile(test_content)

  # Test _AddNewAtfa
  def testAddNewAtfa(self):
    mock_fastboot = MagicMock()
    mock_fastboot_controller = MagicMock()
    mock_fastboot.return_value = mock_fastboot_controller
    mock_fastboot_controller.GetVar = MagicMock()
    mock_fastboot_controller.GetVar.return_value = '10'
    atft_manager = atftman.AtftManager(
        mock_fastboot, self.mock_serial_mapper, self.configs)
    atft_manager._AddNewAtfa(self.ATFA_TEST_SERIAL)
    mock_fastboot.assert_called_once_with(self.ATFA_TEST_SERIAL)
    mock_fastboot_controller.GetVar.assert_has_calls(
        [call('version'), call('os-version')])
    self.assertEqual(
        self.ATFA_TEST_SERIAL, atft_manager.GetATFADevice().serial_number)

  def testAddNewAtfaVersionNotCompatible(self):
    mock_fastboot = MagicMock()
    mock_fastboot_controller = MagicMock()
    mock_fastboot.return_value = mock_fastboot_controller
    mock_fastboot_controller.GetVar = MagicMock()
    mock_fastboot_controller.GetVar.return_value = '8'
    atft_manager = atftman.AtftManager(
        mock_fastboot, self.mock_serial_mapper, self.configs)
    with self.assertRaises(OsVersionNotCompatibleException):
      atft_manager._AddNewAtfa(self.ATFA_TEST_SERIAL)

    mock_fastboot.assert_called_once_with(self.ATFA_TEST_SERIAL)
    mock_fastboot_controller.GetVar.assert_has_calls(
        [call('version'), call('os-version')])
    self.assertEqual(
        self.ATFA_TEST_SERIAL, atft_manager.GetATFADevice().serial_number)

  def MockOsVersionException(self, name):
    if name == 'os-version':
      raise FastbootFailure('')
    else:
      return ''

  def MockGetVersionException(self, name):
    if name == 'version':
      raise FastbootFailure('')
    else:
      return ''

  def testAddNewAtfaVersionNotAvailable(self):
    mock_fastboot = MagicMock()
    mock_fastboot_controller = MagicMock()
    mock_fastboot.return_value = mock_fastboot_controller
    mock_fastboot_controller.GetVar = self.MockOsVersionException
    atft_manager = atftman.AtftManager(
        mock_fastboot, self.mock_serial_mapper, self.configs)
    with self.assertRaises(OsVersionNotAvailableException):
      atft_manager._AddNewAtfa(self.ATFA_TEST_SERIAL)
    self.assertEqual(
        self.ATFA_TEST_SERIAL, atft_manager.GetATFADevice().serial_number)

  # If the atfa device is not ready yet, the getvar('version') would throw
  # exception, we just ignore this device if it is not ready.
  def testAddNewAtfaNotReadyYet(self):
    mock_fastboot = MagicMock()
    mock_fastboot_controller = MagicMock()
    mock_fastboot.return_value = mock_fastboot_controller
    mock_fastboot_controller.GetVar = self.MockGetVersionException
    atft_manager = atftman.AtftManager(
        mock_fastboot, self.mock_serial_mapper, self.configs)
    atft_manager._AddNewAtfa(self.ATFA_TEST_SERIAL)
    self.assertEqual(
        None, atft_manager.GetATFADevice())


if __name__ == '__main__':
  unittest.main()
