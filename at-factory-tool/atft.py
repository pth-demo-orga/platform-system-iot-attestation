#!/usr/bin/python
"""Graphical tool for managing the ATFA and AT communication.

This tool allows for easy graphical access to common ATFA commands.  It also
locates Fastboot devices and can initiate communication between the ATFA and
an Android Things device.
"""
import copy
from datetime import datetime
import threading

import atftman
import fastboot_exceptions
from fastbootsh import FastbootDevice
from serialmapperlinux import SerialMapper
import wx


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
    msg += self.FormatException(self.exception)
    return msg

  def FormatException(self, e):
    """Format the exception. Concatenate the exception type with the message.

    Args:
      e: The exception to be printed.
    Returns:
      The exception message.
    """
    return '{0}: {1}'.format(e.__class__.__name__, e)


class Event(wx.PyCommandEvent):
  """The customized event class.
  """

  def __init__(self, etype, eid, value=None):
    """Create a new customized event.

    Args:
      etype: The event type.
      eid: The event id.
      value: The additional data included in the event.
    """
    wx.PyCommandEvent.__init__(self, etype, eid)
    # In order for thread safety, need to deep copy the string.
    self._value = copy.deepcopy(value)

  def GetValue(self):
    """Get the data included in this event.

    Returns:
      The event data.
    """
    return self._value


