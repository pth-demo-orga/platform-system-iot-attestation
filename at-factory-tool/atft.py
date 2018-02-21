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
from datetime import datetime
import json
import math
import os
import sys
import threading

from atftman import AtftManager
from atftman import ProvisionStatus
from atftman import RebootCallback

from fastboot_exceptions import DeviceCreationException
from fastboot_exceptions import DeviceNotFoundException
from fastboot_exceptions import FastbootFailure
from fastboot_exceptions import NoKeysException
from fastboot_exceptions import OsVersionNotAvailableException
from fastboot_exceptions import OsVersionNotCompatibleException
from fastboot_exceptions import ProductAttributesFileFormatError
from fastboot_exceptions import ProductNotSpecifiedException

import wx

if sys.platform.startswith('linux'):
  from fastbootsh import FastbootDevice
  from serialmapperlinux import SerialMapper
elif sys.platform.startswith('win'):
  from fastbootsubp import FastbootDevice
  from serialmapperwin import SerialMapper


# If this is set to True, no prerequisites would be checked against manual
# operation, such as you can do key provisioning before fusing the vboot key.
TEST_MODE = False


class AtftException(Exception):
  """The exception class to include device and operation information.
  """

  def __init__(self, exception, operation=None, target=None):
    """Init the exception class.

    Args:
      exception: The original exception object.
      operation: The operation that generates this exception.
      target: The operating target device.
    """
    Exception.__init__(self)
    self.exception = exception
    self.operation = operation
    self.target = target

  def __str__(self):
    msg = ''
    if self.target:
      msg += '{' + str(self.target) + '} '
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


