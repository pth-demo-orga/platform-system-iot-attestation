"""Unit test for atft."""
import unittest

import atft

from mock import MagicMock
import fastboot_exceptions


class MockAtft(atft.Atft):

  def __init__(self, *args, **kwargs):
    self.atfa_devices_output = None
    self.atft_manager = None
    self.last_target_list = []
    self.auto_prov = False


class TestDeviceInfo(object):

  def __init__(self, serial_number,
               location=None, provision_status=None):
    self.serial_number = serial_number
    self.location = location
    self.provision_status = provision_status
    self.time_set = False

  def __eq__(self, other):
    return (self.serial_number == other.serial_number and
            self.location == other.location)

  def __ne__(self, other):
    return not self.__eq__(other)


class AtftTest(unittest.TestCase):
  TEST_SERIAL1 = 'test-serial1'
  TEST_LOCATION1 = 'test-location1'
  TEST_SERIAL2 = 'test-serial2'
  TEST_LOCATION2 = 'test-location2'

  def setUp(self):
    self.test_target_devs = []
    self.test_dev1 = TestDeviceInfo(self.TEST_SERIAL1,
                                    self.TEST_LOCATION1)
    self.test_dev2 = TestDeviceInfo(self.TEST_SERIAL2,
                                    self.TEST_LOCATION2)

  def AppendTargetDevice(self, device):
    self.test_target_devs.append(device)

  def DeleteAllItems(self):
    self.test_target_devs = []

  def testDeviceListedEventHandler(self):
    mock_atft = MockAtft(None)
    mock_atft.last_target_list = []
    mock_atft.target_devs_output = MagicMock()
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev = None
    mock_atft.PrintToWindow = MagicMock()
    mock_atft.target_devs_output.Append.side_effect = self.AppendTargetDevice
    (mock_atft.target_devs_output.
     DeleteAllItems.side_effect) = self.DeleteAllItems
    mock_atft.atft_manager.target_devs = []
    mock_atft._DeviceListedEventHandler(None)
    mock_atft.atft_manager.target_devs = [self.test_dev1]
    mock_atft._DeviceListedEventHandler(None)
    mock_atft.target_devs_output.Append.assert_called_once()
    self.assertEqual(1, len(self.test_target_devs))
    self.assertEqual(self.test_dev1.serial_number,
                     self.test_target_devs[0][0])
    mock_atft.atft_manager.target_devs = [self.test_dev1, self.test_dev2]
    mock_atft._DeviceListedEventHandler(None)
    self.assertEqual(2, len(self.test_target_devs))
    self.assertEqual(self.test_dev2.serial_number,
                     self.test_target_devs[1][0])
    mock_atft.atft_manager.target_devs = [self.test_dev1, self.test_dev2]
    mock_atft.target_devs_output.Append.reset_mock()
    mock_atft._DeviceListedEventHandler(None)
    mock_atft.target_devs_output.Append.assert_not_called()
    mock_atft.atft_manager.target_devs = [self.test_dev2, self.test_dev1]
    mock_atft.target_devs_output.Append.reset_mock()
    mock_atft._DeviceListedEventHandler(None)
    mock_atft.target_devs_output.Append.assert_called()
    self.assertEqual(2, len(self.test_target_devs))
    mock_atft.atft_manager.target_devs = [self.test_dev2]
    mock_atft._DeviceListedEventHandler(None)
    self.assertEqual(1, len(self.test_target_devs))
    self.assertEqual(self.test_dev2.serial_number,
                     self.test_target_devs[0][0])
    mock_atft.atft_manager.target_devs = []
    mock_atft._DeviceListedEventHandler(None)
    self.assertEqual(0, len(self.test_target_devs))

  def testProcessKeySuccess(self):
    mock_atft = MockAtft(None)
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev_manager = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()

    mock_atft._ProcessKey('test')
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_not_called()

    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_called_once()

  def testProcessKeyFailure(self):
    self.TestProcessKeyFailureCommon(fastboot_exceptions.FastbootFailure(''))
    self.TestProcessKeyFailureCommon(
        fastboot_exceptions.ProductNotSpecifiedException)
    self.TestProcessKeyFailureCommon(
        fastboot_exceptions.DeviceNotFoundException)

  def TestProcessKeyFailureCommon(self, exception):
    mock_atft = MockAtft(None)
    mock_atft.atft_manager = MagicMock()
    mock_atft.atft_manager.atfa_dev_manager = MagicMock()
    mock_atft._SendOperationStartEvent = MagicMock()
    mock_atft._SendOperationSucceedEvent = MagicMock()
    mock_atft.PauseRefresh = MagicMock()
    mock_atft.ResumeRefresh = MagicMock()
    mock_atft._HandleException = MagicMock()

    mock_atft.atft_manager.atfa_dev_manager.ProcessKey.side_effect = exception

    mock_atft._ProcessKey('test')
    mock_atft.PauseRefresh.assert_called_once()
    mock_atft.ResumeRefresh.assert_called_once()
    mock_atft._HandleException.assert_called_once()

    mock_atft._SendOperationStartEvent.assert_called_once()
    mock_atft._SendOperationSucceedEvent.assert_not_called()


if __name__ == '__main__':
  unittest.main()