class Atft(wx.Frame):
  """wxpython class to handle all GUI commands for the ATFA.

  Creates the GUI and provides various functions for interacting with an
  ATFA and an Android Things device.

  """

  DEVICE_REFRESH_INTERVAL = 1.0
  SORT_BY_LOCATION_TEXT = 'Sort by location'
  SORT_BY_SERIAL_TEXT = 'Sort by serial'
  ID_TOOL_PROVISION = 1
  ID_TOOL_CLEAR = 2

  MENU_APPLICATION = ' Application '
  MENU_KEY_PROVISIONING = 'Key Provisioning'
  MENU_ATFA_DEVICE = ' ATFA Device '
  MENU_AUDIT = '    Audit    '
  MENU_KEY_MANAGEMENT = 'Key Management'

  TITLE = 'Google Android Things Factory Tool'

  def __init__(self, *args, **kwargs):
    # Style is unresizable default style.
    kwargs['style'] = wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER
    super(Atft, self).__init__(*args, **kwargs)

    self.atft_manager = atftman.AtftManager(FastbootDevice, SerialMapper)

    # The target devices refresh timer object
    self.refresh_timer = None

    # The field to sort target devices
    self.sort_by = self.atft_manager.SORT_BY_LOCATION

    # Store the last refreshed target list, we use this list to prevent
    # refreshing the same list.
    self.last_target_list = []

    # Indicate whether in auto provisioning mode.
    self.auto_prov = False

    # Indicate whether refresh is paused. We would pause the refresh during each
    # fastboot command because on Windows, a fastboot device would disappear
    # from fastboot devices while a command is issued.
    self.refresh_pause = False

    # 'fastboot devices' can only run sequentially, so we use this variable
    # to check if there's already a 'fastboot devices' command running. If so,
    # we ignore the second request.
    self.listing_device_lock = threading.Lock()

    # The main panel
    self.panel = wx.Panel(self)

    # Menu:
    # Application   -> Clear Command Output
    #               -> Show Statusbar
    #               -> Show Toolbar
    #               -> Choose Product
    #               -> Quit

    # Key Provision -> Fuse Vboot Key
    #               -> Fuse Permanent Attributes
    #               -> Provision Key

    # ATFA Device   -> ATFA Status
    #               -> Key Warning Threshold
    #               -> Reboot
    #               -> Shutdown

    # Audit         -> Storage Mode
    #               -> ???

    # Key Management-> Store Key Bundle
    #               -> Process Key Bundle

    # Add Menu items to Menubar
    self.menubar = wx.MenuBar()
    self.app_menu = wx.Menu()
    self.menubar.Append(self.app_menu, self.MENU_APPLICATION)
    self.provision_menu = wx.Menu()
    self.menubar.Append(self.provision_menu, self.MENU_KEY_PROVISIONING)
    self.atfa_menu = wx.Menu()
    self.menubar.Append(self.atfa_menu, self.MENU_ATFA_DEVICE)
    self.audit_menu = wx.Menu()
    self.menubar.Append(self.audit_menu, self.MENU_AUDIT)
    self.key_menu = wx.Menu()
    self.menubar.Append(self.key_menu, self.MENU_KEY_MANAGEMENT)

    # App Menu Options
    menu_clear_command = self.app_menu.Append(wx.ID_ANY, 'Clear Command Output')
    self.Bind(wx.EVT_MENU, self.OnClearCommandWindow, menu_clear_command)

    self.menu_shst = self.app_menu.Append(
        wx.ID_ANY, 'Show Statusbar', kind=wx.ITEM_CHECK)
    self.app_menu.Check(self.menu_shst.GetId(), True)
    self.Bind(wx.EVT_MENU, self.ToggleStatusBar, self.menu_shst)

    self.menu_shtl = self.app_menu.Append(
        wx.ID_ANY, 'Show Toolbar', kind=wx.ITEM_CHECK)
    self.app_menu.Check(self.menu_shtl.GetId(), True)
    self.Bind(wx.EVT_MENU, self.ToggleToolBar, self.menu_shtl)

    menu_quit = self.app_menu.Append(wx.ID_EXIT, 'Quit')
    self.Bind(wx.EVT_MENU, self.OnQuit, menu_quit)

    # Key Provision Menu Options
    menu_manual_prov = self.provision_menu.Append(wx.ID_ANY, 'Provision Key')

    # Audit Menu Options
    # TODO(shanyu): audit-related
    menu_storage = self.audit_menu.Append(wx.ID_ANY, 'Storage Mode')
    self.Bind(wx.EVT_MENU, self.OnStorageMode, menu_storage)

    # ATFA Menu Options
    menu_atfa_status = self.atfa_menu.Append(wx.ID_ANY, 'ATFA Status')

    menu_key_threshold = self.atfa_menu.Append(wx.ID_ANY,
                                               'Key Warning Threshold')

    menu_reboot = self.atfa_menu.Append(wx.ID_ANY, 'Reboot')
    self.Bind(wx.EVT_MENU, self.OnReboot, menu_reboot)

    menu_shutdown = self.atfa_menu.Append(wx.ID_ANY, 'Shutdown')
    self.Bind(wx.EVT_MENU, self.OnShutdown, menu_shutdown)

    # Key Management Menu Options
    menu_storekey = self.key_menu.Append(wx.ID_ANY, 'Store Key Bundle')
    menu_processkey = self.key_menu.Append(wx.ID_ANY, 'Process Key Bundle')

    self.SetMenuBar(self.menubar)

    # Toolbar buttons
    # -> 'Automatic Provision'
    # -> 'Refresh Devices'
    # -> 'Manual Provision'
    # -> 'ATFA Status'
    # -> 'Clear Command Output'
    self.toolbar = self.CreateToolBar()
    self.tools = []
    toolbar_auto_provision = self.toolbar.AddCheckTool(self.ID_TOOL_PROVISION,
                                                       'Automatic Provision',
                                                       wx.Bitmap('rocket.png'))
    self.toolbar_auto_provision = toolbar_auto_provision

    toolbar_refresh = self.toolbar.AddTool(wx.ID_ANY, 'Refresh Devices',
                                           wx.Bitmap('cw.png'))
    self.Bind(wx.EVT_TOOL, self.OnListDevices, toolbar_refresh)

    toolbar_manual_prov = self.toolbar.AddTool(wx.ID_ANY, 'Manual Provision',
                                               wx.Bitmap('download.png'))

    toolbar_atfa_status = self.toolbar.AddTool(wx.ID_ANY, 'ATFA Status',
                                               wx.Bitmap('pie-chart.png'))

    toolbar_clear_command = self.toolbar.AddTool(self.ID_TOOL_CLEAR,
                                                 'Clear Command Output',
                                                 wx.Bitmap('eraser.png'))
    self.Bind(wx.EVT_TOOL, self.OnClearCommandWindow, toolbar_clear_command)

    self.tools.append(toolbar_auto_provision)
    self.tools.append(toolbar_refresh)
    self.tools.append(toolbar_manual_prov)
    self.tools.append(toolbar_atfa_status)
    self.tools.append(toolbar_clear_command)

    self.vbox = wx.BoxSizer(wx.VERTICAL)
    self.st = wx.StaticLine(self.panel, wx.ID_ANY, style=wx.LI_HORIZONTAL)
    self.vbox.Add(self.st, 0, wx.ALL | wx.EXPAND, 5)

    # Device Output Title
    self.atfa_dev_title = wx.StaticText(self.panel, wx.ID_ANY, 'ATFA Device:')
    self.atfa_dev_title_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.atfa_dev_title_sizer.Add(self.atfa_dev_title, 0, wx.ALL, 5)
    self.vbox.Add(self.atfa_dev_title_sizer, 0, wx.LEFT)

    # Device Output Window
    self.atfa_devices_output = wx.TextCtrl(
        self.panel,
        wx.ID_ANY,
        size=(800, 20),
        style=wx.TE_MULTILINE | wx.TE_READONLY)
    self.vbox.Add(self.atfa_devices_output, 0, wx.ALL | wx.EXPAND, 5)

    # Device Output Title
    self.target_dev_title = wx.StaticText(self.panel, wx.ID_ANY,
                                          'Target Devices:')
    self.target_dev_title_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.target_dev_title_sizer.Add(self.target_dev_title, 0, wx.ALL, 5)
    self.vbox.Add(self.target_dev_title_sizer, 0, wx.LEFT)

    # Device Output Sort Button
    self.target_dev_toggle_sort = wx.Button(
        self.panel,
        wx.ID_ANY,
        self.SORT_BY_SERIAL_TEXT,
        style=wx.BU_LEFT,
        name='target_device_sort_button',
        size=wx.Size(110, 30))
    self.target_dev_title_sizer.Add(self.target_dev_toggle_sort, 0, wx.LEFT, 10)
    self.Bind(wx.EVT_BUTTON, self.OnToggleTargetSort,
              self.target_dev_toggle_sort)

    # Device Output Window
    self.target_devs_output = wx.ListCtrl(
        self.panel, wx.ID_ANY, size=(800, 200), style=wx.LC_REPORT)
    self.target_devs_output.InsertColumn(0, 'Serial Number', width=200)
    self.target_devs_output.InsertColumn(1, 'USB Location', width=400)
    self.target_devs_output.InsertColumn(2, 'Status', width=190)
    self.vbox.Add(self.target_devs_output, 0, wx.ALL | wx.EXPAND, 5)

    # Command Output Title
    self.command_title = wx.StaticText(self.panel, wx.ID_ANY, 'Command Output')
    self.command_title_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.command_title_sizer.Add(self.command_title, 0, wx.ALL, 5)
    self.vbox.Add(self.command_title_sizer, 0, wx.LEFT)

    # Command Output Window
    self.cmd_output = wx.TextCtrl(
        self.panel,
        wx.ID_ANY,
        size=(800, 320),
        style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
    self.vbox.Add(self.cmd_output, 0, wx.ALL | wx.EXPAND, 5)

    self.panel.SetSizer(self.vbox)
    self.SetMenuBar(self.menubar)
    self.toolbar.Realize()
    self.statusbar = self.CreateStatusBar()
    self.statusbar.SetStatusText('Ready')
    self.SetSize((800, 800))
    self.SetTitle(self.TITLE)
    self.Center()
    self.Show(True)

    # Change Key Threshold Dialog
    self.change_threshold_dialog = wx.TextEntryDialog(
        self,
        'ATFA Key Warning Threshold:',
        'Change ATFA Key Warning Threshold',
        style=wx.TextEntryDialogStyle | wx.CENTRE)

    # Low Key Alert Dialog
    self.low_key_dialog = wx.MessageDialog(
        self,
        '',
        'Low Key Alert',
        style=wx.OK | wx.ICON_EXCLAMATION | wx.CENTRE)

    # General Alert Dialog
    self.alert_dialog = wx.MessageDialog(
        self, '', 'Alert', style=wx.OK | wx.ICON_EXCLAMATION | wx.CENTRE)
    # Lock for showing alert box
    self.alert_lock = threading.Lock()

    self._CreateBindEvents()
    self.StartRefreshingDevices()

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

    # Replace existing message. Need to clean first.
    current_text = text_entry.GetValue()
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
    # TODO(shanyu): Write to log file.
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

    # If refresh is not paused, refresh the devices.
    if not self.refresh_pause:
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

  def OnStorageMode(self, event):
    """Switch ATFA device to storage mode asynchronously.

    Args:
      event: The triggering event.
    """
    operation = 'Switch ATFA device to Storage Mode'
    self._CreateThread(self._SwitchStorageMode, operation)

  def OnReboot(self, event):
    """Reboot ATFA device asynchronously.

    Args:
      event: The triggering event.
    """
    operation = 'Reboot ATFA device'
    self._CreateThread(self._Reboot, operation)

  def OnShutdown(self, event):
    """Shutdown ATFA device asynchronously.

    Args:
      event: The triggering event.
    """
    operation = 'Shut down ATFA device'
    self._CreateThread(self._Shutdown, operation)

  def OnToggleTargetSort(self, event):
    """Switch the target device list sorting field.

    Args:
      event: The triggering event.
    """
    if self.sort_by == self.atft_manager.SORT_BY_LOCATION:
      self.sort_by = self.atft_manager.SORT_BY_SERIAL
      self.target_dev_toggle_sort.SetLabel(self.SORT_BY_LOCATION_TEXT)
    else:
      self.sort_by = self.atft_manager.SORT_BY_LOCATION
      self.target_dev_toggle_sort.SetLabel(self.SORT_BY_SERIAL_TEXT)
    self._ListDevices()

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
    if self.menu_shst.IsChecked():
      self.statusbar.Show()
    else:
      self.statusbar.Hide()

  def ToggleToolBar(self, event):
    """Toggle the tool bar.

    Args:
      event: The triggering event.
    """
    if self.menu_shtl.IsChecked():
      self.toolbar.Show()
    else:
      self.toolbar.Hide()

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

    # Stop the refresh timer on close.
    self.StopRefresh()
    self.Destroy()

  def _HandleException(self, e, operation=None, target=None):
    """Handle the exception.

    Fires a exception event which would be handled in main thread. The exception
    would be shown in the command window. This function also wraps the
    associated operation and device object.

    Args:
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

  def _CreateBindEvents(self):
    """Create customized events and bind them to the event handlers.
    """

    # Event for refreshing device list
    self.refresh_event = wx.NewEventType()
    self.refresh_event_bind = wx.PyEventBinder(self.refresh_event)

    # Event for device listed
    self.dev_listed_event = wx.NewEventType()
    self.dev_listed_event_bind = wx.PyEventBinder(self.dev_listed_event)
    # Event when general exception happens
    self.exception_event = wx.NewEventType()
    self.exception_event_bind = wx.PyEventBinder(self.exception_event)
    # Event for alert box
    self.alert_event = wx.NewEventType()
    self.alert_event_bind = wx.PyEventBinder(self.alert_event)
    # Event for general message to be printed in command window.
    self.print_event = wx.NewEventType()
    self.print_event_bind = wx.PyEventBinder(self.print_event)

    self.Bind(self.refresh_event_bind, self.OnListDevices)
    self.Bind(self.dev_listed_event_bind, self._DeviceListedEventHandler)
    self.Bind(self.exception_event_bind, self._PrintEventHandler)
    self.Bind(self.alert_event_bind, self._AlertEventHandler)
    self.Bind(self.print_event_bind, self._PrintEventHandler)

    # Bind the close event
    self.Bind(wx.EVT_CLOSE, self.OnClose)

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

  def _DeviceListedEventHandler(self, event):
    """Handles the device listed event and list the devices.

    Args:
      event: The event object.
    """
    if self.atft_manager.atfa_dev:
      atfa_message = str(self.atft_manager.atfa_dev)
    else:
      atfa_message = 'No devices found!'
    self.PrintToWindow(self.atfa_devices_output, atfa_message)
    if self.last_target_list == self.atft_manager.target_devs:
      # Nothing changes, no need to refresh
      return

    # Update the stored target list. Need to make a deep copy instead of copying
    # the reference
    self.last_target_list = copy.deepcopy(self.atft_manager.target_devs)
    self.target_devs_output.DeleteAllItems()
    if self.atft_manager.target_devs:
      for target_dev in self.atft_manager.target_devs:
        self.target_devs_output.Append(
            (target_dev.serial_number, target_dev.location,
             target_dev.provision_status))
    # If in auto provisioning mode, handle the newly added devices.
    if self.auto_prov:
      self._HandleAutoProv()

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

    # We need to check the lock to prevent two listdevices running at the same
    # time.
    if self.listing_device_lock.acquire(False):
      operation = 'List Devices'
      try:
        self.atft_manager.ListDevices(self.sort_by)
        wx.QueueEvent(self, Event(self.dev_listed_event, wx.ID_ANY))
      except fastboot_exceptions.FastbootFailure as e:
        self._HandleException(e, operation)
      finally:
        # 'Release the lock'.
        self.listing_device_lock.release()

  def _SwitchStorageMode(self, operation):
    """Switch ATFA device to storage mode.

    Args:
      operation: The associated operation description.
    """
    try:
      self._SendOperationStartEvent(operation)
      self.atft_manager.atfa_dev_manager.SwitchStorage()
      self._SendOperationSucceedEvent(operation)
    except fastboot_exceptions.DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException(e, operation)
    except fastboot_exceptions.FastbootFailure as e:
      self._HandleException(e, operation, self.atft_manager.atfa_dev)

  def _Reboot(self, operation):
    """Reboot ATFA device.

    Args:
      operation: The associated operation description.
    """
    try:
      self._SendOperationStartEvent(operation)
      self.atft_manager.atfa_dev_manager.Reboot()
      self._SendOperationSucceedEvent(operation)
    except fastboot_exceptions.DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException(e, operation)
    except fastboot_exceptions.FastbootFailure as e:
      self._HandleException(e, operation, self.atft_manager.atfa_dev)

  def _Shutdown(self, operation):
    """Shutdown ATFA device.

    Args:
      operation: The associated operation description.
    """
    try:
      self._SendOperationStartEvent(operation)
      self.atft_manager.atfa_dev_manager.Shutdown()
      self._SendOperationSucceedEvent(operation)
    except fastboot_exceptions.DeviceNotFoundException as e:
      e.SetMsg('No Available ATFA!')
      self._HandleException(e, operation)
    except fastboot_exceptions.FastbootFailure as e:
      self._HandleException(e, operation, self.atft_manager.atfa_dev)

  def _GetSelectedTargets(self):
    """Get the list of target device that are selected in the device list.

    Returns:
      A list of serial numbers of the selected target devices.
    """
    selected_serials = []
    selected_item = self.target_devs_output.GetFirstSelected()
    if selected_item == -1:
      return selected_serials
    serial = self.target_devs_output.GetItem(selected_item, 0).GetText()
    selected_serials.append(serial)
    while True:
      selected_item = self.target_devs_output.GetNextSelected(selected_item)
      if selected_item == -1:
        break
      serial = self.target_devs_output.GetItem(selected_item, 0).GetText()
      selected_serials.append(serial)
    return selected_serials


def main():
  # TODO(matta): Check if there's a atft.py already running and not run again
  app = wx.App()
  Atft(None)
  app.MainLoop()


if __name__ == '__main__':
  main()
