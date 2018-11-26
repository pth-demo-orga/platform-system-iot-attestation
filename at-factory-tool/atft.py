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

"""Graphical tool for managing the ATFA and AT communication.

This tool allows for easy graphical access to common ATFA commands.  It also
locates Fastboot devices and can initiate communication between the ATFA and
an Android Things device.
"""
import copy
import datetime
import json
import math
import os
import sets
import sys
import threading
import time

from atftman import AtftManager
from atftman import ProvisionState
from atftman import ProvisionStatus
from atftman import RebootCallback

from fastboot_exceptions import DeviceCreationException
from fastboot_exceptions import DeviceNotFoundException
from fastboot_exceptions import FastbootFailure
from fastboot_exceptions import NoKeysException
from fastboot_exceptions import OsVersionNotAvailableException
from fastboot_exceptions import OsVersionNotCompatibleException
from fastboot_exceptions import PasswordErrorException
from fastboot_exceptions import ProductAttributesFileFormatError
from fastboot_exceptions import ProductNotSpecifiedException

from passlib.hash import pbkdf2_sha256

import psutil

import wx

if sys.platform.startswith('linux'):
  from fastbootsh import FastbootDevice
  from serialmapperlinux import SerialMapper
elif sys.platform.startswith('win'):
  from fastbootsubp import FastbootDevice
  from serialmapperwin import SerialMapper


# The current software version.
VERSION = 3.0

# colors
COLOR_WHITE = wx.Colour(255, 255, 255)
COLOR_RED = wx.Colour(192, 40, 40)
COLOR_YELLOW = wx.Colour(218, 165, 32)
COLOR_GREEN = wx.Colour(15, 133, 33)
COLOR_BLUE = wx.Colour(36, 120, 198)
COLOR_GREY = wx.Colour(237, 237, 237)
COLOR_DARK_GREY = wx.Colour(117, 117, 117)
COLOR_LIGHT_GREY = wx.Colour(247, 247, 247)
COLOR_LIGHT_GREY_TEXT = wx.Colour(214, 214, 214)
COLOR_BLACK = wx.Colour(0, 0, 0)
COLOR_PICK_BLUE = wx.Colour(149, 169, 235)

# How many target devices allowed.
TARGET_DEV_SIZE = 6

# How many audit files are kept for each ATFA in the atft_audit folder
MAX_AUDIT_FILE_NUMBER = 1

LANGUAGE_OPTIONS = ['English', '简体中文']
LANGUAGE_CONFIGS = ['eng', 'cn']

KEYBUNDLE_PROCESSED_MESSAGE = 'Keybundle was previously processed'


class AtftException(Exception):
  """The exception class to include device and operation information.
  """

  def __init__(self, exception, operation=None, targets=None):
    """Init the exception class.

    Args:
      exception: The original exception object.
      operation: The operation that generates this exception.
      targets: The list of operating target devices.
    """
    Exception.__init__(self)
    self.exception = exception
    self.operation = operation
    self.targets = targets

  def __str__(self):
    msg = ''
    if self.targets:
      if len(self.targets) == 1:
        msg += '{' + str(self.targets[0]) + '}'
      else:
        msg += '['
        for target in self.targets:
          msg += '{' + str(target) + '}'
        msg += ']'

    if self.operation:
      msg += self.operation + ' Failed! \n'
    msg += self._AddExceptionType(self.exception)
    return msg

  def _AddExceptionType(self, e):
    """Format the exception. Concatenate the exception type with the message.

    Args:
      e: The exception to be printed.
    Returns:
      The exception message.
    """
    return '{0}: {1}'.format(e.__class__.__name__, e)


class AtftString(object):
  """The class containing literal string. """


  def __init__(self, index):
    # Top level menus
    self.MENU_APPLICATION = ['&Application', '&A应用'][index]
    self.MENU_KEY_PROVISIONING = ['Key Provisioning', '密钥传输'][index]
    self.MENU_ATFA_DEVICE = ['ATFA Device', 'ATFA 管理'][index]
    self.MENU_AUDIT = ['Audit', '审计'][index]
    self.MENU_DOWNLOAD_AUDIT = ['Download Audit File', '下载审计文件'][index]
    self.MENU_KEY_MANAGEMENT = ['Key Management', '密钥管理'][index]

    # Second level menus
    self.MENU_CLEAR_COMMAND = ['Clear Command Output', '清空控制台'][index]
    self.MENU_SHOW_STATUS_BAR = ['Show Statusbar', '显示状态栏'][index]
    self.MENU_CHOOSE_PRODUCT = ['Choose Product', '选择产品'][index]
    self.MENU_SKIP_PRODUCT = ['Skip', '跳过'][index]
    self.MENU_APP_SETTINGS = ['App Settings', '程序设置'][index]
    self.MENU_QUIT = ['quit', '退出'][index]

    self.MENU_MANUAL_FUSE_VBOOT = ['Fuse Bootloader Vboot Key',
                                   '烧录引导密钥'][index]
    self.MENU_MANUAL_FUSE_ATTR = ['Fuse Permanent Attributes',
                                  '烧录产品信息'][index]
    self.MENU_MANUAL_LOCK_AVB = ['Lock Android Verified Boot', '锁定AVB'][index]
    self.MENU_MANUAL_PROV = ['Provision Key', '传输密钥'][index]

    self.MENU_ATFA_STATUS = ['ATFA Status', '查询余量'][index]
    self.MENU_ATFA_UPDATE = ['Update', '升级'][index]
    self.MENU_KEY_THRESHOLD = ['Key Warning Threshold', '密钥警告阈值'][index]
    self.MENU_REG_FILE = ['Download Reg File', '下载注册文件'][index]
    self.MENU_REBOOT = ['Reboot', '重启'][index]
    self.MENU_SHUTDOWN = ['Shutdown', '关闭'][index]

    self.MENU_STOREKEY = ['Store Key Bundle', '存储密钥打包文件'][index]
    self.MENU_PURGE = ['Purge Key Bundle', '清除密钥'][index]

    # Title
    self.TITLE = ['Android Things Factory Tool',
                  'Android Things 工厂程序'][index]

    # Area titles
    self.TITLE_ATFA_DEV = ['ATFA Device: ', 'ATFA 设备： '][index]
    self.TITLE_SOM_NAME = 'SoM: '
    self.TITLE_PRODUCT_NAME = ['Product: ', '产品： '][index]
    self.TITLE_PRODUCT_NAME_NOTCHOSEN = ['Not Chosen', '未选择'][index]
    self.TITLE_KEYS_LEFT = ['Attestation Keys Left:', '剩余密钥:'][index]
    self.TITLE_TARGET_DEV = ['Target Devices', '目标设备'][index]
    self.TITLE_COMMAND_OUTPUT = ['Command Output', '控制台输出'][index]
    self.TITLE_MAP_USB = [
        'Auto map: Click \'Remap\' button, the UI slots would be randomly '
        'mapped to one of the connected Android Things device. \n'
        'Manual map: Insert one Android Things device into the USB port you '
        'want to map, \nthen select one of the six corresponding UI slots and '
        'click \'Map\' button.',
        '自动关联：点击\'自动关联\', 界面上的目标设备将会分配给任意已经连接的Android '
        'Things设备。\n手动关联：将一个Android Things设备插入到你想关联的USB接口，'
        '然后选择界面上六个目标设备位置中的一个并点击\'关联\'。'][index]
    self.TITLE_FIRST_WARNING = ['1st\twarning: ', '警告一：'][index]
    self.TITLE_SECOND_WARNING = ['2nd\twarning: ', '警告二：'][index]
    self.TITLE_SELECT_LANGUAGE = ['Select a language', '选择一种语言'][index]
    self.TITLE_MULTIPLE_DEVICE_DETECTED = [
        'Multiple Device Detected', '检测到多个目标设备'][index]
    # Field names
    self.FIELD_SERIAL_NUMBER = ['SN', '序列号'][index]
    self.SERIAL_NOT_MAPPED = ['Not Mapped', '未分配'][index]
    self.FIELD_USB_LOCATION = ['USB Location', '插入位置'][index]
    self.FIELD_STATUS = ['Status', '状态'][index]

    # Dialogs
    self.DIALOG_CHANGE_THRESHOLD_TEXT = ['ATFA Key Warning Threshold:',
                                         '密钥警告阈值:'][index]
    self.DIALOG_CHANGE_THRESHOLD_TITLE = ['Change ATFA Key Warning Threshold',
                                          '更改密钥警告阈值'][index]
    self.DIALOG_LOW_KEY_TEXT = ''
    self.DIALOG_LOW_KEY_TITLE = ['Low Key Alert', '密钥不足警告'][index]
    self.DIALOG_ALERT_TEXT = ''
    self.DIALOG_ALERT_TITLE = ['Alert', '警告'][index]
    self.DIALOG_WARNING_TITLE = ['Warning', '警告'][index]
    self.DIALOG_CHOOSE_PRODUCT_ATTRIBUTE_FILE = [
        'Choose Product Attributes File', '选择产品文件'][index]
    self.DIALOG_CHOOSE_KEY_FILE = ['Choose Key File', '选择密钥文件'][index]
    self.DIALOG_CHOOSE_UPDATE_FILE = [
        'Choose Update Patch File', '选择升级补丁文件'][index]
    self.DIALOG_SELECT_DIRECTORY = ['Select directory', '选择文件夹'][index]
    self.DIALOG_INPUT_PASSWORD = ['Input the password', '输入密码'][index]
    self.DIALOG_PASSWORD = ['Password', '密码'][index]
    self.DIALOG_ORIG_PASSWORD = ['Original Password: ', '原密码：'][index]
    self.DIALOG_NEW_PASSWORD = ['New Password: ', '新密码：'][index]

    # Buttons
    self.BUTTON_ENTER_SUP_MODE = ['Enter Supervisor Mode', '进入管理模式'][index]
    self.BUTTON_LEAVE_SUP_MODE = ['Leave Supervisor Mode', '离开管理模式'][index]
    self.BUTTON_MAP_USB_LOCATION = ['Map USB Locations', '关联USB位置'][index]
    self.BUTTON_LANGUAGE_PREFERENCE = ['Language Preference', '语言偏好'][index]
    self.BUTTON_SET_PASSWORD = ['Set Password', '设置密码'][index]
    self.BUTTON_UNMAP = ['Unmap', '取消关联'][index]
    self.BUTTON_REMAP = ['Remap', '重新关联'][index]
    self.BUTTON_MAP = ['Map', '关联'][index]
    self.BUTTON_CANCEL = ['Cancel', '取消'][index]
    self.BUTTON_SAVE = ['Save', '保存'][index]
    self.BUTTON_DEVICE_UNPLUGGED = ['Device Unplugged', '设备已拔出'][index]
    self.BUTTON_START_OPERATION = ['Start Operation', '开始'][index]

    # Alerts
    self.ALERT_NO_ATFA = [
        'No ATFA device available!',
        '没有可用的ATFA设备！'][index]
    self.ALERT_AUTO_PROV_NO_ATFA = [
        'Cannot enter auto provision mode\nNo ATFA device available!',
        '无法开启自动模式\n没有可用的ATFA设备！'][index]
    self.ALERT_AUTO_PROV_NO_PRODUCT = [
        'Cannot enter auto provision mode\nNo product specified!',
        '无法开启自动模式\n没有选择产品！'][index]
    self.ALERT_AUTO_PROV_NO_KEYS_LEFT = [
        'Cannot enter auto provision mode\nNo keys left in ATFA!',
        '无法开启自动模式\n没有剩余密钥！'][index]
    self.ALERT_PROV_NO_SELECTED = [
        "Can't Provision! No target device selected!",
        '无法传输密钥！目标设备没有选择！'][index]
    self.ALERT_PROV_NO_ATFA = [
        "Can't Provision! No Available ATFA device!",
        '无法传输密钥！没有ATFA设备!'][index]
    self.ALERT_PROV_NO_KEYS = [
        "Can't Provision! No keys left!",
        '无法传输密钥！没有剩余密钥!'][index]
    self.ALERT_FUSE_NO_SELECTED = [
        "Can't Fuse vboot key! No target device selected!",
        '无法烧录！目标设备没有选择！'][index]
    self.ALERT_FUSE_NO_PRODUCT = [
        "Can't Fuse vboot key! No product specified!",
        '无法烧录！没有选择产品！'][index]
    self.ALERT_FUSE_PERM_NO_SELECTED = [
        "Can't Fuse permanent attributes! No target device selected!",
        '无法烧录产品信息！目标设备没有选择！'][index]
    self.ALERT_FUSE_PERM_NO_PRODUCT = [
        "Can't Fuse permanent attributes! No product specified!",
        '无法烧录产品信息！没有选择产品！'][index]
    self.ALERT_LOCKAVB_NO_SELECTED = [
        "Can't Lock Android Verified Boot! No target device selected!",
        '无法锁定AVB！目标设备没有选择！'][index]
    self.ALERT_FAIL_TO_CREATE_LOG = [
        'Failed to create log!',
        '无法创建日志文件！'][index]
    self.ALERT_FAIL_TO_PARSE_CONFIG = [
        'Failed to find or parse config file, please check your config file'
        ' version!',
        '无法找到或解析配置文件，请确认你的配置文件与软件版本一致！'][index]
    self.ALERT_NO_DEVICE = [
        'No devices found!',
        '无设备！'][index]
    self.ALERT_CANNOT_OPEN_FILE = [
        'Can not open file: ',
        '无法打开文件: '][index]
    self.ALERT_CANNOT_SAVE_FILE = [
        'Cannot save file at file path: ',
        '无法保存文件路径: '][index]
    self.ALERT_FILE_EXISTS = [
        ' already exists, do you want to overwrite it?',
        ' 已经存在，是否覆盖？'][index]
    self.ALERT_PRODUCT_FILE_FORMAT_WRONG = [
        'The format for the product attributes file is not correct!',
        '产品文件格式不正确！'][index]
    self.ALERT_ATFA_UNPLUG = [
        'ATFA device unplugged, exit auto mode!',
        'ATFA设备拔出，退出自动模式！'][index]
    self.ALERT_NO_KEYS_LEFT_LEAVE_PROV = [
        'No keys left! Leave auto provisioning mode!',
        '没有剩余密钥，退出自动模式！'][index]
    self.ALERT_FUSE_VBOOT_FUSED = [
        'Cannot fuse bootloader vboot key for device that is already fused!',
        '无法烧录一个已经烧录过引导密钥的设备！'][index]
    self.ALERT_FUSE_PERM_ATTR_FUSED = [
        'Cannot fuse permanent attributes for device that is not fused '
        'bootloader vboot key or already fused permanent attributes!',
        '无法烧录一个没有烧录过引导密钥或者已经烧录过产品信息的设备！'][index]
    self.ALERT_LOCKAVB_LOCKED = [
        'Cannot lock android verified boot for device that is not fused '
        'permanent attributes or already locked!',
        '无法锁定一个没有烧录过产品信息或者已经锁定AVB的设备！'][index]
    self.ALERT_UNLOCKAVB_UNLOCKED = [
        'Cannot unlock android verified boot for device that is already '
        'unlocked!',
        '无法解锁一个已经解锁AVB的设备'][index]
    self.ALERT_PROV_PROVED = [
        'Cannot provision device that is not ready for provisioning or '
        'already provisioned!',
        '无法传输密钥给一个不在正确状态或者已经拥有密钥的设备！'][index]
    self.ALERT_NO_MAP_DEVICE_CHOSEN = [
        'No device location chosen for mapping!',
        '未选择要关联的设备位置'][index]
    self.ALERT_NO_UNMAP_DEVICE_CHOSEN = [
        'No device location chosen for unmapping!',
        '未选择要取消关联的设备位置'][index]
    self.ALERT_MAP_DEVICE_TIMEOUT = [
        'Mapping Failure!\nNo ATFA device detected at any USB Location!',
        '关联失败！\n没有在任何USB口检测到ATFA设备！'][index]
    self.ALERT_INCOMPATIBLE_ATFA = [
        'Detected an ATFA device having incompatible version with this tool, '
        'please upgrade your ATFA device to the latest version!',
        '检测到一个与这个软件不兼容的ATFA设备，请升级你的ATFA设备！'][index]
    self.ALERT_REMAP_LOCATION_SLOT = [
        lambda location, slot :
            ('The USB location ' + location.encode('utf-8') +
             ' was aleady mapped to slot ' + slot.encode('utf-8') +
             ' before, do you want to overwrite?'),
        lambda location, slot :
            ('USB位置' + location.encode('utf-8') + '已经被关联到设备位置' +
             slot.encode('utf-8') + ', 是否覆盖?')
        ][index]
    self.ALERT_REMAP_SLOT_LOCATION = [
        lambda slot, location :
            'The slot ' + slot + ' was aleady mapped to '
            'USB Location ' + location.encode('utf-8') + ' before, '
            'do you want to overwrite?',
        lambda slot, location :
            ('设备位置' + slot.encode('utf-8') +
             '已经被关联到USB位置' + location.encode('utf-8') + ', 是否覆盖?')
        ][index]
    self.ALERT_UNMAP = [
        'Do you really want to unmap this USB port?',
        '你确定要取消关联这个USB位置吗?'][index]
    self.ALERT_ADD_MORE_KEY = [
        lambda keys_left:
            'Warning - add more keys\n'
            'There are ' + str(keys_left) + ' keys left.',
        lambda keys_left:
            '警告！请添加更多密钥！当前剩余密钥：' + str(keys_left)][index]
    self.ALERT_PROCESS_KEY_FAILURE = [
        'Process key failed, Error: ',
        '处理密钥文件失败！错误信息：'][index]
    self.ALERT_UPDATE_FAILURE = [
        'Update ATFA failed, Error: ',
        '升级ATFA设备失败！错误信息：'][index]
    self.ALERT_PURGE_KEY_FAILURE = [
        'Purge key failed, Error: ',
        '清除密钥失败！错误信息：'][index]
    self.ALERT_CANNOT_GET_REG = [
        'Cannot get registration file! Error: ',
        '无法获得注册文件！错误：'][index]
    self.ALERT_REG_DOWNLOADED = [
        'Registration file downloaded at: ',
        '注册文件下载完成，位置：'][index]
    self.ALERT_CANNOT_GET_AUDIT = [
        'Cannot get audit file! Error: ',
        '无法获得审计文件！错误：'][index]
    self.ALERT_AUDIT_DOWNLOADED = [
        'Audit file downloaded at: ',
        '审计文件下载完成，位置：'][index]
    self.ALERT_KEYS_LEFT = [
        lambda keys_left:
            'There are ' + str(keys_left) + ' keys left for '
            'this product in the ATFA device.',
        lambda keys_left:
            'ATFA设备中对于此产品剩余密钥数量：' + str(keys_left)
        ][index]
    self.ALERT_CONFIRM_PURGE_KEY = [
        'Are you sure you want to purge all the keys for this product?\n'
        'The keys would be purged permanently!!!',
        '你确定要清楚密钥吗？\n设备中的密钥将永久丢失！！！'][index]
    # This variable is intentionally a list instead of a string since we need
    # to show the correct message after language setting is changed.
    self.ALERT_LANGUAGE_RESTART = [
        'The language setting would take effect after you restart the '
        'application.',
        '语言设置将在下次重启程序后生效。']
    self.ALERT_WRONG_PASSWORD = [
        'Wrong Password!!!',
        '密码错误!!!'][index]
    self.ALERT_WRONG_ORIG_PASSWORD = [
        'Wrong Original Password!!!',
        '原密码错误!!!'][index]
    self.ALERT_REPROVISION = [
        lambda device:
            'The device ' + str(device) + ' already has attestation key, '
            'do you want to reprovision a new key?',
        lambda device:
            '设备' + str(device) + '中已经有一个密钥，是否覆盖？'][index]
    self.ALERT_PROVISION_STEPS_SYNTAX_ERROR = [
        'Config "PROVISION_STEPS" is not an array or contains unsupported '
        'operations',
        '设置项"PROVISION_STEPS"不是一个数组或者包含不支持的步骤'][index]
    self.ALERT_PROVISION_STEPS_SECURITY_REQ = [
        'Config "PROVISION_STEPS" does not meet the necessary security '
        'requirement, please check again or set TEST_MODE to true if you are '
        'really sure what you are doing.',
        '设置项"PROVISION_STEPS"不符合必要的信息安全要求，请检查或者设定TEST_MODE为True'
        '如果你明确此行为带来的后果.'][index]
    self.ALERT_INSTANCE_RUNNING = [
        'Another instance of this tool is already running. If you continue, '
        'the tool WILL NOT behave as expected, are you sure you want to '
        'continue?',
        '检测到已经有一个相同的程序在运行，如果继续运行可能会导致错误，确定要'
        '继续吗？'][index]
    self.ALERT_NO_TARGET_DEVICE = [
        'No Android Things device detected, please make sure your device is in '
        'fastboot mode.',
        '没有检测到已连接的Android Things设备，请确保设备在fastboot状态。'][index]
    self.ALERT_MULTIPLE_TARGET_DEVICE = [
        'More than one Android Things connected, please only plug in the one '
        'you want to map.',
        '检测到多个已连接的Android Things设备，请确保仅有一个想要关联的设备。'][index]
    self.ALERT_CHANGE_MAPPING_MODE = [
        'Detected multiple target devices! Unplug one device and click cancel '
        'or click map to map USB locations to UI slots.',
        '检测到多个目标设备，请拔出一个设备或者关联USB位置到一个界面上的设备槽位'][index]
    self.ALERT_TARGET_DEVICE_UNMAPPED = [
        'Detected a target device plugged in an unmapped USB port, this'
        ' device will be ignored unless you map the USB port, do you want to '
        'map the port now?',
        '检测到一个目标设备插在一个没有被关联的USB位置上，这个设备将被忽略除非你关联USB位置'
        '，是否关联？'][index]

    self.STATUS_MAPPED = ['Mapped', '已关联位置'][index]
    self.STATUS_NOT_MAPPED = ['Not mapped', '未关联位置'][index]


