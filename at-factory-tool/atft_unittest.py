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
from mock import mock_open
import os
import wx


# colors
COLOR_WHITE = wx.Colour(255, 255, 255)
COLOR_RED = wx.Colour(194, 40, 40)
COLOR_YELLOW = wx.Colour(218, 165, 32)
COLOR_GREEN = wx.Colour(68, 209, 89)
COLOR_BLUE = wx.Colour(43, 133, 216)
COLOR_GREY = wx.Colour(237, 237, 237)
COLOR_DARK_GREY = wx.Colour(117, 117, 117)
COLOR_BLACK = wx.Colour(0, 0, 0)
COLOR_PICK_BLUE = wx.Colour(149, 169, 235)


class MockAtft(atft.Atft):

  def __init__(self):
    self.InitializeUI = MagicMock()
    self.StartRefreshingDevices = MagicMock()
    self.ChooseProduct = MagicMock()
    self.CreateAtftManager = MagicMock()
    self.CreateAtftLog = MagicMock()
    self.CreateAtftAudit = MagicMock()
    self.ParseConfigFile = self._MockParseConfig
    self._SendPrintEvent = MagicMock()
    self._OnToggleSupMode = MagicMock()
    self.ShowStartScreen = MagicMock()
    self._CreateThread = self._MockCreateThread
    self.TARGET_DEV_SIZE = 6
    atft.Atft.__init__(self)
    self.provision_steps = self.DEFAULT_PROVISION_STEPS_PRODUCT
    self.atft_string = MagicMock()

  def _MockParseConfig(self):
    self.atft_version = 'vTest'
    self.compatible_atfa_version = 'v1'
    self.device_refresh_interval = 1.0
    self.default_key_threshold_1 = 0
    self.log_dir = 'test_log_dir'
    self.log_size = 1000
    self.log_file_number = 2
    self.language = 'ENG'
    self.reboot_timeout = 1.0
    self.product_attribute_file_extension = '*.atpa'

    return {}

  def _MockCreateThread(self, target, *args):
    target(*args)


