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

"""Unit test for atft."""
import types
import unittest

import atft
from atftman import ProvisionStatus
from atftman import ProvisionState
import fastboot_exceptions
from mock import call
from mock import MagicMock
from mock import patch
import os
import wx


class MockAtft(atft.Atft):

  def __init__(self):
    self.InitializeUI = MagicMock()
    self.StartRefreshingDevices = MagicMock()
    self.ChooseProduct = MagicMock()
    self.CreateAtftManager = MagicMock()
    self.CreateAtftLog = MagicMock()
    self.ParseConfigFile = self._MockParseConfig
    self._SendPrintEvent = MagicMock()
    self._OnToggleSupMode = MagicMock()
    self.ShowStartScreen = MagicMock()
    self.TARGET_DEV_SIZE = 6
    atft.Atft.__init__(self)

  def _MockParseConfig(self):
    self.ATFT_VERSION = 'vTest'
    self.COMPATIBLE_ATFA_VERSION = 'v1'
    self.DEVICE_REFRESH_INTERVAL = 1.0
    self.DEFAULT_KEY_THRESHOLD = 0
    self.LOG_DIR = 'test_log_dir'
    self.LOG_SIZE = 1000
    self.LOG_FILE_NUMBER = 2
    self.LANGUAGE = 'ENG'
    self.REBOOT_TIMEOUT = 1.0
    self.PRODUCT_ATTRIBUTE_FILE_EXTENSION = '*.atpa'

    return {}


class TestDeviceInfo(object):

  def __init__(self, serial_number, location=None, provision_status=None):
    self.serial_number = serial_number
    self.location = location
    self.provision_status = provision_status
    self.provision_state = ProvisionState()
    self.time_set = False

  def __eq__(self, other):
    return (self.serial_number == other.serial_number and
            self.location == other.location)

  def __ne__(self, other):
    return not self.__eq__(other)

  def Copy(self):
    return TestDeviceInfo(self.serial_number, self.location,
                          self.provision_status)