class AtftAudit(object):
  """The class to manage audit files in ATFA. """

  @staticmethod
  def GetAuditFileName(serial):
    time = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
    return '{}_{}.audit'.format(serial, time)

  def __init__(self,
               audit_dir,
               download_interval,
               get_file_handler,
               handle_exception_handler,
               get_atfa_serial):
    """Initialize ATFT Audit object.

    Args:
      audit_dir: The audit file directory.
      download_interval: How often (keys) to pull audit file.
      get_file_handler: The function to get file from ATFA.
      handle_exception_handler: The function to handle exception.
      get_atfa_serial: The function to get current ATFA serial.
    """
    self.audit_dir = audit_dir
    self.last_audit_keys_left = -1
    self.download_interval = download_interval
    self.get_file_handler = get_file_handler
    self.get_atfa_serial = get_atfa_serial
    self.handle_exception_handler = handle_exception_handler
    if not os.path.exists(self.audit_dir):
      # If audit directory does not exist, try to create it.
      try:
        os.mkdir(self.audit_dir)
      except IOError:
        return

  def PullAudit(self, keys_left):
    """Pull audit file from ATFA if the download_interval keys has been used.

    Args:
      keys_left: Currently how many keys left in the ATFA.
    """
    if (self.last_audit_keys_left == -1 or (
        self.last_audit_keys_left - self.download_interval >= keys_left)):
      if self._DownloadAudit():
        self.last_audit_keys_left = keys_left

  def _GetAuditFiles(self, serial_number):
    """Get a list of all the audit files in the audit directory.

    Args:
      serial_number: The serial number for the current ATFA.
    Returns:
      A list of audit file names.
    """
    audit_files = []
    for file_name in os.listdir(self.audit_dir):
      if (os.path.isfile(os.path.join(self.audit_dir, file_name)) and
          file_name.endswith('.audit') and
          file_name.startswith(serial_number)):
        audit_files.append(file_name)
    audit_files.sort()
    return audit_files

  def ResetKeysLeft(self):
    """Force to pull ATFA audit file. """
    self.last_audit_keys_left = -1

  def _DownloadAudit(self):
    """Download audit file from ATFA and remove old audit files.

    Returns:
      Whether the audit file is downloaded successfully.
    """
    try:
      serial = self.get_atfa_serial()
    except DeviceNotFoundException as e:
      return False
    except FastbootFailure as e:
      self.handle_exception_handler('E', e)
      return False

    filepath = os.path.join(
        self.audit_dir, AtftAudit.GetAuditFileName(serial))

    # If somehow we have another operation ongoing while trying to download
    # audit file, let the download fail and do not block. Also do not give
    # alert for automatic process.
    if not self.get_file_handler(filepath, 'audit', False, False):
      return False

    # We only remove old files if we successfully pull audit file.
    while True:
      audit_files = self._GetAuditFiles(serial)
      # We keep at most MAX_AUDIT_FILE_NUMBER records in case one is broken.
      if len(audit_files) <= MAX_AUDIT_FILE_NUMBER:
        break
      oldest_file = os.path.join(self.audit_dir, audit_files[0])
      os.remove(oldest_file)

    return True


class AtftKeyHandler(object):
  """The class to manage key file processing."""

  def __init__(self,
               key_dir,
               log_dir,
               key_file_extension,
               process_key_handler,
               handle_exception_handler,
               get_atfa_serial):
    """Initialize ATFT Key object.

    Args:
      key_dir: The folder to look for key files.
      log_dir: The log directory folder to store processed key information.
      key_file_extension: The extension for the key file.
      process_key_handler: The handler to store the key into the ATFA.
      handle_exception_handler: The function to handle exception.
      get_atfa_serial: The handler to get the ATFA serial number.
    """
    # Check for unprocessed key files every 5 minutes.
    self.refresh_interval = 300
    self.key_dir = key_dir
    self.log_dir = log_dir
    self.key_file_extension = key_file_extension
    self.process_key_handler = process_key_handler
    self.handle_exception_handler = handle_exception_handler
    self.get_atfa_serial = get_atfa_serial
    self.timer = None
    self.processed_keys = {}

  def StartProcessKey(self):
    """Start periodically processing keys in the key_dir."""
    if not self.key_dir or not os.path.exists(self.key_dir):
      return
    for key_log_file in os.listdir(self.log_dir):
      if not key_log_file.startswith('ATFA') or not key_log_file.endswith('.log'):
        continue
      atfa_id = key_log_file.replace('.log', '')
      try:
        with open(os.path.join(self.log_dir, key_log_file), 'r') as log_file:
          self.processed_keys[atfa_id] = sets.Set()
          for file_name in log_file:
            self.processed_keys[atfa_id].add(file_name.replace('\n', ''))
      except IOError:
        continue
    self.ProcessKeyFile()

  def StopProcessKey(self):
    """End the processing."""
    if self.timer:
      self.timer.cancel()
    self.timer = None

  def ProcessKeyFile(self):
    """Read unprocessed key files from the key directory and process them."""
    key_files  = []
    atfa_id = None
    self.timer = threading.Timer(self.refresh_interval, self.ProcessKeyFile)
    self.timer.start()
    try:
      atfa_id = self.get_atfa_serial()
    except (DeviceNotFoundException, FastbootFailure):
      # Either ATFA does not exist or something wrong with it, ignore and
      # try again next time.
      return

    for key_file in os.listdir(self.key_dir):
      if not key_file.endswith(self.key_file_extension.replace("*.", "")):
        continue
      if not key_file.startswith(atfa_id):
        continue
      if (atfa_id in self.processed_keys and
          key_file in self.processed_keys[atfa_id]):
        continue
      if os.path.isfile(os.path.join(self.key_dir, key_file)):
        key_files.append(key_file)

    for key_file in key_files:
      key_path = os.path.join(self.key_dir, key_file)
      try:
        self.process_key_handler(key_path, True)
        # Process succeed, record the key file name.
        self.WriteToLog(key_file, atfa_id)
      except DeviceNotFoundException:
        continue
      except FastbootFailure as e:
        # If the process fails, this may because the key bundle file is being
        # written to, the key bundle corrupts or other ephemeral errors that
        # might be fixed in another try. As a result, we don't write it to
        # log and let it automatically retry unless the error is that the key
        # is already processed.
        self.handle_exception_handler('E', e)
        if KEYBUNDLE_PROCESSED_MESSAGE in e.msg:
          self.WriteToLog(key_file, atfa_id)

  def WriteToLog(self, key_file_name, atfa_id):
    """Record key-processed information.

    Args:
      key_file_name: The file name for the key that has been processed.
      atfa_id: The ATFA ID this key file is for.
    """
    if atfa_id not in self.processed_keys:
      self.processed_keys[atfa_id] = sets.Set()
    self.processed_keys[atfa_id].add(key_file_name)

    key_log_file = os.path.join(self.log_dir, '{}.log'.format(atfa_id))
    if not os.path.exists(key_log_file):
      try:
        log_file = open(key_log_file, 'w+')
        log_file.close()
      except IOError:
        return
    try:
      with open(key_log_file, 'a+') as log_file:
        log_file.write(key_file_name + '\n')
        log_file.flush()
    except IOError:
      return


class AtftLog(object):
  """The class to handle logging.

  Logs would be created under log_dir with the time stamp when the log is
  created as file name. There would be at most LOG_FILE_NUMBER log files and
  each log file size would be less than log_size/log_file_number, so the total
  log size would less than log_size.
  """

  def __init__(self, log_dir, log_size, log_file_number):
    """Initiate the AtftLog object.

    This function would also write the first 'Program Start' log entry.

    Args:
      log_dir: The directory to store logs.
      log_size: The maximum total size for all the log files.
      log_file_number: The maximum number for log files.
    """
    self.log_dir = log_dir
    self.log_dir_file = None
    self.file_size = 0
    self.log_size = log_size
    self.log_file_number = log_file_number
    self.file_size_max = math.floor(self.log_size / self.log_file_number)
    self.lock = threading.Lock()
    self.Initialize()

  def Initialize(self):
    """Do the necessary initialization.

    Create log directory if not exists. Also create the first log file if not
    exists. Log a 'Program Start' entry. Point the current log directory to
    the latest log file.
    """
    if not os.path.exists(self.log_dir):
      # If log directory does not exist, try to create it.
      try:
        os.mkdir(self.log_dir)
      except IOError:
        return

    log_files = self._GetLogFiles()
    if not log_files:
      # Create the first log file.
      self._CreateLogFile()
    else:
      self.log_dir_file = os.path.join(self.log_dir, log_files.pop())

  def Error(self, tag, string):
    """Print an error message to the log.

    Args:
      tag: The tag for the message.
      string: The error message.
    """
    self._Output('E', tag, string)

  def Debug(self, tag, string):
    """Print a debug message to the log.

    Args:
      tag: The tag for the message.
      string: The debug message.
    """
    self._Output('D', tag, string)

  def Warning(self, tag, string):
    """Print a warning message to the log.

    Args:
      tag: The tag for the message.
      string: The warning message.
    """
    self._Output('W', tag, string)

  def Info(self, tag, string):
    """Print an info message to the log.

    Args:
      tag: The tag for the message.
      string: The info message.
    """
    self._Output('I', tag, string)

  def CheckInstanceRunning(self):
    """Check whether there is already an instance of ATFT running.

    We do this by checking the log file for 'Program start' without
    'Program exit'.

    Returns:
      True if no other instance is running, false otherwise.
    """
    running_processes = []
    for p in psutil.process_iter(attrs=['name', 'pid', 'ppid', 'cmdline']):
      pname = p.info['name']
      if ('atft.exe' == pname or 'atft' == pname in pname or
          p.info['cmdline'] == ['python', 'atft.py']):
        running_processes.append(p)

    # Remove forked process.
    dedup_running_processes = []
    for p in running_processes:
      dup = False
      for p2 in running_processes:
        if p.info['ppid'] == p2.info['pid']:
          dup = True
          break
      if not dup:
        dedup_running_processes.append(p)

    # Current running process should be 1.
    if len(dedup_running_processes) > 1:
      return False
    return True

  def _Output(self, code, tag, string):
    """Output a line of message to the log file.

    Args:
      code: The log level.
      tag: The log tag.
      string: The log message.
    """
    time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    message = '[{0}] {1}/{2}: {3}'.format(
        time, code, tag, string.replace('\n', '\t'))
    if self.log_dir_file:
      message += '\n'
      with self.lock:
        self._LimitSize(message)
        with open(self.log_dir_file, 'a') as log_file:
          log_file.write(message)
          log_file.flush()

  def _GetLogFiles(self):
    log_files = []
    for file_name in os.listdir(self.log_dir):
      if (os.path.isfile(os.path.join(self.log_dir, file_name)) and
          file_name.startswith('atft_log_')):
        log_files.append(file_name)
    log_files.sort()
    return log_files

  def _LimitSize(self, message):
    """This function limits the total size of logs.

    It would create a new log file if the log file is too large. If the total
    number of log files is larger than threshold, then it would delete the
    oldest log.

    Args:
      message: The log message about to be added.
    """
    file_size = os.path.getsize(self.log_dir_file)
    if file_size + len(message) > self.file_size_max:
      # If file size will exceed file_size_max, then create a new file and close
      # the current one.
      self._CreateLogFile()

    log_files = self._GetLogFiles()
    if len(log_files) > self.log_file_number:
      # If file number exceeds LOG_FILE_NUMBER, then delete the oldest file.
      try:
        oldest_file = os.path.join(self.log_dir, log_files[0])
        os.remove(oldest_file)
      except IOError:
        pass

  def _CreateLogFile(self):
    """Create a new log file using timestamp as file name.
    """
    timestamp = self._GetCurrentTimestamp()
    log_file_name = 'atft_log_' + str(timestamp)
    log_file_path = os.path.join(self.log_dir, log_file_name)
    i = 1
    while os.path.exists(log_file_path):
      # If already exists, create another name, timestamp_1, timestamp_2, etc.
      log_file_name_new = log_file_name + '_' + str(i)
      log_file_path = os.path.join(self.log_dir, log_file_name_new)
      i += 1
    try:
      log_file = open(log_file_path, 'w+')
      log_file.close()
      self.log_dir_file = log_file_path
    except IOError:
      self.log_dir_file = None

  def _GetCurrentTimestamp(self):
    return int((datetime.datetime.now() -
                datetime.datetime(1970, 1, 1)).total_seconds())

  def __del__(self):
    """Cleanup function. This would log the 'Program Exit' message.
    """
    self.Info('Program', 'Program exit')


class Event(wx.PyCommandEvent):
  """The customized event class.
  """

  def __init__(self, etype, eid=-1, value=None):
    """Create a new customized event.

    Args:
      etype: The event type.
      eid: The event id.
      value: The additional data included in the event.
    """
    wx.PyCommandEvent.__init__(self, etype, eid)
    self._value = value

  def GetValue(self):
    """Get the data included in this event.

    Returns:
      The event data.
    """
    return self._value


class ChangeThresholdDialog(wx.Dialog):
  """The dialog class to ask user to change key warning threshold."""

  def GetFirstWarning(self):
    """Get the first warning value.

    Returns:
      The first warning value.
    """
    return self.first_warning

  def GetSecondWarning(self):
    """Get the second warning value.

    Returns:
      The second warning value.
    """
    return self.second_warning

  def __init__(self, atft_string, first_warning, second_warning):
    """Initiate the dialog using the atft class instance.

    Args:
      atft_string: The class for all the string literals.
    """
    self.atft_string = atft_string
    self.first_warning = first_warning
    self.second_warning = second_warning

  def CreateDialog(self, *args, **kwargs):
    """The actual initializer to create the dialog.

    This function creates UI elements within the dialog and only need to be
    called once. This function should be called with the same argument for
    wx.Dialog class and should be called as part of the initialization after
    using __init__.
    """
    super(ChangeThresholdDialog, self).__init__(*args, **kwargs)
    self.SetForegroundColour(wx.Colour(0, 0, 0))
    panel_sizer = wx.BoxSizer(wx.VERTICAL)
    self.SetSizer(panel_sizer)
    self.SetSize(300, 250)

    self._CreateTitle(panel_sizer)
    self._CreateFirstWarningInput(panel_sizer)
    panel_sizer.AddSpacer(10)
    self._CreateSecondWarningInput(panel_sizer)
    panel_sizer.AddSpacer(40)
    self._CreateButtons(panel_sizer)

  def _CreateTitle(self, panel_sizer):
    dialog_title = wx.StaticText(
        self, wx.ID_ANY, self.atft_string.DIALOG_CHANGE_THRESHOLD_TEXT)
    title_font = wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    dialog_title.SetFont(title_font)
    panel_sizer.Add(dialog_title, 0, wx.ALL, 20)

  def _CreateFirstWarningInput(self, panel_sizer):
    line_sizer = wx.BoxSizer(wx.HORIZONTAL)
    first_warning_hint = wx.StaticText(
        self, wx.ID_ANY, self.atft_string.TITLE_FIRST_WARNING)
    line_sizer.Add(first_warning_hint, 0, wx.TOP, 5)
    self.first_warning_input = wx.TextCtrl(self, wx.ID_ANY, '')
    line_sizer.Add(self.first_warning_input, 0, wx.LEFT, 10)
    panel_sizer.Add(line_sizer, 0, wx.LEFT, 20)
    font = wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    first_warning_hint.SetFont(font)
    self.first_warning_input.SetFont(font)

  def _CreateSecondWarningInput(self, panel_sizer):
    line_sizer = wx.BoxSizer(wx.HORIZONTAL)
    second_warning_hint = wx.StaticText(
        self, wx.ID_ANY, self.atft_string.TITLE_SECOND_WARNING)
    line_sizer.Add(second_warning_hint, 0, wx.TOP, 5)
    self.second_warning_input = wx.TextCtrl(
        self, wx.ID_ANY, '')
    line_sizer.Add(self.second_warning_input, 0, wx.LEFT, 10)
    panel_sizer.Add(line_sizer, 0, wx.LEFT, 20)
    font = wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    second_warning_hint.SetFont(font)
    self.second_warning_input.SetFont(font)

  def _CreateButtons(self, panel_sizer):
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_font = wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    button_cancel = wx.Button(
        self, label=self.atft_string.BUTTON_CANCEL, size=(130, 30), id=wx.ID_CANCEL)
    button_save = wx.Button(
        self, label=self.atft_string.BUTTON_SAVE, size=(130, 30), id=wx.ID_OK)
    button_save.SetFont(button_font)
    button_cancel.SetFont(button_font)
    button_sizer.Add(button_cancel, 0)
    button_sizer.Add(button_save, 0, wx.LEFT, 5)
    panel_sizer.Add(button_sizer, 0, wx.ALIGN_CENTER)
    button_save.Bind(wx.EVT_BUTTON, self.OnSave)

  def ShowModal(self):
    """Show the dialog.

    This function would set default value and call wx.Dialog.ShowModal.
    """
    self.first_warning_input.Clear()
    if self.first_warning:
      self.first_warning_input.AppendText(str(self.first_warning))
    self.second_warning_input.Clear()
    if self.second_warning:
      self.second_warning_input.AppendText(str(self.second_warning))
    return super(ChangeThresholdDialog, self).ShowModal()

  def OnSave(self, e):
    """Change warning dialog save callback.

    We allow user to:
    No warning: first warning and second warning empty
    One warning: first warning not empty, second warning empty
    Two warnings: first warning not empty, second warning not empty.

    Args:
      e: The triggering event.
    """
    first_warning = self.first_warning_input.GetValue()
    second_warning = self.second_warning_input.GetValue()
    if not first_warning and second_warning:
      # Do not allow second warning set while first warning is not.
      return
    try:
      if not second_warning:
        if not first_warning:
          # No warning
          self.first_warning = None
          self.second_warning = None
        else:
          # User disable second warning
          self.second_warning = None
          first_warning_number = int(first_warning)
          if first_warning_number <= 0:
            return
          self.first_warning = first_warning_number
      else:
        # Second warning set.
        first_warning_number = int(first_warning)
        second_warning_number = int(second_warning)
        if first_warning_number <= 0 or second_warning_number <= 0:
          # Invalid setting, just ignore.
          return
        if second_warning_number >= first_warning_number:
          return
        self.first_warning = first_warning_number
        self.second_warning = second_warning_number
    except ValueError:
      # If any field is invalid, let user input again.
      return
    self.EndModal(0)


