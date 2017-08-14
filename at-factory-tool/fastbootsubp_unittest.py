"""Unit test for fastboot interface using sh library."""
import unittest

import fastboot_exceptions
import fastbootsubp
from mock import patch


class FastbootSubpTest(unittest.TestCase):
  ATFA_TEST_SERIAL = 'ATFA_TEST_SERIAL'
  TEST_MESSAGE_FAILURE = 'FAIL: TEST MESSAGE'
  TEST_MESSAGE_SUCCESS = 'OKAY: TEST MESSAGE'
  TEST_SERIAL = 'TEST_SERIAL'

  def setUp(self):
    pass

  # Test FastbootDevice.ListDevices
  @patch('subprocess.check_output', create=True)
  def testListDevicesOneDevice(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_SERIAL + '\tfastboot'
    device_serial_numbers = fastbootsubp.FastbootDevice.ListDevices()
    mock_fastboot_commands.assert_called_once_with(['fastboot', 'devices'])
    self.assertEqual(1, len(device_serial_numbers))
    self.assertEqual(self.TEST_SERIAL, device_serial_numbers[0])

  @patch('subprocess.check_output', create=True)
  def testListDevicesTwoDevices(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = (self.TEST_SERIAL + '\tfastboot\n' +
                                           self.ATFA_TEST_SERIAL + '\tfastboot')
    device_serial_numbers = fastbootsubp.FastbootDevice.ListDevices()
    mock_fastboot_commands.assert_called_once_with(['fastboot', 'devices'])
    self.assertEqual(2, len(device_serial_numbers))
    self.assertEqual(self.TEST_SERIAL, device_serial_numbers[0])
    self.assertEqual(self.ATFA_TEST_SERIAL, device_serial_numbers[1])

  @patch('subprocess.check_output', create=True)
  def testListDevicesMultiDevices(self, mock_fastboot_commands):
    one_device = self.TEST_SERIAL + '\tfastboot'
    result = one_device
    for _ in range(0, 9):
      result += '\n' + one_device
    mock_fastboot_commands.return_value = result
    device_serial_numbers = fastbootsubp.FastbootDevice.ListDevices()
    mock_fastboot_commands.assert_called_once_with(['fastboot', 'devices'])
    self.assertEqual(10, len(device_serial_numbers))

  @patch('subprocess.check_output', create=True)
  def testListDevicesNone(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = ''
    device_serial_numbers = fastbootsubp.FastbootDevice.ListDevices()
    mock_fastboot_commands.assert_called_once_with(['fastboot', 'devices'])
    self.assertEqual(0, len(device_serial_numbers))

  @patch('subprocess.check_output', create=True)
  def testListDevicesFailure(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_MESSAGE_FAILURE
    with self.assertRaises(fastboot_exceptions.FastbootFailure) as e:
      fastbootsubp.FastbootDevice.ListDevices()
      self.assertEqual(self.TEST_MESSAGE_FAILURE, str(e))

  # Test FastbootDevice.Oem
  @patch('subprocess.check_output', create=True)
  def testOem(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_MESSAGE_SUCCESS
    command = 'TEST COMMAND'
    device = fastbootsubp.FastbootDevice(self.TEST_SERIAL)
    message = device.Oem(command)
    mock_fastboot_commands.assert_called_once_with(['fastboot', '-s',
                                                    self.TEST_SERIAL,
                                                    'oem',
                                                    command])
    self.assertEqual(self.TEST_MESSAGE_SUCCESS, message)

  @patch('subprocess.check_output', create=True)
  def testOemFailure(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_MESSAGE_FAILURE
    command = 'TEST COMMAND'
    device = fastbootsubp.FastbootDevice(self.TEST_SERIAL)
    with self.assertRaises(fastboot_exceptions.FastbootFailure) as e:
      device.Oem(command)
      self.assertEqual(self.TEST_MESSAGE_FAILURE, str(e))

  # Test FastbootDevice.Upload
  @patch('subprocess.check_output', create=True)
  def testUpload(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_MESSAGE_SUCCESS
    command = 'TEST COMMAND'
    device = fastbootsubp.FastbootDevice(self.TEST_SERIAL)
    message = device.Upload(command)
    mock_fastboot_commands.assert_called_once_with(['fastboot', '-s',
                                                    self.TEST_SERIAL,
                                                    'get_staged',
                                                    command])
    self.assertEqual(self.TEST_MESSAGE_SUCCESS, message)

  @patch('subprocess.check_output', create=True)
  def testUploadFailure(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_MESSAGE_FAILURE
    command = 'TEST COMMAND'
    device = fastbootsubp.FastbootDevice(self.TEST_SERIAL)
    with self.assertRaises(fastboot_exceptions.FastbootFailure) as e:
      device.Upload(command)
      self.assertEqual(self.TEST_MESSAGE_FAILURE, str(e))

  # Test FastbootDevice.Download
  @patch('subprocess.check_output', create=True)
  def testDownload(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_MESSAGE_SUCCESS
    command = 'TEST COMMAND'
    device = fastbootsubp.FastbootDevice(self.TEST_SERIAL)
    message = device.Download(command)
    mock_fastboot_commands.assert_called_once_with(['fastboot', '-s',
                                                    self.TEST_SERIAL,
                                                    'stage',
                                                    command])
    self.assertEqual(self.TEST_MESSAGE_SUCCESS, message)

  @patch('subprocess.check_output', create=True)
  def testDownloadFailure(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_MESSAGE_FAILURE
    command = 'TEST COMMAND'
    device = fastbootsubp.FastbootDevice(self.TEST_SERIAL)
    with self.assertRaises(fastboot_exceptions.FastbootFailure) as e:
      device.Download(command)
      self.assertEqual(self.TEST_MESSAGE_FAILURE, str(e))

if __name__ == '__main__':
  unittest.main()
