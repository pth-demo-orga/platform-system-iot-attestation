"""Unit test for fastboot interface using sh library."""
import unittest

import fastboot_exceptions
import fastbootsh
from mock import patch
import sh


class FastbootShTest(unittest.TestCase):

  ATFA_TEST_SERIAL = 'ATFA_TEST_SERIAL'
  TEST_MESSAGE_FAILURE = 'FAIL: TEST MESSAGE'
  TEST_MESSAGE_SUCCESS = 'OKAY: TEST MESSAGE'
  TEST_SERIAL = 'TEST_SERIAL'

  TEST_VAR = 'VAR1'

  class TestError(sh.ErrorReturnCode):

    def __init__(self):
      pass

  def setUp(self):
    pass

  # Test FastbootDevice.ListDevices
  @patch('sh.fastboot', create=True)
  def testListDevicesOneDevice(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_SERIAL + '\tfastboot'
    device_serial_numbers = fastbootsh.FastbootDevice.ListDevices()
    mock_fastboot_commands.assert_called_once_with('devices')
    self.assertEqual(1, len(device_serial_numbers))
    self.assertEqual(self.TEST_SERIAL, device_serial_numbers[0])

  @patch('sh.fastboot', create=True)
  def testListDevicesTwoDevices(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = (self.TEST_SERIAL + '\tfastboot\n' +
                                           self.ATFA_TEST_SERIAL + '\tfastboot')
    device_serial_numbers = fastbootsh.FastbootDevice.ListDevices()
    mock_fastboot_commands.assert_called_once_with('devices')
    self.assertEqual(2, len(device_serial_numbers))
    self.assertEqual(self.TEST_SERIAL, device_serial_numbers[0])
    self.assertEqual(self.ATFA_TEST_SERIAL, device_serial_numbers[1])

  @patch('sh.fastboot', create=True)
  def testListDevicesMultiDevices(self, mock_fastboot_commands):
    one_device = self.TEST_SERIAL + '\tfastboot'
    result = one_device
    for _ in range(0, 9):
      result += '\n' + one_device
    mock_fastboot_commands.return_value = result
    device_serial_numbers = fastbootsh.FastbootDevice.ListDevices()
    mock_fastboot_commands.assert_called_once_with('devices')
    self.assertEqual(10, len(device_serial_numbers))

  @patch('sh.fastboot', create=True)
  def testListDevicesNone(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = ''
    device_serial_numbers = fastbootsh.FastbootDevice.ListDevices()
    mock_fastboot_commands.assert_called_once_with('devices')
    self.assertEqual(0, len(device_serial_numbers))

  @patch('sh.fastboot', create=True)
  def testListDevicesFailure(self, mock_fastboot_commands):
    mock_error = self.TestError()
    mock_error.stderr = self.TEST_MESSAGE_FAILURE
    mock_fastboot_commands.side_effect = mock_error
    with self.assertRaises(fastboot_exceptions.FastbootFailure) as e:
      fastbootsh.FastbootDevice.ListDevices()
      self.assertEqual(self.TEST_MESSAGE_FAILURE, str(e))

  # Test FastbootDevice.Oem
  @patch('sh.fastboot', create=True)
  def testOem(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_MESSAGE_SUCCESS
    command = 'TEST COMMAND'
    device = fastbootsh.FastbootDevice(self.TEST_SERIAL)
    message = device.Oem(command, False)
    mock_fastboot_commands.assert_called_once_with('-s',
                                                   self.TEST_SERIAL,
                                                   'oem',
                                                   command,
                                                   _err_to_out=False)
    self.assertEqual(self.TEST_MESSAGE_SUCCESS, message)

  @patch('sh.fastboot', create=True)
  def testOemFailure(self, mock_fastboot_commands):
    mock_error = self.TestError()
    mock_error.stderr = self.TEST_MESSAGE_FAILURE
    mock_fastboot_commands.side_effect = mock_error
    command = 'TEST COMMAND'
    device = fastbootsh.FastbootDevice(self.TEST_SERIAL)
    with self.assertRaises(fastboot_exceptions.FastbootFailure) as e:
      device.Oem(command, False)
      self.assertEqual(self.TEST_MESSAGE_FAILURE, str(e))

  # Test FastbootDevice.Upload
  @patch('sh.fastboot', create=True)
  def testUpload(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_MESSAGE_SUCCESS
    command = 'TEST COMMAND'
    device = fastbootsh.FastbootDevice(self.TEST_SERIAL)
    message = device.Upload(command)
    mock_fastboot_commands.assert_called_once_with('-s',
                                                   self.TEST_SERIAL,
                                                   'get_staged',
                                                   command)
    self.assertEqual(self.TEST_MESSAGE_SUCCESS, message)

  @patch('sh.fastboot', create=True)
  def testUploadFailure(self, mock_fastboot_commands):
    mock_error = self.TestError()
    mock_error.stderr = self.TEST_MESSAGE_FAILURE
    mock_fastboot_commands.side_effect = mock_error
    command = 'TEST COMMAND'
    device = fastbootsh.FastbootDevice(self.TEST_SERIAL)
    with self.assertRaises(fastboot_exceptions.FastbootFailure) as e:
      device.Upload(command)
      self.assertEqual(self.TEST_MESSAGE_FAILURE, str(e))

  # Test FastbootDevice.Download
  @patch('sh.fastboot', create=True)
  def testDownload(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_MESSAGE_SUCCESS
    command = 'TEST COMMAND'
    device = fastbootsh.FastbootDevice(self.TEST_SERIAL)
    message = device.Download(command)
    mock_fastboot_commands.assert_called_once_with('-s',
                                                   self.TEST_SERIAL,
                                                   'stage',
                                                   command)
    self.assertEqual(self.TEST_MESSAGE_SUCCESS, message)

  @patch('sh.fastboot', create=True)
  def testDownloadFailure(self, mock_fastboot_commands):
    mock_error = self.TestError()
    mock_error.stderr = self.TEST_MESSAGE_FAILURE
    mock_fastboot_commands.side_effect = mock_error
    command = 'TEST COMMAND'
    device = fastbootsh.FastbootDevice(self.TEST_SERIAL)
    with self.assertRaises(fastboot_exceptions.FastbootFailure) as e:
      device.Download(command)
      self.assertEqual(self.TEST_MESSAGE_FAILURE, str(e))

  # Test FastbootDevice.GetVar
  @patch('sh.fastboot', create=True)
  def testGetVar(self, mock_fastboot_commands):
    mock_fastboot_commands.return_value = self.TEST_VAR + ': ' + 'abcd'
    device = fastbootsh.FastbootDevice(self.TEST_SERIAL)
    message = device.GetVar(self.TEST_VAR)
    mock_fastboot_commands.assert_called_once_with('-s',
                                                   self.TEST_SERIAL,
                                                   'getvar',
                                                   self.TEST_VAR,
                                                   _err_to_out=True)
    self.assertEqual('abcd', message)

if __name__ == '__main__':
  unittest.main()