class AppSettingsDialog(wx.Dialog):
  """The dialog class to ask user to change application settings.

  Now support Mapping USB Location to UI slot, Setting language and Setting
  password for supervisor mode.
  """

  def __init__(self, atft_string,
               unmap_usb_location_handler,
               manual_map_usb_location_handler,
               map_usb_to_slot_handler,
               change_language_handler,
               change_password_handler,
               language_index,
               device_usb_locations):
    """Initiate the dialog using the atft class instance.

    Args:
      atft_string: The class for string constants.
      unmap_usb_location_handler: The handler for clicking 'unmap' button.
      manual_map_usb_location_handler: The handler for clicking 'map' button.
      map_usb_to_slot_handler: The handler for clicking each slot.
      change_language_handler: The handler for changing language.
      change_password_handler: The handler for changing password.
      language_index: The language index.
      device_usb_locations: The device usb location mapping.
    """
    self.atft_string = atft_string
    self.settings = []
    self.menu_items = []
    self.current_setting = None
    self.unmap_usb_location_handler = unmap_usb_location_handler
    self.manual_map_usb_location_handler = manual_map_usb_location_handler
    self.map_usb_to_slot_handler = map_usb_to_slot_handler
    self.change_language_handler = change_language_handler
    self.change_password_handler = change_password_handler
    self.language_index = language_index
    self.device_usb_locations = device_usb_locations

  def CreateDialog(self, *args, **kwargs):
    """The actual initializer to create the dialog.

    This function creates UI elements within the dialog and only need to be
    called once. This function should be called with the same argument for
    wx.Dialog class and should be called as part of the initialization after
    using __init__.
    """
    super(AppSettingsDialog, self).__init__(*args, **kwargs)
    self.SetForegroundColour(COLOR_BLACK)
    self.SetBackgroundColour(COLOR_WHITE)
    self.SetSize(850, 650)
    panel_sizer = wx.BoxSizer(wx.VERTICAL)
    self.SetSizer(panel_sizer)

    self.menu_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.menu_font = wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.menu_font_bold = wx.Font(
        10, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_BOLD)

    panel_sizer.Add(self.menu_sizer, 0, wx.ALL, 15)
    panel_sizer.AddSpacer(10)
    self.settings_sizer = wx.BoxSizer(wx.VERTICAL)

    self._CreateUSBMappingPanel()
    self._CreateLanguagePanel()
    self._CreatePasswordPanel()

    panel_sizer.Add(self.settings_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
    self.panel_sizer = panel_sizer

    self._CreateButtons()
    self.UpdateMappingStatus()

    # By default, we show map usb location setting.
    self.ShowUSBMappingSetting(None)

  def _CreateButtons(self):
    """Add the save, cancel and save buttons."""
    buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_cancel = wx.Button(
        self,label=self.atft_string.BUTTON_CANCEL, size=(130, 30),
        id=wx.ID_CANCEL)
    button_map = wx.Button(
        self, label=self.atft_string.BUTTON_MAP, size=(130, 30), id=wx.ID_ANY)
    button_unmap = wx.Button(
        self, label=self.atft_string.BUTTON_UNMAP, size=(130, 30),
        id=wx.ID_ANY)
    button_save = wx.Button(
        self, label=self.atft_string.BUTTON_SAVE, size=(130, 30), id=wx.ID_ANY)
    button_font = wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    button_map.SetFont(button_font)
    button_unmap.SetFont(button_font)
    button_cancel.SetFont(button_font)
    button_save.SetFont(button_font)

    buttons_sizer.Add(button_cancel)
    buttons_sizer.Add(button_map, 0, wx.LEFT, 10)
    buttons_sizer.Add(button_unmap, 0, wx.LEFT, 10)
    buttons_sizer.Add(button_save, 0, wx.LEFT, 10)

    self.button_cancel = button_cancel
    self.button_map = button_map
    self.button_unmap = button_unmap
    self.button_save = button_save
    self.buttons_sizer = buttons_sizer
    self.panel_sizer.AddSpacer(20)
    self.panel_sizer.Add(buttons_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT, 10)

    # Bind handlers
    self.button_map.Bind(wx.EVT_BUTTON, self.manual_map_usb_location_handler)
    self.button_unmap.Bind(wx.EVT_BUTTON, self.unmap_usb_location_handler)
    self.button_cancel.Bind(wx.EVT_BUTTON, self.OnExit)
    self.button_save.Bind(wx.EVT_BUTTON, self.OnSaveSetting)

  def _CreateUSBMappingPanel(self):
    """Create the panel for mapping USB location to UI slot."""
    menu_map_usb = wx.Button(
        self, label=self.atft_string.BUTTON_MAP_USB_LOCATION,
        style=wx.BORDER_NONE)
    menu_map_usb.Bind(wx.EVT_BUTTON, self.ShowUSBMappingSetting)
    menu_map_usb.SetFont(self.menu_font)
    self.menu_map_usb = menu_map_usb
    self.AddMenuItem(self.menu_map_usb)
    usb_mapping_panel = wx.Window(self, style=wx.BORDER_SUNKEN)
    self.settings_sizer.Add(usb_mapping_panel, 0, wx.EXPAND)
    usb_mapping_panel.SetBackgroundColour(COLOR_WHITE)
    usb_mapping_panel_sizer = wx.BoxSizer(wx.VERTICAL)
    usb_mapping_panel_sizer.SetMinSize((0, 480))
    usb_mapping_title = wx.StaticText(
        usb_mapping_panel, wx.ID_ANY, self.atft_string.TITLE_MAP_USB)
    usb_mapping_panel_sizer.AddSpacer(10)
    usb_mapping_panel_sizer.Add(usb_mapping_title, 0, wx.EXPAND | wx.ALL, 10)
    usb_mapping_panel_sizer.AddSpacer(10)
    usb_mapping_title_font = wx.Font(
        10, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    usb_mapping_title.SetFont(usb_mapping_title_font)
    self.dev_mapping_components = Atft.CreateTargetDeviceList(
        usb_mapping_panel, usb_mapping_panel_sizer, True)[0: TARGET_DEV_SIZE]
    i = 0
    for dev_component in self.dev_mapping_components:
      handler = lambda event, index=i : self.map_usb_to_slot_handler(
          event, index)
      # Bind the select handler
      Atft._BindEventRecursive(wx.EVT_LEFT_DOWN, dev_component.panel, handler)
      i += 1

    usb_mapping_panel.SetSizerAndFit(usb_mapping_panel_sizer)
    self.usb_mapping_panel = usb_mapping_panel
    self.settings.append(self.usb_mapping_panel)

  def _CreateLanguagePanel(self):
    """Create the panel for setting language."""
    menu_language = wx.Button(
        self, label=self.atft_string.BUTTON_LANGUAGE_PREFERENCE,
        style=wx.BORDER_NONE)
    menu_language.Bind(wx.EVT_BUTTON, self.ShowLanguageSetting)
    self.menu_language = menu_language
    self.AddMenuItem(self.menu_language)
    language_setting = wx.Window(self, size=(0, 480))
    language_setting.SetBackgroundColour(COLOR_WHITE)
    language_setting_sizer = wx.BoxSizer(wx.VERTICAL)
    self.settings_sizer.Add(language_setting)
    language_title = wx.StaticText(
        language_setting, wx.ID_ANY, self.atft_string.TITLE_SELECT_LANGUAGE)
    language_title_font = wx.Font(
        14, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    language_title.SetFont(language_title_font)
    language_setting_sizer.AddSpacer(10)
    language_setting_sizer.Add(language_title, 0, wx.EXPAND | wx.LEFT, 20)
    language_setting_sizer.AddSpacer(10)
    language_setting_list = wx.ComboBox(
        language_setting, wx.ID_ANY, style=wx.CB_READONLY | wx.CB_DROPDOWN,
        value=LANGUAGE_OPTIONS[self.language_index],
        choices=LANGUAGE_OPTIONS,
        size=(250, 30))
    language_setting_sizer.Add(language_setting_list, 0, wx.LEFT, 20)
    language_setting.SetSizerAndFit(language_setting_sizer)
    self.language_setting_list = language_setting_list
    self.language_setting = language_setting
    self.settings.append(self.language_setting)

  def _CreatePasswordPanel(self):
    menu_set_password = wx.Button(
        self, label=self.atft_string.BUTTON_SET_PASSWORD, style=wx.BORDER_NONE)
    menu_set_password.Bind(wx.EVT_BUTTON, self.ShowPasswordSetting)
    self.menu_set_password = menu_set_password
    self.AddMenuItem(self.menu_set_password)
    password_setting = wx.Window(self, size=(0, 480))
    password_setting.SetBackgroundColour(COLOR_WHITE)
    password_setting_sizer = wx.BoxSizer(wx.VERTICAL)
    password_middle_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.settings_sizer.Add(password_setting, 0, wx.EXPAND)
    original_password_title = wx.StaticText(
        password_setting, wx.ID_ANY, self.atft_string.DIALOG_ORIG_PASSWORD)
    original_password_title_sizer = wx.BoxSizer(wx.VERTICAL)
    original_password_title_sizer.SetMinSize(0, 30)
    original_password_title_sizer.Add(original_password_title)
    new_password_title = wx.StaticText(
        password_setting, wx.ID_ANY, self.atft_string.DIALOG_NEW_PASSWORD)
    new_password_title_sizer = wx.BoxSizer(wx.VERTICAL)
    new_password_title_sizer.SetMinSize(0, 30)
    new_password_title_sizer.Add(new_password_title)
    password_title_font = wx.Font(
        12, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    original_password_title.SetFont(password_title_font)
    new_password_title.SetFont(password_title_font)
    self.original_password_input = wx.TextCtrl(
        password_setting, wx.ID_ANY, '', size=(240, 30),
        style=wx.TE_PASSWORD)
    self.new_password_input = wx.TextCtrl(
        password_setting, wx.ID_ANY, '', size=(240, 30),
        style=wx.TE_PASSWORD)
    self.original_password_input.SetFont(password_title_font)
    self.new_password_input.SetFont(password_title_font)

    password_title_sizer = wx.BoxSizer(wx.VERTICAL)
    password_title_sizer.Add(original_password_title_sizer)
    password_title_sizer.AddSpacer(10)
    password_title_sizer.Add(new_password_title_sizer)

    password_input_sizer = wx.BoxSizer(wx.VERTICAL)
    password_input_sizer.Add(self.original_password_input)
    password_input_sizer.AddSpacer(10)
    password_input_sizer.Add(self.new_password_input)

    password_middle_sizer.AddSpacer(20)
    password_middle_sizer.Add(password_title_sizer)
    password_middle_sizer.AddSpacer(20)
    password_middle_sizer.Add(password_input_sizer)

    password_setting_sizer.AddSpacer(40)
    password_setting_sizer.Add(password_middle_sizer)

    password_setting.SetSizerAndFit(password_setting_sizer)
    self.password_setting = password_setting
    self.settings.append(self.password_setting)

  def AddMenuItem(self, menu_button):
    menu_button.SetFont(self.menu_font)
    self.menu_sizer.Add(menu_button)
    self.menu_sizer.AddSpacer(10)
    self.menu_items.append(menu_button)

  def UpdateMappingStatus(self):
    """Refresh the mapping status (mapped/not mapped) for each device slot.

    In order for the status to be aligned correctly, this function needs to be
    called each time the status text changes.
    """
    i = 0
    for dev_component in self.dev_mapping_components:
      if self.device_usb_locations[i]:
        dev_component.status.SetLabel(self.atft_string.STATUS_MAPPED)
      else:
        dev_component.status.SetLabel(self.atft_string.STATUS_NOT_MAPPED)
      dev_component.status.GetParent().Layout()
      dev_component.status_wrapper.Layout()
      i += 1

  def ShowUSBMappingSetting(self, event):
    """Show the sub panel for mapping USB location.

    Args:
      event: The triggering event.
    """
    self.button_save.Hide()
    self.button_map.Show()
    self.button_unmap.Show()
    self.buttons_sizer.Layout()
    self.current_setting = self.usb_mapping_panel
    self.current_menu = self.menu_map_usb
    self.ShowCurrentSetting()

  def ShowLanguageSetting(self, event):
    """Show the sub panel for language preference setting.

    Args:
      event: The triggering event.
    """
    self.button_save.Show()
    self.button_map.Hide()
    self.button_unmap.Hide()
    self.buttons_sizer.Layout()
    self.current_setting = self.language_setting
    self.current_menu = self.menu_language
    self.ShowCurrentSetting()

  def ShowPasswordSetting(self, event):
    self.button_save.Show()
    self.button_map.Hide()
    self.button_unmap.Hide()
    self.buttons_sizer.Layout()
    self.current_setting = self.password_setting
    self.current_menu = self.menu_set_password
    self.ShowCurrentSetting()

  def ShowCurrentSetting(self):
    """Switch the setting page to the current chosen page."""
    for setting in self.settings:
      setting.Hide()
    for menu_item in self.menu_items:
      menu_item.SetFont(self.menu_font)
    self.current_setting.Show()
    self.current_menu.SetFont(self.menu_font_bold)
    self.settings_sizer.Layout()
    self.panel_sizer.Layout()

  def OnSaveSetting(self, event):
    """The handler if user clicks save button."""
    if self.current_setting == self.language_setting:
      language_text = self.language_setting_list.GetValue().encode('utf-8')
      self.change_language_handler(language_text)
      self.EndModal(0)
      return
    elif self.current_setting == self.password_setting:
      old_password = self.original_password_input.GetValue()
      self.original_password_input.SetValue('')
      new_password = self.new_password_input.GetValue()
      if self.change_password_handler(old_password, new_password):
        self.new_password_input.SetValue('')
        self.EndModal(0)
      else:
        self.original_password_input.SetValue('')

  def OnExit(self, event):
    """Exit handler when user clicks cancel or press 'esc'.

    Args:
      event: The triggering event.
    """
    self.original_password_input.SetValue('')
    self.new_password_input.SetValue('')
    event.Skip()


class DevComponent(object):
  """The class to represent a target device UI component. """

  # The index for this component.
  index = -1
  # The main target device panel that displays the information.
  panel = None
  # The serial number
  serial_number = None
  # The serial number text field.
  serial_text = None
  # The status text field.
  status = None
  # The field wrapping the status text field. This should be used to change
  # the background color.
  status_background = None
  # The sizer to align status text field. Need to use
  # status_wrapper.Layout() in order to align status text correctly after
  # every status change.
  status_wrapper = None
  # The field wrapping the title text field. This should be used to change
  # background color if the device is selected.
  title_background = None
  # Whether this device slot is selected.
  selected = False
  # Whether this device slot is in use.
  active = False

  def __init__(self, index):
    self.index = index


class Atft(wx.Frame):
  """wxpython class to handle all GUI commands for the ATFA.

  Creates the GUI and provides various functions for interacting with an
  ATFA and an Android Things device.

  """
  CONFIG_FILE = 'config.json'

  ID_TOOL_PROVISION = 1
  ID_TOOL_CLEAR = 2

  # The mapping mode when no USB location has been mapped and there is only one
  # target device.
  SINGLE_DEVICE_MODE = 0

  # The mapping mode when at least one USB location has been mapped to a UI
  # slot.
  MULTIPLE_DEVICE_MODE = 1

  def __init__(self):
    # If this is set to True, no prerequisites would be checked against manual
    # operation, such as you can do key provisioning before fusing the vboot key.
    self.test_mode = False

    self.provision_steps = []

    # The default steps included in the auto provisioning process.
    self.DEFAULT_PROVISION_STEPS_PRODUCT = [
        'FuseVbootKey', 'FusePermAttr', 'LockAvb', 'ProvisionProduct']

    self.DEFAULT_PROVISION_STEPS_SOM = ['FuseVbootKey', 'ProvisionSom']

    # The available provision steps.
    self.AVAILABLE_PROVISION_STEPS = [
        'FuseVbootKey', 'FusePermAttr', 'LockAvb', 'ProvisionProduct',
        'UnlockAvb', 'ProvisionSom']

    self.configs = self.ParseConfigFile()

    self.SetLanguage()

    self.atft_string.TITLE += ' %s' % self.atft_version

    # The atft_manager instance to manage various operations.
    self.atft_manager = self.CreateAtftManager()

    # The target devices refresh timer object.
    self.refresh_timer = None

    # List of serial numbers for the devices in auto provisioning mode.
    self.auto_dev_serials = []

    # Store the last refreshed target list, we use this list to prevent
    # refreshing the same list.
    self.last_target_list = []

    # List of serial numbers of the target devices that are not mapped and
    # ignored.
    self.ignored_unmapped_device_serials = sets.Set()

    # Indicate whether in auto provisioning mode.
    self.auto_prov = False

    # Indicate whether refresh is paused. If we could acquire this lock, this
    # means that the refresh is paused. We would pause the refresh during each
    # fastboot command since on Windows, a fastboot device would disappear from
    # fastboot devices while a fastboot command is issued. We use semaphore to
    # allow layered pause and resume, unless the last layer is resumed, the
    # refresh is in pause state.
    self.refresh_pause_lock = threading.Semaphore(0)

    # 'fastboot devices' can only run sequentially, so we use this lock to check
    # if there's already a 'fastboot devices' command running. If so, we ignore
    # the second request.
    self.listing_device_lock = threading.Lock()

    # To prevent low key alert to show by each provisioning.
    # We only show it once per auto provision.
    self.first_key_alert_shown = False
    self.second_key_alert_shown = False

    # Lock to indicate whether it is currently checking mapping mode to prevent
    # two checks to happen at the same time.
    self.checking_mapping_mode_lock = threading.Lock()

    # Lock to make sure only one device is doing auto provisioning at one time.
    self.auto_prov_lock = threading.Lock()

    # Lock for showing alert box
    self.alert_lock = threading.Lock()

    # Supervisor Mode
    self.sup_mode = True

    # Whether start screen is shown
    self.start_screen_shown = False

    self.InitializeUI()

    if self.configs == None:
      self.ShowAlert(self.atft_string.ALERT_FAIL_TO_PARSE_CONFIG)
      sys.exit(0)

    self.CreateShortCuts()

    self.log = self.CreateAtftLog()

    self.audit = self.CreateAtftAudit()

    self.key_handler = self.CreateAtftKeyHandler()
    self.key_handler.StartProcessKey()

    if not self.log.log_dir_file:
      self._SendAlertEvent(self.atft_string.ALERT_FAIL_TO_CREATE_LOG)

    if (not self.log.CheckInstanceRunning() and
        not self.ShowWarning(self.atft_string.ALERT_INSTANCE_RUNNING)):
        sys.exit(0)

    self.log.Info('Program', 'Program start')

    # Leave supervisor mode
    self._OnToggleSupMode(None)

    self.ShowStartScreen()
    self.StartRefreshingDevices()

  @staticmethod
  def _BindEventRecursive(event, widget, handler):
    """Bind a event to all the children under a widget recursively.

    Because some event such as mouse down would not propagate to parent window,
    we need to bind the event handler to all the children of the target widget.

    Args:
      event: The event to bind.
      widget: The current widget to bind.
      handler: The event handler.
    """
    widget.Bind(event, handler)
    for child in widget.GetChildren():
      Atft._BindEventRecursive(event, child, handler)

  @staticmethod
  def CreateTargetDeviceList(parent, parent_sizer, map_usb=False):
    """Create the grid style panel to display target device information.

    Args:
      parent: The parent window.
      parent_sizer: The parent sizer.
      map_usb: Whether the target list is for USB location mapping.
    Returns:
      A list of DevComponent object that contains necessary information and UI
        element about each target device. The last one is a special component
        object for a single unmapped device in SINGLE_DEVICE_MODE.
    """
    # target device output components
    target_devs_components = []

    # The scale of the display size. We need a smaller version of the target
    # device list for the settings page, so we can use this scale factor to
    # scale the panel's size.
    scale = 1
    if map_usb:
      scale = 0.9

    single_panel_width = 270
    serial_number_alignement = wx.ALIGN_LEFT
    serial_number_width = 180
    serial_number_height = 20
    serial_font_size = 9
    status_font_size = 18
    if map_usb:
      status_font_size = 20

    component_count = TARGET_DEV_SIZE
    if not map_usb:
      # If this is not for mapping usb slots. We create an additional slot
      # for the single unmapped device.
      component_count += 1

    # Device Output Window
    devices_list = wx.GridSizer(2, 3, 40 * scale, 0)
    parent_sizer.Add(devices_list, flag=wx.BOTTOM, border=20)

    for i in range(0, component_count):
      if i == TARGET_DEV_SIZE:
        # This is the special panel for unmapped single device mode.
        # We make the panel larger
        scale = 2
        # We align the serial number in the center
        serial_number_alignement = wx.ALIGN_CENTRE_HORIZONTAL
        # We make the serial number wider because no index.
        serial_number_width = single_panel_width
        serial_number_height = 24
        # We make the serial number larger
        serial_font_size = 14
        # We make the status display larger
        status_font_size = 32

      dev_component = DevComponent(i)
      # Create each target device panel.
      target_devs_output_panel = wx.Window(
          parent, style=wx.BORDER_RAISED)
      target_devs_output_panel_sizer = wx.BoxSizer(wx.VERTICAL)
      dev_component.panel = target_devs_output_panel

      # Create the title panel.
      target_devs_output_title = wx.Window(
          target_devs_output_panel, style=wx.BORDER_NONE,
          size=(single_panel_width * scale, 50 * scale))
      target_devs_output_title.SetBackgroundColour(COLOR_WHITE)
      # Don't accept user input, otherwise user input would change the style.
      target_devs_output_title_sizer = wx.BoxSizer(wx.HORIZONTAL)
      target_devs_output_title.SetSizer(target_devs_output_title_sizer)
      dev_component.title_background = target_devs_output_title

      # The number in the title bar.
      target_devs_output_number = wx.StaticText(
          target_devs_output_title, wx.ID_ANY, str(i + 1).zfill(2))
      dev_component.index_text = target_devs_output_number
      number_font = wx.Font(
          18, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_BOLD)
      target_devs_output_number.SetForegroundColour(COLOR_DARK_GREY)
      target_devs_output_number.SetFont(number_font)
      if i == TARGET_DEV_SIZE:
        # We do not show index for the special panel
        target_devs_output_number.Show(False)
      else:
        target_devs_output_title_sizer.Add(
            target_devs_output_number, 0, wx.ALL, 10)

      # The serial number in the title bar.
      target_devs_output_serial = wx.StaticText(
          target_devs_output_title,
          id=wx.ID_ANY,
          style=(wx.ST_NO_AUTORESIZE | serial_number_alignement |
                 wx.ST_ELLIPSIZE_END),
          name='')
      target_devs_output_serial.SetForegroundColour(COLOR_BLACK)
      target_devs_output_serial.SetMinSize(
          (serial_number_width * scale, serial_number_height))

      serial_font = wx.Font(
          serial_font_size, wx.FONTFAMILY_MODERN, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL)
      target_devs_output_serial.SetFont(serial_font)
      dev_component.serial_text = target_devs_output_serial
      target_devs_output_title_sizer.Add(
          target_devs_output_serial, 0, wx.TOP, 18)

      # The selected icon in the title bar
      selected_image = wx.Image('selected.png', type=wx.BITMAP_TYPE_PNG)
      selected_bitmap = wx.Bitmap(selected_image)
      selected_icon = wx.StaticBitmap(
          target_devs_output_title, bitmap=selected_bitmap)
      target_devs_output_title_sizer.Add(selected_icon, 0, wx.TOP, 12 * scale)

      # The device status panel.
      target_devs_output_status = wx.Window(
          target_devs_output_panel, style=wx.BORDER_NONE,
          size=(single_panel_width * scale, 110 * scale))
      target_devs_output_status.SetBackgroundColour(COLOR_GREY)
      target_devs_output_status_sizer = wx.BoxSizer(wx.HORIZONTAL)
      target_devs_output_status.SetSizer(target_devs_output_status_sizer)
      dev_component.status_background = target_devs_output_status

      # The device status string.
      device_status_string = ''
      target_devs_output_status_info = wx.StaticText(
          target_devs_output_status, wx.ID_ANY, device_status_string)
      status_font = wx.Font(
          status_font_size, wx.FONTFAMILY_SWISS, wx.NORMAL,
          wx.FONTWEIGHT_NORMAL)
      target_devs_output_status_info.SetForegroundColour(COLOR_BLACK)
      target_devs_output_status_info.SetFont(status_font)
      dev_component.status = target_devs_output_status_info

      # We need two sizers, one for vertical alignment and one for horizontal.
      target_devs_output_status_ver_sizer = wx.BoxSizer(wx.VERTICAL)
      target_devs_output_status_ver_sizer.Add(
          target_devs_output_status_info, 1, wx.ALIGN_CENTER)
      target_devs_output_status_sizer.Add(
          target_devs_output_status_ver_sizer, 1, wx.ALIGN_CENTER)
      dev_component.status_wrapper = target_devs_output_status_ver_sizer

      target_devs_output_panel_sizer.Add(target_devs_output_title, 0, wx.EXPAND)
      target_devs_output_panel_sizer.Add(
          target_devs_output_status, 0, wx.EXPAND)
      target_devs_output_panel.SetSizer(target_devs_output_panel_sizer)

      # This sizer is only to add 15px right border
      target_devs_output_panel_sizer_wrap = wx.BoxSizer(wx.HORIZONTAL)
      target_devs_output_panel_sizer_wrap.Add(target_devs_output_panel)
      target_devs_output_panel_sizer_wrap.AddSpacer(15 * scale)
      if i != TARGET_DEV_SIZE:
        # We don't add the special panel as a child of devices_list,
        # instead, it should be same level as devices_list.
        devices_list.Add(
            target_devs_output_panel_sizer_wrap, 0, wx.LEFT | wx.RIGHT, 10)
      target_devs_components.append(dev_component)

    return target_devs_components

  @staticmethod
  def VerifyPassword(password, password_hash):
    """Use pbkdf2_sha256 to verify password against the stored hash.

    Args:
      password: The password to be verified.
      password_hash: The hash for the password.
    Returns:
      True: if password match.
      False: if password does not match.
    """
    try:
      return pbkdf2_sha256.verify(password, password_hash)
    except:
      return False

  @staticmethod
  def GeneratePasswordHash(password):
    """Use pbkdf2_sha256 to generate password hash.

    Args:
      password: The password to be verified.
    Returns:
      password hash
    """
    return pbkdf2_sha256.hash(password)

  def CreateAtftManager(self):
    """Create an AtftManager object.

    This function exists for test mocking.
    """
    return AtftManager(FastbootDevice, SerialMapper, self.configs)

  def CreateAtftLog(self):
    """Create an AtftLog object.

    This function exists for test mocking.
    """
    return AtftLog(self.log_dir, self.log_size, self.log_file_number)

  def CreateAtftAudit(self):
    """Create an AtftAudit object.

    This function exists for test mocking.
    """
    return AtftAudit(self.audit_dir,
                     self.audit_interval,
                     self._GetFileFromATFA,
                     self._HandleException,
                     self.atft_manager.GetATFASerial)

  def CreateAtftKeyHandler(self):
    return AtftKeyHandler(self.key_dir,
                   self.log_dir,
                   self.key_file_extension,
                   self._ProcessKey,
                   self._HandleException,
                   self.atft_manager.GetATFASerial)

  def ParseConfigFile(self):
    """Parse the configuration file and read in the necessary configurations.

    Returns:
      The parsed configuration map.
    """
    # Give default values
    self.atft_version = ''
    self.compatible_atfa_version = '0'
    self.device_refresh_interval = 1.0
    self.default_key_threshold_1 = None
    self.default_key_threshold_2 = None
    self.log_dir = None
    self.log_size = 0
    self.log_file_number = 0
    self.audit_dir = None
    # By default we download audit file per 10 keys provisioned.
    self.audit_interval = 10
    self.language = 'eng'
    self.reboot_timeout = 0
    self.atfa_reboot_timeout = 0
    self.product_attribute_file_extension = '*.atpa'
    self.key_file_extension = '*.atfa'
    self.update_file_extension = '*.upd'
    self.key_dir = None
    self.mapping_mode = self.SINGLE_DEVICE_MODE

    # The list to store the device location for each target device slot. If the
    # slot is not mapped, it will be None.
    self.device_usb_locations = []
    for i in range(TARGET_DEV_SIZE):
      self.device_usb_locations.append(None)

    config_file_path = os.path.join(self._GetCurrentPath(), self.CONFIG_FILE)
    if not os.path.exists(config_file_path):
      return None

    with open(config_file_path, 'r') as config_file:
      configs = json.loads(config_file.read())

    if not configs:
      return None

    try:
      self.atft_version = str(configs['ATFT_VERSION'])
      if self.atft_version != "v%.1f" % VERSION:
        # Config file version mismatch.
        if VERSION == 3.0 and self.atft_version == 'v2.0':
          # 3.0 is compatible with v2.0 config file. Update the config version.
          self.atft_version = 'v3.0'
        else:
          return None

      self.compatible_atfa_version = str(configs['COMPATIBLE_ATFA_VERSION'])
      self.device_refresh_interval = float(configs['DEVICE_REFRESH_INTERVAL'])
      if 'DEFAULT_KEY_THRESHOLD_1' in configs:
        self.default_key_threshold_1 = int(configs['DEFAULT_KEY_THRESHOLD_1'])
      if 'DEFAULT_KEY_THRESHOLD_2' in configs:
        self.default_key_threshold_2 = int(configs['DEFAULT_KEY_THRESHOLD_2'])
      self.log_dir = str(configs['LOG_DIR'])
      self.log_size = int(configs['LOG_SIZE'])
      self.log_file_number = int(configs['LOG_FILE_NUMBER'])
      self.audit_dir = str(configs['AUDIT_DIR'])
      self.language = str(configs['LANGUAGE'])
      self.reboot_timeout = float(configs['REBOOT_TIMEOUT'])
      self.atfa_reboot_timeout = float(configs['ATFA_REBOOT_TIMEOUT'])
      self.product_attribute_file_extension = str(
          configs['PRODUCT_ATTRIBUTE_FILE_EXTENSION'])
      self.key_file_extension = str(configs['KEY_FILE_EXTENSION'])
      self.update_file_extension = str(configs['UPDATE_FILE_EXTENSION'])
      self.password_hash = str(configs['PASSWORD_HASH'])
      if 'DEVICE_USB_LOCATIONS' in configs:
        self.device_usb_locations = configs['DEVICE_USB_LOCATIONS']
      if 'TEST_MODE' in configs:
        self.test_mode = configs['TEST_MODE']
      if 'PROVISION_STEPS' in configs:
        self.provision_steps = configs['PROVISION_STEPS']
      if 'AUDIT_INTERVAL' in configs:
        self.audit_interval = int(configs['AUDIT_INTERVAL'])
      if 'KEY_DIR' in configs:
        self.key_dir = configs['KEY_DIR']

      device_usb_locations_initialized = False
      for i in range(TARGET_DEV_SIZE):
        if self.device_usb_locations[i]:
          device_usb_locations_initialized = True
      if not device_usb_locations_initialized:
        # If the devic usb location is not initialized, the mapping mode
        # should be single_device
        self.mapping_mode = self.SINGLE_DEVICE_MODE
      else:
        self.mapping_mode = self.MULTIPLE_DEVICE_MODE

    except (KeyError, ValueError):
      return None

    return configs

  def _CheckProvisionSteps(self):
    """Check whether the "PROVISION_STEPS" config is valid.

    Check the format of "PROVISION_STEPS" config. If test_mode is not set to
    True, verify that the customized provision steps meet the necessary security
    requirement.
    """
    if self.atft_manager.product_info:
      default_provision_steps = self.DEFAULT_PROVISION_STEPS_PRODUCT
    else:
      default_provision_steps = self.DEFAULT_PROVISION_STEPS_SOM

    if not self.provision_steps:
      self.provision_steps = default_provision_steps
      return
    try:
      provision_steps_verified = (
          self._VerifyProvisionSteps(self.provision_steps))
    except ValueError:
      self.provision_steps = default_provision_steps
      self._SendAlertEvent(self.atft_string.ALERT_PROVISION_STEPS_SYNTAX_ERROR)
      return

    if self.test_mode:
      return
    if not provision_steps_verified:
      self.provision_steps = default_provision_steps
      self._SendAlertEvent(self.atft_string.ALERT_PROVISION_STEPS_SECURITY_REQ)


  def _VerifyProvisionSteps(self, provision_steps):
    """Verify if the customized provision steps meet security requirements.

    Args:
      provision_steps: The customized provision steps to verify.
    Raises:
      ValueError: If the syntax for provision_steps is not correct.
    """
    if not isinstance(provision_steps, list):
      raise ValueError()
    provision_state = ProvisionState()
    for operation in provision_steps:
      if operation not in self.AVAILABLE_PROVISION_STEPS:
        raise ValueError()
      if operation == 'FuseVbootKey':
        provision_state.bootloader_locked = True
        continue
      elif operation == 'FusePermAttr':
        if (not provision_state.bootloader_locked or
            provision_state.avb_perm_attr_set):
          return False
        else:
          provision_state.avb_perm_attr_set = True
          continue
      elif operation == 'LockAvb':
        if (not provision_state.bootloader_locked or
            not provision_state.avb_perm_attr_set):
          return False
        else:
          provision_state.avb_locked = True
        continue
      elif operation == 'UnlockAvb':
        provision_state.avb_locked = False
        continue
      elif operation == 'ProvisionProduct':
        if (not provision_state.bootloader_locked or
            not provision_state.avb_perm_attr_set or
            provision_state.product_provisioned):
          return False
        else:
          provision_state.product_provisioned = True
      elif operation == 'ProvisionSom':
        if (not provision_state.bootloader_locked or
            provision_state.som_provisioned):
          return False
        else:
          provision_state.som_provisioned = True
    return True

  def _StoreConfigToFile(self):
    """Store the configuration to the configuration file.

    By storing the configuration back, the program would remember the
    configuration if it's opened again.
    """
    self.configs['DEVICE_USB_LOCATIONS'] = self.device_usb_locations
    self.configs['PASSWORD_HASH'] = self.password_hash
    self.configs['LANGUAGE'] = self.language
    if self.atft_version:
      self.configs['ATFT_VERSION'] = self.atft_version
    config_file_path = os.path.join(self._GetCurrentPath(), self.CONFIG_FILE)
    with open(config_file_path, 'w') as config_file:
      config_file.write(json.dumps(self.configs, sort_keys=True, indent=4))

  def _GetCurrentPath(self):
    """Get the current directory.

    Returns:
      The current directory.
    """
    if getattr(sys, 'frozen', False):
      # we are running in a bundle
      path = sys._MEIPASS  # pylint: disable=protected-access
    else:
      # we are running in a normal Python environment
      path = os.path.dirname(os.path.abspath(__file__))
    return path

  def GetLanguageIndex(self):
    """Translate language setting to an index.

    Returns:
      index: A index representing the language.
    """
    for index in range(len(LANGUAGE_CONFIGS)):
      if self.language == LANGUAGE_CONFIGS[index]:
        return index
    return -1

  def SetLanguage(self):
    """Set the string constants according to the language setting.
    """
    self.atft_string = AtftString(self.GetLanguageIndex())

  def InitializeUI(self):
    """Initialize the application UI."""
    # The frame style is default style without border.
    style = wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)
    wx.Frame.__init__(self, None, style=style)

    # Menu:
    # Application   -> App Settings
    #               -> Choose Product
    #               -> Key Warning Threshold
    #               -> Clear Command Output
    #               -> Show Statusbar
    #               -> Quit

    # Key Provision -> Fuse Bootloader Vboot Key
    #               -> Fuse Permanent Attributes
    #               -> Lock Android Verified Boot
    #               -> Provision Key

    # ATFA Device   -> ATFA Status
    #               -> Registration
    #               -> Update
    #               -> Reboot
    #               -> Shutdown

    # Audit         -> Download Audit File

    # Key Management-> Store Key Bundle
    #               -> Purge Key Bundle

    # Add Menu items to Menubar
    self.menubar = wx.MenuBar()
    self._CreateAppMenu()
    self._CreateProvisionMenu()
    self._CreateATFAMenu()
    self._CreateAuditMenu()
    self._CreateKeyMenu()
    self.SetMenuBar(self.menubar)

    # The main panel
    self.panel = wx.Window(self)
    self.main_box = wx.BoxSizer(wx.VERTICAL)
    self._CreateHeaderPanel()
    self._CreateTargetDevsPanel()
    self._CreateCommandOutputPanel()
    self._CreateStatusBar()

    self.SetTitle(self.atft_string.TITLE)
    self.panel.SetSizerAndFit(self.main_box)
    self.Show(True)

    # App Settings Dialog
    self.app_settings_dialog = AppSettingsDialog(
        self.atft_string,
        self.UnmapUSBLocationToSlot,
        self.ManualMapUSBLocationToSlot,
        self.MapUSBToSlotHandler,
        self.ChangeLanguage,
        self.ChangePassword,
        self.GetLanguageIndex(),
        self.device_usb_locations)
    self.app_settings_dialog.CreateDialog(
        self, wx.ID_ANY, self.atft_string.MENU_APP_SETTINGS)

    # Change Key Threshold Dialog
    self.change_threshold_dialog = ChangeThresholdDialog(
        self.atft_string,
        self.default_key_threshold_1,
        self.default_key_threshold_2)
    self.change_threshold_dialog.CreateDialog(
        self,
        wx.ID_ANY,
        self.atft_string.DIALOG_CHANGE_THRESHOLD_TITLE)

    # Low Key Alert Dialog
    self.low_key_dialog = wx.MessageDialog(
        self,
        self.atft_string.DIALOG_LOW_KEY_TEXT,
        self.atft_string.DIALOG_LOW_KEY_TITLE,
        style=wx.OK | wx.ICON_EXCLAMATION | wx.CENTRE)

    # General Alert Dialog
    self.alert_dialog = wx.MessageDialog(
        self,
        self.atft_string.DIALOG_ALERT_TEXT,
        self.atft_string.DIALOG_ALERT_TITLE,
        style=wx.OK | wx.ICON_EXCLAMATION | wx.CENTRE)

    # Password Dialog
    self.password_dialog = wx.PasswordEntryDialog(
        self,
        self.atft_string.DIALOG_INPUT_PASSWORD,
        self.atft_string.DIALOG_PASSWORD)

    self.change_mapping_mode_dialog = wx.MessageDialog(
        self,
        self.atft_string.ALERT_CHANGE_MAPPING_MODE,
        self.atft_string.TITLE_MULTIPLE_DEVICE_DETECTED,
        style=wx.YES_NO | wx.ICON_EXCLAMATION)
    self.change_mapping_mode_dialog.SetYesNoLabels(
        self.atft_string.BUTTON_MAP_USB_LOCATION,
        self.atft_string.BUTTON_DEVICE_UNPLUGGED)

    self._CreateBindEvents()

    self.main_box.Layout()
    self.panel.SetSizerAndFit(self.main_box)
    self.Layout()
    self.SetSize(self.GetWindowSize())

    # Display correct target device active/non-active status.
    self._PrintTargetDevices()

    # Change the UI according to the mapping mode.
    # (Single device mode or multiple device mode)
    self._ChangeMappingMode()

  def CreateShortCuts(self):
    """Create hot key bindings. """
    accel_entries = []
    event_id = wx.NewId()
    accel_entries.append(
        wx.AcceleratorEntry(wx.ACCEL_ALT, ord('S'), event_id))
    self.Bind(wx.EVT_MENU, self._OnToggleSupMode, id=event_id)
    event_id = wx.NewId()
    accel_entries.append(
        wx.AcceleratorEntry(wx.ACCEL_ALT, ord('T'), event_id))
    self.Bind(wx.EVT_MENU, self._OnFocusTargetDevList, id=event_id)
    event_id = wx.NewId()
    accel_entries.append(
        wx.AcceleratorEntry(wx.ACCEL_ALT, ord('O'), event_id))
    self.Bind(wx.EVT_MENU, self.OnChangeAutoProv, id=event_id)
    event_id = wx.NewId()
    accel_entries.append(
        wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_TAB, event_id))
    self.Bind(wx.EVT_MENU, self._OnPressTab, id=event_id)
    event_id = wx.NewId()
    accel_entries.append(
        wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_RETURN, event_id))
    self.Bind(wx.EVT_MENU, self._OnPressEnter, id=event_id)
    self.SetAcceleratorTable(wx.AcceleratorTable(accel_entries))

  def _OnFocusTargetDevList(self, event):
    """Focus on the first target device slot.

    Args:
      event: The triggering event.
    """
    if not self.sup_mode:
      return
    self.target_devs_components[0].panel.SetFocus()

  def _OnPressTab(self, event):
    """Handler when 'tab' is pressed. Change focus on target device slot.

    Args:
      event: The triggering event.
    """
    if not self.sup_mode:
      return

    window = wx.Window.FindFocus()

    # If the current focus is on target d
    for i in range(0, TARGET_DEV_SIZE):
      if window == self.target_devs_components[i].panel:
        j = (i + 1) % TARGET_DEV_SIZE
        self.target_devs_components[j].panel.SetFocus()
        return

  def _OnPressEnter(self, event):
    """Handler when 'enter' is pressed.

    If the current focus is on a target device slot, click that slot.

    Args:
      event: The triggering event.
    """
    window = wx.Window.FindFocus()
    for i in range(0, TARGET_DEV_SIZE):
      if window == self.target_devs_components[i].panel:
        window.QueueEvent(wx.MouseEvent(wx.wxEVT_LEFT_DOWN));
        return

  def _CreateAppMenu(self):
    """Create the app menu items."""
    app_menu = wx.Menu()
    self.menubar.Append(app_menu, self.atft_string.MENU_APPLICATION)
    # App Menu Options
    menu_app_settings = app_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_APP_SETTINGS)
    self.Bind(wx.EVT_MENU, self.ChangeSettings, menu_app_settings)
    self.menu_app_settings = menu_app_settings

    menu_choose_product = app_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_CHOOSE_PRODUCT)
    self.Bind(wx.EVT_MENU, self.ChooseProduct, menu_choose_product)

    menu_key_threshold = app_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_KEY_THRESHOLD)
    self.Bind(wx.EVT_MENU, self.OnChangeKeyThreshold, menu_key_threshold)

    menu_clear_command = app_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_CLEAR_COMMAND)

    self.Bind(wx.EVT_MENU, self.OnClearCommandWindow, menu_clear_command)

    self.menu_show_status_bar = app_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_SHOW_STATUS_BAR, kind=wx.ITEM_CHECK)
    app_menu.Check(self.menu_show_status_bar.GetId(), True)
    self.Bind(wx.EVT_MENU, self.ToggleStatusBar, self.menu_show_status_bar)

    menu_quit = app_menu.Append(wx.ID_EXIT, self.atft_string.MENU_QUIT)
    self.Bind(wx.EVT_MENU, self.OnQuit, menu_quit)
    self.app_menu = app_menu

  def _CreateProvisionMenu(self):
    """Create the provision menu items."""
    provision_menu = wx.Menu()
    self.menubar.Append(provision_menu, self.atft_string.MENU_KEY_PROVISIONING)
    # Key Provision Menu Options
    menu_manual_fuse_vboot = provision_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_MANUAL_FUSE_VBOOT)
    self.Bind(wx.EVT_MENU, self.OnFuseVbootKey, menu_manual_fuse_vboot)

    menu_manual_fuse_attr = provision_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_MANUAL_FUSE_ATTR)
    self.Bind(wx.EVT_MENU, self.OnFusePermAttr, menu_manual_fuse_attr)

    menu_manual_lock_avb = provision_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_MANUAL_LOCK_AVB)
    self.Bind(wx.EVT_MENU, self.OnLockAvb, menu_manual_lock_avb)

    menu_manual_prov = provision_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_MANUAL_PROV)
    self.Bind(wx.EVT_MENU, self.OnManualProvision, menu_manual_prov)

    self.provision_menu = provision_menu

  def _CreateATFAMenu(self):
    """Create the ATFA menu items."""
    atfa_menu = wx.Menu()
    self.menubar.Append(atfa_menu, self.atft_string.MENU_ATFA_DEVICE)
    # ATFA Menu Options
    menu_atfa_status = atfa_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_ATFA_STATUS)
    self.Bind(wx.EVT_MENU, self.OnCheckATFAStatus, menu_atfa_status)

    menu_reg_file = atfa_menu.Append(wx.ID_ANY, self.atft_string.MENU_REG_FILE)
    self.Bind(wx.EVT_MENU, self.OnGetRegFile, menu_reg_file)

    menu_update = atfa_menu.Append(wx.ID_ANY, self.atft_string.MENU_ATFA_UPDATE)
    self.Bind(wx.EVT_MENU, self.OnUpdateAtfa, menu_update)

    menu_reboot = atfa_menu.Append(wx.ID_ANY, self.atft_string.MENU_REBOOT)
    self.Bind(wx.EVT_MENU, self.OnReboot, menu_reboot)

    menu_shutdown = atfa_menu.Append(wx.ID_ANY, self.atft_string.MENU_SHUTDOWN)
    self.Bind(wx.EVT_MENU, self.OnShutdown, menu_shutdown)

    self.atfa_menu = atfa_menu

  def _CreateAuditMenu(self):
    """Create the audit menu items."""
    audit_menu = wx.Menu()
    self.menubar.Append(audit_menu, self.atft_string.MENU_AUDIT)
    # Audit Menu Options
    menu_download_audit = audit_menu.Append(
        wx.ID_ANY, self.atft_string.MENU_DOWNLOAD_AUDIT)
    self.Bind(wx.EVT_MENU, self.OnGetAuditFile, menu_download_audit)

    self.audit_menu = audit_menu

  def _CreateKeyMenu(self):
    """Create the key menu items."""
    key_menu = wx.Menu()
    self.menubar.Append(key_menu, self.atft_string.MENU_KEY_MANAGEMENT)
    # Key Management Menu Options
    menu_storekey = key_menu.Append(wx.ID_ANY, self.atft_string.MENU_STOREKEY)
    self.Bind(wx.EVT_MENU, self.OnStoreKey, menu_storekey)

    menu_purgekey = key_menu.Append(wx.ID_ANY, self.atft_string.MENU_PURGE)
    self.Bind(wx.EVT_MENU, self.OnPurgeKey, menu_purgekey)

    self.key_menu = key_menu

  def _CreateHeaderPanel(self):
    """Create the header panel.

    The header panel contains the supervisor button, product information and
    ATFA device information.
    """
    header_panel = wx.Window(self.panel)
    header_panel.SetForegroundColour(COLOR_BLACK)
    header_panel_sizer = wx.BoxSizer(wx.HORIZONTAL)
    header_panel_left_sizer = wx.BoxSizer(wx.VERTICAL)
    header_panel_right_sizer = wx.BoxSizer(wx.VERTICAL)
    header_panel_sizer.Add(header_panel_left_sizer, 0)
    header_panel_sizer.Add(
        header_panel_right_sizer, 1, wx.RIGHT, 10)

    self.button_supervisor = wx.Button(
        header_panel, wx.ID_ANY, style=wx.BORDER_NONE, label='...',
        name='Toggle Supervisor Mode', size=(40, 40))
    button_supervisor_font = wx.Font(
        20, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.button_supervisor.SetFont(button_supervisor_font)
    self.button_supervisor.SetForegroundColour(COLOR_BLACK)
    header_panel_right_sizer.Add(self.button_supervisor, 0, wx.ALIGN_RIGHT)
    self.button_supervisor_toggle = wx.Button(
        header_panel,
        wx.ID_ANY,
        style=wx.BU_LEFT,
        label=self.atft_string.BUTTON_LEAVE_SUP_MODE,
        name=self.atft_string.BUTTON_LEAVE_SUP_MODE,
        size=(200, 30))
    button_supervisor_font = wx.Font(
        10, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.button_supervisor_toggle.SetFont(button_supervisor_font)
    self.button_supervisor_toggle.SetForegroundColour(COLOR_BLACK)
    self.button_supervisor_toggle.Hide()
    self.header_panel_right_sizer = header_panel_right_sizer

    self.Bind(wx.EVT_BUTTON, self._OnToggleSupButton, self.button_supervisor)
    self.Bind(
        wx.EVT_BUTTON, self._OnToggleSupMode, self.button_supervisor_toggle)

    # Product Name Display
    self.product_name_title = wx.StaticText(header_panel, wx.ID_ANY, '')
    self.product_name_display = wx.StaticText(
        header_panel, wx.ID_ANY, self.atft_string.TITLE_PRODUCT_NAME_NOTCHOSEN)
    product_name_font = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.product_name_title.SetFont(product_name_font)
    self.product_name_display.SetFont(product_name_font)
    self.product_name_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.product_name_sizer.Add(self.product_name_title)
    self.product_name_sizer.Add(self.product_name_display, 0, wx.LEFT, 2)
    header_panel_left_sizer.Add(self.product_name_sizer, 0, wx.ALL, 5)

    self.main_box.Add(header_panel, 0, wx.EXPAND)

    # Device Output Title
    atfa_dev_title = wx.StaticText(
        header_panel,
        wx.ID_ANY,
        self.atft_string.TITLE_ATFA_DEV)
    self.atfa_dev_output = wx.StaticText(header_panel, wx.ID_ANY, '')
    atfa_dev_title_sizer = wx.BoxSizer(wx.HORIZONTAL)
    atfa_dev_title_sizer.Add(atfa_dev_title)
    atfa_dev_title_sizer.Add(self.atfa_dev_output)
    header_panel_left_sizer.Add(atfa_dev_title_sizer, 0, wx.LEFT | wx.BOTTOM, 5)

    header_panel.SetSizerAndFit(header_panel_sizer)

  def _CreateTargetDevsPanel(self):
    """Create the target device panel to list target devices."""
    # Device Output Title
    target_devs_panel = wx.Window(self.panel, style=wx.BORDER_NONE)
    target_devs_panel_sizer = wx.BoxSizer(wx.VERTICAL)

    self.target_devs_title = wx.StaticText(
        target_devs_panel, wx.ID_ANY, self.atft_string.TITLE_TARGET_DEV)
    target_dev_font = wx.Font(
        16, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.target_devs_title.SetFont(target_dev_font)
    self.target_devs_title_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.target_devs_title_sizer.Add(self.target_devs_title, 0, wx.LEFT, 10)
    auto_prov_button_font = wx.Font(
        12, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.autoprov_button = wx.ToggleButton(
        target_devs_panel, id=wx.ID_ANY,
        label=self.atft_string.BUTTON_START_OPERATION)
    self.autoprov_button.SetFont(auto_prov_button_font)
    self.Bind(wx.EVT_TOGGLEBUTTON, self.OnToggleAutoProv, self.autoprov_button)
    # The vertical sizer to occupy all the right side space so that the button
    # could align right.
    right_sizer = wx.BoxSizer(wx.VERTICAL)
    self.target_devs_title_sizer.Add(right_sizer, 1)
    right_sizer.Add(
        self.autoprov_button, 0, wx.ALIGN_RIGHT | wx.RIGHT, 25)
    target_devs_panel_sizer.Add(
        self.target_devs_title_sizer, 1, wx.TOP | wx.BOTTOM | wx.EXPAND, 10)
    target_devs_list_sizer = wx.BoxSizer(wx.HORIZONTAL)
    components = Atft.CreateTargetDeviceList(
        target_devs_panel, target_devs_list_sizer)
    self.target_devs_components = components[0: TARGET_DEV_SIZE]
    # The last target device components is a special component for single
    # unmapped device in SINGLE_DEVICE_MODE.
    self.unmapped_target_dev_component = components[TARGET_DEV_SIZE]
    # The active state for the unmapped target device is also True
    self.unmapped_target_dev_component.active = True

    target_devs_panel_sizer.Add(
        self.unmapped_target_dev_component.panel, 0, wx.ALIGN_CENTER)
    target_devs_panel_sizer.Add(target_devs_list_sizer, 0)
    self.unmapped_target_dev_component.panel.Show(False)

    target_devs_panel.SetSizerAndFit(target_devs_panel_sizer)
    target_devs_panel.SetBackgroundColour(COLOR_WHITE)

    self.main_box.Add(target_devs_panel, 0, wx.EXPAND)

  def _CreateCommandOutputPanel(self):
    """Create command output panel to show command outputs."""
    # Command Output Title
    self.cmd_output_wrap = wx.Window(self.panel)
    cmd_output_wrap_sizer = wx.BoxSizer(wx.VERTICAL)

    static_line = wx.StaticLine(self.cmd_output_wrap)
    static_line.SetForegroundColour(COLOR_BLACK)
    cmd_output_wrap_sizer.Add(static_line, 0, wx.EXPAND)

    command_title_panel = wx.Window(self.cmd_output_wrap)
    command_title_sizer = wx.BoxSizer(wx.VERTICAL)
    command_title = wx.StaticText(
        command_title_panel, wx.ID_ANY, self.atft_string.TITLE_COMMAND_OUTPUT)
    command_title.SetForegroundColour(COLOR_BLACK)
    command_title_font = wx.Font(
        16, wx.FONTFAMILY_MODERN, wx.NORMAL, wx.FONTWEIGHT_BOLD)
    command_title.SetFont(command_title_font)
    command_title_sizer.Add(command_title, 0, wx.ALL, 5)
    command_title_panel.SetSizerAndFit(command_title_sizer)
    command_title_panel.SetBackgroundColour(COLOR_WHITE)
    cmd_output_wrap_sizer.Add(
        command_title_panel, 0, wx.EXPAND)
    self.cmd_output_wrap_sizer = cmd_output_wrap_sizer

    # Command Output Window
    cmd_output_panel = wx.Window(self.cmd_output_wrap)
    self.cmd_output = wx.TextCtrl(
        cmd_output_panel,
        wx.ID_ANY,
        size=(0, 110),
        style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.BORDER_NONE)
    cmd_output_sizer = wx.BoxSizer(wx.VERTICAL)
    cmd_output_sizer.Add(
        self.cmd_output, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)
    cmd_output_panel.SetSizerAndFit(cmd_output_sizer)
    cmd_output_panel.SetBackgroundColour(COLOR_WHITE)

    cmd_output_wrap_sizer.Add(cmd_output_panel, 0, wx.ALL | wx.EXPAND, 0)
    self.cmd_output_wrap.SetSizerAndFit(cmd_output_wrap_sizer)

    self.main_box.Add(self.cmd_output_wrap, 0, wx.EXPAND, 0)

  def _CreateStatusBar(self):
    """Create the bottom status bar."""
    self.statusbar = self.CreateStatusBar(1, style=wx.STB_DEFAULT_STYLE)
    self.statusbar.SetBackgroundColour(COLOR_BLACK)
    self.statusbar.SetForegroundColour(COLOR_WHITE)
    status_sizer = wx.BoxSizer(wx.VERTICAL)
    self.status_text = wx.StaticText(
        self.statusbar, wx.ID_ANY, self.atft_string.TITLE_KEYS_LEFT)
    status_sizer.AddSpacer(5)
    status_sizer.Add(self.status_text, 0, wx.LEFT, 10)
    statusbar_font = wx.Font(
        10, wx.FONTFAMILY_MODERN, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.status_text.SetFont(statusbar_font)
    self.status_text.SetForegroundColour(COLOR_WHITE)
    self.statusbar.SetSize(0, 35)
    self.statusbar.SetSizer(status_sizer)
    # Add the spacer for statusbar
    self.main_box.AddSpacer(40)

  def ShowStartScreen(self):
    """Show the start screen which contains start logo.

    We also ask user to choose product file at the start screen
    """
    self.start_screen_shown = True
    self.panel.Hide()
    self.statusbar.Hide()
    self.SetMenuBar(None)
    self.start_screen = wx.Window(self, size=(960, 600))
    self.start_screen.SetBackgroundColour(COLOR_BLACK)
    start_screen_sizer = wx.BoxSizer(wx.VERTICAL)
    self.start_screen.SetSizer(start_screen_sizer)
    start_screen_sizer.AddSpacer(120)
    athings_logo_img = wx.Image('athings_icon.png', type=wx.BITMAP_TYPE_PNG)
    athings_logo = wx.Bitmap(athings_logo_img)
    logo_img = wx.StaticBitmap(self.start_screen, bitmap=athings_logo)
    start_screen_sizer.Add(logo_img, 0, wx.ALIGN_CENTER)
    start_screen_sizer.AddSpacer(30)
    athings_text_image = wx.Image('androidthings.png', type=wx.BITMAP_TYPE_PNG)
    athings_text = wx.Bitmap(athings_text_image)
    athings_img = wx.StaticBitmap(self.start_screen, bitmap=athings_text)
    start_screen_sizer.Add(athings_img, 0, wx.ALIGN_CENTER)
    start_screen_sizer.AddSpacer(50)

    button_choose_product = wx.Button(
        self.start_screen,
        label=self.atft_string.MENU_CHOOSE_PRODUCT,
        size=(250, 50))
    font = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    button_choose_product.SetFont(font)
    button_choose_product.SetBackgroundColour(COLOR_DARK_GREY)
    button_choose_product.SetForegroundColour(COLOR_WHITE)
    start_screen_sizer.Add(button_choose_product, 0, wx.ALIGN_CENTER)
    button_choose_product.Bind(wx.EVT_BUTTON, self.ChooseProduct)

    button_skip_product = wx.Button(
        self.start_screen,
        label=self.atft_string.MENU_SKIP_PRODUCT,
        size=(150, 30))
    font = wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    button_skip_product.SetFont(font)
    button_skip_product.SetBackgroundColour(COLOR_DARK_GREY)
    button_skip_product.SetForegroundColour(COLOR_LIGHT_GREY_TEXT)
    start_screen_sizer.AddSpacer(20)
    start_screen_sizer.Add(button_skip_product, 0, wx.ALIGN_CENTER)
    button_skip_product.Bind(wx.EVT_BUTTON, self.SkipProduct)

    self.start_screen.Layout()
    self.SetSize(self.start_screen.GetSize())
    self.CenterOnParent()
    button_choose_product.SetFocus()

  def HideStartScreen(self):
    """Hide the start screen."""
    self.start_screen_shown = False
    self.start_screen.Hide()
    self.panel.Show()
    self.statusbar.Show()
    if self.sup_mode:
      self.SetMenuBar(self.menubar)
    self.main_box.Layout()
    self.panel.SetSizerAndFit(self.main_box)
    self.Layout()
    self.SetSize(self.GetWindowSize())
    self.SetFocus()

  def GetWindowSize(self):
    """Get the current main window size."""
    size_x = self.panel.GetSize()[0]
    size_y = 0
    if self.menubar.IsShown():
      size_y += self.menubar.GetSize()[1]
    size_y += self.panel.GetSize()[1]
    if self.statusbar.IsShown():
      size_y += self.statusbar.GetSize()[1]
    return (size_x, size_y)

  def PauseRefresh(self):
    """Pause the refresh for device list during fastboot operations.
    """
    self.refresh_pause_lock.release()

  def ResumeRefresh(self):
    """Resume the refresh for device list.
    """
    self.refresh_pause_lock.acquire()

  def PrintToWindow(self, text_entry, text, append=False):
    """Print some message to a text_entry window.

    Args:
      text_entry: The window to print to.
      text: The text to be printed.
      append: Whether to replace or append the message.
    """
    # Append the message.
    if append:
      text_entry.AppendText(text)
      return

    # Replace existing message. Need to clean first. The GetValue() returns
    # unicode string, need to encode that to utf-8 to compare.
    current_text = text_entry.GetValue().encode('utf-8')
    if text == current_text:
      # If nothing changes, don't refresh.
      return
    text_entry.Clear()
    text_entry.AppendText(text)

  def PrintToCommandWindow(self, text):
    """Print some message to the command window.

    Args:
      text: The text to be printed.
    """
    msg = '[' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '] '
    msg += text + '\n'
    self.PrintToWindow(self.cmd_output, msg, True)

  def StartRefreshingDevices(self):
    """Refreshing the device list by interval of device_refresh_interval.
    """
    # If there's already a timer running, stop it first.
    self.StopRefresh()
    # Start a new timer.
    self.refresh_timer = threading.Timer(self.device_refresh_interval,
                                         self.StartRefreshingDevices)
    self.refresh_timer.start()
    if self.refresh_pause_lock.acquire(False):
      # Semaphore > 0, refresh is still paused.
      self.refresh_pause_lock.release()
      self._SendDeviceListedEvent()
    else:
      # If refresh is not paused, refresh the devices.
      self._ListDevices()

  def StopRefresh(self):
    """Stop the refresh timer if there's any.
    """
    if self.refresh_timer:
      timer = self.refresh_timer
      self.refresh_timer = None
      timer.cancel()

  def OnClearCommandWindow(self, event=None):
    """Clear the command window.

    Args:
      event: The triggering event.
    """
    self.cmd_output.Clear()

  def OnListDevices(self, event=None):
    """List devices asynchronously.

    Args:
      event: The triggering event.
    """
    if event is not None:
      event.Skip()

    self._CreateThread(self._ListDevices)

  def OnReboot(self, event):
    """Reboot ATFA device asynchronously.

    Args:
      event: The triggering event.
    """
    try:
      self.atft_manager.CheckDevice(self.atft_manager.GetATFADevice())
    except DeviceNotFoundException:
      self._SendAlertEvent(self.atft_string.ALERT_NO_ATFA)
      return
    self._CreateThread(self._Reboot)

  def OnShutdown(self, event):
    """Shutdown ATFA device asynchronously.

    Args:
      event: The triggering event.
    """
    try:
      self.atft_manager.CheckDevice(self.atft_manager.GetATFADevice())
    except DeviceNotFoundException:
      self._SendAlertEvent(self.atft_string.ALERT_NO_ATFA)
      return
    self._CreateThread(self._Shutdown)

  def OnChangeAutoProv(self, event):
    """Change the auto provisioning mode and the button status.

    Args:
      event: The triggering event.
    """
    if self.autoprov_button.GetValue():
      self.autoprov_button.SetValue(False)
    else:
      self.autoprov_button.SetValue(True)
    self.OnToggleAutoProv(None)

  def OnToggleAutoProv(self, event):
    """Toggle the auto provisioning mode.

    Args:
      event: The triggering event.
    """
    if self.autoprov_button.GetValue():
      self.OnEnterAutoProv()
    else:
      self.OnLeaveAutoProv()

  def OnEnterAutoProv(self):
    """Enter auto provisioning mode."""
    if self.auto_prov:
      return
    if not self.atft_manager.GetATFADevice():
      self.ShowAlert(self.atft_string.ALERT_AUTO_PROV_NO_ATFA)
      self.autoprov_button.SetValue(False)
      return
    if not self.atft_manager.product_info and not self.atft_manager.som_info:
      self.ShowAlert(self.atft_string.ALERT_AUTO_PROV_NO_PRODUCT)
      self.autoprov_button.SetValue(False)
      return
    if not self._GetCachedATFAKeysLeft():
      self.ShowAlert(self.atft_string.ALERT_AUTO_PROV_NO_KEYS_LEFT)
      self.autoprov_button.SetValue(False)
      return

    # If product info file is chosen and atfa device is present and there are
    # keys left. Enter auto provisioning mode.
    self.auto_prov = True
    self.first_key_alert_shown = False
    self.second_key_alert_shown = False
    message = 'Automatic key provisioning start'
    self.PrintToCommandWindow(message)
    self.log.Info('Autoprov', message)

  def OnLeaveAutoProv(self):
    """Leave auto provisioning mode."""
    if not self.auto_prov:
      return
    self.auto_prov = False
    for device in self._GetAvailableDevices():
      # Change all waiting devices' status to it's original state.
      if device.provision_status == ProvisionStatus.WAITING:
        self.atft_manager.CheckProvisionStatus(device)
    message = 'Automatic key provisioning end'
    self.PrintToCommandWindow(message)
    self.log.Info('Autoprov', message)

  def _OnToggleSupButton(self, event):
    """Show/Hide 'Enter Supervisor Mode' button.

    Args:
      event: The triggering event.
    """
    if self.button_supervisor_toggle.IsShown():
      self.button_supervisor_toggle.Show(False)
    else:
      self.button_supervisor_toggle.SetPosition((630,20))
      self.button_supervisor_toggle.Show(True)
      self.button_supervisor_toggle.SetSize(250, 30)
      self.button_supervisor_toggle.Raise()

  def _OnToggleSupMode(self, event):
    """Enter/leave supervisor mode.

    Args:
      event: The triggering event.
    """
    if self.sup_mode:
     self.OnLeaveSupMode()
    else:
      self.OnEnterSupMode()
    self.button_supervisor_toggle.Show(False)
    self.main_box.Layout()
    self.panel.SetSizerAndFit(self.main_box)
    self.Layout()
    self.SetSize(self.GetWindowSize())
    self.SetFocus()

  def OnLeaveSupMode(self):
    """Leave supervisor mode"""
    message = 'Leave supervisor mode'

     # Clear all the selected target devices.
    for index in range(0, TARGET_DEV_SIZE):
      if self.target_devs_components[index].selected:
        self._DeviceSelectHandler(None, index)
    self.PrintToCommandWindow(message)
    self.log.Info('Supmode', message)
    self.sup_mode = False
    self.button_supervisor_toggle.SetLabel(
        self.atft_string.BUTTON_ENTER_SUP_MODE)
    self.main_box.Hide(self.cmd_output_wrap)
    self.SetMenuBar(None)
    self.autoprov_button.Show(True)

  def OnEnterSupMode(self):
    """Enter supervisor mode, ask for credential."""
    self.password_dialog.CenterOnParent()
    if self.password_dialog.ShowModal() != wx.ID_OK:
      return
    password = self.password_dialog.GetValue()
    self.password_dialog.SetValue('')
    result = Atft.VerifyPassword(password, self.password_hash)
    password = None
    if result:
      message = 'Enter supervisor mode'
      self.PrintToCommandWindow(message)
      self.log.Info('Supmode', message)
      self.sup_mode = True
      self.button_supervisor_toggle.SetLabel(
          self.atft_string.BUTTON_LEAVE_SUP_MODE)
      self.SetMenuBar(self.menubar)
      self.cmd_output_wrap.Show()
      self.autoprov_button.SetValue(False)
      self.OnLeaveAutoProv()
      self.autoprov_button.Show(False)
    else:
      e = PasswordErrorException()
      # Log the wrong password event.
      self._HandleException('W', e)
      self._SendAlertEvent(self.atft_string.ALERT_WRONG_PASSWORD)

  def OnManualProvision(self, event):
    """Manual provision key asynchronously.

    Args:
      event: The triggering event.
    """
    selected_serials = self._GetSelectedSerials()
    if not selected_serials:
      self._SendAlertEvent(self.atft_string.ALERT_PROV_NO_SELECTED)
      return
    if not self.atft_manager.GetATFADevice():
      self._SendAlertEvent(self.atft_string.ALERT_PROV_NO_ATFA)
      return
    if self._GetCachedATFAKeysLeft() == 0:
      self._SendAlertEvent(self.atft_string.ALERT_PROV_NO_KEYS)
      return
    is_som_key = (self.atft_manager.som_info is not None)
    for serial in selected_serials:
      target_dev = self.atft_manager.GetTargetDevice(serial)
      if (not target_dev or
          target_dev.provision_status == ProvisionStatus.REBOOT_IN_PROGRESS):
        continue
      status = target_dev.provision_status
      if (self.test_mode):
        target_dev.provision_status = ProvisionStatus.WAITING
      elif (
          target_dev.provision_state.bootloader_locked and
          target_dev.provision_state.avb_perm_attr_set and
          target_dev.provision_state.avb_locked):
        if ((target_dev.provision_state.product_provisioned and not is_som_key)
            or
            (target_dev.provision_state.som_provisioned and is_som_key)):
          if not self.ShowWarning(
              self.atft_string.ALERT_REPROVISION(target_dev)):
            continue
        target_dev.provision_status = ProvisionStatus.WAITING
      else:
        self._SendAlertEvent(self.atft_string.ALERT_PROV_PROVED)
    self._CreateThread(self._ManualProvision, selected_serials, is_som_key)

  def OnCheckATFAStatus(self, event):
    """Check the attestation key status from ATFA device asynchronously.

    Args:
      event: The triggering event.
    """
    self._CreateThread(self._ShowATFAStatus)

  def OnFuseVbootKey(self, event):
    """Fuse the vboot key to the target device asynchronously.

    Args:
      event: The triggering event.
    """
    selected_serials = self._GetSelectedSerials()
    if not selected_serials:
      self._SendAlertEvent(self.atft_string.ALERT_FUSE_NO_SELECTED)
      return
    if not self.atft_manager.product_info and not self.atft_manager.som_info:
      self._SendAlertEvent(self.atft_string.ALERT_FUSE_NO_PRODUCT)
      return

    self._CreateThread(self._FuseVbootKey, selected_serials)

  def OnFusePermAttr(self, event):
    """Fuse the permanent attributes to the target device asynchronously.

    Args:
      event: The triggering event.
    """
    selected_serials = self._GetSelectedSerials()
    if not selected_serials:
      self._SendAlertEvent(self.atft_string.ALERT_FUSE_PERM_NO_SELECTED)
      return
    if not self.atft_manager.product_info:
      self._SendAlertEvent(self.atft_string.ALERT_FUSE_PERM_NO_PRODUCT)
      return

    self._CreateThread(self._FusePermAttr, selected_serials)

  def OnLockAvb(self, event):
    """Lock the AVB asynchronously.

    Args:
      event: The triggering event
    """
    selected_serials = self._GetSelectedSerials()
    if not selected_serials:
      self._SendAlertEvent(self.atft_string.ALERT_LOCKAVB_NO_SELECTED)
      return

    self._CreateThread(self._LockAvb, selected_serials)

  def OnQuit(self, event):
    """Quit the application.

    Args:
      event: The triggering event.
    """
    self.Close()

  def ToggleStatusBar(self, event):
    """Toggle the status bar.

    Args:
      event: The triggering event.
    """
    if self.menu_show_status_bar.IsChecked():
      self.statusbar.Show()
    else:
      self.statusbar.Hide()
    self.SetSize(self.GetWindowSize())

  class SelectFileArg(object):
    """The argument structure for SelectFileHandler.

    Attributes:
      message: The message for the select file window.
      wildcard: The wildcard to filter the files to be selected.
      callback: The callback to be called once the file is selected with
        argument pathname of the selected file.
    """

    def __init__(self, message, wildcard, callback):
      self.message = message
      self.wildcard = wildcard
      self.callback = callback

  class SaveFileArg(object):
    """The argument structure for SaveFileHandler.

    Attributes:
      message: The message for the select file window.
      filename: The filename of the file to be saved to.
      callback: The callback to be called once the file is selected with
        argument pathname of the selected file.
    """
    def __init__(self, message, filename, callback):
      self.message = message
      self.filename = filename
      self.callback = callback

  def SkipProduct(self, event):
    """User skip choosing product.

    Args:
      event: The triggering event.
    """

    if self.start_screen_shown:
      self.HideStartScreen()
    self._EnableDisableMenuItems(False)

  def _EnableDisableMenuItems(self, enable_menu):
    """Disable/Enable part of the menu items that require product file.

    Disable/Enable all the actions that would not work if product attribute file
    is not selected.

    Args:
      enable_menu: Whether to enable/disable menu items.
    """
    manual_prov_id = self.provision_menu.FindItem(
        self.atft_string.MENU_MANUAL_PROV)
    self.provision_menu.Enable(manual_prov_id, enable_menu)
    manual_fuse_vboot_id = self.provision_menu.FindItem(
        self.atft_string.MENU_MANUAL_FUSE_VBOOT)
    self.provision_menu.Enable(manual_fuse_vboot_id, enable_menu)
    manual_fuse_attr_id = self.provision_menu.FindItem(
        self.atft_string.MENU_MANUAL_FUSE_ATTR)
    self.provision_menu.Enable(manual_fuse_attr_id, enable_menu)
    atfa_status_id = self.atfa_menu.FindItem(
        self.atft_string.MENU_ATFA_STATUS)
    self.atfa_menu.Enable(atfa_status_id, enable_menu)
    purge_key_id = self.key_menu.FindItem(self.atft_string.MENU_PURGE)
    self.key_menu.Enable(purge_key_id, enable_menu)

  def ChooseProduct(self, event):
    """Ask user to choose the product attributes file.

    Args:
      event: The triggering event.
    """
    message = self.atft_string.DIALOG_CHOOSE_PRODUCT_ATTRIBUTE_FILE
    wildcard = self.product_attribute_file_extension
    callback = self.ProcessAttributesFile
    data = self.SelectFileArg(message, wildcard, callback)
    event = Event(self.select_file_event, value=data)
    wx.QueueEvent(self, event)

  def ChangeSettings(self, event):
    self.app_settings_dialog.CenterOnParent()
    self.app_settings_dialog.ShowModal()

  def ProcessAttributesFile(self, pathname):
    """Process the selected attributes file.

    Args:
      pathname: The path for the attributes file to parse.
    """
    try:
      with open(pathname, 'r') as attribute_file:
        content = attribute_file.read()
        self.atft_manager.ProcessAttributesFile(content)
        if self.start_screen_shown:
          self.HideStartScreen()
        name = ''
        if self.atft_manager.product_info:
          # product mode
          self.product_name_title.SetLabel(self.atft_string.TITLE_PRODUCT_NAME)
          name = self.atft_manager.product_info.product_name
        elif self.atft_manager.som_info:
          # som mode
          self.product_name_title.SetLabel(self.atft_string.TITLE_SOM_NAME)
          name = self.atft_manager.som_info.som_name

        # Update the name display
        self.product_name_display.SetLabel(name)
        self.product_name_title.Refresh()
        self.product_name_display.Refresh()
        self.product_name_sizer.Layout()
        self.main_box.Layout()
        # User choose a new product, reset how many keys left.
        if (self.atft_manager.GetATFADevice() and (
              self.atft_manager.product_info or self.atft_manager.som_info)):
          self.audit.ResetKeysLeft()
          self._UpdateKeysLeftInATFA()

        if self.atft_manager.product_info or self.atft_manager.som_info:
          # If a product or som is chosen, enable the menu items that require
          # a product file.
          self._EnableDisableMenuItems(True)

        # If user change from one mode to another mode, change the default
        # provision steps.
        if (self.provision_steps == self.DEFAULT_PROVISION_STEPS_SOM and
            self.atft_manager.product_info):
          self.provision_steps = self.DEFAULT_PROVISION_STEPS_PRODUCT
        elif (self.provision_steps == self.DEFAULT_PROVISION_STEPS_PRODUCT and
              self.atft_manager.som_info):
          self.provision_steps = self.DEFAULT_PROVISION_STEPS_SOM
        self._CheckProvisionSteps()
    except IOError:
      self._SendAlertEvent(
          self.atft_string.ALERT_CANNOT_OPEN_FILE + pathname.encode('utf-8'))
    except ProductAttributesFileFormatError as e:
      self._SendAlertEvent(self.atft_string.ALERT_PRODUCT_FILE_FORMAT_WRONG)
      self._HandleException('W', e)

  def OnChangeKeyThreshold(self, event):
    """Change the threshold for low number of key warning.

    Args:
      event: The button click event.
    """
    self.change_threshold_dialog.ShowModal()
    # Update the configuration
    first_warning = self.change_threshold_dialog.GetFirstWarning()
    second_warning = self.change_threshold_dialog.GetSecondWarning()
    if first_warning:
      self.configs['DEFAULT_KEY_THRESHOLD_1'] = str(first_warning)
    elif 'DEFAULT_KEY_THRESHOLD_1' in self.configs:
      del self.configs['DEFAULT_KEY_THRESHOLD_1']
    if second_warning:
      self.configs['DEFAULT_KEY_THRESHOLD_2'] = str(second_warning)
    elif 'DEFAULT_KEY_THRESHOLD_2' in self.configs:
      del self.configs['DEFAULT_KEY_THRESHOLD_2']

  def OnGetRegFile(self, event):
    """Download the registration file from the atfa device.

    Args:
      event: The triggering event.
    """
    message = self.atft_string.DIALOG_SELECT_DIRECTORY
    try:
      filename = self.atft_manager.GetATFASerial() + '.reg'
    except DeviceNotFoundException as e:
      self._SendAlertEvent(self.atft_string.ALERT_NO_ATFA)
      return
    except FastbootFailure as e:
      self._HandleException('E', e)
      return
    callback = self._GetRegFile
    data = self.SaveFileArg(message, filename, callback)
    event = Event(self.save_file_event, value=data)
    wx.QueueEvent(self, event)

  def OnGetAuditFile(self, event):
    """Download the audit file from the atfa device.

    Args:
      event: The triggering event.
    """
    message = self.atft_string.DIALOG_SELECT_DIRECTORY
    try:
      serial = self.atft_manager.GetATFASerial()
    except DeviceNotFoundException as e:
      self._SendAlertEvent(self.atft_string.ALERT_NO_ATFA)
      return
    except FastbootFailure as e:
      self._HandleException('E', e)
      return
    filename = AtftAudit.GetAuditFileName(serial)
    callback = self._GetAuditFile
    data = self.SaveFileArg(message, filename, callback)
    event = Event(self.save_file_event, value=data)
    wx.QueueEvent(self, event)

  def OnStoreKey(self, event):
    """Upload the key bundle file to ATFA device and process it.

    Give user a prompt to choose a keybundle file then upload that file
    to the ATFA device and process it.

    Args:
      event: The button click event.
    """
    try:
      self.atft_manager.CheckDevice(self.atft_manager.GetATFADevice())
    except DeviceNotFoundException:
      self._SendAlertEvent(self.atft_string.ALERT_NO_ATFA)
      return

    message = self.atft_string.DIALOG_CHOOSE_KEY_FILE
    wildcard = self.key_file_extension
    callback = self._ProcessKeyCallback
    data = self.SelectFileArg(message, wildcard, callback)
    event = Event(self.select_file_event, value=data)
    wx.QueueEvent(self, event)

  def OnUpdateAtfa(self, event):
    """Store the update file to the ATFA device and process it.

    Give user a prompt to choose an update patch file and then upload that
    file to the ATFA device and process it.

    Args:
      event: The button click event.
    """
    try:
      self.atft_manager.CheckDevice(self.atft_manager.GetATFADevice())
    except DeviceNotFoundException:
      self._SendAlertEvent(self.atft_string.ALERT_NO_ATFA)
      return

    message = self.atft_string.DIALOG_CHOOSE_UPDATE_FILE
    wildcard = self.update_file_extension
    callback = self._UpdateATFACallback
    data = self.SelectFileArg(message, wildcard, callback)
    event = Event(self.select_file_event, value=data)
    wx.QueueEvent(self, event)

  def OnPurgeKey(self, event):
    """Purge the keybundle for the product in the ATFA device.

    Args:
      event: The button click event.
    """
    try:
      self.atft_manager.CheckDevice(self.atft_manager.GetATFADevice())
    except DeviceNotFoundException:
      self._SendAlertEvent(self.atft_string.ALERT_NO_ATFA)
      return
    if self.ShowWarning(self.atft_string.ALERT_CONFIRM_PURGE_KEY):
      self._CreateThread(self._PurgeKey)

  def ShowAlert(self, msg):
    """Show an alert box at the center of the parent window.

    Args:
      msg: The message to be shown in the alert box.
    """
    self.alert_dialog.CenterOnParent()
    self.alert_dialog.SetMessage(msg)
    self.alert_dialog.ShowModal()

  def _is_provision_steps_finished(self, provision_state):
    """Check if the target device has successfully finished provision steps.

    Args:
      target: The target device.
    Returns:
      success if the target device has already gone through the provision steps
      successfully.
    """
    final_state = copy.deepcopy(provision_state)
    for operation in self.provision_steps:
      if operation == 'FuseVbootKey':
        final_state.bootloader_locked = True
        continue
      elif operation == 'FusePermAttr':
        final_state.avb_perm_attr_set = True
        continue
      elif operation == 'LockAvb':
        final_state.avb_locked = True
        continue
      elif operation == 'UnlockAvb':
        final_state.avb_locked = False
        continue
      elif operation == 'ProvisionProduct':
        final_state.product_provisioned = True
        continue
      elif operation == 'ProvisionSom':
        final_state.som_provisioned = True
    return (provision_state == final_state);

  def _HandleAutoProv(self):
    """Do the state transition for devices if in auto provisioning mode.

    """
    # All idle devices -> waiting.
    for target_dev in self._GetAvailableDevices():
      if (target_dev.serial_number not in self.auto_dev_serials and
          not self._is_provision_steps_finished(target_dev.provision_state) and
          not ProvisionStatus.isFailed(target_dev.provision_status)
          ):
        self.auto_dev_serials.append(target_dev.serial_number)
        target_dev.provision_status = ProvisionStatus.WAITING
        self._CreateThread(self._HandleStateTransition, target_dev)


  def _HandleKeysLeft(self):
    """Display how many keys left in the ATFA device.
    """
    text = self.atft_string.TITLE_KEYS_LEFT
    color = COLOR_BLACK

    try:
      if (not self.atft_manager.GetATFADevice() or (
          not self.atft_manager.product_info and
          not self.atft_manager.som_info)):
        raise DeviceNotFoundException
      keys_left = self._GetCachedATFAKeysLeft()
      if not keys_left and keys_left != 0:
        # If keys_left is not set, try to set it and pull the audit.
        self.audit.ResetKeysLeft()
        self._UpdateKeysLeftInATFA()
        keys_left = self._GetCachedATFAKeysLeft()
      text = self.atft_string.TITLE_KEYS_LEFT + str(keys_left)
      if not keys_left or keys_left < 0:
        raise NoKeysException

      first_warning = self.change_threshold_dialog.GetFirstWarning()
      second_warning = self.change_threshold_dialog.GetSecondWarning()
      if first_warning and keys_left < first_warning:
        color = COLOR_YELLOW
      if second_warning and keys_left < second_warning:
        color = COLOR_RED
      self._SetStatusTextColor(text, color)
    except (DeviceNotFoundException, NoKeysException):
      self._SetStatusTextColor(text, color)

  def _SetStatusTextColor(self, text, color):
    """Set the background color and the text for the status bar.

    Args:
      text: The text to be displayed on the status bar.
      color: The background color.
    """
    if self.statusbar.GetBackgroundColour() != color:
      self.statusbar.SetBackgroundColour(color)
      self.statusbar.Refresh()
    if self.statusbar.GetStatusText().encode('utf-8') != text:
      self.status_text.SetLabel(text)
      self.statusbar.Refresh()

  def ShowWarning(self, text):
    """Show a warning to the user.

    Args:
      text: The content of the warning.
    Returns:
      True if the user clicks yes, otherwise, False.
    """
    warning_dialog = wx.MessageDialog(
        self,
        text,
        self.atft_string.DIALOG_WARNING_TITLE,
        style=wx.YES_NO | wx.ICON_EXCLAMATION)
    if warning_dialog.ShowModal() == wx.ID_YES:
      return True
    return False

  def _CopyList(self, old_list):
    """Copy a device list.

    Args:
      old_list: The original list
    Returns:
      The duplicate with all the public member copied.
    """
    copy_list = []
    for dev in old_list:
      copy_list.append(dev.Copy())
    return copy_list

  def _HandleException(self, level, e, operation=None, targets=None):
    """Handle the exception.

    Fires a exception event which would be handled in main thread. The exception
    would be shown in the command window. This function also wraps the
    associated operation and device object.

    Args:
      level: The log level for the exception.
      e: The original exception.
      operation: The operation associated with this exception.
      targets: The list of DeviceInfo object associated with this exception.
    """
    atft_exception = AtftException(e, operation, targets)
    wx.QueueEvent(self,
                  Event(
                      self.exception_event,
                      wx.ID_ANY,
                      value=str(atft_exception)))
    self._LogException(level, atft_exception)

  def _LogException(self, level, atft_exception):
    """Log the exceptions.

    Args:
      level: The log level for this exception. 'E': error or 'W': warning.
      atft_exception: The exception to be logged.
    """
    if level == 'E':
      self.log.Error('OpException', str(atft_exception))
    elif level == 'W':
      self.log.Warning('OpException', str(atft_exception))

  def _CreateBindEvents(self):
    """Create customized events and bind them to the event handlers.
    """

    # Event for refreshing device list.
    self.refresh_event = wx.NewEventType()
    self.refresh_event_bind = wx.PyEventBinder(self.refresh_event)

    # Event for device listed.
    self.dev_listed_event = wx.NewEventType()
    self.dev_listed_event_bind = wx.PyEventBinder(self.dev_listed_event)
    # Event when general exception happens.
    self.exception_event = wx.NewEventType()
    self.exception_event_bind = wx.PyEventBinder(self.exception_event)
    # Event for alert box.
    self.alert_event = wx.NewEventType()
    self.alert_event_bind = wx.PyEventBinder(self.alert_event)
    # Event for general message to be printed in command window.
    self.print_event = wx.NewEventType()
    self.print_event_bind = wx.PyEventBinder(self.print_event)
    # Event for low key alert.
    self.low_key_alert_event = wx.NewEventType()
    self.low_key_alert_event_bind = wx.PyEventBinder(self.low_key_alert_event)
    # Event for select a file.
    self.select_file_event = wx.NewEventType()
    self.select_file_event_bind = wx.PyEventBinder(self.select_file_event)
    # Event for save a file.
    self.save_file_event = wx.NewEventType()
    self.save_file_event_bind = wx.PyEventBinder(self.save_file_event)
    # Event for update the mapping status for mapping USB location
    self.update_mapping_status_event = wx.NewEventType()
    self.update_mapping_status_bind = wx.PyEventBinder(
        self.update_mapping_status_event)

    self.map_usb_success_event = wx.NewEventType()
    self.map_usb_success_bind = wx.PyEventBinder(self.map_usb_success_event)

    self.Bind(self.refresh_event_bind, self.OnListDevices)
    self.Bind(self.dev_listed_event_bind, self._DeviceListedEventHandler)
    self.Bind(self.exception_event_bind, self._PrintEventHandler)
    self.Bind(self.alert_event_bind, self._AlertEventHandler)
    self.Bind(self.print_event_bind, self._PrintEventHandler)
    self.Bind(self.low_key_alert_event_bind, self._LowKeyAlertEventHandler)
    self.Bind(self.select_file_event_bind, self._SelectFileEventHandler)
    self.Bind(self.save_file_event_bind, self._SaveFileEventHandler)
    self.Bind(self.update_mapping_status_bind, self._UpdateMappingStatusHandler)

    i = 0
    for dev_component in self.target_devs_components:
      Atft._BindEventRecursive(
          wx.EVT_LEFT_DOWN, dev_component.panel,
          lambda event, index=i : self._DeviceSelectHandler(event, index))
      Atft._BindEventRecursive(
          wx.EVT_SET_FOCUS, dev_component.panel,
          lambda event, index=i : self._DeviceFocusHandler(event, index))
      Atft._BindEventRecursive(
          wx.EVT_KILL_FOCUS, dev_component.panel,
          lambda event, index=i : self._DeviceLostFocusHandler(event, index))
      i += 1

    # Bind the close event
    self.Bind(wx.EVT_CLOSE, self.OnClose)

  def _DeviceSelectHandler(self, event, index):
    """The handler to handle user selecting a target device.
    Args:
      event: The triggering event.
      index: The index for the target device.
    """
    if not self.sup_mode:
      return
    dev_component = self.target_devs_components[index]
    if not dev_component.active or not dev_component.serial_number:
      return
    title_background = dev_component.title_background
    if not dev_component.selected:
      title_background.SetBackgroundColour(COLOR_PICK_BLUE)
    else:
      title_background.SetBackgroundColour(COLOR_WHITE)
    title_background.Refresh()
    dev_component.selected = not dev_component.selected
    dev_component.panel.SetFocus()
    if event:
      event.Skip()

  def _DeviceFocusHandler(self, event, index):
    """The handler when a target device slot is focused.

    Args:
      event: The triggering event.
      index: The index for the target device.
    """
    dev_component = self.target_devs_components[index]
    dev_component.panel.SetWindowStyleFlag(wx.BORDER_SUNKEN)
    dev_component.panel.GetParent().Refresh()

  def _DeviceLostFocusHandler(self, event, index):
    """The handler when a target device slot loses focus.

    Args:
      event: The triggering event.
      index: The index for the target device.
    """
    dev_component = self.target_devs_components[index]
    dev_component.panel.SetWindowStyleFlag(wx.BORDER_RAISED)
    dev_component.panel.GetParent().Refresh()

  def MapUSBToSlotHandler(self, event, index):
    """The handler to map a target device's USB location to a UI slot.

    This should be a single select since user can only select one device
    location to be mapped.

    Args:
      event: The triggering event.
      index: The index for the target device.
    """
    i = 0
    for dev_component in self.app_settings_dialog.dev_mapping_components:
      title_background = dev_component.title_background
      if i == index:
        title_background.SetBackgroundColour(COLOR_PICK_BLUE)
        if self.device_usb_locations[i]:
          # If already selected, change the button to 'remap'
          self.app_settings_dialog.button_map.SetLabel(
              self.atft_string.BUTTON_REMAP)
        else:
          self.app_settings_dialog.button_map.SetLabel(
              self.atft_string.BUTTON_MAP)
        self.app_settings_dialog.button_map.GetParent().Layout()
        dev_component.selected = True
      else:
        title_background.SetBackgroundColour(COLOR_WHITE)
        dev_component.selected = False
      title_background.Refresh()
      i += 1

    event.Skip()

  def _SendAlertEvent(self, msg):
    """Send an event to generate an alert box.

    Args:
      msg: The message to be displayed in the alert box.
    """
    evt = Event(self.alert_event, wx.ID_ANY, msg)
    wx.QueueEvent(self, evt)

  def _PrintEventHandler(self, event):
    """The handler to handle the event to display a message in the cmd output.

    Args:
      event: The message to be displayed.
    """
    msg = str(event.GetValue())
    self.PrintToCommandWindow(msg)

  def _SendPrintEvent(self, msg):
    """Send an event to print a message to the cmd output.

    Args:
      msg: The message to be displayed.
    """
    evt = Event(self.print_event, wx.ID_ANY, msg)
    wx.QueueEvent(self, evt)

  def _StartOperation(self, operation, target, show_alert=True, blocking=False):
    """Set the target to operating status, print out the start message.

    This methods prevent two operations on the same device interleaving with
    each other. If blocking is False, then this function would return False
    if there is another interleaving operation running. Otherwise, this call
    would block until the other operation finishes. This function would then
    obtain the operation lock the target device. This function would also
    pause the 'fastboot devices' refresh because that would interfere with any
    other operations.

    Args:
      operation: The operation to start.
      target: The target device.
      show_alert: Whether to print alert message if another operation is
        ongoing.
      blocking: Whether to wait for the other operation.
    Returns:
      False if blocking is set to False and another operation is ongoing,
      otherwise return True.
    """
    if not target:
      self.PauseRefresh()
      return True
    if target.operation_lock.acquire(blocking):
      target.operation = operation
      self._SendOperationStartEvent(operation, target)
      self.PauseRefresh()
      return True

    if show_alert:
      self._SendAlertEvent(
          'Unable to start operation: ' + operation + ', ' +
          'Target: ' + str(target) + ' is currently in another operation: '  +
          target.operation + '. Please try again later')
    return False

  def _EndOperation(self, target):
    """Clear the operation status and release the operation lock.

    Args:
      target: The target device.
    """
    self.ResumeRefresh()
    if not target:
      return
    target.operation = None
    target.operation_lock.release()

  def _SendOperationStartEvent(self, operation, target):
    """Send an event to print an operation start message.

    Args:
      operation: The operation name.
      target: The target of the operation.
    """
    msg = ''
    if target:
      msg += '{' + str(target) + '} '
    msg += operation + ' Start'
    self._SendPrintEvent(msg)
    self.log.Info('OpStart', msg)

  def _SendOperationSucceedEvent(self, operation, target=None):
    """Send an event to print an operation succeed message.

    Args:
      operation: The operation name.
      target: The target of the operation.
    """
    msg = ''
    if target:
      msg += '{' + str(target) + '} '
    msg += operation + ' Succeed'
    self._SendPrintEvent(msg)
    self.log.Info('OpSucceed', msg)

  def _SendDeviceListedEvent(self):
    """Send an event to indicate device list is refreshed, need to refresh UI.
    """
    wx.QueueEvent(self, Event(self.dev_listed_event))

  def _SendLowKeyAlertEvent(self, keys_left):
    """Send low key alert event.

    Send an event to indicate the keys left in the ATFA device is lower than
    threshold.

    Args:
      keys_left: The number of keys left.
    """
    wx.QueueEvent(self, Event(self.low_key_alert_event, value=keys_left))

  def SendUpdateMappingEvent(self):
    """Send an event to indicate the mapping status need to be updated.
    """
    self.mapping_mode = self.SINGLE_DEVICE_MODE
    for i in range(TARGET_DEV_SIZE):
      if self.device_usb_locations[i]:
        self.mapping_mode = self.MULTIPLE_DEVICE_MODE
        break
    self._ChangeMappingMode()
    wx.QueueEvent(self, Event(self.update_mapping_status_event))

  def _AlertEventHandler(self, event):
    """The handler to handle the event to display an alert box.

    Args:
      event: The alert event containing the message to be displayed.
    """
    msg = event.GetValue()
    # Need to check if any other handler is using the alert box.
    # All the handler is in the main thread
    # So we cannot block to acquire this lock
    # The main reason of the async is the showModal is async
    # However, we cannot make sure SetMsg and ShowModel is atomic
    # So we can only ignore the overlapping request.
    if self.alert_lock.acquire(False):
      self.ShowAlert(msg)
      self.alert_lock.release()

  def _DeviceListedEventHandler(self, event):
    """Handles the device listed event and list the devices.

    Args:
      event: The event object.
    """
    self._HandleKeysLeft()

    if not self.sup_mode:
      # If in normal mode
      if self.auto_prov and not self.atft_manager.GetATFADevice():
        # If ATFA unplugged during normal mode,
        # exit the mode with an alert.
        self.autoprov_button.SetValue(False)
        self.OnLeaveAutoProv()
        # Add log here.
        self._SendAlertEvent('ATFA device unplugged, exit auto mode!')

    # If in auto provisioning mode, handle the newly added devices.
    if self.auto_prov:
      self._HandleAutoProv()

    if (not self.start_screen_shown and self.sup_mode and
        self.checking_mapping_mode_lock.acquire(False)):
      if not self.app_settings_dialog.IsShown():
        # Check if multiple devices detected in SINGLE_DEVICE mode. We only
        # check mapping mode if in supervisor mode, the welcome screen
        # is not shown and not in settings.
        self._CheckMappingMode()
      self.checking_mapping_mode_lock.release()

    self._PrintAtfaDevice()

    # Remove ignored target device if the device is unplugged
    new_ignored_serials = sets.Set()
    for serial in self.ignored_unmapped_device_serials:
      if self.atft_manager.GetTargetDevice(serial):
        new_ignored_serials.add(serial)
    self.ignored_unmapped_device_serials = new_ignored_serials

    if self.last_target_list == self.atft_manager.target_devs:
      # Nothing changes, no need to refresh
      return

    # Update the stored target list. Need to make a deep copy instead of copying
    # the reference.
    self.last_target_list = self._CopyList(self.atft_manager.target_devs)
    self._PrintTargetDevices()

  def _CheckMappingMode(self):
    """Check if the current mapping mode need to change.

    Check if the current mapping mode is single device mode, however, we find
    multiple target devices, then we would need user to unplug a device or
    change the mapping mode to multi device mode.
    """
    if self.mapping_mode == self.SINGLE_DEVICE_MODE:
      if len(self.atft_manager.target_devs) > 1:
        # We detected multiple target devices in single device mode.
        while True:
          if self.change_mapping_mode_dialog.ShowModal() == wx.ID_YES:
            self.ChangeSettings(None)
            self.app_settings_dialog.ShowUSBMappingSetting(None)
            break
          elif len(self.atft_manager.target_devs) <= 1:
            break
    else:
      for target_dev in self.atft_manager.target_devs:
        if target_dev.serial_number in self.ignored_unmapped_device_serials:
          continue
        if target_dev.location not in self.device_usb_locations:
          if self.ShowWarning(self.atft_string.ALERT_TARGET_DEVICE_UNMAPPED):
            self.ChangeSettings(None)
            self.app_settings_dialog.ShowUSBMappingSetting(None)
          # No matter user choose mapping or not, we would not ask again unless
          # this device is unplugged.
          self.ignored_unmapped_device_serials.add(target_dev.serial_number)

  def _ChangeMappingMode(self):
    """Change the mapping mode.

    This would change the UI display according to the mapping mode. In single
    device mode, a large panel would appear and the devices list would be
    hidden, in multiple device mode, the user would see a six-slot devices
    list.
    """
    for i in range(0, TARGET_DEV_SIZE):
      self.target_devs_components[i].panel.Show(
          self.mapping_mode == self.MULTIPLE_DEVICE_MODE)

    self.unmapped_target_dev_component.panel.Show(
        self.mapping_mode == self.SINGLE_DEVICE_MODE)
    self.main_box.Layout()

  def _PrintAtfaDevice(self):
    """Print atfa device to atfa device output area.
    """
    if self.atft_manager.GetATFADevice():
      atfa_message = str(self.atft_manager.GetATFADevice())
    else:
      atfa_message = self.atft_string.ALERT_NO_DEVICE
    self.atfa_dev_output.SetLabel(atfa_message)

  def _PrintTargetDevices(self):
    """Print target devices to target device output area.
    """
    target_devs = self._GetDisplayedDevices()
    if self.mapping_mode == self.SINGLE_DEVICE_MODE:
      serial_text = ''
      status = None
      state = None
      serial_number = None
      if target_devs:
        target_dev = target_devs[0]
        serial_number = target_dev.serial_number
        serial_text = '{}: {}'.format(
            self.atft_string.FIELD_SERIAL_NUMBER, str(serial_number))
        status = target_dev.provision_status
        state = target_dev.provision_state

      self._ShowTargetDevice(
          self.unmapped_target_dev_component, serial_number, serial_text,
          status, state)
    else:
      target_dev_index = 0
      for i in range(TARGET_DEV_SIZE):
        serial_text = ''
        status = None
        state = None
        serial_number = None
        target_dev_component = self.target_devs_components[i]
        if self.device_usb_locations[i]:
          target_dev_component.active = True
          if (target_dev_index < len(target_devs) and
              (target_devs[target_dev_index].location ==
               self.device_usb_locations[i])):
            serial_number = target_devs[target_dev_index].serial_number
            serial_text = '{}: {}'.format(
                self.atft_string.FIELD_SERIAL_NUMBER, str(serial_number))
            status = target_devs[target_dev_index].provision_status
            state = target_devs[target_dev_index].provision_state
            target_dev_index += 1
        else:
          target_dev_component.active = False
        self._ShowTargetDevice(
            target_dev_component, serial_number, serial_text, status, state)

  def _GetDisplayedDevices(self):
    """Get the list of target devices that are displayed.

    If in single device mode, return the first target device.
    If in multiple device mode, return the list of target devices that are
    mapped to a UI slot. We only do operations to the target devices that are
    displayed in the UI and ignore the rest of the unmapped target devices.

    Returns:
      A list of displayed target device objects.
    """
    if self.mapping_mode == self.SINGLE_DEVICE_MODE:
      # If we have a single device already displayed and we still could find
      # that device, than just return that device.
      target_dev = self.atft_manager.GetTargetDevice(
          self.unmapped_target_dev_component.serial_number)
      if target_dev:
        return [target_dev]
      # Otherwise, we return the first available target devices. If there is
      # more than one device, _CheckMappingMode would handle that.
      if self.atft_manager.target_devs:
        return self.atft_manager.target_devs[0:1]
      # No target devices, return empty set.
      return []

    # If in multiple device mode, return the devices that have usb locations
    # mapped to UI slots.
    displayed_devs = []
    for target_dev in self.atft_manager.target_devs:
      for i in range(TARGET_DEV_SIZE):
        if (self.device_usb_locations[i] and
            target_dev.location == self.device_usb_locations[i]):
          displayed_devs.append(target_dev)
    return displayed_devs

  def _GetAvailableDevices(self):
    """Get the list of target devices that we could do operation to.

    We would only be able to do operations to the target devices that are
    displayed and also not rebooting.

    Returns:
      A list of available target device objects that we could do operation to.
    """
    displayed_devs = self._GetDisplayedDevices()
    return [dev for dev in displayed_devs if
            dev.provision_status != ProvisionStatus.REBOOT_IN_PROGRESS]

  def _ShowTargetDevice(self, dev_component, serial_number, serial_text, status,
                        state):
    """Display information about one target device.

    Args:
      dev_component: The device component object to be displayed.
      serial_nubmer: The serial number of the device.
      serial_text: The serial number text to be displayed.
      status: The provision status.
      state: The provision state.
    """
    if not dev_component.active:
      serial_text = self.atft_string.SERIAL_NOT_MAPPED
      dev_component.serial_text.SetForegroundColour(COLOR_LIGHT_GREY_TEXT)
      dev_component.index_text.SetForegroundColour(COLOR_LIGHT_GREY_TEXT)
    else:
      dev_component.serial_text.SetForegroundColour(COLOR_BLACK)
      dev_component.index_text.SetForegroundColour(COLOR_DARK_GREY)
    dev_component.serial_text.SetLabel(serial_text)
    dev_component.serial_text.Refresh()
    dev_component.index_text.Refresh()
    dev_component.serial_number = serial_number
    color = self._GetStatusColor(status, state)
    if status != None:
      dev_component.status.SetLabel(
          ProvisionStatus.ToString(status, self.GetLanguageIndex()))
    else:
      # This slot currently has no device
      dev_component.status.SetLabel('')
      # If the device is selected, unselect it.
      if dev_component.selected:
        dev_component.title_background.SetBackgroundColour(COLOR_WHITE)
        dev_component.title_background.Refresh()
        dev_component.selected = False
    if status == ProvisionStatus.IDLE:
      dev_component.status.SetForegroundColour(COLOR_DARK_GREY)
    else:
      dev_component.status.SetForegroundColour(COLOR_WHITE)
    dev_component.status_wrapper.Layout()
    dev_component.status_background.SetBackgroundColour(color)
    dev_component.status_background.Refresh()

  def _GetStatusColor(self, status, state):
    """Get the color according to the status.

    Args:
      status: The target device status.
      state: The target device provision state.
    Returns:
      The color to be shown for the status.
    """
    if status == None:
      return COLOR_LIGHT_GREY
    if status == ProvisionStatus.IDLE:
      return COLOR_GREY
    if self._is_provision_steps_finished(state):
      return COLOR_GREEN
    if ProvisionStatus.isFailed(status):
      return COLOR_RED
    return COLOR_BLUE

  def _SelectFileEventHandler(self, event):
    """Show the select file window.

    Args:
      event: containing data of SelectFileArg type.
    """
    data = event.GetValue()
    message = data.message
    wildcard = data.wildcard
    callback = data.callback
    with wx.FileDialog(
        self,
        message,
        wildcard=wildcard,
        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
      ) as file_dialog:
      if file_dialog.ShowModal() == wx.ID_CANCEL:
        return  # the user changed their mind
      pathname = file_dialog.GetPath()
    callback(pathname)

  def _SaveFileEventHandler(self, event):
    """Show the save file window and save the file to selected folder.

    This function would give user a directory selection dialog, and download
    the files from the atfa device to a file named event.filename under the
    selected folder.

    Args:
      event: containing data of SaveFileArg type.
    """
    data = event.GetValue()
    message = data.message
    filename = data.filename
    callback = data.callback
    with wx.DirDialog(
        self, message, '', wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST
      ) as file_dialog:
      if file_dialog.ShowModal() == wx.ID_CANCEL:
        return  # the user changed their mind
      pathname = file_dialog.GetPath()
      filepath = os.path.join(pathname, filename)
      if os.path.isdir(filepath):
        self._SendAlertEvent(
            self.atft_string.ALERT_CANNOT_SAVE_FILE + filepath.encode('utf-8'))
      warning_text = (
          filepath.encode('utf-8') +
          self.atft_string.ALERT_FILE_EXISTS)
      if os.path.isfile(filepath) and not self.ShowWarning(warning_text):
        return
    callback(filepath)

  def _LowKeyAlertEventHandler(self, event):
    """Show the alert box to alert user that the key in ATFA device is low.

    Args:
      event: The triggering event.
    """
    keys_left = event.GetValue()
    self.low_key_dialog.SetMessage(
        self.atft_string.ALERT_ADD_MORE_KEY(keys_left))
    self.low_key_dialog.CenterOnParent()
    self.low_key_dialog.ShowModal()

  def _UpdateMappingStatusHandler(self, event):
    """Update the device mapping status in the Mapping USB Location page.

    Args:
      event: The triggering event.
    """
    if self.app_settings_dialog:
      self.app_settings_dialog.UpdateMappingStatus()

    # Update the UI on the target devices (grey out unmapped devices).
    self._PrintTargetDevices()

  def _CreateThread(self, target, *args):
    """Create and start a thread.

    Args:
      target: The function that the thread should run.
      *args: The arguments for the function
    Returns:
      The thread object
    """
    t = threading.Thread(target=target, args=args)
    t.setDaemon(True)
    t.start()
    return t

  def _ListDevices(self):
    """List fastboot devices.
    """

    # We need to check the lock to prevent two _ListDevices running at the same
    # time.
    if self.listing_device_lock.acquire(False):
      operation = 'List Devices'
      try:
        self.atft_manager.ListDevices()
      except DeviceCreationException as e:
        self._HandleException('W', e, operation, e.devices)
      except OsVersionNotAvailableException as e:
        e.msg = 'Failed to get ATFA version'
        self._HandleException('W', e, operation, e.devices)
        self._SendAlertEvent(self.atft_string.ALERT_INCOMPATIBLE_ATFA)
      except OsVersionNotCompatibleException as e:
        e.msg = 'Incompatible ATFA version, version is ' + str(e.version)
        self._HandleException('W', e, operation, e.devices)
        self._SendAlertEvent(self.atft_string.ALERT_INCOMPATIBLE_ATFA)
      except FastbootFailure as e:
        self._HandleException('W', e, operation)
      finally:
        # 'Release the lock'.
        self.listing_device_lock.release()
      wx.QueueEvent(self, Event(self.dev_listed_event, wx.ID_ANY))

  def _UpdateKeysLeftInATFA(self):
    """Update the number of keys left in ATFA.

    Update the number of keys left for the selected product in the ATFA device.
    Note that this operation would possibly include downloading audit file
    operation, so you should not call this function within any operation.

    Returns:
      Whether the check succeed or not.
    """
    operation = 'Check ATFA status'
    self._SendOperationStartEvent(operation, self.atft_manager.GetATFADevice())
    self.PauseRefresh()

    try:
      if self.atft_manager.product_info:
        self.atft_manager.UpdateATFAKeysLeft(False)
      elif self.atft_manager.som_info:
        self.atft_manager.UpdateATFAKeysLeft(True)
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      return False
    except ProductNotSpecifiedException as e:
      self._HandleException('W', e, operation)
      return False
    except FastbootFailure as e:
      self._HandleException('E', e, operation)
      return False
    finally:
      self.ResumeRefresh()

    self._SendOperationSucceedEvent(operation)
    # Try to pull audit from ATFA if keys_left changes.
    self.audit.PullAudit(self._GetCachedATFAKeysLeft())
    return True

  def _GetCachedATFAKeysLeft(self):
    """Get the cached number of keys left in the ATFA device.

    Returns:
      The cached number of keys left in the ATFA.
    """
    return self.atft_manager.GetCachedATFAKeysLeft()

  def _ShowATFAStatus(self):
    """Show the attestation key status of the ATFA device.
    """
    try:
      self.atft_manager.CheckDevice(self.atft_manager.GetATFADevice())
    except DeviceNotFoundException:
      self._SendAlertEvent(self.atft_string.ALERT_NO_ATFA)
      return
    if self._UpdateKeysLeftInATFA():
      self._SendAlertEvent(
          self.atft_string.ALERT_KEYS_LEFT(self._GetCachedATFAKeysLeft()))

  def _FuseVbootKey(self, selected_serials):
    """Fuse the verified boot key to the devices.

    Args:
      selected_serials: The list of serial numbers for the selected devices.
    """
    pending_targets = []
    for serial in selected_serials:
      target = self.atft_manager.GetTargetDevice(serial)
      if not target or target.provision_status == ProvisionStatus.REBOOT_IN_PROGRESS:
        continue
      # Start state could be IDLE or FUSEVBOOT_FAILED
      if (self.test_mode or not target.provision_state.bootloader_locked):
        target.provision_status = ProvisionStatus.WAITING
        pending_targets.append(target)
      else:
        self._SendAlertEvent(self.atft_string.ALERT_FUSE_VBOOT_FUSED)

    for target in pending_targets:
      self._FuseVbootKeyTarget(target)

  def _FuseVbootKeyTarget(self, target, auto_prov=False):
    """Fuse the verified boot key to a specific device.

    We would first fuse the bootloader vboot key
    and then reboot the device to check whether the bootloader is locked.
    This function would block until the reboot succeed or timeout.

    Args:
      target: The target device DeviceInfo object.
      auto_prov: Whether this operation is done in automatic mode.
    """
    operation = 'Fuse bootloader verified boot key'
    serial = target.serial_number
    if not self._StartOperation(operation, target, True, auto_prov):
      return

    try:
      self.atft_manager.FuseVbootKey(target)
      self._SendOperationSucceedEvent(operation, target)

      operation = 'Verify bootloader locked, rebooting'
      self._SendOperationStartEvent(operation, target)

      if auto_prov:
        # Allow other devices to continue state transition.
        self.auto_prov_lock.release()

      # If the device would reboot after fusing vboot key, need to wait for
      # device to disappear, then the reboot command would hold until the
      # device is back online.
      time.sleep(1)

      success_msg = '{' + str(target) + '} ' + 'Reboot Succeed'
      timeout_msg = '{' + str(target) + '} ' + 'Reboot Failed! Timeout!'
      reboot_lock = threading.Lock()
      reboot_lock.acquire()

      def LambdaSuccessCallback(msg=success_msg, lock=reboot_lock):
        self._RebootSuccessCallback(msg, lock)

      def LambdaTimeoutCallback(msg=timeout_msg, lock=reboot_lock):
        self._RebootTimeoutCallback(msg, lock)

      # Reboot the device to verify the bootloader is locked.
      target.provision_status = ProvisionStatus.REBOOT_IN_PROGRESS
      wx.QueueEvent(self, Event(self.dev_listed_event, wx.ID_ANY))

      # Reboot would change device status, so we disable reading device status
      # during reboot.
      try:
        self.listing_device_lock.acquire()
        self.atft_manager.Reboot(
            target, self.reboot_timeout, LambdaSuccessCallback,
            LambdaTimeoutCallback)
      finally:
        self.listing_device_lock.release()
    except ProductNotSpecifiedException as e:
      self._HandleException('W', e, operation, [target])
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation, [target])
      return
    finally:
      self._EndOperation(target)

    # Wait until callback finishes. After the callback, reboot_lock would be
    # released.
    reboot_lock.acquire()
    if auto_prov:
      # Try to get our turn again.
      self.auto_prov_lock.acquire()

    target = self.atft_manager.GetTargetDevice(serial)
    if target and not target.provision_state.bootloader_locked:
      target.provision_status = ProvisionStatus.FUSEVBOOT_FAILED
      e = FastbootFailure('Status not updated.')
      self._HandleException('E', e, operation, [target])
      return

  def _RebootSuccessCallback(self, msg, lock):
    """The callback if reboot succeed.

    Args:
      msg: The message to be shown
      lock: The lock to indicate the callback is called.
    """
    self._SendPrintEvent(msg)
    self.log.Info('OpSucceed', msg)
    lock.release()

  def _RebootTimeoutCallback(self, msg, lock):
    """The callback if reboot timeout.

    Args:
      msg: The message to be shown
      lock: The lock to indicate the callback is called.
    """
    self._SendPrintEvent(msg)
    self.log.Error('OpException', msg)
    lock.release()

  def _FusePermAttr(self, selected_serials):
    """Fuse the permanent attributes to the target devices.

    Args:
      selected_serials: The list of serial numbers for the selected devices.
    """
    pending_targets = []
    for serial in selected_serials:
      target = self.atft_manager.GetTargetDevice(serial)
      if not target or (target.provision_status ==
                        ProvisionStatus.REBOOT_IN_PROGRESS):
        return
      # Start state could be FUSEVBOOT_SUCCESS or REBOOT_SUCCESS
      # or FUSEATTR_FAILED
      # Note: Reboot to check vboot is optional, user can skip that manually.
      if (self.test_mode or (
            target.provision_state.bootloader_locked and
            not target.provision_state.avb_perm_attr_set
          )):
        pending_targets.append(target)
      else:
        self._SendAlertEvent(self.atft_string.ALERT_FUSE_PERM_ATTR_FUSED)

    for target in pending_targets:
      self._FusePermAttrTarget(target)

  def _FusePermAttrTarget(self, target, auto_prov=False):
    """Fuse the permanent attributes to the specific target device.

    Args:
      target: The target device DeviceInfo object.
      auto_prov: Whether this operation is part of automatic operations.
    """
    operation = 'Fuse permanent attributes'
    if not self._StartOperation(operation, target, True, auto_prov):
      return

    try:
      self.atft_manager.FusePermAttr(target)
    except ProductNotSpecifiedException as e:
      self._HandleException('W', e, operation, [target])
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation, [target])
      return
    finally:
      self._EndOperation(target)

    self._SendOperationSucceedEvent(operation, target)

  def _LockAvb(self, selected_serials):
    """Lock android verified boot for selected devices.

    Args:
      selected_serials: The list of serial numbers for the selected devices.
    """
    pending_targets = []
    for serial in selected_serials:
      target = self.atft_manager.GetTargetDevice(serial)
      if not target or (target.provision_status ==
                        ProvisionStatus.REBOOT_IN_PROGRESS):
        continue
      # Start state could be FUSEATTR_SUCCESS or LOCKAVB_FAIELD
      if (self.test_mode or(
            target.provision_state.bootloader_locked and
            target.provision_state.avb_perm_attr_set and
            not target.provision_state.avb_locked
          )):
        target.provision_status = ProvisionStatus.WAITING
        pending_targets.append(target)
      else:
        self._SendAlertEvent(self.atft_string.ALERT_LOCKAVB_LOCKED)

    for target in pending_targets:
      self._LockAvbTarget(target)

  def _LockAvbTarget(self, target, auto_prov=False):
    """Lock android verified boot for the specific target device.

    Args:
      target: The target device DeviceInfo object.
      auto_prov: Whether this operation is part of automatic operations.
    """
    operation = 'Lock android verified boot'
    if not self._StartOperation(operation, target, True, auto_prov):
      return

    try:
      self.atft_manager.LockAvb(target)
    except FastbootFailure as e:
      self._HandleException('E', e, operation, [target])
      return
    finally:
      self._EndOperation(target)

    self._SendOperationSucceedEvent(operation, target)

  def _UnlockAvb(self, selected_serials):
    """Unlock android verified boot for selected devices.

    Args:
      selected_serials: The list of serial numbers for the selected devices.
    """
    pending_targets = []
    for serial in selected_serials:
      target = self.atft_manager.GetTargetDevice(serial)
      if not target or (target.provision_status ==
                        ProvisionStatus.REBOOT_IN_PROGRESS):
        continue
      if (self.test_mode or target.provision_state.avb_locked):
        target.provision_status = ProvisionStatus.WAITING
        pending_targets.append(target)
      else:
        self._SendAlertEvent(self.atft_string.ALERT_UNLOCKAVB_UNLOCKED)

    for target in pending_targets:
      self._UnlockAvbTarget(target)

  def _UnlockAvbTarget(self, target, auto_prov=False):
    """Unlock android verified boot for the specific target device.

    Args:
      target: The target device DeviceInfo object.
      auto_prov: Whether this operation is part of automatic operations.
    """
    operation = 'Unlock android verified boot'
    if not self._StartOperation(operation, target, True, auto_prov):
      return

    try:
      self.atft_manager.UnlockAvb(target)
    except FastbootFailure as e:
      self._HandleException('E', e, operation, [target])
      return
    finally:
      self._EndOperation(target)

    self._SendOperationSucceedEvent(operation, target)

  def _CheckLowKeyAlert(self):
    """Check whether the attestation key is lower than the threshold.

    If so, an alert box would appear to warn the user.
    """
    operation = 'Check ATFA Status'

    if self._UpdateKeysLeftInATFA():
      keys_left = self._GetCachedATFAKeysLeft()
      if keys_left and keys_left >= 0:
        first_warning = self.change_threshold_dialog.GetFirstWarning()
        second_warning = self.change_threshold_dialog.GetSecondWarning()
        if (second_warning and keys_left < second_warning and
            not self.second_key_alert_shown):
          self.second_key_alert_shown = True
          if not self.first_key_alert_shown:
            # If already past the first alert and second alert is shown,
            # We would not show the first alert again.
            self.first_key_alert_shown = True
          self._SendLowKeyAlertEvent(keys_left)
          return

        if keys_left < first_warning and not self.first_key_alert_shown:
          self.first_key_alert_shown = True
          self._SendLowKeyAlertEvent(keys_left)
          return

  def _Reboot(self):
    """Reboot ATFA device.
    """
    operation = 'Reboot ATFA device'
    atfa_dev = self.atft_manager.GetATFADevice()
    if not self._StartOperation(operation, atfa_dev):
      return

    try:
      self.atft_manager.RebootATFA()
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation, [atfa_dev])
      return
    finally:
      self._EndOperation(atfa_dev)

    self._SendOperationSucceedEvent(operation)

  def _Shutdown(self):
    """Shutdown ATFA device.
    """
    operation = 'Shutdown ATFA device'
    atfa_dev = self.atft_manager.GetATFADevice()
    if not self._StartOperation(operation, atfa_dev):
      return

    try:
      self.atft_manager.ShutdownATFA()
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation, [atfa_dev])
      return
    finally:
      self._EndOperation(atfa_dev)

    self._SendOperationSucceedEvent(operation)

  def _ManualProvision(self, selected_serials, is_som_key):
    """Manual provision the selected devices.

    Args:
      selected_serials: A list of the serial numbers of the target devices.
      is_som_key: Whether provision som key (or product key).
    """
    # Reset alert_shown
    self.first_key_alert_shown = False
    self.second_key_alert_shown = False
    for serial in selected_serials:
      target = self.atft_manager.GetTargetDevice(serial)
      if (not target or
          target.provision_status == ProvisionStatus.REBOOT_IN_PROGRESS):
        continue
      if target.provision_status == ProvisionStatus.WAITING:
        self._ProvisionTarget(target, is_som_key)

  def _ProvisionTarget(self, target, is_som_key, auto_prov=False):
    """Provision the attestation key into the specific target.

    Args:
      target: The target to be provisioned.
      is_som_key: Whether provision som key (or product key).
      auto_prov: Whether this operation is part of automatic operations.
    """
    operation = 'Product Attestation Key Provisioning'
    if is_som_key:
      operation = 'SoM Attestation Key Provisioning'
    atfa_dev = self.atft_manager.GetATFADevice()
    if not self._StartOperation(operation, target, True, auto_prov):
      return
    if not self._StartOperation(operation, atfa_dev, True, auto_prov):
     return

    provision_failed = False
    try:
      self.atft_manager.Provision(target, is_som_key)
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation, [target])
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation, [target])
      provision_failed = True
    finally:
      self._EndOperation(atfa_dev)
      self._EndOperation(target)

    if provision_failed:
      # If it fails, one key might also be used.
      self._UpdateKeysLeftInATFA()
      return

    self._SendOperationSucceedEvent(operation, target)
    if not is_som_key:
      self.log.Info(
        'Key Provisioning',
        'Device: ' + str(target) + ' AT-ATTEST-UUID: ' + target.at_attest_uuid)
    self._CheckLowKeyAlert()

  def _HandleStateTransition(self, target):
    """Handles the state transition for automatic key provisioning.

    A normal flow should be:
      WAITING->FUSEVBOOT_SUCCESS->REBOOT_SUCCESS->LOCKAVB_SUCCESS
      ->PROVISION_SUCCESS

    Args:
      target: The target device object.
    """
    self.auto_prov_lock.acquire()
    serial = target.serial_number
    i = 0
    while True:
      target = self.atft_manager.GetTargetDevice(serial)
      if not target or ProvisionStatus.isFailed(target.provision_status):
        break
      if not self.auto_prov:
        # Auto provision mode exited.
        break
      if i == len(self.provision_steps):
        break
      operation = self.provision_steps[i]
      i += 1
      if (not target.provision_state.bootloader_locked and
          operation == 'FuseVbootKey'):
        self._FuseVbootKeyTarget(target, True)
        continue
      elif (not target.provision_state.avb_perm_attr_set and
            operation == 'FusePermAttr'):
        self._FusePermAttrTarget(target, True)
        continue
      elif (not target.provision_state.avb_locked and operation == 'LockAvb'):
        self._LockAvbTarget(target, True)
        continue
      elif (target.provision_state.avb_locked and operation == 'UnlockAvb'):
        self._UnlockAvbTarget(target, True)
        continue
      elif (not target.provision_state.product_provisioned and
            operation == 'ProvisionProduct'):
        # Provision product key.
        self._ProvisionTarget(target, False, True)
        if self._GetCachedATFAKeysLeft() == 0:
          # No keys left. If it's auto provisioning mode, exit.
          self._SendAlertEvent(self.atft_string.ALERT_NO_KEYS_LEFT_LEAVE_PROV)
          self.autoprov_button.SetValue(False)
          self.OnLeaveAutoProv()
        continue
      elif (not target.provision_state.som_provisioned and
            operation == 'ProvisionSom'):
        # Provision som key.
        self._ProvisionTarget(target, True, True)
        if self._GetCachedATFAKeysLeft() == 0:
          # No keys left. If it's auto provisioning mode, exit.
          self._SendAlertEvent(self.atft_string.ALERT_NO_KEYS_LEFT_LEAVE_PROV)
          self.autoprov_button.SetValue(False)
          self.OnLeaveAutoProv()

    if target and self._is_provision_steps_finished(target.provision_state):
      self._SendOperationSucceedEvent('All steps', target)

    self.auto_dev_serials.remove(serial)
    self.auto_prov_lock.release()

  def _ProcessKeyCallback(self, pathname):
    self._CreateThread(self._ProcessKey, pathname)

  def _ProcessKey(self, pathname, auto_process=False):
    """Ask ATFA device to store and process the stored keybundle.

    Args:
      pathname: The path name to the key bundle file.
      auto_process: Whether this operation is automatic.
    """
    operation = 'ATFA device store and process key bundle'
    atfa_dev = self.atft_manager.GetATFADevice()
    show_alert = True
    blocking = False
    if auto_process:
      # If this processing is trigger automatically, then there might be chance
      # when another operation is ongoing. We would block this thread until
      # there is no other operation and we could start the processing.
      show_alert = False
      blocking = True
    if not self._StartOperation(operation, atfa_dev, show_alert, blocking):
      return
    try:
      self.atft_manager.CheckDevice(atfa_dev)
      atfa_dev.Download(pathname)
      self.atft_manager.ProcessATFAKey()
      self._SendOperationSucceedEvent(operation)

    except DeviceNotFoundException as e:
      if auto_process:
        raise e
        return
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      if auto_process:
        raise e
        return
      self._HandleException('E', e, operation)
      if show_alert:
        self._SendAlertEvent(
            self.atft_string.ALERT_PROCESS_KEY_FAILURE + e.msg.encode('utf-8'))
      return
    finally:
      self._EndOperation(atfa_dev)

    # Check ATFA status after new key stored.
    if self.atft_manager.product_info or self.atft_manager.som_info:
      # Force download audit file if you switch to a new product.
      self.audit.ResetKeysLeft()
      self._UpdateKeysLeftInATFA()

  def _UpdateATFACallback(self, pathname):
    self._CreateThread(self._UpdateATFA, pathname)

  def _UpdateATFA(self, pathname):
    """Ask ATFA device to store and process the stored keybundle.

    Args:
      pathname: The path name to the key bundle file.
    """
    operation = 'Update ATFA device'
    atfa_dev = self.atft_manager.GetATFADevice()
    if not self._StartOperation(operation, atfa_dev):
      return
    try:
      atfa_dev.Download(pathname)
      self.atft_manager.UpdateATFA()
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation)
      self._SendAlertEvent(
          self.atft_string.ALERT_UPDATE_FAILURE + e.msg.encode('utf-8'))
      return
    finally:
      self._EndOperation(atfa_dev)

    self._SendOperationSucceedEvent(operation)

  def _PurgeKey(self):
    """Purge the key for the selected product in the ATFA device.
    """
    operation = 'ATFA purge key'
    atfa_dev = self.atft_manager.GetATFADevice()
    if not self._StartOperation(operation, atfa_dev):
      return
    try:
      is_som_key = self.atft_manager.som_info is not None
      self.atft_manager.PurgeATFAKey(is_som_key)
      self._SendOperationSucceedEvent(operation)
    except ProductNotSpecifiedException as e:
      self._HandleException('W', e, operation)
      return
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation)
      self._SendAlertEvent(
          self.atft_string.ALERT_PURGE_KEY_FAILURE + e.msg.encode('utf-8'))
      return
    finally:
      self._EndOperation(atfa_dev)
    # Update the number of keys left, should be 0.
    self._UpdateKeysLeftInATFA()

  def _GetRegFile(self, filepath):
    self._CreateThread(self._GetFileFromATFA, filepath, 'reg', True, False)

  def _GetAuditFile(self, filepath):
    self._CreateThread(self._GetFileFromATFA, filepath, 'audit', True, False)

  def _GetFileFromATFA(self, filepath, file_type, show_alert, blocking):
    """Download a type of file from the ATFA device.

    Args:
      filepath: The path to the downloaded file.
      file_type: The type of the file to be downloaded. Supported options are
        'reg'/'audit'.
      show_alert: Whether to display an alert if error happens.
      blocking: Whether to block the operation on other pending operations.
    Returns:
      Whether this operation succeed.
    """
    atfa_dev = self.atft_manager.GetATFADevice()
    if file_type == 'audit':
      alert_message = self.atft_string.ALERT_AUDIT_DOWNLOADED
      alert_cannot_get_file_message = self.atft_string.ALERT_CANNOT_GET_AUDIT
    elif file_type == 'reg':
      alert_message = self.atft_string.ALERT_REG_DOWNLOADED
      alert_cannot_get_file_message = self.atft_string.ALERT_CANNOT_GET_REG
    else:
      # Should not reach here.
      return False
    operation = 'ATFA device prepare and download ' + file_type + ' file'
    if not self._StartOperation(operation, atfa_dev, show_alert, blocking):
      return False
    try:
      filepath = filepath.encode('utf-8')
      write_file = open(filepath, 'w+')
      write_file.close()
      self.atft_manager.PrepareFile(file_type)
      atfa_dev.Upload(filepath)
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      if show_alert:
        self._SendAlertEvent(self.atft_string.ALERT_NO_ATFA)
      return False
    except IOError as e:
      self._HandleException('E', e)
      if show_alert:
        self._SendAlertEvent(self.atft_string.ALERT_CANNOT_SAVE_FILE + filepath)
      return False
    except FastbootFailure as e:
      self._HandleException('E', e)
      if show_alert:
        self._SendAlertEvent(
            alert_cannot_get_file_message + e.msg.encode('utf-8'))
      return False
    finally:
      self._EndOperation(atfa_dev)

    self._SendOperationSucceedEvent(operation)
    if show_alert:
      self._SendAlertEvent(alert_message + filepath)
    return True

  def _GetSelectedSerials(self):
    """Get the list of selected serial numbers in the device list.

    Returns:
      A list of serial numbers of the selected target devices.
    """
    selected_serials = []
    if self.SINGLE_DEVICE_MODE == self.mapping_mode:
      unmapped_component = self.unmapped_target_dev_component;
      if unmapped_component.serial_number:
        selected_serials.append(unmapped_component.serial_number)
    else:
      i = 0
      for dev_component in self.target_devs_components:
        if self.device_usb_locations[i] and dev_component.selected:
          selected_serials.append(dev_component.serial_number)
        i += 1
    return selected_serials

  def ManualMapUSBLocationToSlot(self, event):
    """The handler to map a USB location to an UI slot in the tool.

    This handler would be triggered if the 'map' button on the USB Location
    Mapping interface is clicked. It would map the connected Android Things
    device to the selected UI slot.

    Args:
      event: The triggering event.
    """
    selected = [
        dev_component
            for dev_component in self.app_settings_dialog.dev_mapping_components
            if dev_component.selected]

    if not selected:
      self._SendAlertEvent(self.atft_string.ALERT_NO_MAP_DEVICE_CHOSEN)
      return

    component = selected[0]
    index = component.index

    if self.device_usb_locations[index]:
      # If this slot was already mapped, warn the user.
      warning_message = self.atft_string.ALERT_REMAP_SLOT_LOCATION(
          str(component.index + 1), self.device_usb_locations[component.index])
      if not self.ShowWarning(warning_message):
        return

    if not self.atft_manager.target_devs:
      self._SendAlertEvent(self.atft_string.ALERT_NO_TARGET_DEVICE)
      return

    if len(self.atft_manager.target_devs) > 1:
      self._SendAlertEvent(self.atft_string.ALERT_MULTIPLE_TARGET_DEVICE)
      return

    location = self.atft_manager.target_devs[0].location

    # Check if the location is already mounted to a slot, if so gives a warning
    # since this mapping would overwrite previous configuration.
    for i in range(TARGET_DEV_SIZE):
      if (self.device_usb_locations[i] and
          self.device_usb_locations[i] == location and i != component.index):
        warning_text = self.atft_string.ALERT_REMAP_LOCATION_SLOT(
            self.device_usb_locations[i], str(i + 1))
        if not self.ShowWarning(warning_text):
          self.SendUpdateMappingEvent()
          return
        else:
          self.device_usb_locations[i] = None

    self.device_usb_locations[index] = location
    self.SendUpdateMappingEvent()

  def UnmapUSBLocationToSlot(self, event):
    """The handler to unmap a UI slot from a mapped USB port.

    This handler would be triggered if the 'unmap' button on the USB Location
    Mapping interface is clicked. It would unmap a UI slot from a already mapped
    USB port.

    Args:
      event: The triggering event.
    """

    selected = [
        dev_component
            for dev_component in self.app_settings_dialog.dev_mapping_components
            if dev_component.selected]

    if not selected:
      self._SendAlertEvent(self.atft_string.ALERT_NO_UNMAP_DEVICE_CHOSEN)
      return

    component = selected[0]
    index = component.index

    if self.device_usb_locations[index]:
      # If this slot was already mapped, warn the user.
      if not self.ShowWarning(self.atft_string.ALERT_UNMAP):
        return

    self.device_usb_locations[index] = None
    self.SendUpdateMappingEvent()

  def ChangeLanguage(self, language_text):
    """Change the language setting according to the selected language name.

    Args:
      language_text: The name of the language selected.
    """
    for i in range(len(LANGUAGE_OPTIONS)):
      if LANGUAGE_OPTIONS[i] == language_text:
        self.language = LANGUAGE_CONFIGS[i]
        self._SendAlertEvent(
            self.atft_string.ALERT_LANGUAGE_RESTART[self.GetLanguageIndex()])
        break

  def ChangePassword(self, old_password, new_password):
    result = Atft.VerifyPassword(old_password, self.password_hash)
    if result:
      new_hash = Atft.GeneratePasswordHash(new_password)
      self.password_hash = new_hash
      self.log.Info('Password', 'Password Changed')
      self._SendPrintEvent('Password Changed!')
      return True
    else:
      e = PasswordErrorException()
      self._HandleException('W', e)
      self._SendAlertEvent(self.atft_string.ALERT_WRONG_ORIG_PASSWORD)
      return False

  def OnClose(self, event):
    """This is the place for close callback, need to do cleanups.

    Args:
      event: The triggering event.
    """
    self._StoreConfigToFile()
    # Stop the refresh timer on close.
    self.StopRefresh()
    # Stop automatic processing keys.
    self.key_handler.StopProcessKey()
    self.DeletePendingEvents()
    self.Destroy()

def main():
  app = wx.App()
  Atft()
  app.MainLoop()


if __name__ == '__main__':
  main()