class AtftTest(unittest.TestCase):
  TEST_SERIAL1 = 'test-serial1'
  TEST_LOCATION1 = 'test-location1'
  TEST_SERIAL2 = 'test-serial2'
  TEST_LOCATION2 = 'test-location2'
  TEST_SERIAL3 = 'test-serial3'
  TEST_SERIAL4 = 'test-serial4'
  TEST_TEXT = 'test-text'
  TEST_TEXT2 = 'test-text2'
  LOG_DIR = 'test-dir'
  TEST_TIME = '0000-00-00 00:00:00'
  TEST_TIMESTAMP = 1000
  TEST_PASSWORD1 = 'password 1'
  TEST_PASSWORD2 = 'PassWord 2!'
  TEST_FILENAME = 'filename'

  def setUp(self):
    self.test_target_devs = []
    self.test_dev1 = TestDeviceInfo(
        self.TEST_SERIAL1, self.TEST_LOCATION1, ProvisionStatus.IDLE)
    self.test_dev2 = TestDeviceInfo(
        self.TEST_SERIAL2, self.TEST_LOCATION2, ProvisionStatus.IDLE)
    self.test_text_window = ''
    self.atfa_keys = None
    self.device_map = {}
    # Disable the test mode. (This mode is just for usage test, not unit test)
    atft.TEST_MODE = False

  def AppendTargetDevice(self, device):
    self.test_target_devs.append(device)

  def DeleteAllItems(self):
    self.test_target_devs = []

  # Test atft._DeviceListedEventHandler
  # Make sure if nothing changes, we would not rerender the target list.
  def testDeviceListedEventHandler(self):
    mock_atft = MockAtft()
    mock_atft.atfa_dev_output = MagicMock()
    mock_atft.last_target_list = []
    mock_atft.target_devs_output = MagicMock()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = None
    mock_atft.PrintToWindow = MagicMock()
    mock_atft._HandleKeysLeft = MagicMock()
    mock_atft._PrintTargetDevices = MagicMock()
    mock_atft._PrintAtfaDevice = MagicMock()
    mock_atft.atft_manager.target_devs = []
    mock_atft._DeviceListedEventHandler(None)
    mock_atft.atft_manager.target_devs = [self.test_dev1]
    mock_atft._DeviceListedEventHandler(None)
    mock_atft._PrintTargetDevices.assert_called_once()
    mock_atft._PrintTargetDevices.reset_mock()
    mock_atft.atft_manager.target_devs = [self.test_dev1, self.test_dev2]
    mock_atft._DeviceListedEventHandler(None)
    mock_atft._PrintTargetDevices.assert_called_once()
    mock_atft._PrintTargetDevices.reset_mock()
    mock_atft._DeviceListedEventHandler(None)
    mock_atft._PrintTargetDevices.assert_not_called()
    mock_atft.atft_manager.target_devs = [self.test_dev2]
    mock_atft._DeviceListedEventHandler(None)
    mock_atft._PrintTargetDevices.assert_called_once()

  # Test _PrintTargetDevices
  def testPrintTargetDevices(self):
    mock_atft = MockAtft()
    mock_atft.FIELD_SERIAL_NUMBER = ''
    mock_atft.atft_manager = MagicMock()
    dev1 = self.test_dev1
    dev2 = self.test_dev2
    dev1.provision_status = ProvisionStatus.IDLE
    dev2.provision_status = ProvisionStatus.PROVISION_ING
    mock_atft.atft_manager.target_devs = [dev1, dev2]
    mock_atft.device_usb_locations = []
    for i in range(0, mock_atft.TARGET_DEV_SIZE):
      mock_atft.device_usb_locations.append(None)
    mock_atft.device_usb_locations[0] = self.TEST_LOCATION1
    mock_atft.device_usb_locations[5] = self.TEST_LOCATION2
    mock_atft._ShowTargetDevice = MagicMock()
    mock_atft._PrintTargetDevices()
    mock_atft._ShowTargetDevice.assert_has_calls([
        call(
            0, self.TEST_SERIAL1, ': ' +
            self.TEST_SERIAL1, ProvisionStatus.IDLE),
        call(1, None, '', None),
        call(2, None, '', None),
        call(3, None, '', None),
        call(4, None, '', None),
        call(
            5, self.TEST_SERIAL2, ': ' +
            self.TEST_SERIAL2, ProvisionStatus.PROVISION_ING)
        ])

  # Test atft._SelectFileEventHandler
  @patch('wx.FileDialog')
  def testSelectFileEventHandler(self, mock_file_dialog):
    mock_atft = MockAtft()
    mock_event = MagicMock()
    mock_callback = MagicMock()
    mock_dialog = MagicMock()
    mock_instance = MagicMock()
    mock_file_dialog.return_value = mock_instance
    mock_instance.__enter__.return_value = mock_dialog
    mock_event.GetValue.return_value = (mock_atft.SelectFileArg(
        self.TEST_TEXT, self.TEST_TEXT2, mock_callback))
    mock_dialog.ShowModal.return_value = wx.ID_OK
    mock_dialog.GetPath.return_value = self.TEST_TEXT
    mock_atft._SelectFileEventHandler(mock_event)
    mock_callback.assert_called_once_with(self.TEST_TEXT)

  @patch('wx.FileDialog')
  def testSelectFileEventHandlerCancel(self, mock_file_dialog):
    mock_atft = MockAtft()
    mock_event = MagicMock()
    mock_callback = MagicMock()
    mock_dialog = MagicMock()
    mock_instance = MagicMock()
    mock_file_dialog.return_value = mock_instance
    mock_instance.__enter__.return_value = mock_dialog
    mock_event.GetValue.return_value = (mock_atft.SelectFileArg(
        self.TEST_TEXT, self.TEST_TEXT2, mock_callback))
    mock_dialog.ShowModal.return_value = wx.ID_CANCEL
    mock_dialog.GetPath.return_value = self.TEST_TEXT
    mock_atft._SelectFileEventHandler(mock_event)
    mock_callback.assert_not_called()

  # Test atft.PrintToWindow
  def MockAppendText(self, text):
    self.test_text_window += text

  def MockClear(self):
    self.test_text_window = ''

  def MockGetValue(self):
    return self.test_text_window

  def testPrintToWindow(self):
    self.test_text_window = ''
    mock_atft = MockAtft()
    mock_text_entry = MagicMock()
    mock_text_entry.AppendText.side_effect = self.MockAppendText
    mock_text_entry.Clear.side_effect = self.MockClear
    mock_text_entry.GetValue.side_effect = self.MockGetValue
    mock_atft.PrintToWindow(mock_text_entry, self.TEST_TEXT)
    self.assertEqual(self.TEST_TEXT, self.test_text_window)
    mock_atft.PrintToWindow(mock_text_entry, self.TEST_TEXT2)
    self.assertEqual(self.TEST_TEXT2, self.test_text_window)
    mock_text_entry.AppendText.reset_mock()
    mock_atft.PrintToWindow(mock_text_entry, self.TEST_TEXT2)
    self.assertEqual(False, mock_text_entry.AppendText.called)
    self.assertEqual(self.TEST_TEXT2, self.test_text_window)
    mock_text_entry.Clear()
    mock_atft.PrintToWindow(mock_text_entry, self.TEST_TEXT, True)
    mock_atft.PrintToWindow(mock_text_entry, self.TEST_TEXT2, True)
    self.assertEqual(self.TEST_TEXT + self.TEST_TEXT2, self.test_text_window)

  # Test atft.StartRefreshingDevices(), atft.StopRefresh()
  # Test atft.PauseRefresh(), atft.ResumeRefresh()

  @patch('threading.Timer')
  @patch('wx.QueueEvent')
  def testStartRefreshingDevice(self, mock_queue_event, mock_timer):
    mock_atft = MockAtft()
    mock_atft.StartRefreshingDevices = types.MethodType(
        atft.Atft.StartRefreshingDevices, mock_atft, atft.Atft)
    mock_atft.DEVICE_REFRESH_INTERVAL = 0.01
    mock_atft._ListDevices = MagicMock()
    mock_atft.dev_listed_event = MagicMock()
    mock_timer.side_effect = MagicMock()

    mock_atft.StartRefreshingDevices()

    mock_atft._ListDevices.assert_called()
    mock_atft.StopRefresh()
    self.assertEqual(None, mock_atft.refresh_timer)

  @patch('threading.Timer')
  def testPauseResumeRefreshingDevice(self, mock_timer):
    mock_atft = MockAtft()
    mock_atft.StartRefreshingDevices = types.MethodType(
        atft.Atft.StartRefreshingDevices, mock_atft, atft.Atft)
    mock_atft.DEVICE_REFRESH_INTERVAL = 0.01
    mock_atft._ListDevices = MagicMock()
    mock_atft.dev_listed_event = MagicMock()
    mock_atft._SendDeviceListedEvent = MagicMock()
    mock_timer.side_effect = MagicMock()

    mock_atft.PauseRefresh()
    mock_atft.StartRefreshingDevices()
    mock_atft._ListDevices.assert_not_called()
    mock_atft._SendDeviceListedEvent.assert_called()
    mock_atft.ResumeRefresh()
    mock_atft.StartRefreshingDevices()
    mock_atft._ListDevices.assert_called()
    mock_atft.StopRefresh()

  # Test atft.OnEnterAutoProv
  def testOnEnterAutoProvNormal(self):
    mock_atft = MockAtft()
    mock_atft.auto_prov = False
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft.atft_manager.product_info = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.return_value = 10
    mock_atft.PrintToCommandWindow = MagicMock()
    mock_atft.OnEnterAutoProv()
    self.assertEqual(True, mock_atft.auto_prov)

  def testOnEnterAutoProvNoAtfa(self):
    # Cannot enter auto provisioning mode without an ATFA device
    mock_atft = MockAtft()
    mock_atft.auto_prov = False
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = None
    mock_atft.atft_manager.product_info = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.return_value = 10
    mock_atft.PrintToCommandWindow = MagicMock()
    mock_atft.OnEnterAutoProv()
    self.assertEqual(False, mock_atft.auto_prov)

  def testOnEnterAutoProvNoProduct(self):
    # Cannot enter auto provisioning mode without a product
    mock_atft = MockAtft()
    mock_atft.auto_prov = False
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft.atft_manager.product_info = None
    mock_atft.atft_manager.GetCachedATFAKeysLeft.return_value = 10
    mock_atft.PrintToCommandWindow = MagicMock()
    mock_atft.OnEnterAutoProv()
    self.assertEqual(False, mock_atft.auto_prov)

  def testOnEnterAutoProvNoKeysLeft(self):
    # Cannot enter auto provisioning mode when no keys left
    mock_atft = MockAtft()
    mock_atft.auto_prov = False
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft.atft_manager.product_info = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.return_value = 0
    mock_atft.PrintToCommandWindow = MagicMock()
    mock_atft.OnEnterAutoProv()
    self.assertEqual(False, mock_atft.auto_prov)

  # Test atft.OnLeaveAutoProv
  def testLeaveAutoProvNormal(self):
    # While leaving auto prov mode, need to check device status if the device
    # is waiting.
    mock_atft = MockAtft()
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft.atft_manager.product_info = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.return_value = 0
    mock_atft.PrintToCommandWindow = MagicMock()
    mock_atft.atft_manager.target_devs = []
    test_dev1 = TestDeviceInfo(
        self.TEST_SERIAL1, self.TEST_LOCATION1,
        ProvisionStatus.PROVISION_SUCCESS)
    test_dev2 = TestDeviceInfo(
        self.TEST_SERIAL2, self.TEST_LOCATION1,
        ProvisionStatus.WAITING)
    mock_atft.atft_manager.target_devs.append(test_dev1)
    mock_atft.atft_manager.target_devs.append(test_dev2)
    mock_atft.atft_manager.CheckProvisionStatus.side_effect = (
        lambda target=test_dev2, state=ProvisionStatus.LOCKAVB_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft.OnLeaveAutoProv()
    self.assertEqual(False, mock_atft.auto_prov)
    self.assertEqual(test_dev1.provision_status,
                     ProvisionStatus.PROVISION_SUCCESS)
    mock_atft.atft_manager.CheckProvisionStatus.assert_called_once()
    self.assertEqual(
        test_dev2.provision_status, ProvisionStatus.LOCKAVB_SUCCESS)

  # Test atft.OnChangeKeyThreshold
  def testOnChangeKeyThreshold(self):
    mock_atft = MockAtft()
    mock_atft.configs = {}
    mock_atft.change_threshold_dialog = MagicMock()
    mock_atft.change_threshold_dialog.ShowModal.return_value = wx.ID_OK
    mock_atft.change_threshold_dialog.GetFirstWarning.return_value = 100
    mock_atft.change_threshold_dialog.GetSecondWarning.return_value = 80
    mock_atft.OnChangeKeyThreshold(None)
    self.assertEqual('100', mock_atft.configs['DEFAULT_KEY_THRESHOLD_1'])
    self.assertEqual('80', mock_atft.configs['DEFAULT_KEY_THRESHOLD_2'])

  def testOnChangeKeyThresholdOnlyFirst(self):
    mock_atft = MockAtft()
    mock_atft.configs = {}
    mock_atft.change_threshold_dialog = MagicMock()
    mock_atft.change_threshold_dialog.ShowModal.return_value = wx.ID_OK
    mock_atft.change_threshold_dialog.GetFirstWarning.return_value = 100
    mock_atft.change_threshold_dialog.GetSecondWarning.return_value = None
    mock_atft.OnChangeKeyThreshold(None)
    self.assertEqual('100', mock_atft.configs['DEFAULT_KEY_THRESHOLD_1'])
    self.assertEqual(False, 'DEFAULT_KEY_THRESHOLD_2' in mock_atft.configs)

  def testOnChangeKeyThresholdNone(self):
    mock_atft = MockAtft()
    mock_atft.configs = {}
    mock_atft.change_threshold_dialog = MagicMock()
    mock_atft.change_threshold_dialog.ShowModal.return_value = wx.ID_OK
    mock_atft.change_threshold_dialog.GetFirstWarning.return_value = None
    mock_atft.change_threshold_dialog.GetSecondWarning.return_value = None
    mock_atft.OnChangeKeyThreshold(None)
    self.assertEqual(False, 'DEFAULT_KEY_THRESHOLD_1' in mock_atft.configs)
    self.assertEqual(False, 'DEFAULT_KEY_THRESHOLD_2' in mock_atft.configs)

  # Test atft._HandleAutoProv
  def testHandleAutoProv(self):
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.PROVISION_SUCCESS)
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION1,
                               ProvisionStatus.IDLE)
    mock_atft.atft_manager.target_devs = []
    mock_atft.atft_manager.target_devs.append(test_dev1)
    mock_atft.atft_manager.target_devs.append(test_dev2)
    mock_atft._CreateThread = MagicMock()
    mock_atft._HandleStateTransition = MagicMock()
    mock_atft._HandleAutoProv()
    self.assertEqual(test_dev2.provision_status, ProvisionStatus.WAITING)
    self.assertEqual(1, mock_atft._CreateThread.call_count)

  # Test atft._HandleKeysLeft
  def MockGetKeysLeft(self, keys_left_array):
    if keys_left_array:
      return keys_left_array[0]
    else:
      return None

  def MockSetKeysLeft(self, keys_left_array):
    keys_left_array.append(10)

  def testHandleKeysLeft(self):
    mock_atft = MockAtft()
    mock_black = MagicMock()
    mock_atft.COLOR_BLACK = mock_black
    mock_atft.TITLE_KEYS_LEFT = ''
    mock_atft._SetStatusTextColor = MagicMock()
    mock_atft.change_threshold_dialog = MagicMock()
    mock_atft.change_threshold_dialog.GetFirstWarning.return_value = None
    mock_atft.change_threshold_dialog.GetSecondWarning.return_value = None
    keys_left_array = []
    mock_atft.atft_manager.GetCachedATFAKeysLeft = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.side_effect = (
        lambda: self.MockGetKeysLeft(keys_left_array))
    mock_atft.atft_manager.UpdateATFAKeysLeft.side_effect = (
        lambda: self.MockSetKeysLeft(keys_left_array))
    mock_atft._HandleKeysLeft()
    mock_atft._SetStatusTextColor.assert_called_once_with('10', mock_black)

  def testHandleKeysLeftKeysNotNone(self):
    mock_atft = MockAtft()
    mock_black = MagicMock()
    mock_atft.COLOR_BLACK = mock_black
    mock_atft.TITLE_KEYS_LEFT = ''
    mock_atft._SetStatusTextColor = MagicMock()
    mock_atft.change_threshold_dialog = MagicMock()
    mock_atft.change_threshold_dialog.GetFirstWarning.return_value = None
    mock_atft.change_threshold_dialog.GetSecondWarning.return_value = None
    keys_left_array = [10]
    mock_atft.atft_manager.GetCachedATFAKeysLeft = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.side_effect = (
        lambda: self.MockGetKeysLeft(keys_left_array))
    mock_atft._HandleKeysLeft()
    mock_atft._SetStatusTextColor.assert_called_once_with('10', mock_black)
    mock_atft.atft_manager.UpdateATFAKeysLeft.assert_not_called()

  def testHandleKeysLeftKeysNone(self):
    mock_atft = MockAtft()
    mock_black = MagicMock()
    mock_atft.COLOR_BLACK = mock_black
    mock_atft.TITLE_KEYS_LEFT = ''
    mock_atft._SetStatusTextColor = MagicMock()
    mock_atft.change_threshold_dialog = MagicMock()
    mock_atft.change_threshold_dialog.GetFirstWarning.return_value = None
    mock_atft.change_threshold_dialog.GetSecondWarning.return_value = None
    keys_left_array = []
    mock_atft.atft_manager.GetCachedATFAKeysLeft = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.return_value = 0
    mock_atft._HandleKeysLeft()
    mock_atft._SetStatusTextColor.assert_called_once_with('0', mock_black)

  # The statusbar should change color if the key is lower than threshold.
  def testHandleKeysLeftChangeStatusColor(self):
    mock_atft = MockAtft()
    mock_black = MagicMock()
    mock_yellow = MagicMock()
    mock_red = MagicMock()
    mock_atft.COLOR_BLACK = mock_black
    mock_atft.COLOR_YELLOW = mock_yellow
    mock_atft.COLOR_RED = mock_red
    mock_atft.TITLE_KEYS_LEFT = ''
    mock_atft._SetStatusTextColor = MagicMock()
    mock_atft.change_threshold_dialog = MagicMock()
    mock_atft.change_threshold_dialog.GetFirstWarning.return_value = 11
    mock_atft.change_threshold_dialog.GetSecondWarning.return_value = 10
    # past first warning.
    keys_left_array = [10]
    mock_atft.atft_manager.GetCachedATFAKeysLeft = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.side_effect = (
        lambda: self.MockGetKeysLeft(keys_left_array))
    mock_atft._HandleKeysLeft()
    mock_atft._SetStatusTextColor.assert_called_once_with('10', mock_yellow)

    # past second warning
    mock_atft._SetStatusTextColor.reset_mock()
    keys_left_array = [9]
    mock_atft.atft_manager.GetCachedATFAKeysLeft = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.side_effect = (
        lambda: self.MockGetKeysLeft(keys_left_array))
    mock_atft._HandleKeysLeft()
    mock_atft._SetStatusTextColor.assert_called_once_with('9', mock_red)

  # Test atft._HandleStateTransition
  def MockStateChange(self, target, state):
    target.provision_status = state
    if state == ProvisionStatus.REBOOT_SUCCESS:
      target.provision_state.bootloader_locked = True
    if state == ProvisionStatus.FUSEATTR_SUCCESS:
      target.provision_state.avb_perm_attr_set = True
    if state == ProvisionStatus.LOCKAVB_SUCCESS:
      target.provision_state.avb_locked = True
    if state == ProvisionStatus.PROVISION_SUCCESS:
      target.provision_state.provisioned = True

  def testHandleStateTransition(self):
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.REBOOT_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    self.assertEqual(ProvisionStatus.PROVISION_SUCCESS,
                     test_dev1.provision_status)

  def testHandleStateTransitionFuseVbootFail(self):
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEVBOOT_FAILED:
            self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_SUCCESS:
            self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_SUCCESS:
            self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.PROVISION_SUCCESS:
            self.MockStateChange(target, state))
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    self.assertEqual(ProvisionStatus.FUSEVBOOT_FAILED,
                     test_dev1.provision_status)

  def testHandleStateTransitionRebootFail(self):
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.REBOOT_FAILED:
        self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    self.assertEqual(ProvisionStatus.REBOOT_FAILED, test_dev1.provision_status)

  def testHandleStateTransitionFuseAttrFail(self):
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.REBOOT_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_FAILED:
        self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    self.assertEqual(ProvisionStatus.FUSEATTR_FAILED,
                     test_dev1.provision_status)

  def testHandleStateTransitionLockAVBFail(self):
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.REBOOT_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_FAILED:
        self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    self.assertEqual(ProvisionStatus.LOCKAVB_FAILED, test_dev1.provision_status)

  def testHandleStateTransitionProvisionFail(self):
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.REBOOT_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.PROVISION_FAILED:
        self.MockStateChange(target, state))
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    self.assertEqual(ProvisionStatus.PROVISION_FAILED,
                     test_dev1.provision_status)

  def testHandleStateTransitionSkipStep(self):
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.REBOOT_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))

    # The device has bootloader_locked and avb_locked set. Should fuse perm attr
    # and provision key.
    test_dev1.provision_state.bootloader_locked = True
    test_dev1.provision_state.avb_locked = True
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    self.assertEqual(ProvisionStatus.PROVISION_SUCCESS,
                     test_dev1.provision_status)
    mock_atft._FusePermAttrTarget.assert_called_once()
    mock_atft._ProvisionTarget.assert_called_once()
    self.assertEqual(True, test_dev1.provision_state.bootloader_locked)
    self.assertEqual(True, test_dev1.provision_state.avb_perm_attr_set)
    self.assertEqual(True, test_dev1.provision_state.avb_locked)
    self.assertEqual(True, test_dev1.provision_state.provisioned)

  # Test atft._UpdateKeysLeftInATFA
  def testUpdateATFAKeysLeft(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._UpdateKeysLeftInATFA()
    mock_atft.atft_manager.UpdateATFAKeysLeft.assert_called()

  # Test atft._FuseVbootKey
  def MockGetTargetDevice(self, serial):
    return self.device_map.get(serial)

  def MockReboot(self, target, timeout, success, fail):
    success()
    target.provision_state.bootloader_locked = True

  def MockRebootStateNoChange(self, target, timeout, success, fail):
    success()
    target.provision_state.bootloader_locked = False

  @patch('wx.QueueEvent')
  @patch('time.sleep')
  def testFuseVbootKey(self, mock_sleep, mock_queue_event):
    mock_atft = MockAtft()
    mock_atft.dev_listed_event = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft._SendMessageEvent = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.side_effect = (
        self.MockGetTargetDevice)
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.IDLE)
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEVBOOT_FAILED)
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEVBOOT_SUCCESS)
    test_dev3.provision_state.bootloader_locked = True
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    serials = [self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3]
    mock_atft.atft_manager.Reboot.side_effect = self.MockReboot
    mock_atft._FuseVbootKey(serials)
    calls = [call(test_dev1), call(test_dev2)]
    mock_atft.atft_manager.FuseVbootKey.assert_has_calls(calls)
    self.assertEqual(2, mock_atft.atft_manager.Reboot.call_count)
    mock_queue_event.assert_called()

  @patch('wx.QueueEvent')
  @patch('time.sleep')
  def testFuseVbootKeyExceptions(self, mock_sleep, mock_queue_event):
    mock_atft = MockAtft()
    mock_atft.dev_listed_event = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft._SendMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.side_effect = (
        self.MockGetTargetDevice)
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.IDLE)
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEVBOOT_FAILED)
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEVBOOT_SUCCESS)
    test_dev3.provision_state.bootloader_locked = True
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    serials = [self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3]
    mock_atft.atft_manager.Reboot.side_effect = self.MockReboot
    mock_atft.atft_manager.FuseVbootKey.side_effect = (
        fastboot_exceptions.ProductNotSpecifiedException)
    mock_atft._FuseVbootKey(serials)
    self.assertEqual(2, mock_atft._HandleException.call_count)
    mock_queue_event.assert_not_called()

    # Reset states.
    mock_atft._HandleException.reset_mock()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.IDLE)
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEVBOOT_FAILED)
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEVBOOT_SUCCESS)
    test_dev3.provision_state.bootloader_locked = True
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    serials = [self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3]
    mock_atft.atft_manager.FuseVbootKey.side_effect = (
        fastboot_exceptions.FastbootFailure(''))
    mock_atft._FuseVbootKey(serials)
    self.assertEqual(2, mock_atft._HandleException.call_count)

    # Reset states, test reboot failure
    mock_atft._HandleException.reset_mock()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.IDLE)
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEVBOOT_FAILED)
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEVBOOT_SUCCESS)
    test_dev3.provision_state.bootloader_locked = True
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    serials = [self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3]
    mock_atft.atft_manager.Reboot.side_effect = (
        fastboot_exceptions.FastbootFailure(''))
    mock_atft.atft_manager.FuseVbootKey = MagicMock()
    mock_atft._FuseVbootKey(serials)
    self.assertEqual(2, mock_atft._HandleException.call_count)

  # Test atft._FusePermAttr
  def testFusePermAttr(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft._SendMessageEvent = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.side_effect = (
        self.MockGetTargetDevice)
    test_dev1 = TestDeviceInfo(
        self.TEST_SERIAL1, self.TEST_LOCATION1,
        ProvisionStatus.FUSEVBOOT_SUCCESS)
    test_dev1.provision_state.bootloader_locked = True
    test_dev2 = TestDeviceInfo(
        self.TEST_SERIAL2, self.TEST_LOCATION2,
        ProvisionStatus.REBOOT_SUCCESS)
    test_dev2.provision_state.bootloader_locked = True
    test_dev3 = TestDeviceInfo(
        self.TEST_SERIAL3, self.TEST_LOCATION2,
        ProvisionStatus.FUSEATTR_FAILED)
    test_dev3.provision_state.bootloader_locked = True
    test_dev4 = TestDeviceInfo(
        self.TEST_SERIAL4, self.TEST_LOCATION2,
        ProvisionStatus.FUSEATTR_SUCCESS)
    test_dev4.provision_state.bootloader_locked = True
    test_dev4.provision_state.avb_perm_attr_set = True
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    self.device_map[self.TEST_SERIAL4] = test_dev4
    serials = [
        self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3,
        self.TEST_SERIAL4
    ]
    mock_atft._FusePermAttr(serials)
    calls = [call(test_dev1), call(test_dev2), call(test_dev3)]
    mock_atft.atft_manager.FusePermAttr.assert_has_calls(calls)

  def testFusePermAttrExceptions(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft._SendMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.side_effect = (
        self.MockGetTargetDevice)
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.FUSEVBOOT_SUCCESS)
    test_dev1.provision_state.bootloader_locked = True
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.REBOOT_SUCCESS)
    test_dev2.provision_state.bootloader_locked = True
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEATTR_FAILED)
    test_dev3.provision_state.bootloader_locked = True
    test_dev4 = TestDeviceInfo(self.TEST_SERIAL4, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEATTR_SUCCESS)
    test_dev4.provision_state.bootloader_locked = True
    test_dev4.provision_state.avb_perm_attr_set = True
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    self.device_map[self.TEST_SERIAL4] = test_dev4
    serials = [
        self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3,
        self.TEST_SERIAL4
    ]
    mock_atft.atft_manager.FusePermAttr.side_effect = (
        fastboot_exceptions.ProductNotSpecifiedException)
    mock_atft._FusePermAttr(serials)
    self.assertEqual(3, mock_atft._HandleException.call_count)
    # Reset states
    mock_atft._HandleException.reset_mock()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.FUSEVBOOT_SUCCESS)
    test_dev1.provision_state.bootloader_locked = True
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.REBOOT_SUCCESS)
    test_dev2.provision_state.bootloader_locked = True
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEATTR_FAILED)
    test_dev3.provision_state.bootloader_locked = True
    test_dev4 = TestDeviceInfo(self.TEST_SERIAL4, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEATTR_SUCCESS)
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    self.device_map[self.TEST_SERIAL4] = test_dev4
    mock_atft.atft_manager.FusePermAttr.side_effect = (
        fastboot_exceptions.FastbootFailure(''))
    mock_atft._FusePermAttr(serials)
    self.assertEqual(3, mock_atft._HandleException.call_count)

  # Test atft._LockAvb
  def testLockAvb(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft._SendMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.side_effect = (
        self.MockGetTargetDevice)
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.FUSEATTR_SUCCESS)
    test_dev1.provision_state.bootloader_locked = True
    test_dev1.provision_state.avb_perm_attr_set = True
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.LOCKAVB_FAILED)
    test_dev2.provision_state.bootloader_locked = True
    test_dev2.provision_state.avb_perm_attr_set = True
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEATTR_FAILED)
    test_dev3.provision_state.bootloader_locked = True
    test_dev3.provision_state.avb_perm_attr_set = False
    test_dev4 = TestDeviceInfo(self.TEST_SERIAL4, self.TEST_LOCATION2,
                               ProvisionStatus.IDLE)
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    self.device_map[self.TEST_SERIAL4] = test_dev4
    serials = [
        self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3,
        self.TEST_SERIAL4
    ]
    mock_atft._LockAvb(serials)
    calls = [call(test_dev1), call(test_dev2)]
    mock_atft.atft_manager.LockAvb.assert_has_calls(calls)

  def testLockAvbExceptions(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft._SendMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.side_effect = (
        self.MockGetTargetDevice)
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.FUSEATTR_SUCCESS)
    test_dev1.provision_state.bootloader_locked = True
    test_dev1.provision_state.avb_perm_attr_set = True
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.LOCKAVB_FAILED)
    test_dev2.provision_state.bootloader_locked = True
    test_dev2.provision_state.avb_perm_attr_set = True
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEATTR_FAILED)
    test_dev3.provision_state.bootloader_locked = True
    test_dev3.provision_state.avb_perm_attr_set = False
    test_dev4 = TestDeviceInfo(self.TEST_SERIAL4, self.TEST_LOCATION2,
                               ProvisionStatus.IDLE)
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    self.device_map[self.TEST_SERIAL4] = test_dev4
    serials = [
        self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3,
        self.TEST_SERIAL4
    ]
    mock_atft.atft_manager.LockAvb.side_effect = (
        fastboot_exceptions.FastbootFailure(''))
    mock_atft._LockAvb(serials)
    self.assertEqual(2, mock_atft._HandleException.call_count)

  # Test atft._CheckLowKeyAlert
  def MockGetCachedATFAKeysLeft(self):
    return self.atfa_keys

  def MockSuccessProvision(self, target):
    self.atfa_keys -= 1

  def MockFailedProvision(self, target):
    pass

  def testCheckLowKeyAlert(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._SendLowKeyAlertEvent = MagicMock()
    dialog = MagicMock()
    dialog.GetFirstWarning = MagicMock()
    dialog.GetSecondWarning = MagicMock()
    dialog.GetFirstWarning.return_value = 101
    dialog.GetSecondWarning.return_value = 100
    mock_atft.change_threshold_dialog = dialog
    mock_atft.first_key_alert_shown = False
    mock_atft.second_key_alert_shown = False
    test_dev1 = TestDeviceInfo(
        self.TEST_SERIAL1, self.TEST_LOCATION1, ProvisionStatus.WAITING)
    mock_atft.atft_manager.GetCachedATFAKeysLeft.side_effect = (
        self.MockGetCachedATFAKeysLeft)
    self.atfa_keys = 102
    # First provision succeed
    # First check 101 left, no alert
    mock_atft.atft_manager.Provision.side_effect = self.MockSuccessProvision
    mock_atft._ProvisionTarget(test_dev1)
    mock_atft._SendLowKeyAlertEvent.assert_not_called()
    # Second provision failed
    # Second check, assume 100 left, verify, 101 left no alert
    mock_atft.atft_manager.Provision.side_effect = self.MockFailedProvision
    mock_atft._ProvisionTarget(test_dev1)
    mock_atft._SendLowKeyAlertEvent.assert_not_called()
    # Third check, assume 100 left, verify, 100 left, first warning
    mock_atft.atft_manager.Provision.side_effect = self.MockSuccessProvision
    mock_atft._ProvisionTarget(test_dev1)
    mock_atft._SendLowKeyAlertEvent.assert_called_once()
    self.assertEqual(True, mock_atft.first_key_alert_shown)
    mock_atft._SendLowKeyAlertEvent.reset_mock()
    # Fourth check, assume 99 left, verify, 99 left, second warning
    mock_atft._ProvisionTarget(test_dev1)
    mock_atft._SendLowKeyAlertEvent.assert_called_once()
    self.assertEqual(True, mock_atft.second_key_alert_shown)
    mock_atft._SendLowKeyAlertEvent.reset_mock()
    # Fifth check, no more warning, 98 left
    mock_atft._ProvisionTarget(test_dev1)
    mock_atft._SendLowKeyAlertEvent.assert_not_called()

  def testCheckLowKeyAlertException(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._SendLowKeyAlertEvent = MagicMock()
    dialog = MagicMock()
    dialog.GetFirstWarning = MagicMock()
    dialog.GetSecondWarning = MagicMock()
    dialog.GetFirstWarning.return_value = 101
    dialog.GetSecondWarning.return_value = 100
    mock_atft.change_threshold_dialog = dialog
    mock_atft.first_key_alert_shown = False
    mock_atft.second_key_alert_shown = False
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.UpdateATFAKeysLeft.side_effect = (
        fastboot_exceptions.FastbootFailure(''))
    mock_atft._CheckLowKeyAlert()
    mock_atft._HandleException.assert_called_once()
    mock_atft._HandleException.reset_mock()
    mock_atft.atft_manager.UpdateATFAKeysLeft.side_effect = (
        fastboot_exceptions.ProductNotSpecifiedException)
    mock_atft._CheckLowKeyAlert()
    mock_atft._HandleException.assert_called_once()
    mock_atft._HandleException.reset_mock()
    mock_atft.atft_manager.UpdateATFAKeysLeft.side_effect = (
        fastboot_exceptions.DeviceNotFoundException)
    mock_atft._CheckLowKeyAlert()
    mock_atft._HandleException.assert_called_once()

  # Test atft._Reboot
  def testReboot(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._Reboot()
    mock_atft.atft_manager.RebootATFA.assert_called_once()

  def testRebootExceptions(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.RebootATFA.side_effect = (
        fastboot_exceptions.DeviceNotFoundException())
    mock_atft._Reboot()
    mock_atft._HandleException.assert_called_once()
    mock_atft._HandleException.reset_mock()
    mock_atft.atft_manager.RebootATFA.side_effect = (
        fastboot_exceptions.FastbootFailure(''))
    mock_atft._Reboot()
    mock_atft._HandleException.assert_called_once()

  # Test atft._Shutdown
  def testShutdown(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._Shutdown()
    mock_atft.atft_manager.ShutdownATFA.assert_called_once()

  def testShutdownExceptions(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.ShutdownATFA.side_effect = (
        fastboot_exceptions.DeviceNotFoundException())
    mock_atft._Shutdown()
    mock_atft._HandleException.assert_called_once()
    mock_atft._HandleException.reset_mock()
    mock_atft.atft_manager.ShutdownATFA.side_effect = (
        fastboot_exceptions.FastbootFailure(''))
    mock_atft._Shutdown()
    mock_atft._HandleException.assert_called_once()

  # Test atft._ManualProvision
  def testManualProvision(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.Provision = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft._CheckLowKeyAlert = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.side_effect = (
        self.MockGetTargetDevice)
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.PROVISION_FAILED)
    test_dev1.provision_state.bootloader_locked = True
    test_dev1.provision_state.avb_perm_attr_set = True
    test_dev1.provision_state.avb_locked = True
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.LOCKAVB_SUCCESS)
    test_dev2.provision_state.bootloader_locked = True
    test_dev2.provision_state.avb_perm_attr_set = True
    test_dev2.provision_state.avb_locked = True
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEATTR_FAILED)
    test_dev3.provision_state.bootloader_locked = True
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    serials = [self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3]
    mock_atft._ManualProvision(serials)
    calls = [call(test_dev1), call(test_dev2)]
    mock_atft.atft_manager.Provision.assert_has_calls(calls)

  def testManualProvisionExceptions(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.Provision = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft._CheckLowKeyAlert = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.side_effect = (
        self.MockGetTargetDevice)
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.PROVISION_FAILED)
    test_dev1.provision_state.bootloader_locked = True
    test_dev1.provision_state.avb_perm_attr_set = True
    test_dev1.provision_state.avb_locked = True
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.LOCKAVB_SUCCESS)
    test_dev2.provision_state.bootloader_locked = True
    test_dev2.provision_state.avb_perm_attr_set = True
    test_dev2.provision_state.avb_locked = True
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEATTR_FAILED)
    test_dev3.provision_state.bootloader_locked = True
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    serials = [self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3]
    mock_atft.atft_manager.Provision.side_effect = (
        fastboot_exceptions.FastbootFailure(''))
    mock_atft._ManualProvision(serials)
    self.assertEqual(2, mock_atft._HandleException.call_count)
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.PROVISION_FAILED)
    test_dev1.provision_state.bootloader_locked = True
    test_dev1.provision_state.avb_perm_attr_set = True
    test_dev1.provision_state.avb_locked = True
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.LOCKAVB_SUCCESS)
    test_dev2.provision_state.bootloader_locked = True
    test_dev2.provision_state.avb_perm_attr_set = True
    test_dev2.provision_state.avb_locked = True
    test_dev3 = TestDeviceInfo(self.TEST_SERIAL3, self.TEST_LOCATION2,
                               ProvisionStatus.FUSEATTR_FAILED)
    test_dev3.provision_state.bootloader_locked = True
    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3
    serials = [self.TEST_SERIAL1, self.TEST_SERIAL2, self.TEST_SERIAL3]
    mock_atft._HandleException.reset_mock()
    mock_atft.atft_manager.Provision.side_effect = (
        fastboot_exceptions.DeviceNotFoundException())
    mock_atft._ManualProvision(serials)
    self.assertEqual(2, mock_atft._HandleException.call_count)

  # Test atft._ProcessKey
  def testProcessKeySuccess(self):
    mock_atft = MockAtft()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft._UpdateKeysLeftInATFA = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_path = MagicMock()

    mock_atft._ProcessKey(mock_path)
    mock_atft.atft_manager.atfa_dev.Download.assert_called_once_with(mock_path)
    mock_atft.atft_manager.ProcessATFAKey.assert_called_once()
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_not_called()

    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_called_once()
    mock_atft._UpdateKeysLeftInATFA.assert_called_once()

  def testProcessKeyFailure(self):
    self.TestProcessKeyFailureCommon(
        fastboot_exceptions.FastbootFailure(''))
    self.TestProcessKeyFailureCommon(
        fastboot_exceptions.DeviceNotFoundException)
    self.TestProcessKeyFailureCommon(
        fastboot_exceptions.FastbootFailure(''), True)
    self.TestProcessKeyFailureCommon(
        fastboot_exceptions.DeviceNotFoundException, True)

  def TestProcessKeyFailureCommon(self, exception, failure_download=False):
    mock_atft = MockAtft()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft._UpdateKeysLeftInATFA = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_path = MagicMock()
    if not failure_download:
      mock_atft.atft_manager.ProcessATFAKey = MagicMock()
      mock_atft.atft_manager.ProcessATFAKey.side_effect = exception
    else:
      mock_atft.atft_manager.atfa_dev.Download = MagicMock()
      mock_atft.atft_manager.atfa_dev.Download.side_effect = exception

    mock_atft._ProcessKey(mock_path)
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_called_once()

    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_not_called()

  # Test atft._UpdateATFA
  def testUpdateATFASuccess(self):
    mock_atft = MockAtft()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft._UpdateKeysLeftInATFA = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_path = MagicMock()

    mock_atft._UpdateATFA(mock_path)
    mock_atft.atft_manager.atfa_dev.Download.assert_called_once_with(mock_path)
    mock_atft.atft_manager.UpdateATFA.assert_called_once()
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_not_called()

    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_called_once()
    mock_atft._UpdateKeysLeftInATFA.assert_called_once()

  def testUpdateATFAFailure(self):
    self.TestUpdateATFAFailureCommon(
        fastboot_exceptions.FastbootFailure(''))
    self.TestUpdateATFAFailureCommon(
        fastboot_exceptions.DeviceNotFoundException)
    self.TestUpdateATFAFailureCommon(
        fastboot_exceptions.FastbootFailure(''), True)
    self.TestUpdateATFAFailureCommon(
        fastboot_exceptions.DeviceNotFoundException, True)

  def TestUpdateATFAFailureCommon(self, exception, failure_download=False):
    mock_atft = MockAtft()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft._UpdateKeysLeftInATFA = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_path = MagicMock()
    if not failure_download:
      mock_atft.atft_manager.UpdateATFA = MagicMock()
      mock_atft.atft_manager.UpdateATFA.side_effect = exception
    else:
      mock_atft.atft_manager.atfa_dev.Download = MagicMock()
      mock_atft.atft_manager.atfa_dev.Download.side_effect = exception

    mock_atft._UpdateATFA(mock_path)
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_called_once()

    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_not_called()

  # Test atft._PurgeKey
  def testPurgeKey(self):
    mock_atft = MockAtft()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft._UpdateKeysLeftInATFA = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()

    mock_atft._PurgeKey()
    mock_atft.atft_manager.PurgeATFAKey.assert_called_once()
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_not_called()
    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_called_once()

    # FastbootFailure
    mock_atft._HandleException.reset_mock()
    mock_atft._SendOperationSucceedEvent.reset_mock()
    mock_atft.atft_manager.PurgeATFAKey = MagicMock()
    mock_atft.atft_manager.PurgeATFAKey.side_effect = (
        fastboot_exceptions.FastbootFailure(''))
    mock_atft._PurgeKey()
    mock_atft._SendOperationSucceedEvent.assert_not_called()
    mock_atft._HandleException.assert_called_once()

    # DeviceNotFoundException
    mock_atft._HandleException.reset_mock()
    mock_atft._SendOperationSucceedEvent.reset_mock()
    mock_atft.atft_manager.PurgeATFAKey = MagicMock()
    mock_atft.atft_manager.PurgeATFAKey.side_effect = (
        fastboot_exceptions.DeviceNotFoundException)
    mock_atft._PurgeKey()
    mock_atft._SendOperationSucceedEvent.assert_not_called()
    mock_atft._HandleException.assert_called_once()

    # ProductNotSpecifiedException
    mock_atft._HandleException.reset_mock()
    mock_atft._SendOperationSucceedEvent.reset_mock()
    mock_atft.atft_manager.PurgeATFAKey = MagicMock()
    mock_atft.atft_manager.PurgeATFAKey.side_effect = (
        fastboot_exceptions.ProductNotSpecifiedException)
    mock_atft._PurgeKey()
    mock_atft._SendOperationSucceedEvent.assert_not_called()
    mock_atft._HandleException.assert_called_once()

  # Test atft._GetRegFile
  @patch('__builtin__.open')
  def testGetRegFile(self, mock_open):
    mock_atft = MockAtft()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft._UpdateKeysLeftInATFA = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_path = MagicMock()
    mock_path.encode.return_value = mock_path

    mock_atft._GetRegFile(mock_path)
    mock_open.assert_called_once_with(mock_path, 'w+')
    mock_atft.atft_manager.atfa_dev.Upload.assert_called_once_with(mock_path)
    mock_atft.atft_manager.PrepareFile.assert_called_once_with('reg')
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_not_called()
    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_called_once()

    # Cannot create file
    mock_atft._HandleException.reset_mock()
    mock_atft._SendOperationStartEvent.reset_mock()
    mock_atft._SendOperationSucceedEvent.reset_mock()
    mock_atft.PauseRefresh.reset_mock()
    mock_atft.ResumeRefresh.reset_mock()
    mock_open.side_effect = IOError
    mock_atft._GetRegFile(mock_path)
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_called_once()
    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_not_called()

  def testGetRegFileFailure(self):
    self.TestGetRegFileFailureCommon(
        fastboot_exceptions.FastbootFailure(''))
    self.TestGetRegFileFailureCommon(
        fastboot_exceptions.DeviceNotFoundException)
    self.TestGetRegFileFailureCommon(
        fastboot_exceptions.FastbootFailure(''), True)
    self.TestGetRegFileFailureCommon(
        fastboot_exceptions.DeviceNotFoundException, True)

  def TestGetRegFileFailureCommon(
      self, exception, upload_fail=False):
    with patch('__builtin__.open') as mock_open:
      mock_atft = MockAtft()
      mock_atft.atft_manager = MagicMock()
      mock_atft.atft_manager.atfa_dev = MagicMock()
      mock_atft._UpdateKeysLeftInATFA = MagicMock()
      mock_atft._SendOperationStartEvent = MagicMock()
      mock_atft._SendOperationSucceedEvent = MagicMock()
      mock_atft.PauseRefresh = MagicMock()
      mock_atft.ResumeRefresh = MagicMock()
      mock_atft._HandleException = MagicMock()
      mock_atft._SendAlertEvent = MagicMock()
      mock_path = MagicMock()
      mock_path.encode.return_value = mock_path
      mock_open.side_effect = IOError
      if not upload_fail:
        mock_atft.atft_manager.PrepareFile.side_effect = exception
      else:
        mock_atft.atft_manager.atfa_dev.Upload.side_effect = exception

      mock_atft._GetRegFile(mock_path)

      mock_atft.PauseRefresh.assert_called_once()
      mock_atft.ResumeRefresh.assert_called_once()
      mock_atft._HandleException.assert_called_once()
      mock_atft._SendOperationStartEvent.assert_called_once()
      mock_atft._SendOperationSucceedEvent.assert_not_called()

  # Test atft._GetAuditFile
  @patch('__builtin__.open')
  def testGetAuditFile(self, mock_open):
    mock_atft = MockAtft()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = MagicMock()
    mock_atft._UpdateKeysLeftInATFA = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft._SendAlertEvent = MagicMock()
    mock_path = MagicMock()
    mock_path.encode.return_value = mock_path

    mock_atft._GetAuditFile(mock_path)
    mock_open.assert_called_once_with(mock_path, 'w+')
    mock_atft.atft_manager.atfa_dev.Upload.assert_called_once_with(mock_path)
    mock_atft.atft_manager.PrepareFile.assert_called_once_with('audit')
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_not_called()
    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_called_once()

    # Cannot create file
    mock_atft._HandleException.reset_mock()
    mock_atft._SendOperationStartEvent.reset_mock()
    mock_atft._SendOperationSucceedEvent.reset_mock()
    mock_atft.PauseRefresh.reset_mock()
    mock_atft.ResumeRefresh.reset_mock()
    mock_open.side_effect = IOError
    mock_atft._GetAuditFile(mock_path)
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_called_once()
    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_not_called()

  def testGetAuditFileFailure(self):
    self.TestGetAuditFileFailureCommon(
        fastboot_exceptions.FastbootFailure(''))
    self.TestGetAuditFileFailureCommon(
        fastboot_exceptions.DeviceNotFoundException)
    self.TestGetAuditFileFailureCommon(
        fastboot_exceptions.FastbootFailure(''), True)
    self.TestGetAuditFileFailureCommon(
        fastboot_exceptions.DeviceNotFoundException, True)

  def TestGetAuditFileFailureCommon(
      self, exception, upload_fail=False):
    with patch('__builtin__.open') as mock_open:
      mock_atft = MockAtft()
      mock_atft.atft_manager = MagicMock()
      mock_atft.atft_manager.atfa_dev = MagicMock()
      mock_atft._UpdateKeysLeftInATFA = MagicMock()
      mock_atft._SendOperationStartEvent = MagicMock()
      mock_atft._SendOperationSucceedEvent = MagicMock()
      mock_atft.PauseRefresh = MagicMock()
      mock_atft.ResumeRefresh = MagicMock()
      mock_atft._HandleException = MagicMock()
      mock_atft._SendAlertEvent = MagicMock()
      mock_path = MagicMock()
      mock_path.encode.return_value = mock_path
      mock_open.side_effect = IOError
      if not upload_fail:
        mock_atft.atft_manager.PrepareFile.side_effect = exception
      else:
        mock_atft.atft_manager.atfa_dev.Upload.side_effect = exception

      mock_atft._GetAuditFile(mock_path)

      mock_atft.PauseRefresh.assert_called_once()
      mock_atft.ResumeRefresh.assert_called_once()
      mock_atft._HandleException.assert_called_once()
      mock_atft._SendOperationStartEvent.assert_called_once()
      mock_atft._SendOperationSucceedEvent.assert_not_called()

  # Test AtftLog.Initialize()
  @patch('atft.AtftLog.Info', MagicMock())
  @patch('atft.AtftLog._CreateLogFile')
  @patch('os.path.isfile')
  @patch('os.path.exists')
  @patch('os.mkdir')
  @patch('os.listdir')
  @patch('__builtin__.open')
  def testAtftLogCreate(self, mock_open, mock_listdir, mock_makedir,
                        mock_path_exists, mock_isfile, mock_createfile):
    log_dir = self.LOG_DIR
    log_size = 10
    log_file_number = 1
    mock_listdir.return_value = ['atft_log_1', 'atft_log_2']
    # Log directory not exist
    mock_path_exists.return_value = False
    # listdir return value is file
    mock_isfile.return_value = True
    atft_log = atft.AtftLog(log_dir, log_size, log_file_number)
    mock_makedir.assert_called_once_with(self.LOG_DIR)
    mock_createfile.assert_not_called()
    self.assertEqual(atft_log.log_dir_file, os.path.join(
        self.LOG_DIR, 'atft_log_2'))

  @patch('atft.AtftLog.Info', MagicMock())
  @patch('atft.AtftLog._CreateLogFile')
  @patch('os.path.isfile')
  @patch('os.path.exists')
  @patch('os.mkdir')
  @patch('os.listdir')
  @patch('__builtin__.open')
  def testAtftLogCreateDirExists(
      self, mock_open, mock_listdir, mock_makedir,
      mock_path_exists, mock_isfile, mock_createfile):
    log_dir = self.LOG_DIR
    log_size = 10
    log_file_number = 1
    mock_listdir.return_value = ['atft_log_1', 'atft_log_2']
    # Log directory already exists
    mock_path_exists.return_value = True
    # listdir return value is file
    mock_isfile.return_value = True
    atft_log = atft.AtftLog(log_dir, log_size, log_file_number)
    mock_makedir.assert_not_called()
    mock_createfile.assert_not_called()

  @patch('atft.AtftLog.Info', MagicMock())
  @patch('atft.AtftLog._CreateLogFile')
  @patch('os.path.isfile')
  @patch('os.path.exists')
  @patch('os.mkdir')
  @patch('os.listdir')
  @patch('__builtin__.open')
  def testAtftLogCreateFirstLog(
      self, mock_open, mock_listdir, mock_makedir,
      mock_path_exists, mock_isfile, mock_createfile):
    log_dir = self.LOG_DIR
    log_size = 10
    log_file_number = 1
    mock_listdir.return_value = []
    # Log directory already exists
    mock_path_exists.return_value = True
    # listdir return value is file
    mock_isfile.return_value = True
    atft_log = atft.AtftLog(log_dir, log_size, log_file_number)
    mock_createfile.assert_called_once()

  # Test AtftLog._CreateLogFile()
  def MockCheckPath(self, path):
    if path == self.LOG_DIR:
      return True
    else:
      return False

  @patch('atft.AtftLog.Initialize', MagicMock())
  @patch('os.path.exists')
  @patch('os.listdir')
  @patch('__builtin__.open')
  def testAtftLogCreate(self, mock_open, mock_listdir, mock_path_exists):
    log_dir = self.LOG_DIR
    log_size = 10
    log_file_number = 1
    mock_listdir.return_value = []
    mock_path_exists.side_effect = self.MockCheckPath
    atft_log = atft.AtftLog(log_dir, log_size, log_file_number)
    atft_log.Info = MagicMock()
    mock_get_time = MagicMock()
    atft_log._GetCurrentTimestamp = mock_get_time
    mock_get_time.return_value = self.TEST_TIMESTAMP
    atft_log._CreateLogFile()
    mock_open.assert_called_once()
    log_file = mock_open.call_args[0][0]
    mock_get_time.assert_called_once()
    self.assertEqual(log_file, atft_log.log_dir_file)
    self.assertEqual(os.path.join(
        self.LOG_DIR, 'atft_log_' + str(self.TEST_TIMESTAMP)), log_file)

  # Test AtftLog._LimitSize()
  def MockListDir(self, dir):
    return self.files

  def MockCreateFile(self, add_file):
    self.files.append(add_file)

  @patch('os.path.getsize')
  @patch('atft.AtftLog.Initialize', MagicMock())
  @patch('os.path.isfile')
  @patch('os.path.exists')
  @patch('os.listdir')
  @patch('os.remove')
  @patch('__builtin__.open')
  def testLimitSize(
      self, mock_open, mock_remove, mock_listdir, mock_path_exists, mock_isfile,
      mock_getsize):
    log_dir = self.LOG_DIR
    log_size = 10
    log_file_number = 2
    # 1 is older than 2
    self.files = ['atft_log_1', 'atft_log_2']
    mock_listdir.side_effect = self.MockListDir
    mock_isfile.return_value = True
    mock_getsize.return_value = 5
    atft_log = atft.AtftLog(log_dir, log_size, log_file_number)
    atft_log.Info = MagicMock()
    mock_createfile = MagicMock()
    mock_createfile.side_effect = (
        lambda file='atft_log_3': self.MockCreateFile(file))
    atft_log._CreateLogFile = mock_createfile
    # 5 + 6 should be larger than 10
    atft_log._LimitSize('abcdefg')
    atft_log._CreateLogFile.assert_called_once()
    mock_remove.assert_called_once_with(os.path.join(
        self.LOG_DIR, 'atft_log_1'))

  # Test ChangeThresholdDialog.OnSave()
  def testChangeThresholdDialogSaveNormal(self):
    self.TestChangeThresholdDialogSaveNormalEach('10', '5')
    self.TestChangeThresholdDialogSaveNormalEach('10', '')
    self.TestChangeThresholdDialogSaveNormalEach('', '')

  def TestChangeThresholdDialogSaveNormalEach(self, value1, value2):
    mock_atft = MagicMock()
    mock_atft.DEFAULT_KEY_THRESHOLD_1 = 2
    mock_atft.DEFAULT_KEY_THRESHOLD_2 = None
    test_dialog = atft.ChangeThresholdDialog(mock_atft)
    test_dialog.EndModal = MagicMock()
    test_dialog.first_warning_input = MagicMock()
    test_dialog.first_warning_input.GetValue.return_value = value1
    test_dialog.second_warning_input = MagicMock()
    test_dialog.second_warning_input.GetValue.return_value = value2
    test_dialog.OnSave(None)
    test_dialog.EndModal.assert_called_once()
    if value1:
      self.assertEqual(int(value1), test_dialog.GetFirstWarning())
    if value2:
      self.assertEqual(int(value2), test_dialog.GetSecondWarning())

  def testChangeThresholdDialogSaveInvalid(self):
    # Invalid format
    self.TestChangeThresholdDialogSaveInvalidEach('a', '5')
    self.TestChangeThresholdDialogSaveInvalidEach('5', 'a')
    self.TestChangeThresholdDialogSaveInvalidEach('a', 'b')
    # Second < First
    self.TestChangeThresholdDialogSaveInvalidEach('4', '5')
    # Invalid format
    self.TestChangeThresholdDialogSaveInvalidEach('a', '')
    # Only second, not first
    self.TestChangeThresholdDialogSaveInvalidEach('', '5')
    # Negative value
    self.TestChangeThresholdDialogSaveInvalidEach('-2', '')
    self.TestChangeThresholdDialogSaveInvalidEach('5', '-2')

  def TestChangeThresholdDialogSaveInvalidEach(self, value1, value2):
    mock_atft = MagicMock()
    mock_atft.DEFAULT_KEY_THRESHOLD_1 = 2
    mock_atft.DEFAULT_KEY_THRESHOLD_2 = None
    test_dialog = atft.ChangeThresholdDialog(mock_atft)
    test_dialog.EndModal = MagicMock()
    test_dialog.first_warning_input = MagicMock()
    test_dialog.first_warning_input.GetValue.return_value = value1
    test_dialog.second_warning_input = MagicMock()
    test_dialog.second_warning_input.GetValue.return_value = value2
    test_dialog.OnSave(None)
    test_dialog.EndModal.assert_not_called()
    self.assertEqual(2, test_dialog.GetFirstWarning())
    self.assertEqual(None, test_dialog.GetSecondWarning())

  # Test AppSettingsDialog.OnSaveSetting
  def testSavePasswordSetting(self):
    mock_atft = MockAtft()
    test_password_dialog = atft.AppSettingsDialog(mock_atft)
    test_password_dialog.EndModal = MagicMock()
    test_password_dialog.ShowCurrentSetting = MagicMock()
    test_password_dialog.password_setting = MagicMock()
    test_password_dialog.language_setting = MagicMock()
    test_password_dialog.menu_set_password = MagicMock()
    test_password_dialog.button_save = MagicMock()
    test_password_dialog.button_map = MagicMock()
    test_password_dialog.buttons_sizer = MagicMock()
    old_password = self.TEST_PASSWORD1
    new_password = self.TEST_PASSWORD2
    mock_atft.PASSWORD_HASH = mock_atft.GeneratePasswordHash(old_password)
    test_password_dialog.ShowPasswordSetting(None)
    test_password_dialog.original_password_input = MagicMock()
    test_password_dialog.original_password_input.GetValue.return_value = (
        old_password)
    test_password_dialog.original_password_input.SetValue = MagicMock()
    test_password_dialog.new_password_input = MagicMock()
    test_password_dialog.new_password_input.GetValue.return_value = (
        new_password)
    test_password_dialog.new_password_input.SetValue = MagicMock()
    test_password_dialog.OnSaveSetting(None)
    (test_password_dialog.original_password_input
     .SetValue.assert_called_once_with(''))
    test_password_dialog.new_password_input.SetValue.assert_called_once_with('')
    test_password_dialog.EndModal.assert_called_once()
    self.assertEqual(True, mock_atft.VerifyPassword(new_password))

  def testSavePasswordSettingPasswordIncorrect(self):
    mock_atft = MockAtft()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    test_password_dialog = atft.AppSettingsDialog(mock_atft)
    test_password_dialog.EndModal = MagicMock()
    test_password_dialog.ShowCurrentSetting = MagicMock()
    test_password_dialog.password_setting = MagicMock()
    test_password_dialog.language_setting = MagicMock()
    test_password_dialog.menu_set_password = MagicMock()
    test_password_dialog.button_save = MagicMock()
    test_password_dialog.button_map = MagicMock()
    test_password_dialog.buttons_sizer = MagicMock()
    old_password = self.TEST_PASSWORD1
    new_password = self.TEST_PASSWORD2
    mock_atft.PASSWORD_HASH = mock_atft.GeneratePasswordHash(old_password)
    test_password_dialog.ShowPasswordSetting(None)
    test_password_dialog.original_password_input = MagicMock()
    test_password_dialog.original_password_input.GetValue.return_value = (
        new_password)
    test_password_dialog.original_password_input.SetValue = MagicMock()
    test_password_dialog.new_password_input = MagicMock()
    test_password_dialog.new_password_input.GetValue.return_value = (
        new_password)
    test_password_dialog.new_password_input.SetValue = MagicMock()
    test_password_dialog.OnSaveSetting(None)
    test_password_dialog.original_password_input.SetValue.assert_called_with('')
    test_password_dialog.EndModal.assert_not_called()
    self.assertEqual(True, mock_atft.VerifyPassword(old_password))
    self.assertEqual(False, mock_atft.VerifyPassword(new_password))
    mock_atft._HandleException.assert_called_once()
    mock_atft._SendAlertEvent.assert_called_once()

  # Test _SaveFileEventHandler
  @patch('os.path.isfile')
  @patch('os.path.isdir')
  @patch('wx.DirDialog')
  def testSaveFileEvent(self, mock_create_dialog, mock_isdir, mock_isfile):
    mock_atft = MockAtft()
    message = self.TEST_TEXT
    filename = self.TEST_FILENAME
    callback = MagicMock()
    mock_isdir.return_value = False
    mock_isfile.return_value = False
    mock_create_dialog.ShowModal = MagicMock()
    mock_create_dialog.ShowModal.return_value = wx.ID_YES
    data = mock_atft.SaveFileArg(message, filename, callback)
    event = MagicMock()
    event.GetValue.return_value = data
    mock_atft._SaveFileEventHandler(event)
    callback.assert_called_once()

  @patch('os.path.isfile')
  @patch('os.path.isdir')
  @patch('wx.DirDialog')
  def testSaveFileEventFileExists(
      self, mock_create_dialog, mock_isdir, mock_isfile):
    mock_atft = MockAtft()
    mock_atft._ShowWarning = MagicMock()
    mock_atft._ShowWarning.return_value = True
    message = self.TEST_TEXT
    filename = self.TEST_FILENAME
    callback = MagicMock()
    mock_isdir.return_value = False
    # File already exists, need to give a warning.
    mock_isfile.return_value = True
    mock_create_dialog.ShowModal = MagicMock()
    mock_create_dialog.ShowModal.return_value = wx.ID_YES
    data = mock_atft.SaveFileArg(message, filename, callback)
    event = MagicMock()
    event.GetValue.return_value = data
    mock_atft._SaveFileEventHandler(event)
    mock_atft._ShowWarning.assert_called_once()
    callback.assert_called_once()

    # If use clicks no to the warning.
    callback.reset_mock()
    mock_atft._ShowWarning.return_value = False
    mock_atft._SaveFileEventHandler(event)
    callback.assert_not_called()


if __name__ == '__main__':
  unittest.main()
