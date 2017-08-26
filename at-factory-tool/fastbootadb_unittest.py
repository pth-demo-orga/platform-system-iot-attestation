"""Unit test for fastboot interface using adb library."""
import unittest

from adb import usb_exceptions
import fastboot_exceptions
import fastbootadb
from mock import MagicMock
from mock import patch


class FastbootAdbTest(unittest.TestCase):
  ATFA_TEST_SERIAL = 'ATFA_TEST_SERIAL'
  TEST_COMMAND = 'COMMAND'
  TEST_MESSAGE_FAILURE = 'FAIL: TEST MESSAGE'
  TEST_MESSAGE_SUCCESS = 'OKAY: TEST MESSAGE'
  TEST_SERIAL = 'TEST_SERIAL'

  def setUp(self):
    pass

  # Test FastbootDevice.__init__
  @patch('adb.fastboot.FastbootCommands')
  def testFastbootDeviceInit(self, mock_fastboot_commands):
    mock_fastboot_instance = MagicMock()
    mock_fastboot_commands.ConnectDevice.return_value = mock_fastboot_instance
    fastboot_device = fastbootadb.FastbootDevice(self.TEST_SERIAL)
    mock_fastboot_commands.ConnectDevice.assert_called_with(
        serial=self.TEST_SERIAL)
    self.assertEqual(fastboot_device._fastboot_commands, mock_fastboot_instance)
    self.assertEqual(fastboot_device.serial_number, self.TEST_SERIAL)
    return fastboot_device

  # Test FastbootDevice.disconnect
  @patch('adb.fastboot.FastbootCommands')
  def testFastbootDeviceDisconnect(self, mock_fastboot_commands):
    mock_fastboot_instance = MagicMock()
    mock_fastboot_commands.ConnectDevice.return_value = mock_fastboot_instance
    fastboot_device = fastbootadb.FastbootDevice(self.TEST_SERIAL)
    fastboot_device.Disconnect()
    mock_fastboot_instance.Close.assert_called()

  # Test FastbootDevice.__del__
  @patch('adb.fastboot.FastbootCommands')
  def testFastbootDeviceDestroy(self, mock_fastboot_commands):
    mock_fastboot_instance = MagicMock()
    mock_fastboot_commands.ConnectDevice.return_value = mock_fastboot_instance
    fastboot_device = fastbootadb.FastbootDevice(self.TEST_SERIAL)
    del fastboot_device
    mock_fastboot_instance.Close.assert_called()

  # Test FastbootDevice.ListDevices
  @patch('adb.fastboot.FastbootCommands')
  def testListDevicesNormal(self, mock_fastboot_commands):
    mock_atfa_usb_handle = MagicMock()
    mock_target_usb_handle = MagicMock()
    mock_atfa_usb_handle.serial_number = self.ATFA_TEST_SERIAL
    mock_target_usb_handle.serial_number = self.TEST_SERIAL
    # Should return a generator.
    mock_fastboot_commands.Devices.return_value = (d for d in
                                                   [mock_atfa_usb_handle,
                                                    mock_target_usb_handle])
    devices = fastbootadb.FastbootDevice.ListDevices()
    mock_fastboot_commands.Devices.assert_called()
    self.assertEqual(len(devices), 2)
    self.assertEqual(devices[0], self.ATFA_TEST_SERIAL)
    self.assertEqual(devices[1], self.TEST_SERIAL)

  @patch('adb.fastboot.FastbootCommands')
  def testListDevicesFailure(self, mock_fastboot_commands):
    test_exception = (usb_exceptions.
                      FormatMessageWithArgumentsException(self.
                                                          TEST_MESSAGE_FAILURE)
                     )
    mock_fastboot_commands.Devices.side_effect = test_exception
    with self.assertRaises(fastboot_exceptions.FastbootFailure) as e:
      fastbootadb.FastbootDevice.ListDevices()
      self.assertEqual(self.TEST_MESSAGE_FAILURE, str(e))

  # Test FastbootDevice.Oem
  @patch('adb.fastboot.FastbootCommands')
  def testOemNormal(self, mock_fastboot_commands):
    mock_fastboot_device = MagicMock()
    mock_fastboot_commands.ConnectDevice.return_value = mock_fastboot_device
    mock_fastboot_device.Oem.return_value = self.TEST_MESSAGE_SUCCESS
    fastboot_device = fastbootadb.FastbootDevice(self.TEST_SERIAL)
    out = fastboot_device.Oem(self.TEST_COMMAND)
    mock_fastboot_device.Oem.assert_called_once_with(self.TEST_COMMAND)
    self.assertEqual(self.TEST_MESSAGE_SUCCESS, out)

  @patch('adb.fastboot.FastbootCommands')
  def testOemFailure(self, mock_fastboot_commands):
    test_exception = (usb_exceptions.
                      FormatMessageWithArgumentsException(self.
                                                          TEST_MESSAGE_FAILURE)
                     )
    mock_fastboot_device = MagicMock()
    mock_fastboot_commands.ConnectDevice.return_value = mock_fastboot_device
    mock_fastboot_device.Oem.side_effect = test_exception
    with self.assertRaises(fastboot_exceptions.FastbootFailure) as e:
      fastboot_device = fastbootadb.FastbootDevice(self.TEST_SERIAL)
      fastboot_device.Oem(self.TEST_COMMAND)
      self.assertEqual(self.TEST_MESSAGE_FAILURE, str(e))


if __name__ == '__main__':
  unittest.main()
