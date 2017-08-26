"""Unit test for atftman."""
import unittest

import atftman
import fastboot_exceptions
from mock import patch


files = []


class AtftManTest(unittest.TestCase):
  ATFA_TEST_SERIAL = 'ATFA_TEST_SERIAL'
  TEST_TMP_FOLDER = '/tmp/TMPTEST/'
  TEST_SERIAL = 'TEST_SERIAL'
  TEST_UUID = 'TEST-UUID'

  class FastbootDeviceTemplate(object):

    @staticmethod
    def ListDevices():
      pass

    def __init__(self, serial_number):
      self.serial_number = serial_number

    def Oem(self, oem_command):
      pass

    def Upload(self, file_path):
      pass

    def Download(self, file_path):
      pass

    def Disconnect(self):
      pass

    def __del__(self):
      pass

  def setUp(self):
    self.atft_manager = atftman.AtftManager(self.FastbootDeviceTemplate)

  # Test AtftManager.ListDevices
  @patch('atftman.AtfaDeviceManager')
  @patch('__main__.AtftManTest.FastbootDeviceTemplate.ListDevices')
  def testListDevicesNormal(self, mock_list_devices, mock_atfa_device_manager):
    mock_list_devices.return_value = [self.TEST_SERIAL,
                                      self.ATFA_TEST_SERIAL]
    devices = self.atft_manager.ListDevices()
    self.assertEqual(devices['atfa_dev'], self.ATFA_TEST_SERIAL)
    self.assertEqual(devices['target_dev'], self.TEST_SERIAL)
    mock_atfa_device_manager.assert_called()

  @patch('__main__.AtftManTest.FastbootDeviceTemplate.ListDevices')
  def testListDevicesATFA(self, mock_list_devices):
    mock_list_devices.return_value = [self.ATFA_TEST_SERIAL]
    devices = self.atft_manager.ListDevices()
    self.assertEqual(devices['atfa_dev'], self.ATFA_TEST_SERIAL)
    self.assertEqual(devices['target_dev'], None)

  @patch('__main__.AtftManTest.FastbootDeviceTemplate.ListDevices')
  def testListDevicesTarget(self, mock_list_devices):
    mock_list_devices.return_value = [self.TEST_SERIAL]
    devices = self.atft_manager.ListDevices()
    self.assertEqual(devices['atfa_dev'], None)
    self.assertEqual(devices['target_dev'], self.TEST_SERIAL)

  @patch('__main__.AtftManTest.FastbootDeviceTemplate.ListDevices')
  def testListDevicesNotFound(self, mock_list_devices):
    mock_list_devices.return_value = []
    with self.assertRaises(fastboot_exceptions.DeviceNotFoundException):
      self.atft_manager.ListDevices()

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
  def testTransferContentNormal(self, mock_download, mock_upload,
                                mock_uuid, mock_create_folder,
                                mock_exists, mock_remove, mock_rmdir):
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
    self.atft_manager.TransferContent(src, dst)
    src.Upload.assert_called_once_with(tmp_path)
    src.Download.assert_called_once_with(tmp_path)
    # we should have no temporary file at the end
    self.assertTrue(not files)

if __name__ == '__main__':
  unittest.main()