class TestDeviceInfo(object):

  def __init__(self, serial_number, location=None, provision_status=None):
    self.serial_number = serial_number
    self.location = location
    self.provision_status = provision_status
    self.provision_state = ProvisionState()
    self.time_set = False
    self.operation_lock = MagicMock()
    self.operation = None
    self.at_attest_uuid = None

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
  AUDIT_DIR = 'test-audit'
  TEST_TIME = '0000-00-00 00:00:00'
  TEST_TIMESTAMP = 1000
  TEST_PASSWORD1 = 'password 1'
  TEST_PASSWORD2 = 'PassWord 2!'
  TEST_FILENAME = 'filename'
  TEST_ATTEST_UUID = 'test attest uuid'

  def setUp(self):
    self.test_target_devs = []
    self.test_dev1 = TestDeviceInfo(
        self.TEST_SERIAL1, self.TEST_LOCATION1, ProvisionStatus.IDLE)
    self.test_dev2 = TestDeviceInfo(
        self.TEST_SERIAL2, self.TEST_LOCATION2, ProvisionStatus.IDLE)
    self.test_text_window = ''
    self.atfa_keys = None
    self.device_map = {}

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
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = None
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
    mock_serial_string = MagicMock()
    mock_atft.atft_string.FIELD_SERIAL_NUMBER = mock_serial_string
    mock_atft.atft_manager = MagicMock()
    dev1 = self.test_dev1
    dev2 = self.test_dev2
    dev1.provision_status = ProvisionStatus.IDLE
    dev2.provision_status = ProvisionStatus.PROVISION_ING
    dev1_state = ProvisionState()
    dev1.provision_state = dev1_state
    dev2_state = ProvisionState()
    dev2_state.bootloader_locked = True
    dev2_state.avb_perm_attr_set = True
    dev2_state.avb_locked = True
    dev2.provision_state = dev2_state
    mock_atft.atft_manager.target_devs = [dev1, dev2]
    mock_atft.device_usb_locations = []
    for i in range(mock_atft.TARGET_DEV_SIZE):
      mock_atft.device_usb_locations.append(None)
    mock_atft.device_usb_locations[0] = self.TEST_LOCATION1
    mock_atft.device_usb_locations[5] = self.TEST_LOCATION2
    mock_atft._ShowTargetDevice = MagicMock()
    mock_atft._PrintTargetDevices()
    mock_atft._ShowTargetDevice.assert_has_calls([
        call(
            0, self.TEST_SERIAL1, mock_serial_string + ': ' +
            self.TEST_SERIAL1, ProvisionStatus.IDLE, dev1_state),
        call(1, None, '', None, None),
        call(2, None, '', None, None),
        call(3, None, '', None, None),
        call(4, None, '', None, None),
        call(
            5, self.TEST_SERIAL2, mock_serial_string + ': ' +
            self.TEST_SERIAL2, ProvisionStatus.PROVISION_ING, dev2_state)
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
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
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
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = None
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
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
    mock_atft.atft_manager.product_info = None
    mock_atft.atft_manager.som_info = None
    mock_atft.atft_manager.GetCachedATFAKeysLeft.return_value = 10
    mock_atft.PrintToCommandWindow = MagicMock()
    mock_atft.OnEnterAutoProv()
    self.assertEqual(False, mock_atft.auto_prov)

  def testOnEnterAutoProvNoKeysLeft(self):
    # Cannot enter auto provisioning mode when no keys left
    mock_atft = MockAtft()
    mock_atft.auto_prov = False
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
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
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
    mock_atft.atft_manager.product_info = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.return_value = 0
    mock_atft.PrintToCommandWindow = MagicMock()
    test_dev1 = TestDeviceInfo(
        self.TEST_SERIAL1, self.TEST_LOCATION1,
        ProvisionStatus.PROVISION_SUCCESS)
    test_dev2 = TestDeviceInfo(
        self.TEST_SERIAL2, self.TEST_LOCATION1,
        ProvisionStatus.WAITING)
    mock_atft._GetTargetDevices = MagicMock()
    mock_atft._GetTargetDevices.return_value = [
        test_dev1, test_dev2]
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
    test_dev1.provision_state.bootloader_locked = True
    test_dev1.provision_state.avb_perm_attr_set = True
    test_dev1.provision_state.avb_locked = True
    test_dev1.provision_state.product_provisioned = True
    test_dev2 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION1,
                               ProvisionStatus.IDLE)
    mock_atft._GetTargetDevices = MagicMock()
    mock_atft._GetTargetDevices.return_value = [
        test_dev1, test_dev2]
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
    mock_title = MagicMock()
    mock_atft.atft_string.TITLE_KEYS_LEFT = mock_title
    mock_atft._SetStatusTextColor = MagicMock()
    mock_atft.change_threshold_dialog = MagicMock()
    mock_atft.change_threshold_dialog.GetFirstWarning.return_value = None
    mock_atft.change_threshold_dialog.GetSecondWarning.return_value = None
    keys_left_array = []
    mock_atft.atft_manager.GetCachedATFAKeysLeft = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.side_effect = (
        lambda: self.MockGetKeysLeft(keys_left_array))
    mock_atft.atft_manager.UpdateATFAKeysLeft.side_effect = (
        lambda is_som_key: self.MockSetKeysLeft(keys_left_array))
    mock_atft._HandleKeysLeft()
    mock_atft._SetStatusTextColor.assert_called_once_with(
        mock_title + '10', COLOR_BLACK)

  def testHandleKeysLeftKeysNotNone(self):
    mock_atft = MockAtft()
    mock_title = MagicMock()
    mock_atft.atft_string.TITLE_KEYS_LEFT = mock_title
    mock_atft._SetStatusTextColor = MagicMock()
    mock_atft.change_threshold_dialog = MagicMock()
    mock_atft.change_threshold_dialog.GetFirstWarning.return_value = None
    mock_atft.change_threshold_dialog.GetSecondWarning.return_value = None
    keys_left_array = [10]
    mock_atft.atft_manager.GetCachedATFAKeysLeft = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.side_effect = (
        lambda: self.MockGetKeysLeft(keys_left_array))
    mock_atft._HandleKeysLeft()
    mock_atft._SetStatusTextColor.assert_called_once_with(
        mock_title + '10', COLOR_BLACK)
    mock_atft.atft_manager.UpdateATFAKeysLeft.assert_not_called()

  def testHandleKeysLeftKeysNone(self):
    mock_atft = MockAtft()
    mock_title = MagicMock()
    mock_atft.atft_string.TITLE_KEYS_LEFT = mock_title
    mock_atft._SetStatusTextColor = MagicMock()
    mock_atft.change_threshold_dialog = MagicMock()
    mock_atft.change_threshold_dialog.GetFirstWarning.return_value = None
    mock_atft.change_threshold_dialog.GetSecondWarning.return_value = None
    keys_left_array = []
    mock_atft.atft_manager.GetCachedATFAKeysLeft = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.return_value = 0
    mock_atft._HandleKeysLeft()
    mock_atft._SetStatusTextColor.assert_called_once_with(
        mock_title + '0', COLOR_BLACK)

  # The statusbar should change color if the key is lower than threshold.
  def testHandleKeysLeftChangeStatusColor(self):
    mock_atft = MockAtft()
    mock_title = MagicMock()
    mock_atft.atft_string.TITLE_KEYS_LEFT = mock_title
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
    mock_atft._SetStatusTextColor.assert_called_once_with(
        mock_title + '10', COLOR_YELLOW)

    # past second warning
    mock_atft._SetStatusTextColor.reset_mock()
    keys_left_array = [9]
    mock_atft.atft_manager.GetCachedATFAKeysLeft = MagicMock()
    mock_atft.atft_manager.GetCachedATFAKeysLeft.side_effect = (
        lambda: self.MockGetKeysLeft(keys_left_array))
    mock_atft._HandleKeysLeft()
    mock_atft._SetStatusTextColor.assert_called_once_with(
        mock_title + '9', COLOR_RED)

  # Test atft._HandleStateTransition
  def MockStateChange(self, target, state):
    if ProvisionStatus.isFailed(state):
      target.provision_status = state
      return
    if state == ProvisionStatus.REBOOT_SUCCESS:
      target.provision_state.bootloader_locked = True
    if state == ProvisionStatus.FUSEATTR_SUCCESS:
      target.provision_state.avb_perm_attr_set = True
    if state == ProvisionStatus.LOCKAVB_SUCCESS:
      target.provision_state.avb_locked = True
    if state == ProvisionStatus.PROVISION_SUCCESS:
      target.provision_state.product_provisioned = True
    if state == ProvisionStatus.UNLOCKAVB_SUCCESS:
      target.provision_state.avb_locked = False
    if target.provision_state.product_provisioned:
      target.provision_status = ProvisionStatus.PROVISION_SUCCESS
      return
    if target.provision_state.avb_locked:
      target.provision_status = ProvisionStatus.LOCKAVB_SUCCESS
      return
    if target.provision_state.avb_perm_attr_set:
      target.provision_status = ProvisionStatus.FUSEATTR_SUCCESS
      return
    if target.provision_state.bootloader_locked:
      target.provision_status = ProvisionStatus.FUSEVBOOT_SUCCESS

  def testHandleStateTransition(self):
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target, auto_prov, state=ProvisionStatus.REBOOT_SUCCESS:
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
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    self.assertEqual(ProvisionStatus.PROVISION_SUCCESS,
                     test_dev1.provision_status)

  def testHandleStateTransitionSame(self):
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
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1, self.TEST_SERIAL1]
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
        lambda target, auto_prov, state=ProvisionStatus.FUSEVBOOT_FAILED:
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
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
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
        lambda target, auto_prov, state=ProvisionStatus.REBOOT_FAILED:
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
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
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
        lambda target, auto_prov, state=ProvisionStatus.REBOOT_SUCCESS:
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
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
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
        lambda target, auto_prov, state=ProvisionStatus.REBOOT_SUCCESS:
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
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
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
        lambda target, auto_prov, state=ProvisionStatus.REBOOT_SUCCESS:
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
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_FAILED:
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
        lambda target, auto_prov, state=ProvisionStatus.REBOOT_SUCCESS:
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
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
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
    self.assertEqual(True, test_dev1.provision_state.product_provisioned)

  def testHandleStateTransitionIncludeUnlock(self):
    """Test the provision_steps that unlock avb after provisioning.

    We assume that the device would be locked avb during fuse vboot key and
    we want the final state to be avb unlocked.
    """
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target, auto_prov, state=ProvisionStatus.REBOOT_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._UnlockAvbTarget = MagicMock()
    mock_atft._UnlockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.UNLOCKAVB_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_SUCCESS:
        self.MockStateChange(target, state))

    mock_atft.provision_steps = ['FuseVbootKey', 'FusePermAttr', 'LockAvb',
         'ProvisionProduct', 'UnlockAvb']
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    mock_atft._FuseVbootKeyTarget.assert_called_once()
    mock_atft._LockAvbTarget.assert_called_once()
    mock_atft._UnlockAvbTarget.assert_called_once()
    mock_atft._FusePermAttrTarget.assert_called_once()
    mock_atft._ProvisionTarget.assert_called_once()
    self.assertEqual(True, test_dev1.provision_state.bootloader_locked)
    self.assertEqual(True, test_dev1.provision_state.avb_perm_attr_set)
    self.assertEqual(False, test_dev1.provision_state.avb_locked)
    self.assertEqual(True, test_dev1.provision_state.product_provisioned)
    self.assertEqual(
        ProvisionStatus.PROVISION_SUCCESS, test_dev1.provision_status)
    self.assertEqual(
        True, mock_atft._is_provision_steps_finished(test_dev1.provision_state))

  def testHandleStateTransitionLockUnlockLock(self):
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target, auto_prov, state=ProvisionStatus.REBOOT_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._UnlockAvbTarget = MagicMock()
    mock_atft._UnlockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.UNLOCKAVB_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_SUCCESS:
        self.MockStateChange(target, state))

    mock_atft.provision_steps = ['FuseVbootKey', 'FusePermAttr', 'LockAvb',
         'ProvisionProduct', 'UnlockAvb', 'LockAvb', 'UnlockAvb']
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    self.assertEqual(True, test_dev1.provision_state.bootloader_locked)
    self.assertEqual(True, test_dev1.provision_state.avb_perm_attr_set)
    self.assertEqual(False, test_dev1.provision_state.avb_locked)
    self.assertEqual(True, test_dev1.provision_state.product_provisioned)
    self.assertEqual(
        ProvisionStatus.PROVISION_SUCCESS, test_dev1.provision_status)
    self.assertEqual(
        True, mock_atft._is_provision_steps_finished(test_dev1.provision_state))

  def testHandleStateTransitionReorder(self):
    """Test the provision_steps that has been reordered.

    We should make sure all the steps are executed even if they are reordered.
    """
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target, auto_porov, state=ProvisionStatus.REBOOT_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_SUCCESS:
        self.MockStateChange(target, state))

    mock_atft.provision_steps = ['FusePermAttr', 'FuseVbootKey', 'ProvisionProduct',
                                 'LockAvb']
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    mock_atft._FuseVbootKeyTarget.assert_called_once()
    mock_atft._LockAvbTarget.assert_called_once()
    mock_atft._FusePermAttrTarget.assert_called_once()
    mock_atft._ProvisionTarget.assert_called_once()
    self.assertEqual(True, test_dev1.provision_state.bootloader_locked)
    self.assertEqual(True, test_dev1.provision_state.avb_perm_attr_set)
    self.assertEqual(True, test_dev1.provision_state.avb_locked)
    self.assertEqual(True, test_dev1.provision_state.product_provisioned)
    self.assertEqual(
        ProvisionStatus.PROVISION_SUCCESS, test_dev1.provision_status)
    self.assertEqual(
        True, mock_atft._is_provision_steps_finished(test_dev1.provision_state))

  def testHandleStateTransitionNoProvision(self):
    """Test the provision_steps that does not provision key.
    """
    mock_atft = MockAtft()
    test_dev1 = TestDeviceInfo(self.TEST_SERIAL1, self.TEST_LOCATION1,
                               ProvisionStatus.WAITING)
    mock_atft._FuseVbootKeyTarget = MagicMock()
    mock_atft._FuseVbootKeyTarget.side_effect = (
        lambda target, auto_prov, state=ProvisionStatus.REBOOT_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._FusePermAttrTarget = MagicMock()
    mock_atft._FusePermAttrTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.FUSEATTR_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._ProvisionTarget = MagicMock()
    mock_atft._ProvisionTarget.side_effect = (
        lambda target, is_som_key, state=ProvisionStatus.PROVISION_SUCCESS:
        self.MockStateChange(target, state))
    mock_atft._LockAvbTarget = MagicMock()
    mock_atft._LockAvbTarget.side_effect = (
        lambda target=mock_atft, state=ProvisionStatus.LOCKAVB_SUCCESS:
        self.MockStateChange(target, state))

    mock_atft.provision_steps = ['FusePermAttr', 'FuseVbootKey', 'LockAvb']
    mock_atft.auto_dev_serials = [self.TEST_SERIAL1]
    mock_atft.auto_prov = True
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetTargetDevice = MagicMock()
    mock_atft.atft_manager.GetTargetDevice.return_value = test_dev1
    mock_atft._HandleStateTransition(test_dev1)
    mock_atft._FuseVbootKeyTarget.assert_called_once()
    mock_atft._LockAvbTarget.assert_called_once()
    mock_atft._FusePermAttrTarget.assert_called_once()
    mock_atft._ProvisionTarget.assert_not_called()
    self.assertEqual(True, test_dev1.provision_state.bootloader_locked)
    self.assertEqual(True, test_dev1.provision_state.avb_perm_attr_set)
    self.assertEqual(True, test_dev1.provision_state.avb_locked)
    self.assertEqual(False, test_dev1.provision_state.product_provisioned)
    self.assertEqual(
        ProvisionStatus.LOCKAVB_SUCCESS, test_dev1.provision_status)
    self.assertEqual(
        True, mock_atft._is_provision_steps_finished(test_dev1.provision_state))

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

  def MockSuccessProvision(self, target, is_som_key=False):
    self.atfa_keys -= 1
    self.MockSetAttestUuid(target)

  def MockFailedProvision(self, target, is_som_key=False):
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
    mock_atft._ProvisionTarget(test_dev1, False)
    mock_atft._SendLowKeyAlertEvent.assert_not_called()
    # Second provision failed
    # Second check, assume 100 left, verify, 101 left no alert
    mock_atft.atft_manager.Provision.side_effect = self.MockFailedProvision
    mock_atft._ProvisionTarget(test_dev1, False)
    mock_atft._SendLowKeyAlertEvent.assert_not_called()
    # Third check, assume 100 left, verify, 100 left, first warning
    mock_atft.atft_manager.Provision.side_effect = self.MockSuccessProvision
    mock_atft._ProvisionTarget(test_dev1, False)
    mock_atft._SendLowKeyAlertEvent.assert_called_once()
    self.assertEqual(True, mock_atft.first_key_alert_shown)
    mock_atft._SendLowKeyAlertEvent.reset_mock()
    # Fourth check, assume 99 left, verify, 99 left, second warning
    mock_atft._ProvisionTarget(test_dev1, False)
    mock_atft._SendLowKeyAlertEvent.assert_called_once()
    self.assertEqual(True, mock_atft.second_key_alert_shown)
    mock_atft._SendLowKeyAlertEvent.reset_mock()
    # Fifth check, no more warning, 98 left
    mock_atft._ProvisionTarget(test_dev1, False)
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

  def MockSetAttestUuid(self, target, is_som_key=False):
    target.at_attest_uuid = self.TEST_ATTEST_UUID

  # Test atft._ManualProvision
  def testManualProvision(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.Provision = MagicMock()
    mock_atft.atft_manager.Provision.side_effect = self.MockSetAttestUuid
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
    mock_atft._GetSelectedSerials = MagicMock()
    mock_atft._GetSelectedSerials.return_value = serials
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
    # We are operating with product key.
    mock_atft.atft_manager.product_info = MagicMock()
    mock_atft.atft_manager.som_info = None
    mock_atft._ShowWarning = MagicMock()
    mock_atft._ShowWarning.return_value = False
    mock_atft.OnManualProvision(None)
    calls = [call(test_dev1, False), call(test_dev2, False)]
    mock_atft.atft_manager.Provision.assert_has_calls(calls)

    # Test som provision
    mock_atft.atft_manager.Provision.reset_mock()
    mock_atft.atft_manager.product_info = None
    mock_atft.atft_manager.som_info = MagicMock
    mock_atft.OnManualProvision(None)
    calls = [call(test_dev1, True), call(test_dev2, True)]

  def testManualProvisionReprovision(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.Provision = MagicMock()
    mock_atft.atft_manager.Provision.side_effect = self.MockSetAttestUuid
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
                               ProvisionStatus.PROVISION_SUCCESS)
    test_dev2.provision_state.bootloader_locked = True
    test_dev2.provision_state.avb_perm_attr_set = True
    test_dev2.provision_state.avb_locked = True
    test_dev2.provision_state.product_provisioned = True

    test_dev3 = TestDeviceInfo(self.TEST_SERIAL2, self.TEST_LOCATION2,
                               ProvisionStatus.SOM_PROVISION_SUCCESS)
    test_dev3.provision_state.bootloader_locked = True
    test_dev3.provision_state.avb_perm_attr_set = True
    test_dev3.provision_state.avb_locked = True
    test_dev3.provision_state.som_provisioned = True

    self.device_map[self.TEST_SERIAL1] = test_dev1
    self.device_map[self.TEST_SERIAL2] = test_dev2
    self.device_map[self.TEST_SERIAL3] = test_dev3

    serials = [self.TEST_SERIAL1, self.TEST_SERIAL2]
    mock_atft._GetSelectedSerials = MagicMock()
    mock_atft._GetSelectedSerials.return_value = serials
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
    mock_atft._ShowWarning = MagicMock()
    # We are operating with product key.
    mock_atft.atft_manager.product_info = MagicMock()
    mock_atft.atft_manager.som_info = None

    # User click No for reprovision.
    mock_atft._ShowWarning.return_value = False
    mock_atft.OnManualProvision(None)
    mock_atft.atft_manager.Provision.assert_called_once_with(test_dev1, False)
    mock_atft._ShowWarning.assert_called_once()

    # User click yes.
    mock_atft._ShowWarning.reset_mock()
    mock_atft.atft_manager.Provision.reset_mock()
    mock_atft._ShowWarning.return_value = True
    mock_atft.OnManualProvision(None)
    calls = [call(test_dev1, False), call(test_dev2, False)]
    mock_atft.atft_manager.Provision.assert_has_calls(calls)
    mock_atft._ShowWarning.assert_called_once()

    # Now operating in som mode
    mock_atft._ShowWarning.reset_mock()
    mock_atft.atft_manager.Provision.reset_mock()
    mock_atft.atft_manager.product_info = None
    mock_atft.atft_manager.som_info = MagicMock()
    mock_atft._GetSelectedSerials.return_value = [self.TEST_SERIAL3]
    # User click No for reprovision.
    mock_atft._ShowWarning.return_value = False
    mock_atft.OnManualProvision(None)
    mock_atft.atft_manager.Provision.assert_not_called()
    mock_atft._ShowWarning.assert_called_once()
    # User click yes.
    mock_atft._ShowWarning.reset_mock()
    mock_atft.atft_manager.Provision.reset_mock()
    mock_atft._ShowWarning.return_value = True
    mock_atft.OnManualProvision(None)
    mock_atft.atft_manager.Provision.assert_called_with(test_dev2, True)
    mock_atft._ShowWarning.assert_called_once()

  def testManualProvisionExceptions(self):
    mock_atft = MockAtft()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._SendStartMessageEvent = MagicMock()
    mock_atft._SendSucceedMessageEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_atft.atft_manager.Provision = MagicMock()
    mock_atft.atft_manager.Provision.side_effect = self.MockSetAttestUuid
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
    mock_atft._GetSelectedSerials = MagicMock()
    mock_atft._GetSelectedSerials.return_value = serials
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
    mock_atft._ShowWarning = MagicMock()
    mock_atft.atft_manager.Provision.side_effect = (
        fastboot_exceptions.FastbootFailure(''))
    mock_atft.OnManualProvision(None)
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
    mock_atft._GetSelectedSerials.return_value = serials
    mock_atft._HandleException.reset_mock()
    mock_atft.atft_manager.Provision.side_effect = (
        fastboot_exceptions.DeviceNotFoundException())
    mock_atft.OnManualProvision(None)
    self.assertEqual(2, mock_atft._HandleException.call_count)

  # Test atft._ProcessKey
  def testProcessKeySuccess(self):
    mock_atft = MockAtft()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atfa = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = mock_atfa
    mock_atft._UpdateKeysLeftInATFA = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_path = MagicMock()

    mock_atft._ProcessKey(mock_path)
    mock_atfa.Download.assert_called_once_with(mock_path)
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
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
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
      mock_atft.atft_manager.GetATFADevice = MagicMock()
      mock_atft.atft_manager.GetATFADevice.return_value.Download = MagicMock()
      mock_atft.atft_manager.GetATFADevice = MagicMock()
      mock_atft.atft_manager.GetATFADevice.return_value.Download.side_effect = exception

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
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atfa = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = mock_atfa
    mock_atft._UpdateKeysLeftInATFA = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()
    mock_path = MagicMock()

    mock_atft._UpdateATFA(mock_path)
    mock_atfa.Download.assert_called_once_with(mock_path)
    mock_atft.atft_manager.UpdateATFA.assert_called_once()
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_not_called()

    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_called_once()

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
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
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
      mock_atft.atft_manager.GetATFADevice = MagicMock()
      mock_atft.atft_manager.GetATFADevice.return_value.Download = MagicMock()
      mock_atft.atft_manager.GetATFADevice = MagicMock()
      mock_atft.atft_manager.GetATFADevice.return_value.Download.side_effect = exception

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
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
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
  def testGetRegFile(self, my_mock_open):
    mock_atft = MockAtft()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atfa = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = mock_atfa
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
    my_mock_open.assert_called_once_with(mock_path, 'w+')
    mock_atfa.Upload.assert_called_once_with(mock_path)
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
    my_mock_open.side_effect = IOError
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
    with patch('__builtin__.open') as my_mock_open:
      mock_atft = MockAtft()
      mock_atft.atft_manager = MagicMock()
      mock_atft.atft_manager.GetATFADevice = MagicMock()
      mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
      mock_atft._UpdateKeysLeftInATFA = MagicMock()
      mock_atft._SendOperationStartEvent = MagicMock()
      mock_atft._SendOperationSucceedEvent = MagicMock()
      mock_atft.PauseRefresh = MagicMock()
      mock_atft.ResumeRefresh = MagicMock()
      mock_atft._HandleException = MagicMock()
      mock_atft._SendAlertEvent = MagicMock()
      mock_path = MagicMock()
      mock_path.encode.return_value = mock_path
      my_mock_open.side_effect = IOError
      if not upload_fail:
        mock_atft.atft_manager.PrepareFile.side_effect = exception
      else:
        mock_atft.atft_manager.GetATFADevice = MagicMock()
        mock_atft.atft_manager.GetATFADevice.return_value.Upload.side_effect = exception

      mock_atft._GetRegFile(mock_path)

      mock_atft.PauseRefresh.assert_called_once()
      mock_atft.ResumeRefresh.assert_called_once()
      mock_atft._HandleException.assert_called_once()
      mock_atft._SendOperationStartEvent.assert_called_once()
      mock_atft._SendOperationSucceedEvent.assert_not_called()

  # Test atft._GetAuditFile
  @patch('__builtin__.open')
  def testGetAuditFile(self, my_mock_open):
    mock_atft = MockAtft()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.GetATFADevice = MagicMock()
    mock_atfa = MagicMock()
    mock_atft.atft_manager.GetATFADevice.return_value = mock_atfa
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
    my_mock_open.assert_called_once_with(mock_path, 'w+')
    mock_atfa.Upload.assert_called_once_with(mock_path)
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
    my_mock_open.side_effect = IOError
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
    with patch('__builtin__.open') as my_mock_open:
      mock_atft = MockAtft()
      mock_atft.atft_manager = MagicMock()
      mock_atft.atft_manager.GetATFADevice = MagicMock()
      mock_atft.atft_manager.GetATFADevice.return_value = MagicMock()
      mock_atft._UpdateKeysLeftInATFA = MagicMock()
      mock_atft._SendOperationStartEvent = MagicMock()
      mock_atft._SendOperationSucceedEvent = MagicMock()
      mock_atft.PauseRefresh = MagicMock()
      mock_atft.ResumeRefresh = MagicMock()
      mock_atft._HandleException = MagicMock()
      mock_atft._SendAlertEvent = MagicMock()
      mock_path = MagicMock()
      mock_path.encode.return_value = mock_path
      my_mock_open.side_effect = IOError
      if not upload_fail:
        mock_atft.atft_manager.PrepareFile.side_effect = exception
      else:
        mock_atft.atft_manager.GetATFADevice = MagicMock()
        mock_atft.atft_manager.GetATFADevice.return_value.Upload.side_effect = exception

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
  def testAtftLogCreate(self, my_mock_open, mock_listdir, mock_makedir,
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
      self, my_mock_open, mock_listdir, mock_makedir,
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
      self, my_mock_open, mock_listdir, mock_makedir,
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
  def testAtftLogCreate(self, my_mock_open, mock_listdir, mock_path_exists):
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
    my_mock_open.assert_called_once()
    log_file = my_mock_open.call_args[0][0]
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
      self, my_mock_open, mock_remove, mock_listdir, mock_path_exists, mock_isfile,
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
    test_dialog = atft.ChangeThresholdDialog(MagicMock(), 2, 0)
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
    test_dialog = atft.ChangeThresholdDialog(MagicMock(), 2, None)
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
    test_password_dialog = atft.AppSettingsDialog(
        MagicMock(), MagicMock(), MagicMock(), MagicMock(),
        mock_atft.ChangePassword, MagicMock(), 0, MagicMock())
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
    mock_atft.password_hash = mock_atft.GeneratePasswordHash(old_password)
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
    self.assertEqual(True, atft.Atft.VerifyPassword(
        new_password, mock_atft.password_hash))

  def testSavePasswordSettingPasswordIncorrect(self):
    mock_atft = MockAtft()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft._HandleException = MagicMock()
    test_password_dialog = atft.AppSettingsDialog(
        MagicMock(), MagicMock(), MagicMock(), MagicMock(),
        mock_atft.ChangePassword, MagicMock(), 0, MagicMock())
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
    mock_atft.password_hash = mock_atft.GeneratePasswordHash(old_password)
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
    self.assertEqual(
        True, atft.Atft.VerifyPassword(old_password, mock_atft.password_hash))
    self.assertEqual(
        False, atft.Atft.VerifyPassword(new_password, mock_atft.password_hash))
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

  def testCheckProvisionStepsSuccess(self):
    mock_atft = MockAtft()
    mock_atft._SendAlertEvent = MagicMock()
    mock_atft.provision_steps = []
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_not_called()
    self.assertEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Test [step1], [step1, step2], [step1, step2, step3] ...
    for i in range(1, len(mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT)):
      provision_steps = []
      for j in range(i):
        provision_steps.append(mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT[j])
      mock_atft.provision_steps = provision_steps
      mock_atft._CheckProvisionSteps()
      mock_atft._SendAlertEvent.assert_not_called()
      self.assertEqual(
          provision_steps, mock_atft.provision_steps)

  def testCheckProvisionStepsInvalidSyntax(self):
    mock_atft = MockAtft()
    mock_atft._SendAlertEvent = MagicMock()
    # Test invalid format (not array).
    mock_atft.provision_steps = '1234'
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_called_once()
    mock_atft._SendAlertEvent.reset_mock()
    self.assertEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Test invalid operation.
    mock_atft.provision_steps = ['1234']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_called_once()
    mock_atft._SendAlertEvent.reset_mock()
    self.assertEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Even if test_mode is true, syntax error is still failure.
    mock_atft.test_mode = True
    mock_atft.provision_steps = '1234'
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_called_once()
    mock_atft._SendAlertEvent.reset_mock()
    self.assertEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    mock_atft.provision_steps = ['1234']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_called_once()
    mock_atft._SendAlertEvent.reset_mock()
    self.assertEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

  def testCheckProvisionStepsSecurityReq(self):
    # Test cases when the provision steps do not meet security requirement.
    mock_atft = MockAtft()
    mock_atft._SendAlertEvent = MagicMock()
    # Test fuse perm attr without fusing vboot key.
    mock_atft.provision_steps = ['FusePermAttr']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_called_once()
    mock_atft._SendAlertEvent.reset_mock()
    self.assertEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Test fuse perm attr when already fused.
    mock_atft.provision_steps = ['FuseVbootKey', 'FusePermAttr', 'FusePermAttr']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_called_once()
    mock_atft._SendAlertEvent.reset_mock()
    self.assertEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Test LockAvb when vboot key is not fused.
    mock_atft.provision_steps = ['LockAvb']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_called_once()
    mock_atft._SendAlertEvent.reset_mock()
    self.assertEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Test LockAvb when perm attr not fused.
    mock_atft.provision_steps = ['FuseVbootKey', 'LockAvb']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_called_once()
    mock_atft._SendAlertEvent.reset_mock()
    self.assertEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Test provision when perm attr not fused.
    mock_atft.provision_steps = [
        'FuseVbootKey', 'LockAvb', 'ProvisionProduct']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_called_once()
    mock_atft._SendAlertEvent.reset_mock()
    self.assertEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # All the tests should succeed if TEST_MODE is set to True

    # Test fuse perm attr without fusing vboot key.
    mock_atft.test_mode = True
    mock_atft.provision_steps = ['FusePermAttr']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_not_called()
    self.assertNotEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Test fuse perm attr when already fused.
    mock_atft.provision_steps = ['FuseVbootKey', 'FusePermAttr', 'FusePermAttr']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_not_called()
    self.assertNotEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Test LockAvb when vboot key is not fused.
    mock_atft.provision_steps = ['LockAvb']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_not_called()
    self.assertNotEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Test LockAvb when perm attr not fused.
    mock_atft.provision_steps = ['FuseVbootKey', 'LockAvb']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_not_called()
    self.assertNotEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

    # Test provision when perm attr not fused.
    mock_atft.provision_steps = [
        'FuseVbootKey', 'LockAvb', 'ProvisionProduct']
    mock_atft._CheckProvisionSteps()
    mock_atft._SendAlertEvent.assert_not_called()
    self.assertNotEqual(
        mock_atft.DEFAULT_PROVISION_STEPS_PRODUCT, mock_atft.provision_steps)

  # Test AtftLog.Initialize()
  def IncreaseMockTime(self, format):
    self.mock_time += 1
    return str(self.mock_time - 1)

  def CreateAuditFiles(self, file_path, file_type, show_alert):
    self.mock_audit_files.append(os.path.basename(file_path))
    return True

  def RemoveAuditFiles(self, file_path):
    self.mock_audit_files.remove(os.path.basename(file_path))

  @patch('os.mkdir')
  @patch('datetime.datetime')
  @patch('os.path.isfile')
  @patch('os.remove')
  @patch('os.listdir')
  def testAtftAudit(
      self, mock_listdir, mock_remove, mock_isfile, mock_datetime,
      mock_makedir):
    download_interval = 2
    get_file_handler = MagicMock()
    get_file_handler.side_effect = self.CreateAuditFiles
    get_atfa_serial = MagicMock()
    get_atfa_serial.return_value = self.TEST_SERIAL1
    mock_remove.side_effect = self.RemoveAuditFiles
    mock_time = MagicMock()
    mock_datetime.utcnow.return_value = mock_time
    mock_time.strftime.side_effect = self.IncreaseMockTime
    mock_isfile.return_value = True

    audit_file_path_0 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_0.audit')
    audit_file_path_1 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_1.audit')
    audit_file_path_2 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_2.audit')
    audit_file_path_3 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_3.audit')

    self.mock_audit_files = []
    self.mock_time = 0
    mock_listdir.return_value = self.mock_audit_files

    test_audit = atft.AtftAudit(
        self.AUDIT_DIR,
        download_interval,
        get_file_handler,
        get_atfa_serial)
    mock_makedir.assert_called_with(self.AUDIT_DIR)
    test_audit.PullAudit(10)
    get_file_handler.assert_called_once_with(audit_file_path_0, 'audit', False)
    mock_remove.assert_not_called()
    get_file_handler.reset_mock()
    test_audit.PullAudit(9)
    get_file_handler.assert_not_called()
    test_audit.PullAudit(8)
    get_file_handler.assert_called_once_with(audit_file_path_1, 'audit', False)
    mock_remove.assert_called_once_with(audit_file_path_0)
    mock_remove.reset_mock()
    get_file_handler.reset_mock()
    test_audit.PullAudit(7)
    get_file_handler.assert_not_called()
    test_audit.PullAudit(6)
    get_file_handler.assert_called_once_with(audit_file_path_2, 'audit', False)
    get_file_handler.reset_mock()
    mock_remove.assert_called_once_with(audit_file_path_1)
    mock_remove.reset_mock()
    test_audit.ResetKeysLeft()
    test_audit.PullAudit(10)
    get_file_handler.assert_called_once_with(audit_file_path_3, 'audit', False)
    mock_remove.assert_called_once_with(audit_file_path_2)

  @patch('os.mkdir')
  @patch('datetime.datetime')
  @patch('os.path.isfile')
  @patch('os.remove')
  @patch('os.listdir')
  def testAtftAuditRemoveMultipleFiles(
      self, mock_listdir, mock_remove, mock_isfile, mock_datetime,
      mock_makedir):
    download_interval = 2
    get_file_handler = MagicMock()
    get_file_handler.side_effect = self.CreateAuditFiles
    get_atfa_serial = MagicMock()
    get_atfa_serial.return_value = self.TEST_SERIAL1
    mock_remove.side_effect = self.RemoveAuditFiles
    mock_time = MagicMock()
    mock_datetime.utcnow.return_value = mock_time
    mock_time.strftime.side_effect = self.IncreaseMockTime
    mock_isfile.return_value = True

    audit_file_path_0 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_0.audit')
    audit_file_path_1 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_1.audit')
    audit_file_path_2 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_2.audit')
    audit_file_path_3 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_3.audit')

    # If more than one files for one ATFA left, must remove them all.
    self.mock_audit_files = [
        self.TEST_SERIAL1 + '_0.audit',
        self.TEST_SERIAL1 + '_1.audit',
        self.TEST_SERIAL1 + '_2.audit']
    self.mock_time = 3
    mock_listdir.return_value = self.mock_audit_files

    test_audit = atft.AtftAudit(
        self.AUDIT_DIR,
        download_interval,
        get_file_handler,
        get_atfa_serial)
    test_audit.PullAudit(10)
    get_file_handler.assert_called_once_with(audit_file_path_3, 'audit', False)
    mock_remove.assert_has_calls([
        call(audit_file_path_0),
        call(audit_file_path_1),
        call(audit_file_path_2)])

  @patch('os.mkdir')
  @patch('datetime.datetime')
  @patch('os.path.isfile')
  @patch('os.remove')
  @patch('os.listdir')
  def testAtftAuditRemoveMultipleFiles(
      self, mock_listdir, mock_remove, mock_isfile, mock_datetime,
      mock_makedir):
    download_interval = 2
    get_file_handler = MagicMock()
    get_atfa_serial = MagicMock()
    get_atfa_serial.return_value = self.TEST_SERIAL1
    mock_remove.side_effect = self.RemoveAuditFiles
    mock_time = MagicMock()
    mock_datetime.utcnow.return_value = mock_time
    mock_time.strftime.side_effect = self.IncreaseMockTime
    mock_isfile.return_value = True

    # If get file fails, must not remove file.
    get_file_handler.return_value = False

    audit_file_path_0 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_0.audit')
    audit_file_path_1 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_1.audit')
    audit_file_path_2 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_2.audit')
    audit_file_path_3 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_3.audit')

    self.mock_audit_files = [
        self.TEST_SERIAL1 + '_0.audit',
        self.TEST_SERIAL1 + '_1.audit',
        self.TEST_SERIAL1 + '_2.audit']
    self.mock_time = 3
    mock_listdir.return_value = self.mock_audit_files

    test_audit = atft.AtftAudit(
        self.AUDIT_DIR,
        download_interval,
        get_file_handler,
        get_atfa_serial)
    test_audit.PullAudit(10)
    get_file_handler.assert_called_once_with(audit_file_path_3, 'audit', False)
    mock_remove.assert_not_called()

  @patch('os.mkdir')
  @patch('datetime.datetime')
  @patch('os.path.isfile')
  @patch('os.remove')
  @patch('os.listdir')
  def testAtftAuditMultipleATFAs(
      self, mock_listdir, mock_remove, mock_isfile, mock_datetime,
      mock_makedir):
    download_interval = 2
    get_file_handler = MagicMock()
    get_file_handler.side_effect = self.CreateAuditFiles
    get_atfa_serial = MagicMock()
    get_atfa_serial.return_value = self.TEST_SERIAL1
    mock_remove.side_effect = self.RemoveAuditFiles
    mock_time = MagicMock()
    mock_datetime.utcnow.return_value = mock_time
    mock_time.strftime.side_effect = self.IncreaseMockTime
    mock_isfile.return_value = True

    audit_file_path_1_0 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_0.audit')
    audit_file_path_2_1 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL2 + '_1.audit')
    audit_file_path_1_2 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL1 + '_2.audit')
    audit_file_path_2_3 = os.path.join(
        self.AUDIT_DIR, self.TEST_SERIAL2 + '_3.audit')

    self.mock_audit_files = []
    self.mock_time = 0
    mock_listdir.return_value = self.mock_audit_files

    test_audit = atft.AtftAudit(
        self.AUDIT_DIR,
        download_interval,
        get_file_handler,
        get_atfa_serial)
    test_audit.PullAudit(10)
    get_file_handler.assert_called_once_with(
        audit_file_path_1_0, 'audit', False)
    mock_remove.assert_not_called()
    get_file_handler.reset_mock()

    # Insert a new ATFA
    test_audit.ResetKeysLeft()
    get_atfa_serial.return_value = self.TEST_SERIAL2
    test_audit.PullAudit(10)
    get_file_handler.assert_called_once_with(
        audit_file_path_2_1, 'audit', False)
    mock_remove.assert_not_called()
    get_file_handler.reset_mock()

    # Insert the old one back
    test_audit.ResetKeysLeft()
    get_atfa_serial.return_value = self.TEST_SERIAL1
    test_audit.PullAudit(9)
    get_file_handler.assert_called_once_with(
        audit_file_path_1_2, 'audit', False)
    mock_remove.assert_called_once_with(audit_file_path_1_0)
    mock_remove.reset_mock()
    get_file_handler.reset_mock()

    # Insert ATFA2 back
    test_audit.ResetKeysLeft()
    get_atfa_serial.return_value = self.TEST_SERIAL2
    test_audit.PullAudit(9)
    get_file_handler.assert_called_once_with(
        audit_file_path_2_3, 'audit', False)
    mock_remove.assert_called_once_with(audit_file_path_2_1)
    mock_remove.reset_mock()
    get_file_handler.reset_mock()


if __name__ == '__main__':
  unittest.main()