class AtftLog(object):
  """The class to handle logging.

  Logs would be created under LOG_DIR with the time stamp when the log is
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

    log_files = []
    for file_name in os.listdir(self.log_dir):
      if (os.path.isfile(os.path.join(self.log_dir, file_name)) and
          file_name.startswith('atft_log_')):
        log_files.append(file_name)
    if not log_files:
      # Create the first log file.
      self._CreateLogFile()
    else:
      log_files.sort()
      self.log_dir_file = os.path.join(self.log_dir, log_files.pop())
    self.Info('Program', 'Program start')

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

  def _Output(self, code, tag, string):
    """Output a line of message to the log file.

    Args:
      code: The log level.
      tag: The log tag.
      string: The log message.
    """
    time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    message = '[{0}] {1}/{2}: {3}'.format(
        time, code, tag, string.replace('\n', '\t'))
    if self.log_dir_file:
      message += '\n'
      with self.lock:
        self._LimitSize(message)
        with open(self.log_dir_file, 'a') as log_file:
          log_file.write(message)
          log_file.flush()

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
    log_files = []
    for file_name in os.listdir(self.log_dir):
      if (os.path.isfile(os.path.join(self.log_dir, file_name)) and
          file_name.startswith('atft_log_')):
        log_files.append(file_name)

    if len(log_files) > self.log_file_number:
      # If file number exceeds LOG_FILE_NUMBER, then delete the oldest file.
      try:
        log_files.sort()
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
    return int((datetime.now() - datetime(1970, 1, 1)).total_seconds())

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

  def __init__(self, atft):
    """Initiate the dialog using the atft class instance.

    Args:
      atft: The atft class instance.
    """
    self.atft = atft
    self.first_warning = self.atft.DEFAULT_KEY_THRESHOLD_1
    self.second_warning = self.atft.DEFAULT_KEY_THRESHOLD_2

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
        self, wx.ID_ANY, self.atft.DIALOG_CHANGE_THRESHOLD_TEXT)
    title_font = wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    dialog_title.SetFont(title_font)
    panel_sizer.Add(dialog_title, 0, wx.ALL, 20)

  def _CreateFirstWarningInput(self, panel_sizer):
    line_sizer = wx.BoxSizer(wx.HORIZONTAL)
    first_warning_hint = wx.StaticText(
        self, wx.ID_ANY, self.atft.TITLE_FIRST_WARNING)
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
        self, wx.ID_ANY, self.atft.TITLE_SECOND_WARNING)
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
        self, label=self.atft.BUTTON_CANCEL, size=(130, 30), id=wx.ID_CANCEL)
    button_save = wx.Button(
        self, label=self.atft.BUTTON_SAVE, size=(130, 30), id=wx.ID_OK)
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

  def __init__(self, atft):
    """Initiate the dialog using the atft class instance.

    Args:
      atft: The atft class instance.
    """
    self.atft = atft
    self.settings = []
    self.menu_items = []
    self.current_setting = None

  def CreateDialog(self, *args, **kwargs):
    """The actual initializer to create the dialog.

    This function creates UI elements within the dialog and only need to be
    called once. This function should be called with the same argument for
    wx.Dialog class and should be called as part of the initialization after
    using __init__.
    """
    super(AppSettingsDialog, self).__init__(*args, **kwargs)
    self.SetForegroundColour(self.atft.COLOR_BLACK)
    self.SetBackgroundColour(self.atft.COLOR_WHITE)
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
        self, label=self.atft.BUTTON_CANCEL, size=(130, 30), id=wx.ID_CANCEL)
    button_map = wx.Button(
        self, label=self.atft.BUTTON_MAP, size=(130, 30), id=wx.ID_ANY)
    button_font = wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    button_save = wx.Button(
        self, label=self.atft.BUTTON_SAVE, size=(130, 30), id=wx.ID_ANY)
    button_map.SetFont(button_font)
    button_cancel.SetFont(button_font)
    button_save.SetFont(button_font)

    buttons_sizer.Add(button_cancel)
    buttons_sizer.Add(button_map, 0, wx.LEFT, 10)
    buttons_sizer.Add(button_save, 0, wx.LEFT, 10)

    self.button_cancel = button_cancel
    self.button_map = button_map
    self.button_save = button_save
    self.buttons_sizer = buttons_sizer
    self.panel_sizer.AddSpacer(20)
    self.panel_sizer.Add(buttons_sizer, 0, wx.ALIGN_RIGHT | wx.RIGHT, 10)

    # Bind handlers
    self.button_map.Bind(wx.EVT_BUTTON, self.atft.MapUSBLocationToSlot)
    self.button_cancel.Bind(wx.EVT_BUTTON, self.OnExit)
    self.button_save.Bind(wx.EVT_BUTTON, self.OnSaveSetting)

  def _CreateUSBMappingPanel(self):
    """Create the panel for mapping USB location to UI slot."""
    menu_map_usb = wx.Button(
        self, label=self.atft.BUTTON_MAP_USB_LOCATION, style=wx.BORDER_NONE)
    menu_map_usb.Bind(wx.EVT_BUTTON, self.ShowUSBMappingSetting)
    menu_map_usb.SetFont(self.menu_font)
    self.menu_map_usb = menu_map_usb
    self.AddMenuItem(self.menu_map_usb)
    usb_mapping_panel = wx.Window(self, style=wx.BORDER_SUNKEN)
    self.settings_sizer.Add(usb_mapping_panel, 0, wx.EXPAND)
    usb_mapping_panel.SetBackgroundColour(self.atft.COLOR_WHITE)
    usb_mapping_panel_sizer = wx.BoxSizer(wx.VERTICAL)
    usb_mapping_panel_sizer.SetMinSize((0, 480))
    usb_mapping_title = wx.StaticText(
        usb_mapping_panel, wx.ID_ANY, self.atft.TITLE_MAP_USB)
    usb_mapping_panel_sizer.AddSpacer(10)
    usb_mapping_panel_sizer.Add(usb_mapping_title, 0, wx.EXPAND | wx.ALL, 10)
    usb_mapping_panel_sizer.AddSpacer(10)
    usb_mapping_title_font = wx.Font(
        12, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    usb_mapping_title.SetFont(usb_mapping_title_font)
    self.atft.dev_mapping_components = self.atft.CreateTargetDeviceList(
        usb_mapping_panel, usb_mapping_panel_sizer, True)
    i = 0
    for dev_component in self.atft.dev_mapping_components:
      handler = lambda event, index=i : self.atft._MapUSBToSlotHandler(
          event, index)
      # Bind the select handler
      self.atft._BindEventRecursive(wx.EVT_LEFT_DOWN, dev_component.panel, handler)
      i += 1

    usb_mapping_panel.SetSizerAndFit(usb_mapping_panel_sizer)
    self.usb_mapping_panel = usb_mapping_panel
    self.settings.append(self.usb_mapping_panel)

  def _CreateLanguagePanel(self):
    """Create the panel for setting language."""
    menu_language = wx.Button(
        self, label=self.atft.BUTTON_LANGUAGE_PREFERENCE, style=wx.BORDER_NONE)
    menu_language.Bind(wx.EVT_BUTTON, self.ShowLanguageSetting)
    self.menu_language = menu_language
    self.AddMenuItem(self.menu_language)
    language_setting = wx.Window(self, size=(0, 480))
    language_setting.SetBackgroundColour(self.atft.COLOR_WHITE)
    language_setting_sizer = wx.BoxSizer(wx.VERTICAL)
    self.settings_sizer.Add(language_setting)
    language_title = wx.StaticText(
        language_setting, wx.ID_ANY, self.atft.TITLE_SELECT_LANGUAGE)
    language_title_font = wx.Font(
        14, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    language_title.SetFont(language_title_font)
    language_setting_sizer.AddSpacer(10)
    language_setting_sizer.Add(language_title, 0, wx.EXPAND | wx.LEFT, 20)
    language_setting_sizer.AddSpacer(10)
    language_setting_list = wx.ComboBox(
        language_setting, wx.ID_ANY, style=wx.CB_READONLY | wx.CB_DROPDOWN,
        value=self.atft.LANGUAGE_OPTIONS[self.atft.GetLanguageIndex()],
        choices=self.atft.LANGUAGE_OPTIONS,
        size=(250, 30))
    language_setting_sizer.Add(language_setting_list, 0, wx.LEFT, 20)
    language_setting.SetSizerAndFit(language_setting_sizer)
    self.language_setting_list = language_setting_list
    self.language_setting = language_setting
    self.settings.append(self.language_setting)

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
    for dev_component in self.atft.dev_mapping_components:
      if self.atft.device_usb_locations[i]:
        dev_component.status.SetLabel(self.atft.STATUS_MAPPED)
      else:
        dev_component.status.SetLabel(self.atft.STATUS_NOT_MAPPED)
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
    self.buttons_sizer.Layout()
    self.current_setting = self.language_setting
    self.current_menu = self.menu_language
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
      self.atft.ChangeLanguage(language_text)
      self.EndModal(0)
      return

  def OnExit(self, event):
    """Exit handler when user clicks cancel or press 'esc'.

    Args:
      event: The triggering event.
    """
    self.atft.ClearATFADiscoveryCallback()
    event.Skip()


class Atft(wx.Frame):
  """wxpython class to handle all GUI commands for the ATFA.

  Creates the GUI and provides various functions for interacting with an
  ATFA and an Android Things device.

  """
  CONFIG_FILE = 'config.json'

  ID_TOOL_PROVISION = 1
  ID_TOOL_CLEAR = 2

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

  # How many target devices allowed.
  TARGET_DEV_SIZE = 6

  LANGUAGE_OPTIONS = ['English', '简体中文']
  LANGUAGE_CONFIGS = ['eng', 'cn']

  def __init__(self):

    self.configs = self.ParseConfigFile()

    self.SetLanguage()

    self.TITLE += ' ' + self.ATFT_VERSION

    # The atft_manager instance to manage various operations.
    self.atft_manager = self.CreateAtftManager()

    # The target devices refresh timer object.
    self.refresh_timer = None

    # The callback to wait for the appearance of an ATFA device for USB location
    # mapping.
    self.wait_atfa_callback = None

    # The field to sort target devices
    self.sort_by = self.atft_manager.SORT_BY_LOCATION

    # List of serial numbers for the devices in auto provisioning mode.
    self.auto_dev_serials = []

    # Store the last refreshed target list, we use this list to prevent
    # refreshing the same list.
    self.last_target_list = []

    # Indicate whether in auto provisioning mode.
    self.auto_prov = False

    # Indicate whether refresh is paused. If we could acquire this lock, this
    # means that the refresh is paused. We would pause the refresh during each
    # fastboot command since on Windows, a fastboot device would disappear from
    # fastboot devices while a fastboot command is issued.
    self.refresh_pause_lock = threading.Semaphore(value=0)

    # 'fastboot devices' can only run sequentially, so we use this lock to check
    # if there's already a 'fastboot devices' command running. If so, we ignore
    # the second request.
    self.listing_device_lock = threading.Lock()

    # To prevent low key alert to show by each provisioning.
    # We only show it once per auto provision.
    self.first_key_alert_shown = False
    self.second_key_alert_shown = False

    # Lock to make sure only one device is doing auto provisioning at one time.
    self.auto_prov_lock = threading.Lock()

    # Lock for showing alert box
    self.alert_lock = threading.Lock()

    # Supervisor Mode
    self.sup_mode = True

    self.InitializeUI()

    self.log = self.CreateAtftLog()

    # Leave supervisor mode
    self._OnToggleSupMode(None)

    if self.configs == None:
      self.ShowAlert(self.ALERT_FAIL_TO_PARSE_CONFIG)
      sys.exit(0)

    if not self.log.log_dir_file:
      self._SendAlertEvent(self.ALERT_FAIL_TO_CREATE_LOG)

    self.StartRefreshingDevices()

    self.ShowStartScreen()

  def CreateAtftManager(self):
    """Create an AtftManager object.

    This function exists for test mocking.
    """
    return AtftManager(FastbootDevice, SerialMapper, self.configs)

  def CreateAtftLog(self):
    """Create an AtftLog object.

    This function exists for test mocking.
    """
    return AtftLog(self.LOG_DIR, self.LOG_SIZE, self.LOG_FILE_NUMBER)

  def ParseConfigFile(self):
    """Parse the configuration file and read in the necessary configurations.

    Returns:
      The parsed configuration map.
    """
    # Give default values
    self.ATFT_VERSION = 'v0.0'
    self.COMPATIBLE_ATFA_VERSION = '0'
    self.DEVICE_REFRESH_INTERVAL = 1.0
    self.DEFAULT_KEY_THRESHOLD_1 = None
    self.DEFAULT_KEY_THRESHOLD_2 = None
    self.LOG_DIR = None
    self.LOG_SIZE = 0
    self.LOG_FILE_NUMBER = 0
    self.LANGUAGE = 'eng'
    self.REBOOT_TIMEOUT = 0
    self.ATFA_REBOOT_TIMEOUT = 0
    self.PRODUCT_ATTRIBUTE_FILE_EXTENSION = '*.atpa'
    self.KEY_FILE_EXTENSION = '*.atfa'
    self.UPDATE_FILE_EXTENSION = '*.upd'

    # The list to store the device location for each target device slot. If the
    # slot is not mapped, it will be None.
    self.device_usb_locations = []
    for i in range(0, self.TARGET_DEV_SIZE):
      self.device_usb_locations.append(None)

    config_file_path = os.path.join(self._GetCurrentPath(), self.CONFIG_FILE)
    if not os.path.exists(config_file_path):
      return None

    with open(config_file_path, 'r') as config_file:
      configs = json.loads(config_file.read())

    if not configs:
      return None

    try:
      self.ATFT_VERSION = str(configs['ATFT_VERSION'])
      self.COMPATIBLE_ATFA_VERSION = str(configs['COMPATIBLE_ATFA_VERSION'])
      self.DEVICE_REFRESH_INTERVAL = float(configs['DEVICE_REFRESH_INTERVAL'])
      if 'DEFAULT_KEY_THRESHOLD_1' in configs:
        self.DEFAULT_KEY_THRESHOLD_1 = int(configs['DEFAULT_KEY_THRESHOLD_1'])
      if 'DEFAULT_KEY_THRESHOLD_2' in configs:
        self.DEFAULT_KEY_THRESHOLD_2 = int(configs['DEFAULT_KEY_THRESHOLD_2'])
      self.LOG_DIR = str(configs['LOG_DIR'])
      self.LOG_SIZE = int(configs['LOG_SIZE'])
      self.LOG_FILE_NUMBER = int(configs['LOG_FILE_NUMBER'])
      self.LANGUAGE = str(configs['LANGUAGE'])
      self.REBOOT_TIMEOUT = float(configs['REBOOT_TIMEOUT'])
      self.ATFA_REBOOT_TIMEOUT = float(configs['ATFA_REBOOT_TIMEOUT'])
      self.PRODUCT_ATTRIBUTE_FILE_EXTENSION = str(
          configs['PRODUCT_ATTRIBUTE_FILE_EXTENSION'])
      self.KEY_FILE_EXTENSION = str(configs['KEY_FILE_EXTENSION'])
      self.UPDATE_FILE_EXTENSION = str(configs['UPDATE_FILE_EXTENSION'])
      if 'DEVICE_USB_LOCATIONS' in configs:
        self.device_usb_locations = configs['DEVICE_USB_LOCATIONS']
    except (KeyError, ValueError):
      return None

    return configs

  def _StoreConfigToFile(self):
    """Store the configuration to the configuration file.

    By storing the configuration back, the program would remember the
    configuration if it's opened again.
    """
    self.configs['DEVICE_USB_LOCATIONS'] = self.device_usb_locations
    self.configs['LANGUAGE'] = self.LANGUAGE
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
    for index in range(0, len(self.LANGUAGE_CONFIGS)):
      if self.LANGUAGE == self.LANGUAGE_CONFIGS[index]:
        return index
    return -1

  def SetLanguage(self):
    """Set the string constants according to the language setting.
    """
    index = self.GetLanguageIndex()

    # Top level menus
    self.MENU_APPLICATION = ['Application', '应用'][index]
    self.MENU_KEY_PROVISIONING = ['Key Provisioning', '密钥传输'][index]
    self.MENU_ATFA_DEVICE = ['ATFA Device', 'ATFA 管理'][index]
    self.MENU_AUDIT = ['Audit', '审计'][index]
    self.MENU_DOWNLOAD_AUDIT = ['Download Audit File', '下载审计文件'][index]
    self.MENU_KEY_MANAGEMENT = ['Key Management', '密钥管理'][index]

    # Second level menus
    self.MENU_CLEAR_COMMAND = ['Clear Command Output', '清空控制台'][index]
    self.MENU_SHOW_STATUS_BAR = ['Show Statusbar', '显示状态栏'][index]
    self.MENU_CHOOSE_PRODUCT = ['Choose Product', '选择产品'][index]
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
    self.TITLE = ['Google Android Things Factory Tool',
                  'Google Android Things 工厂程序'][index]

    # Area titles
    self.TITLE_ATFA_DEV = ['ATFA Device: ', 'ATFA 设备： '][index]
    self.TITLE_PRODUCT_NAME = ['Product: ', '产品： '][index]
    self.TITLE_PRODUCT_NAME_NOTCHOSEN = ['Not Chosen', '未选择'][index]
    self.TITLE_KEYS_LEFT = ['Attestation Keys Left:', '剩余密钥:'][index]
    self.TITLE_TARGET_DEV = ['Target Devices', '目标设备'][index]
    self.TITLE_COMMAND_OUTPUT = ['Command Output', '控制台输出'][index]
    self.TITLE_MAP_USB = [
        'Insert one ATFA device into the USB port you want to map, then select '
        'one of the six corresponding\nUI slots. This UI slot would be '
        'mapped to the USB port with the ATFA plugged in.',
        '将一个ATFA设备插入到你想关联的USB接口，然后选择界面上六个目标设备位置中的一个。\n'
        '这个目标设备位置将被关联到你插入ATFA设备的USB接口'][index]
    self.TITLE_FIRST_WARNING = ['1st\twarning: ', '警告一：'][index]
    self.TITLE_SECOND_WARNING = ['2nd\twarning: ', '警告二：'][index]
    self.TITLE_SELECT_LANGUAGE = ['Select a language', '选择一种语言'][index]

    # Field names
    self.FIELD_SERIAL_NUMBER = ['SN', '序列号'][index]
    self.FIELD_USB_LOCATION = ['USB Location', '插入位置'][index]
    self.FIELD_STATUS = ['Status', '状态'][index]
    self.FIELD_SERIAL_WIDTH = 200
    self.FIELD_USB_WIDTH = 350
    self.FIELD_STATUS_WIDTH = 240

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

    # Buttons
    self.BUTTON_ENTER_SUP_MODE = ['Enter Supervisor Mode', '进入管理模式'][index]
    self.BUTTON_LEAVE_SUP_MODE = ['Leave Supervisor Mode', '离开管理模式'][index]
    self.BUTTON_MAP_USB_LOCATION = ['Map USB Locations', '关联USB位置'][index]
    self.BUTTON_LANGUAGE_PREFERENCE = ['Language Preference', '语言偏好'][index]
    self.BUTTON_REMAP = ['Remap', '重新关联'][index]
    self.BUTTON_MAP = ['Map', '关联'][index]
    self.BUTTON_CANCEL = ['Cancel', '取消'][index]
    self.BUTTON_SAVE = ['Save', '保存'][index]

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
        'Failed to find or parse config file!',
        '无法找到或解析配置文件！'][index]
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
    self.ALERT_PROV_PROVED = [
        'Cannot provision device that is not ready for provisioning or '
        'already provisioned!',
        '无法传输密钥给一个不在正确状态或者已经拥有密钥的设备！'][index]
    self.ALERT_NO_MAP_DEVICE_CHOSEN = [
        'No device location chosen for mapping!',
        ' 未选择要关联的设备位置'][index]
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

    self.STATUS_MAPPED = ['Mapped', '已关联位置'][index]
    self.STATUS_NOT_MAPPED = ['Not mapped', '未关联位置'][index]
    self.STATUS_MAPPING = ['Mapping', '正在关联'][index]

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

    self.SetTitle(self.TITLE)
    self.panel.SetSizerAndFit(self.main_box)
    self.Show(True)

    # App Settings Dialog
    self.app_settings_dialog = AppSettingsDialog(self)
    self.app_settings_dialog.CreateDialog(
        self, wx.ID_ANY, self.MENU_APP_SETTINGS)

    # Change Key Threshold Dialog
    self.change_threshold_dialog = ChangeThresholdDialog(self)
    self.change_threshold_dialog.CreateDialog(
        self,
        wx.ID_ANY,
        self.DIALOG_CHANGE_THRESHOLD_TITLE)

    # Low Key Alert Dialog
    self.low_key_dialog = wx.MessageDialog(
        self,
        self.DIALOG_LOW_KEY_TEXT,
        self.DIALOG_LOW_KEY_TITLE,
        style=wx.OK | wx.ICON_EXCLAMATION | wx.CENTRE)

    # General Alert Dialog
    self.alert_dialog = wx.MessageDialog(
        self,
        self.DIALOG_ALERT_TEXT,
        self.DIALOG_ALERT_TITLE,
        style=wx.OK | wx.ICON_EXCLAMATION | wx.CENTRE)

    self._CreateBindEvents()

  def _CreateAppMenu(self):
    """Create the app menu items."""
    app_menu = wx.Menu()
    self.menubar.Append(app_menu, self.MENU_APPLICATION)
    # App Menu Options
    menu_app_settings = app_menu.Append(
        wx.ID_ANY, self.MENU_APP_SETTINGS)
    self.Bind(wx.EVT_MENU, self.ChangeSettings, menu_app_settings)

    menu_choose_product = app_menu.Append(
        wx.ID_ANY, self.MENU_CHOOSE_PRODUCT)
    self.Bind(wx.EVT_MENU, self.ChooseProduct, menu_choose_product)

    menu_key_threshold = app_menu.Append(
        wx.ID_ANY, self.MENU_KEY_THRESHOLD)
    self.Bind(wx.EVT_MENU, self.OnChangeKeyThreshold, menu_key_threshold)

    menu_clear_command = app_menu.Append(
        wx.ID_ANY, self.MENU_CLEAR_COMMAND)

    self.Bind(wx.EVT_MENU, self.OnClearCommandWindow, menu_clear_command)

    self.menu_show_status_bar = app_menu.Append(
        wx.ID_ANY, self.MENU_SHOW_STATUS_BAR, kind=wx.ITEM_CHECK)
    app_menu.Check(self.menu_show_status_bar.GetId(), True)
    self.Bind(wx.EVT_MENU, self.ToggleStatusBar, self.menu_show_status_bar)

    menu_quit = app_menu.Append(wx.ID_EXIT, self.MENU_QUIT)
    self.Bind(wx.EVT_MENU, self.OnQuit, menu_quit)
    self.app_menu = app_menu

  def _CreateProvisionMenu(self):
    """Create the provision menu items."""
    provision_menu = wx.Menu()
    self.menubar.Append(provision_menu, self.MENU_KEY_PROVISIONING)
    # Key Provision Menu Options
    menu_manual_fuse_vboot = provision_menu.Append(
        wx.ID_ANY, self.MENU_MANUAL_FUSE_VBOOT)
    self.Bind(wx.EVT_MENU, self.OnFuseVbootKey, menu_manual_fuse_vboot)

    menu_manual_fuse_attr = provision_menu.Append(
        wx.ID_ANY, self.MENU_MANUAL_FUSE_ATTR)
    self.Bind(wx.EVT_MENU, self.OnFusePermAttr, menu_manual_fuse_attr)

    menu_manual_lock_avb = provision_menu.Append(
        wx.ID_ANY, self.MENU_MANUAL_LOCK_AVB)
    self.Bind(wx.EVT_MENU, self.OnLockAvb, menu_manual_lock_avb)

    menu_manual_prov = provision_menu.Append(
        wx.ID_ANY, self.MENU_MANUAL_PROV)
    self.Bind(wx.EVT_MENU, self.OnManualProvision, menu_manual_prov)

    self.provision_menu = provision_menu

  def _CreateATFAMenu(self):
    """Create the ATFA menu items."""
    atfa_menu = wx.Menu()
    self.menubar.Append(atfa_menu, self.MENU_ATFA_DEVICE)
    # ATFA Menu Options
    menu_atfa_status = atfa_menu.Append(wx.ID_ANY, self.MENU_ATFA_STATUS)
    self.Bind(wx.EVT_MENU, self.OnCheckATFAStatus, menu_atfa_status)

    menu_reg_file = atfa_menu.Append(wx.ID_ANY, self.MENU_REG_FILE)
    self.Bind(wx.EVT_MENU, self.OnGetRegFile, menu_reg_file)

    menu_update = atfa_menu.Append(wx.ID_ANY, self.MENU_ATFA_UPDATE)
    self.Bind(wx.EVT_MENU, self.OnUpdateAtfa, menu_update)

    menu_reboot = atfa_menu.Append(wx.ID_ANY, self.MENU_REBOOT)
    self.Bind(wx.EVT_MENU, self.OnReboot, menu_reboot)

    menu_shutdown = atfa_menu.Append(wx.ID_ANY, self.MENU_SHUTDOWN)
    self.Bind(wx.EVT_MENU, self.OnShutdown, menu_shutdown)

    self.atfa_menu = atfa_menu

  def _CreateAuditMenu(self):
    """Create the audit menu items."""
    audit_menu = wx.Menu()
    self.menubar.Append(audit_menu, self.MENU_AUDIT)
    # Audit Menu Options
    menu_download_audit = audit_menu.Append(
        wx.ID_ANY, self.MENU_DOWNLOAD_AUDIT)
    self.Bind(wx.EVT_MENU, self.OnGetAuditFile, menu_download_audit)

    self.audit_menu = audit_menu

  def _CreateKeyMenu(self):
    """Create the key menu items."""
    key_menu = wx.Menu()
    self.menubar.Append(key_menu, self.MENU_KEY_MANAGEMENT)
    # Key Management Menu Options
    menu_storekey = key_menu.Append(wx.ID_ANY, self.MENU_STOREKEY)
    self.Bind(wx.EVT_MENU, self.OnStoreKey, menu_storekey)

    menu_purgekey = key_menu.Append(wx.ID_ANY, self.MENU_PURGE)
    self.Bind(wx.EVT_MENU, self.OnPurgeKey, menu_purgekey)

    self.key_menu = key_menu

  def _CreateHeaderPanel(self):
    """Create the header panel.

    The header panel contains the supervisor button, product information and
    ATFA device information.
    """
    header_panel = wx.Window(self.panel)
    header_panel.SetForegroundColour(self.COLOR_BLACK)
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
    self.button_supervisor.SetForegroundColour(self.COLOR_BLACK)
    header_panel_right_sizer.Add(self.button_supervisor, 0, wx.ALIGN_RIGHT)
    self.button_supervisor_toggle = wx.Button(
        header_panel, wx.ID_ANY, style=wx.BU_LEFT,
        label=self.BUTTON_LEAVE_SUP_MODE, name=self.BUTTON_LEAVE_SUP_MODE,
        size=(200, 30))
    button_supervisor_font = wx.Font(
        10, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.button_supervisor_toggle.SetFont(button_supervisor_font)
    self.button_supervisor_toggle.SetForegroundColour(self.COLOR_BLACK)
    self.button_supervisor_toggle.Hide()
    header_panel_right_sizer.Add(
        self.button_supervisor_toggle, 0, wx.ALIGN_RIGHT)
    self.header_panel_right_sizer = header_panel_right_sizer

    self.Bind(wx.EVT_BUTTON, self._OnToggleSupButton, self.button_supervisor)
    self.Bind(
        wx.EVT_BUTTON, self._OnToggleSupMode, self.button_supervisor_toggle)

    # Product Name Display
    product_name_title = wx.StaticText(
        header_panel, wx.ID_ANY, self.TITLE_PRODUCT_NAME)
    self.product_name_display = wx.StaticText(
        header_panel, wx.ID_ANY, self.TITLE_PRODUCT_NAME_NOTCHOSEN)
    product_name_font = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    product_name_title.SetFont(product_name_font)
    self.product_name_display.SetFont(product_name_font)
    product_name_sizer = wx.BoxSizer(wx.HORIZONTAL)
    product_name_sizer.Add(product_name_title)
    product_name_sizer.Add(self.product_name_display, 0, wx.LEFT, 2)
    header_panel_left_sizer.Add(product_name_sizer, 0, wx.ALL, 5)

    self.main_box.Add(header_panel, 0, wx.EXPAND)

    # Device Output Title
    atfa_dev_title = wx.StaticText(header_panel, wx.ID_ANY, self.TITLE_ATFA_DEV)
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
        target_devs_panel, wx.ID_ANY, self.TITLE_TARGET_DEV)
    target_dev_font = wx.Font(
        16, wx.FONTFAMILY_MODERN, wx.NORMAL, wx.FONTWEIGHT_BOLD)
    self.target_devs_title.SetFont(target_dev_font)
    self.target_devs_title_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.target_devs_title_sizer.Add(self.target_devs_title, 0, wx.LEFT, 10)

    target_devs_panel_sizer.Add(
        self.target_devs_title_sizer, 0, wx.TOP | wx.BOTTOM, 10)

    self.target_dev_components = self.CreateTargetDeviceList(
        target_devs_panel, target_devs_panel_sizer)

    target_devs_panel.SetSizerAndFit(target_devs_panel_sizer)
    target_devs_panel.SetBackgroundColour(self.COLOR_WHITE)

    self.main_box.Add(target_devs_panel, 0, wx.EXPAND)

  def _CreateCommandOutputPanel(self):
    """Create command output panel to show command outputs."""
    # Command Output Title
    self.cmd_output_wrap = wx.Window(self.panel)
    cmd_output_wrap_sizer = wx.BoxSizer(wx.VERTICAL)

    static_line = wx.StaticLine(self.cmd_output_wrap)
    static_line.SetForegroundColour(self.COLOR_BLACK)
    cmd_output_wrap_sizer.Add(static_line, 0, wx.EXPAND)

    command_title_panel = wx.Window(self.cmd_output_wrap)
    command_title_sizer = wx.BoxSizer(wx.VERTICAL)
    command_title = wx.StaticText(
        command_title_panel, wx.ID_ANY, self.TITLE_COMMAND_OUTPUT)
    command_title.SetForegroundColour(self.COLOR_BLACK)
    command_title_font = wx.Font(
        16, wx.FONTFAMILY_MODERN, wx.NORMAL, wx.FONTWEIGHT_BOLD)
    command_title.SetFont(command_title_font)
    command_title_sizer.Add(command_title, 0, wx.ALL, 5)
    command_title_panel.SetSizerAndFit(command_title_sizer)
    command_title_panel.SetBackgroundColour(self.COLOR_WHITE)
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
    cmd_output_panel.SetBackgroundColour(self.COLOR_WHITE)

    cmd_output_wrap_sizer.Add(cmd_output_panel, 0, wx.ALL | wx.EXPAND, 0)
    self.cmd_output_wrap.SetSizerAndFit(cmd_output_wrap_sizer)

    self.main_box.Add(self.cmd_output_wrap, 0, wx.EXPAND, 0)

  def _CreateStatusBar(self):
    """Create the bottom status bar."""
    self.statusbar = self.CreateStatusBar(1, style=wx.STB_DEFAULT_STYLE)
    self.statusbar.SetBackgroundColour(self.COLOR_BLACK)
    self.statusbar.SetForegroundColour(self.COLOR_WHITE)
    status_sizer = wx.BoxSizer(wx.VERTICAL)
    self.status_text = wx.StaticText(
        self.statusbar, wx.ID_ANY, self.TITLE_KEYS_LEFT)
    status_sizer.AddSpacer(5)
    status_sizer.Add(self.status_text, 0, wx.LEFT, 10)
    statusbar_font = wx.Font(
        10, wx.FONTFAMILY_MODERN, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.status_text.SetFont(statusbar_font)
    self.status_text.SetForegroundColour(self.COLOR_WHITE)
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
    self.start_screen.SetBackgroundColour(self.COLOR_BLACK)
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
        self.start_screen, label=self.MENU_CHOOSE_PRODUCT, size=(250, 50))
    font = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    button_choose_product.SetFont(font)
    button_choose_product.SetBackgroundColour(self.COLOR_DARK_GREY)
    button_choose_product.SetForegroundColour(self.COLOR_WHITE)

    start_screen_sizer.Add(button_choose_product, 0, wx.ALIGN_CENTER)
    button_choose_product.Bind(wx.EVT_BUTTON, self.ChooseProduct)
    self.start_screen.Layout()
    self.SetSize(self.start_screen.GetSize())
    self.CenterOnParent()

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

  def CreateTargetDeviceList(self, parent, parent_sizer, map_usb=False):
    """Create the grid style panel to display target device information.

    Args:
      parent: The parent window.
      parent_sizer: The parent sizer.
      map_usb: Whether the target list is for USB location mapping.
    Returns:
      A list of DevComponent object that contains necessary information and UI
        element about each target device.
    """
    # target device output components
    target_dev_components = []

    # The scale of the display size. We need a smaller version of the target
    # device list for the settings page, so we can use this scale factor to
    # scale the panel's size.
    scale = 1

    if map_usb:
      scale = 0.9

    # Device Output Window
    devices_list = wx.GridSizer(2, 3, 40 * scale, 0)
    parent_sizer.Add(devices_list, flag=wx.BOTTOM, border=20)

    class DevComponent(object):
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

    for i in range(0, self.TARGET_DEV_SIZE):
      dev_component = DevComponent(i)
      # Create each target device panel.
      target_devs_output_panel = wx.Window(parent, style=wx.BORDER_RAISED)
      target_devs_output_panel_sizer = wx.BoxSizer(wx.VERTICAL)
      dev_component.panel = target_devs_output_panel

      # Create the title panel.
      target_devs_output_title = wx.Window(
          target_devs_output_panel, style=wx.BORDER_NONE,
          size=(270 * scale, 50 * scale))
      target_devs_output_title.SetBackgroundColour(self.COLOR_WHITE)
      # Don't accept user input, otherwise user input would change the style.
      target_devs_output_title_sizer = wx.BoxSizer(wx.HORIZONTAL)
      target_devs_output_title.SetSizer(target_devs_output_title_sizer)
      dev_component.title_background = target_devs_output_title

      # The number in the title bar.
      target_devs_output_number = wx.StaticText(
          target_devs_output_title, wx.ID_ANY, str(i + 1).zfill(2))
      target_devs_output_title_sizer.Add(
          target_devs_output_number, 0, wx.ALL, 10)
      number_font = wx.Font(
          18, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_BOLD)
      target_devs_output_number.SetForegroundColour(self.COLOR_DARK_GREY)
      target_devs_output_number.SetFont(number_font)

      # The serial number in the title bar.
      target_devs_output_serial = wx.StaticText(
          target_devs_output_title, wx.ID_ANY, '')
      target_devs_output_serial.SetForegroundColour(self.COLOR_BLACK)
      target_devs_output_serial.SetMinSize((180 * scale, 0))
      target_devs_output_title_sizer.Add(
          target_devs_output_serial, 0, wx.TOP, 18)
      serial_font = wx.Font(
          9, wx.FONTFAMILY_MODERN, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
      target_devs_output_serial.SetFont(serial_font)
      dev_component.serial_text = target_devs_output_serial

      # The selected icon in the title bar
      selected_image = wx.Image('selected.png', type=wx.BITMAP_TYPE_PNG)
      selected_bitmap = wx.Bitmap(selected_image)
      selected_icon = wx.StaticBitmap(
          target_devs_output_title, bitmap=selected_bitmap)
      target_devs_output_title_sizer.Add(selected_icon, 0, wx.TOP, 12 * scale)

      # The device status panel.
      target_devs_output_status = wx.Window(
          target_devs_output_panel, style=wx.BORDER_NONE,
          size=(270 * scale, 110 * scale))
      target_devs_output_status.SetBackgroundColour(self.COLOR_GREY)
      target_devs_output_status_sizer = wx.BoxSizer(wx.HORIZONTAL)
      target_devs_output_status.SetSizer(target_devs_output_status_sizer)
      dev_component.status_background = target_devs_output_status

      # The device status string.
      device_status_string = ''
      target_devs_output_status_info = wx.StaticText(
          target_devs_output_status, wx.ID_ANY, device_status_string)
      font_size = 18
      if map_usb:
        font_size = 20
      status_font = wx.Font(
          font_size, wx.FONTFAMILY_MODERN, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
      target_devs_output_status_info.SetForegroundColour(self.COLOR_BLACK)
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

      devices_list.Add(
          target_devs_output_panel_sizer_wrap, 0, wx.LEFT | wx.RIGHT, 10)
      target_dev_components.append(dev_component)

    return target_dev_components

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
    msg = '[' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '] '
    msg += text + '\n'
    self.PrintToWindow(self.cmd_output, msg, True)

  def StartRefreshingDevices(self):
    """Refreshing the device list by interval of DEVICE_REFRESH_INTERVAL.
    """
    # If there's already a timer running, stop it first.
    self.StopRefresh()
    # Start a new timer.
    self.refresh_timer = threading.Timer(self.DEVICE_REFRESH_INTERVAL,
                                         self.StartRefreshingDevices)
    self.refresh_timer.start()

    if self.refresh_pause_lock.acquire(False):
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
      self.atft_manager.CheckDevice(self.atft_manager.atfa_dev)
    except DeviceNotFoundException:
      self._SendAlertEvent(self.ALERT_NO_ATFA)
      return
    self._CreateThread(self._Reboot)

  def OnShutdown(self, event):
    """Shutdown ATFA device asynchronously.

    Args:
      event: The triggering event.
    """
    try:
      self.atft_manager.CheckDevice(self.atft_manager.atfa_dev)
    except DeviceNotFoundException:
      self._SendAlertEvent(self.ALERT_NO_ATFA)
      return
    self._CreateThread(self._Shutdown)

  def OnEnterAutoProv(self):
    """Enter auto provisioning mode."""
    if self.auto_prov:
      return
    if (self.atft_manager.atfa_dev and self.atft_manager.product_info and
        self.atft_manager.GetATFAKeysLeft() > 0):
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
    for device in self.atft_manager.target_devs:
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
      self.button_supervisor_toggle.Layout()
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

  def OnLeaveSupMode(self):
    """Leave supervisor mode"""
    message = 'Leave supervisor mode'
    self.PrintToCommandWindow(message)
    self.log.Info('Supmode', message)
    self.sup_mode = False
    self.button_supervisor_toggle.SetLabel(self.BUTTON_ENTER_SUP_MODE)
    self.main_box.Hide(self.cmd_output_wrap)
    self.SetMenuBar(None)
    self.OnEnterAutoProv()

  def OnEnterSupMode(self):
    """Enter supervisor mode, ask for credential."""
    message = 'Enter supervisor mode'
    self.PrintToCommandWindow(message)
    self.log.Info('Supmode', message)
    self.sup_mode = True
    self.button_supervisor_toggle.SetLabel(self.BUTTON_LEAVE_SUP_MODE)
    self.SetMenuBar(self.menubar)
    self.cmd_output_wrap.Show()
    self.OnLeaveAutoProv()

  def OnManualProvision(self, event):
    """Manual provision key asynchronously.

    Args:
      event: The triggering event.
    """
    selected_serials = self._GetSelectedSerials()
    if not selected_serials:
      self._SendAlertEvent(self.ALERT_PROV_NO_SELECTED)
      return
    if not self.atft_manager.atfa_dev:
      self._SendAlertEvent(self.ALERT_PROV_NO_ATFA)
      return
    if self._GetCachedATFAKeysLeft() == 0:
      self._SendAlertEvent(self.ALERT_PROV_NO_KEYS)
      return
    self._CreateThread(self._ManualProvision, selected_serials)

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
      self._SendAlertEvent(self.ALERT_FUSE_NO_SELECTED)
      return
    if not self.atft_manager.product_info:
      self._SendAlertEvent(self.ALERT_FUSE_NO_PRODUCT)
      return

    self._CreateThread(self._FuseVbootKey, selected_serials)

  def OnFusePermAttr(self, event):
    """Fuse the permanent attributes to the target device asynchronously.

    Args:
      event: The triggering event.
    """
    selected_serials = self._GetSelectedSerials()
    if not selected_serials:
      self._SendAlertEvent(self.ALERT_FUSE_PERM_NO_SELECTED)
      return
    if not self.atft_manager.product_info:
      self._SendAlertEvent(self.ALERT_FUSE_PERM_NO_PRODUCT)
      return

    self._CreateThread(self._FusePermAttr, selected_serials)

  def OnLockAvb(self, event):
    """Lock the AVB asynchronously.

    Args:
      event: The triggering event
    """
    selected_serials = self._GetSelectedSerials()
    if not selected_serials:
      self._SendAlertEvent(self.ALERT_LOCKAVB_NO_SELECTED)
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

  def ChooseProduct(self, event):
    """Ask user to choose the product attributes file.

    Args:
      event: The triggering event.
    """
    message = self.DIALOG_CHOOSE_PRODUCT_ATTRIBUTE_FILE
    wildcard = self.PRODUCT_ATTRIBUTE_FILE_EXTENSION
    callback = self.ProcessProductAttributesFile
    data = self.SelectFileArg(message, wildcard, callback)
    event = Event(self.select_file_event, value=data)
    wx.QueueEvent(self, event)

  def ChangeSettings(self, event):
    self.app_settings_dialog.CenterOnParent()
    self.app_settings_dialog.ShowModal()

  def ProcessProductAttributesFile(self, pathname):
    """Process the selected product attributes file.

    Args:
      pathname: The path for the product attributes file to parse.
    """
    try:
      with open(pathname, 'r') as attribute_file:
        content = attribute_file.read()
        self.atft_manager.ProcessProductAttributesFile(content)
        if self.start_screen_shown:
          self.HideStartScreen()
        # Update the product name display
        self.product_name_display.SetLabelText(
            self.atft_manager.product_info.product_name)
        # User choose a new product, reset how many keys left.
        if self.atft_manager.atfa_dev and self.atft_manager.product_info:
          self._UpdateKeysLeftInATFA()
    except IOError:
      self._SendAlertEvent(
          self.ALERT_CANNOT_OPEN_FILE + pathname.encode('utf-8'))
    except ProductAttributesFileFormatError as e:
      self._SendAlertEvent(self.ALERT_PRODUCT_FILE_FORMAT_WRONG)
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
    message = self.DIALOG_SELECT_DIRECTORY
    try:
      filename = self.atft_manager.GetATFASerial() + '.reg'
    except DeviceNotFoundException as e:
      self._SendAlertEvent(self.ALERT_NO_ATFA)
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
    message = self.DIALOG_SELECT_DIRECTORY
    time = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    try:
      filename = self.atft_manager.GetATFASerial() + '_' + time +'.audit'
    except DeviceNotFoundException as e:
      self._SendAlertEvent(self.ALERT_NO_ATFA)
      return
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
      self.atft_manager.CheckDevice(self.atft_manager.atfa_dev)
    except DeviceNotFoundException:
      self._SendAlertEvent(self.ALERT_NO_ATFA)
      return

    message = self.DIALOG_CHOOSE_KEY_FILE
    wildcard = self.KEY_FILE_EXTENSION
    callback = self._ProcessKey
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
      self.atft_manager.CheckDevice(self.atft_manager.atfa_dev)
    except DeviceNotFoundException:
      self._SendAlertEvent(self.ALERT_NO_ATFA)
      return

    message = self.DIALOG_CHOOSE_UPDATE_FILE
    wildcard = self.UPDATE_FILE_EXTENSION
    callback = self._UpdateATFA
    data = self.SelectFileArg(message, wildcard, callback)
    event = Event(self.select_file_event, value=data)
    wx.QueueEvent(self, event)

  def OnPurgeKey(self, event):
    """Purge the keybundle for the product in the ATFA device.

    Args:
      event: The button click event.
    """
    try:
      self.atft_manager.CheckDevice(self.atft_manager.atfa_dev)
    except DeviceNotFoundException:
      self._SendAlertEvent(self.ALERT_NO_ATFA)
      return
    if self._ShowWarning(self.ALERT_CONFIRM_PURGE_KEY):
      self._CreateThread(self._PurgeKey)

  def ShowAlert(self, msg):
    """Show an alert box at the center of the parent window.

    Args:
      msg: The message to be shown in the alert box.
    """
    self.alert_dialog.CenterOnParent()
    self.alert_dialog.SetMessage(msg)
    self.alert_dialog.ShowModal()

  def OnClose(self, event):
    """This is the place for close callback, need to do cleanups.

    Args:
      event: The triggering event.
    """
    self._StoreConfigToFile()
    # Stop the refresh timer on close.
    self.StopRefresh()
    self.Destroy()

  def _HandleAutoProv(self):
    """Do the state transition for devices if in auto provisioning mode.

    """
    # All idle devices -> waiting.
    for target_dev in self.atft_manager.target_devs:
      if (target_dev.serial_number not in self.auto_dev_serials and
          target_dev.provision_status != ProvisionStatus.PROVISION_SUCCESS and
          not ProvisionStatus.isFailed(target_dev.provision_status)
          ):
        self.auto_dev_serials.append(target_dev.serial_number)
        target_dev.provision_status = ProvisionStatus.WAITING
        self._CreateThread(self._HandleStateTransition, target_dev)


  def _HandleKeysLeft(self):
    """Display how many keys left in the ATFA device.
    """
    text = self.TITLE_KEYS_LEFT
    color = self.COLOR_BLACK

    try:
      if not self.atft_manager.atfa_dev or not self.atft_manager.product_info:
        raise DeviceNotFoundException
      keys_left = self.atft_manager.GetATFAKeysLeft()
      if not keys_left:
        # If keys_left is not set, try to set it.
        self._CheckATFAStatus()
        keys_left = self.atft_manager.GetATFAKeysLeft()
      if not keys_left or keys_left < 0:
        raise NoKeysException

      text = self.TITLE_KEYS_LEFT + str(keys_left)
      first_warning = self.change_threshold_dialog.GetFirstWarning()
      second_warning = self.change_threshold_dialog.GetSecondWarning()
      if first_warning and keys_left < first_warning:
        color = self.COLOR_YELLOW
      if second_warning and keys_left < second_warning:
        color = self.COLOR_RED
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

  def _ShowWarning(self, text):
    """Show a warning to the user.

    Args:
      text: The content of the warning.
    Returns:
      True if the user clicks yes, otherwise, False.
    """
    warning_dialog = wx.MessageDialog(
        self, text,
        self.DIALOG_WARNING_TITLE, style=wx.YES_NO | wx.ICON_EXCLAMATION)
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

  def _HandleException(self, level, e, operation=None, target=None):
    """Handle the exception.

    Fires a exception event which would be handled in main thread. The exception
    would be shown in the command window. This function also wraps the
    associated operation and device object.

    Args:
      level: The log level for the exception.
      e: The original exception.
      operation: The operation associated with this exception.
      target: The DeviceInfo object associated with this exception.
    """
    atft_exception = AtftException(e, operation, target)
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
    self.Bind(self.map_usb_success_bind, self.MapUSBToSlotSuccessMainThread)

    i = 0
    for dev_component in self.target_dev_components:
      self._BindEventRecursive(
          wx.EVT_LEFT_DOWN, dev_component.panel,
          lambda event, index=i : self._DeviceSelectHandler(event, index))
      i += 1

    # Bind the close event
    self.Bind(wx.EVT_CLOSE, self.OnClose)

  def _DeviceSelectHandler(self, event, index):
    """The handler to handle user selecting a target device.
    Args:
      event: The triggering event.
      index: The index for the target device.
    """
    dev_component = self.target_dev_components[index]
    title_background = dev_component.title_background
    if not dev_component.selected:
      title_background.SetBackgroundColour(self.COLOR_PICK_BLUE)
    else:
      title_background.SetBackgroundColour(self.COLOR_WHITE)
    title_background.Refresh()
    dev_component.selected = not dev_component.selected
    event.Skip()

  def _MapUSBToSlotHandler(self, event, index):
    """The handler to map a target device's USB location to a UI slot.

    This should be a single select since user can only select one device
    location to be mapped.

    Args:
      event: The triggering event.
      index: The index for the target device.
    """
    i = 0
    for dev_component in self.dev_mapping_components:
      title_background = dev_component.title_background
      if i == index:
        title_background.SetBackgroundColour(self.COLOR_PICK_BLUE)
        if self.device_usb_locations[i]:
          # If already selected, change the button to 'remap'
          self.app_settings_dialog.button_map.SetLabel(self.BUTTON_REMAP)
        else:
          self.app_settings_dialog.button_map.SetLabel(self.BUTTON_MAP)
        self.app_settings_dialog.button_map.GetParent().Layout()
        dev_component.selected = True
      else:
        title_background.SetBackgroundColour(self.COLOR_WHITE)
        dev_component.selected = False
      title_background.Refresh()
      i += 1

    event.Skip()

  def _BindEventRecursive(self, event, widget, handler):
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
      self._BindEventRecursive(event, child, handler)

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

  def _SendOperationStartEvent(self, operation, target=None):
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
      if self.auto_prov and not self.atft_manager.atfa_dev:
        # If ATFA unplugged during normal mode,
        # exit the mode with an alert.
        self.OnLeaveAutoProv()
        # Add log here.
        self._SendAlertEvent('ATFA device unplugged, exit auto mode!')
      if not self.auto_prov:
        # If not already in auto provisioning mode, try enable it.
        self.OnEnterAutoProv()

    # If in auto provisioning mode, handle the newly added devices.
    if self.auto_prov:
      self._HandleAutoProv()

    self._PrintAtfaDevice()
    self._HandleATFADiscovery()
    if self.last_target_list == self.atft_manager.target_devs:
      # Nothing changes, no need to refresh
      return

    # Update the stored target list. Need to make a deep copy instead of copying
    # the reference.
    self.last_target_list = self._CopyList(self.atft_manager.target_devs)
    self._PrintTargetDevices()

  def _PrintAtfaDevice(self):
    """Print atfa device to atfa device output area.
    """
    if self.atft_manager.atfa_dev:
      atfa_message = str(self.atft_manager.atfa_dev)
    else:
      atfa_message = self.ALERT_NO_DEVICE
    self.atfa_dev_output.SetLabel(atfa_message)

  def _PrintTargetDevices(self):
    """Print target devices to target device output area.
    """
    target_devs = self.atft_manager.target_devs
    for i in range(0, self.TARGET_DEV_SIZE):
      serial_text = ''
      status = None
      serial_number = None
      if self.device_usb_locations[i]:
        for target_dev in target_devs:
          if target_dev.location == self.device_usb_locations[i]:
            serial_number = target_dev.serial_number
            serial_text = (
                self.FIELD_SERIAL_NUMBER + ': ' + str(serial_number))
            status = target_dev.provision_status

      self._ShowTargetDevice(i, serial_number, serial_text, status)

  def _ShowTargetDevice(self, i, serial_number, serial_text, status):
    """Display information about one target device.

    Args:
      i: The slot index of the device to be displayed.
      serial_nubmer: The serial number of the device.
      serial_text: The serial number text to be displayed.
      status: The provision status.
    """
    dev_component = self.target_dev_components[i]
    dev_component.serial_text.SetLabel(serial_text)
    dev_component.serial_number = serial_number
    color = self._GetStatusColor(status)
    if status != None:
      dev_component.status.SetLabel(
          ProvisionStatus.ToString(status, self.GetLanguageIndex()))
    else:
      dev_component.status.SetLabel('')
    dev_component.status_wrapper.Layout()
    dev_component.status_background.SetBackgroundColour(color)
    dev_component.status_background.Refresh()

  def _GetStatusColor(self, status):
    """Get the color according to the status.

    Args:
      status: The target device status.
    Returns:
      The color to be shown for the status.
    """
    if status == None:
      return self.COLOR_GREY
    if status == ProvisionStatus.IDLE:
      return self.COLOR_GREY
    if status == ProvisionStatus.PROVISION_SUCCESS:
      return self.COLOR_GREEN
    if ProvisionStatus.isFailed(status):
      return self.COLOR_RED
    return self.COLOR_BLUE

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
            self.ALERT_CANNOT_SAVE_FILE + filepath.encode('utf-8'))
      warning_text = filepath.encode('utf-8') + self.ALERT_FILE_EXISTS
      if os.path.isfile(filepath) and not self._ShowWarning(warning_text):
        return
    callback(filepath)

  def _LowKeyAlertEventHandler(self, event):
    """Show the alert box to alert user that the key in ATFA device is low.

    Args:
      event: The triggering event.
    """
    keys_left = event.GetValue()
    self.low_key_dialog.SetMessage(self.ALERT_ADD_MORE_KEY(keys_left))
    self.low_key_dialog.CenterOnParent()
    self.low_key_dialog.ShowModal()

  def _UpdateMappingStatusHandler(self, event):
    """Update the device mapping status in the Mapping USB Location page.

    Args:
      event: The triggering event.
    """
    if self.app_settings_dialog:
      self.app_settings_dialog.UpdateMappingStatus()

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
        self.atft_manager.ListDevices(self.sort_by)
      except DeviceCreationException as e:
        self._HandleException('W', e, operation, e.device)
      except OsVersionNotAvailableException as e:
        e.msg = 'Failed to get ATFA version'
        self._HandleException('W', e, operation, e.device)
        self._SendAlertEvent(self.ALERT_INCOMPATIBLE_ATFA)
      except OsVersionNotCompatibleException as e:
        e.msg = 'Incompatible ATFA version, version is ' + str(e.version)
        self._HandleException('W', e, operation, e.device)
        self._SendAlertEvent(self.ALERT_INCOMPATIBLE_ATFA)
      except FastbootFailure as e:
        self._HandleException('W', e, operation)
      finally:
        # 'Release the lock'.
        self.listing_device_lock.release()

      wx.QueueEvent(self, Event(self.dev_listed_event, wx.ID_ANY))

  def _UpdateKeysLeftInATFA(self):
    """Update the number of keys left in ATFA.

    Update the number of keys left for the selected product in the ATFA device.

    Returns:
      Whether the check succeed or not.
    """
    operation = 'Check ATFA status'
    self._SendOperationStartEvent(operation)
    self.PauseRefresh()

    try:
      self.atft_manager.UpdateATFAKeysLeft()
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
      self.atft_manager.CheckDevice(self.atft_manager.atfa_dev)
    except DeviceNotFoundException:
      self._SendAlertEvent(self.ALERT_NO_ATFA)
      return
    if self._UpdateKeysLeftInATFA():
      self._SendAlertEvent(
          self.ALERT_KEYS_LEFT(self.atft_manager.GetATFAKeysLeft()))

  def _FuseVbootKey(self, selected_serials):
    """Fuse the verified boot key to the devices.

    Args:
      selected_serials: The list of serial numbers for the selected devices.
    """
    pending_targets = []
    for serial in selected_serials:
      target = self.atft_manager.GetTargetDevice(serial)
      if not target:
        continue
      # Start state could be IDLE or FUSEVBOOT_FAILED
      if (TEST_MODE or not target.provision_state.bootloader_locked):
        target.provision_status = ProvisionStatus.WAITING
        pending_targets.append(target)
      else:
        self._SendAlertEvent(self.ALERT_FUSE_VBOOT_FUSED)

    for target in pending_targets:
      self._FuseVbootKeyTarget(target)

  def _FuseVbootKeyTarget(self, target):
    """Fuse the verified boot key to a specific device.

    We would first fuse the bootloader vboot key
    and then reboot the device to check whether the bootloader is locked.
    This function would block until the reboot succeed or timeout.

    Args:
      target: The target device DeviceInfo object.
    """
    operation = 'Fuse bootloader verified boot key'
    serial = target.serial_number
    self._SendOperationStartEvent(operation, target)
    self.PauseRefresh()

    try:
      self.atft_manager.FuseVbootKey(target)
    except ProductNotSpecifiedException as e:
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation)
      return
    finally:
      self.ResumeRefresh()

    self._SendOperationSucceedEvent(operation, target)

    operation = 'Verify bootloader locked, rebooting'
    self._SendOperationStartEvent(operation, target)
    success_msg = '{' + str(target) + '} ' + 'Reboot Succeed'
    timeout_msg = '{' + str(target) + '} ' + 'Reboot Failed! Timeout!'
    reboot_lock = threading.Lock()
    reboot_lock.acquire()

    def LambdaSuccessCallback(msg=success_msg, lock=reboot_lock):
      self._RebootSuccessCallback(msg, lock)

    def LambdaTimeoutCallback(msg=timeout_msg, lock=reboot_lock):
      self._RebootTimeoutCallback(msg, lock)

    # Reboot the device to verify the bootloader is locked.
    try:
      target.provision_status = ProvisionStatus.REBOOT_ING
      wx.QueueEvent(self, Event(self.dev_listed_event, wx.ID_ANY))

      # Reboot would change device status, so we disable reading device status
      # during reboot.
      self.listing_device_lock.acquire()
      self.atft_manager.Reboot(
          target, self.REBOOT_TIMEOUT, LambdaSuccessCallback,
          LambdaTimeoutCallback)
    except FastbootFailure as e:
      self._HandleException('E', e, operation)
      return
    finally:
      self.listing_device_lock.release()

    # Wait until callback finishes. After the callback, reboot_lock would be
    # released.
    reboot_lock.acquire()

    target = self.atft_manager.GetTargetDevice(serial)
    if target and not target.provision_state.bootloader_locked:
      target.provision_status = ProvisionStatus.FUSEVBOOT_FAILED
      e = FastbootFailure('Status not updated.')
      self._HandleException('E', e, operation)
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
      if not target:
        return
      # Start state could be FUSEVBOOT_SUCCESS or REBOOT_SUCCESS
      # or FUSEATTR_FAILED
      # Note: Reboot to check vboot is optional, user can skip that manually.
      if (TEST_MODE or (
            target.provision_state.bootloader_locked and
            not target.provision_state.avb_perm_attr_set
          )):
        pending_targets.append(target)
      else:
        self._SendAlertEvent(self.ALERT_FUSE_PERM_ATTR_FUSED)

    for target in pending_targets:
      self._FusePermAttrTarget(target)

  def _FusePermAttrTarget(self, target):
    """Fuse the permanent attributes to the specific target device.

    Args:
      target: The target device DeviceInfo object.
    """
    operation = 'Fuse permanent attributes'
    self._SendOperationStartEvent(operation, target)
    self.PauseRefresh()

    try:
      self.atft_manager.FusePermAttr(target)
    except ProductNotSpecifiedException as e:
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation)
      return
    finally:
      self.ResumeRefresh()

    self._SendOperationSucceedEvent(operation, target)

  def _LockAvb(self, selected_serials):
    """Lock android verified boot for selected devices.

    Args:
      selected_serials: The list of serial numbers for the selected devices.
    """
    pending_targets = []
    for serial in selected_serials:
      target = self.atft_manager.GetTargetDevice(serial)
      if not target:
        continue
      # Start state could be FUSEATTR_SUCCESS or LOCKAVB_FAIELD
      if (TEST_MODE or(
            target.provision_state.bootloader_locked and
            target.provision_state.avb_perm_attr_set and
            not target.provision_state.avb_locked
          )):
        target.provision_status = ProvisionStatus.WAITING
        pending_targets.append(target)
      else:
        self._SendAlertEvent(self.ALERT_LOCKAVB_LOCKED)

    for target in pending_targets:
      self._LockAvbTarget(target)

  def _LockAvbTarget(self, target):
    """Lock android verified boot for the specific target device.

    Args:
      target: The target device DeviceInfo object.
    """
    operation = 'Lock android verified boot'
    self._SendOperationStartEvent(operation, target)
    self.PauseRefresh()

    try:
      self.atft_manager.LockAvb(target)
    except FastbootFailure as e:
      self._HandleException('E', e, operation)
      return
    finally:
      self.ResumeRefresh()

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
    self._SendOperationStartEvent(operation)
    self.PauseRefresh()

    try:
      self.atft_manager.RebootATFA()
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation, self.atft_manager.atfa_dev)
      return
    finally:
      self.ResumeRefresh()

    self._SendOperationSucceedEvent(operation)

  def _Shutdown(self):
    """Shutdown ATFA device.
    """
    operation = 'Shutdown ATFA device'
    self._SendOperationStartEvent(operation)
    self.PauseRefresh()

    try:
      self.atft_manager.ShutdownATFA()
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation, self.atft_manager.atfa_dev)
      return
    finally:
      self.ResumeRefresh()

    self._SendOperationSucceedEvent(operation)

  def _ManualProvision(self, selected_serials):
    """Manual provision the selected devices.

    Args:
      selected_serials: A list of the serial numbers of the target devices.
    """
    # Reset alert_shown
    self.first_key_alert_shown = False
    self.second_key_alert_shown = False
    pending_targets = []
    for serial in selected_serials:
      target_dev = self.atft_manager.GetTargetDevice(serial)
      if not target_dev:
        continue
      pending_targets.append(target_dev)
      status = target_dev.provision_status
      if (TEST_MODE or (
          target_dev.provision_state.bootloader_locked and
          target_dev.provision_state.avb_perm_attr_set and
          target_dev.provision_state.avb_locked and
          not target_dev.provision_state.provisioned
        )):
        target_dev.provision_status = ProvisionStatus.WAITING
      else:
        self._SendAlertEvent(self.ALERT_PROV_PROVED)
    for target in pending_targets:
      if target.provision_status == ProvisionStatus.WAITING:
        self._ProvisionTarget(target)

  def _ProvisionTarget(self, target):
    """Provision the attestation key into the specific target.

    Args:
      target: The target to be provisioned.
    """
    operation = 'Attestation Key Provisioning'
    self._SendOperationStartEvent(operation, target)
    self.PauseRefresh()

    try:
      self.atft_manager.Provision(target)
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation, target)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation, target)
      # If it fails, one key might also be used.
      self._UpdateKeysLeftInATFA()
      return
    finally:
      self.ResumeRefresh()

    self._SendOperationSucceedEvent(operation, target)
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
    while not ProvisionStatus.isFailed(target.provision_status):
      target = self.atft_manager.GetTargetDevice(serial)
      if not target:
        # The target disappear somehow.
        break
      if not self.auto_prov:
        # Auto provision mode exited.
        break
      if not target.provision_state.bootloader_locked:
        self._FuseVbootKeyTarget(target)
        continue
      elif not target.provision_state.avb_perm_attr_set:
        self._FusePermAttrTarget(target)
        continue
      elif not target.provision_state.avb_locked:
        self._LockAvbTarget(target)
        continue
      elif not target.provision_state.provisioned:
        self._ProvisionTarget(target)
        if self._GetCachedATFAKeysLeft() == 0:
          # No keys left. If it's auto provisioning mode, exit.
          self._SendAlertEvent(self.ALERT_NO_KEYS_LEFT_LEAVE_PROV)
          self.OnLeaveAutoProv()
      break
    self.auto_dev_serials.remove(serial)
    self.auto_prov_lock.release()

  def _ProcessKey(self, pathname):
    """Ask ATFA device to store and process the stored keybundle.

    Args:
      pathname: The path name to the key bundle file.
    """
    operation = 'ATFA device store and process key bundle'
    self._SendOperationStartEvent(operation)
    self.PauseRefresh()
    try:
      self.atft_manager.atfa_dev.Download(pathname)
      self.atft_manager.ProcessATFAKey()
      self._SendOperationSucceedEvent(operation)

      # Check ATFA status after new key stored.
      if self.atft_manager.product_info:
        self._UpdateKeysLeftInATFA()
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation)
      self._SendAlertEvent(
          self.ALERT_PROCESS_KEY_FAILURE + e.msg.encode('utf-8'))
      return
    finally:
      self.ResumeRefresh()

  def _UpdateATFA(self, pathname):
    """Ask ATFA device to store and process the stored keybundle.

    Args:
      pathname: The path name to the key bundle file.
    """
    operation = 'Update ATFA device'
    self._SendOperationStartEvent(operation)
    self.PauseRefresh()
    try:
      self.atft_manager.atfa_dev.Download(pathname)
      self.atft_manager.UpdateATFA()
      self._SendOperationSucceedEvent(operation)

      # Check ATFA status after update succeeds.
      if self.atft_manager.product_info:
        self._UpdateKeysLeftInATFA()
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      return
    except FastbootFailure as e:
      self._HandleException('E', e, operation)
      self._SendAlertEvent(
          self.ALERT_UPDATE_FAILURE + e.msg.encode('utf-8'))
      return
    finally:
      self.ResumeRefresh()

  def _PurgeKey(self):
    """Purge the key for the selected product in the ATFA device.
    """
    operation = 'ATFA purge key'
    self._SendOperationStartEvent()
    self.PauseRefresh()
    try:
      self.atft_manager.PurgeATFAKey()
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
          self.ALERT_PURGE_KEY_FAILURE + e.msg.encode('utf-8'))
      return
    finally:
      self.ResumeRefresh()

  def _GetRegFile(self, filepath):
    self._GetFileFromATFA(filepath, 'reg')

  def _GetAuditFile(self, filepath):
    self._GetFileFromATFA(filepath, 'audit')

  def _GetFileFromATFA(self, filepath, file_type):
    """Download a type of file from the ATFA device.

    Args:
      file_type: The type of the file to be downloaded. Supported options are
        'reg'/'audit'.
    Args:
      pathname: The path to the downloaded file.
    """
    if file_type == 'audit':
      alert_message = self.ALERT_AUDIT_DOWNLOADED
      alert_cannot_get_file_message = self.ALERT_CANNOT_GET_AUDIT
    elif file_type == 'reg':
      alert_message = self.ALERT_REG_DOWNLOADED
      alert_cannot_get_file_message = self.ALERT_CANNOT_GET_REG
    else:
      # Should not reach here.
      return
    operation = 'ATFA device prepare and download ' + file_type + ' file'
    self._SendOperationStartEvent(operation)
    self.PauseRefresh()
    filepath = filepath.encode('utf-8')
    try:
      write_file = open(filepath, 'w+')
      write_file.close()
      self.atft_manager.PrepareFile(file_type)
      self.atft_manager.atfa_dev.Upload(filepath)
      self._SendOperationSucceedEvent(operation)
      self._SendAlertEvent(alert_message + filepath)
    except DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException('W', e, operation)
      self._SendAlertEvent(self.ALERT_NO_ATFA)
      return
    except IOError as e:
      self._HandleException('E', e)
      self._SendAlertEvent(self.ALERT_CANNOT_SAVE_FILE + filepath)
      return
    except FastbootFailure as e:
      self._HandleException('E', e)
      self._SendAlertEvent(
          alert_cannot_get_file_message + e.msg.encode('utf-8'))
      return
    finally:
      self.ResumeRefresh()

  def _GetSelectedSerials(self):
    """Get the list of selected serial numbers in the device list.

    Returns:
      A list of serial numbers of the selected target devices.
    """
    selected_serials = []
    i = 0
    for dev_component in self.target_dev_components:
      if self.device_usb_locations[i] and dev_component.selected:
        selected_serials.append(dev_component.serial_number)
      i += 1
    return selected_serials

  def MapUSBLocationToSlot(self, event):
    """The handler to map a USB location to an UI slot in the tool.

    This handler would be triggered if the 'map' button on the USB Location
    Mapping interface is clicked. We need to wait for an ATFA device to appear
    at a location and then map this location to a target device slot on the UI.

    Args:
      event: The triggering event.
    """
    selected = [
        dev_component for dev_component in self.dev_mapping_components if
            dev_component.selected]

    if not selected:
      self._SendAlertEvent(self.ALERT_NO_MAP_DEVICE_CHOSEN)
      return

    self.ClearATFADiscoveryCallback()

    component = selected[0]

    if self.device_usb_locations[component.index]:
      # If this slot was already mapped, warn the user.
      warning_message = self.ALERT_REMAP_SLOT_LOCATION(
          str(component.index + 1), self.device_usb_locations[component.index])
      if not self._ShowWarning(warning_message):
        return

    # Need to call parent.layout to refresh
    component.status.SetLabel(self.STATUS_MAPPING)
    component.status.GetParent().Layout()
    component.status_wrapper.Layout()

    success_callback = (
        lambda location, component=component :
        self.MapUSBToSlotSuccess(location, component))
    fail_callback = (
        lambda component=component : self.MapUSBToSlotTimeout(component))
    # Wait for an ATFA device to show up at the selected slot.
    self.wait_atfa_callback = RebootCallback(
        self.ATFA_REBOOT_TIMEOUT, success_callback, fail_callback)

  def ClearATFADiscoveryCallback(self):
    """Cancel a currently waiting for ATFA device and cancel the callback.
    """
    if not self.wait_atfa_callback:
      return
    lock = self.wait_atfa_callback.lock
    # If there's no callback current happening on this ATFA device, Release the
    # lock and the structure allocated to it.
    if lock and lock.acquire(False):
      # Remember to release the lock when the success callback is finished.
      self.wait_atfa_callback.Release()

    # If some of the mapping status is 'mapping', change them to the correct
    # status.
    self.app_settings_dialog.UpdateMappingStatus()

  def _HandleATFADiscovery(self):
    """This function handles ATFA device discovery.

    This function would call the success callback if an atfa device is found.
    """
    if not self.atft_manager.atfa_dev or not self.wait_atfa_callback:
      return
    # If we are waiting for an ATFA and we find one.
    lock = self.wait_atfa_callback.lock
    location = self.atft_manager.atfa_dev.location
    if lock and lock.acquire(False):
      self.wait_atfa_callback.success(location)

  class MapUSBToSlotArgs(object):

    def __init__(self, location, index):
      self.location = location
      self.index = index

  def MapUSBToSlotSuccess(self, location, component):
    """The success callback for location mapping.

    Note that we need to have UI operations and this callback would be called
    within a different thread, thus we need to use event to let the
    MapUSBToSlotSuccessMainThread to actually handles the callback.

    Args:
      location: The USB location to be mapped.
      component: The UI component to be mapped to the location.
    """
    evt = Event(
        self.map_usb_success_event, wx.ID_ANY,
        self.MapUSBToSlotArgs(location, component.index))
    wx.QueueEvent(self, evt)

  def MapUSBToSlotSuccessMainThread(self, event):
    """The success callback if we find an atfa device.

    We map the selected slot to the location where we find the device. We also
    release the resources after the callback.
    """
    location = event.GetValue().location
    index = event.GetValue().index
    # Check if the location is already mounted to a slot, if so gives a warning
    # since this mapping would overwrite previous configuration.
    for i in range(0, self.TARGET_DEV_SIZE):
      if (self.device_usb_locations[i] and
          self.device_usb_locations[i] == location and i != index):
        warning_text = self.ALERT_REMAP_LOCATION_SLOT(
            self.device_usb_locations[i], str(i + 1))
        if not self._ShowWarning(warning_text):
          self.SendUpdateMappingEvent()
          self.wait_atfa_callback.Release()
          self.wait_atfa_callback = None
          return
        else:
          self.device_usb_locations[i] = None

    self.device_usb_locations[index] = location
    self.SendUpdateMappingEvent()
    # Finished handling the success callback, release the callback lock.
    self.wait_atfa_callback.Release()
    self.wait_atfa_callback = None

  def MapUSBToSlotTimeout(self, component):
    """The callback when an ATFA device is not found before timeout.

    This means the mapping operation times out.
    """
    self._SendAlertEvent(self.ALERT_MAP_DEVICE_TIMEOUT)
    self.SendUpdateMappingEvent()
    self.wait_atfa_callback.Release()
    self.wait_atfa_callback = None

  def ChangeLanguage(self, language_text):
    """Change the language setting according to the selected language name.

    Args:
      language_text: The name of the language selected.
    """
    for i in range(0, len(self.LANGUAGE_OPTIONS)):
      if self.LANGUAGE_OPTIONS[i] == language_text:
        self.LANGUAGE = self.LANGUAGE_CONFIGS[i]
        self._SendAlertEvent(
            self.ALERT_LANGUAGE_RESTART[self.GetLanguageIndex()])
        break


def main():
  app = wx.App()
  Atft()
  app.MainLoop()


if __name__ == '__main__':
  main()
