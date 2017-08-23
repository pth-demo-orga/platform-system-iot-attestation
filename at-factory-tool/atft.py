#!/usr/bin/python
"""Graphical tool for managing the ATFA and AT communication.

This tool allows for easy graphical access to common ATFA commands.  It also
locates Fastboot devices and can initiate communication between the ATFA and
an Android Things device.
"""
import atftman
import fastboot_exceptions
import fastbootsh
import wx


class Atft(wx.Frame):
  """wxpython class to handle all GUI commands for the ATFA.

  Creates the GUI and provides various functions for interacting with an
  ATFA and an Android Things device.

  """

  def __init__(self, *args, **kwargs):
    super(Atft, self).__init__(*args, **kwargs)

    self.atft_manager = atftman.AtftManager(fastbootsh.FastbootDevice)

    self.panel = wx.Panel(self)
    self.menubar = wx.MenuBar()
    self.app_menu = wx.Menu()
    self.atfa_menu = wx.Menu()
    self.space_menu = wx.Menu()
    self.toolbar = self.CreateToolBar()

    # App Menu Options
    self.shst = self.app_menu.Append(
        wx.ID_ANY, 'Show Statusbar', kind=wx.ITEM_CHECK)
    self.app_menu.Check(self.shst.GetId(), True)
    self.Bind(wx.EVT_MENU, self.ToggleStatusBar, self.shst)

    self.shtl = self.app_menu.Append(
        wx.ID_ANY, 'Show Toolbar', kind=wx.ITEM_CHECK)
    self.app_menu.Check(self.shtl.GetId(), True)
    self.Bind(wx.EVT_MENU, self.ToggleToolBar, self.shtl)

    app_menu_quit = self.app_menu.Append(wx.ID_EXIT, 'Quit')
    self.Bind(wx.EVT_MENU, self.OnQuit, app_menu_quit)

    # ATFA Menu Options
    atfa_menu_listdev = self.atfa_menu.Append(wx.ID_ANY, 'List Devices')
    self.Bind(wx.EVT_MENU, self.OnListDevices, atfa_menu_listdev)

    atfa_menu_storage = self.atfa_menu.Append(wx.ID_ANY, 'Storage Mode')
    self.Bind(wx.EVT_MENU, self.OnStorageMode, atfa_menu_storage)

    atfa_menu_reboot = self.atfa_menu.Append(wx.ID_ANY, 'Reboot')
    self.Bind(wx.EVT_MENU, self.OnReboot, atfa_menu_reboot)

    atfa_menu_shutdown = self.atfa_menu.Append(wx.ID_ANY, 'Shutdown')
    self.Bind(wx.EVT_MENU, self.OnShutdown, atfa_menu_shutdown)

    # Add Menu items to Menubar
    self.menubar.Append(self.app_menu, 'Application')
    self.menubar.Append(self.space_menu, ' ')
    self.menubar.Append(self.atfa_menu, 'ATFA Device')
    self.SetMenuBar(self.menubar)

    # Toolbar buttons
    toolbar_devices = self.toolbar.AddLabelTool(
        wx.ID_ANY, 'List Devices', wx.Bitmap('toolbar_devices.png'))
    self.Bind(wx.EVT_TOOL, self.OnListDevices, toolbar_devices)
    toolbar_storage = self.toolbar.AddLabelTool(
        wx.ID_ANY, 'Storage Mode', wx.Bitmap('toolbar_storage.png'))
    self.Bind(wx.EVT_TOOL, self.OnStorageMode, toolbar_storage)
    toolbar_quit = self.toolbar.AddLabelTool(wx.ID_ANY, 'Quit App',
                                             wx.Bitmap('toolbar_exit.png'))
    self.Bind(wx.EVT_TOOL, self.OnQuit, toolbar_quit)
    toolbar_reboot = self.toolbar.AddLabelTool(wx.ID_ANY, 'Reboot ATFA',
                                               wx.Bitmap('toolbar_reboot.png'))
    self.Bind(wx.EVT_TOOL, self.OnReboot, toolbar_reboot)
    toolbar_shutdown = self.toolbar.AddLabelTool(
        wx.ID_ANY, 'Shutdown ATFA', wx.Bitmap('toolbar_shutdown.png'))
    self.Bind(wx.EVT_TOOL, self.OnShutdown, toolbar_shutdown)

    self.vbox = wx.BoxSizer(wx.VERTICAL)
    self.st = wx.StaticLine(self.panel, wx.ID_ANY, style=wx.LI_HORIZONTAL)
    self.vbox.Add(self.st, 0, wx.ALL | wx.EXPAND, 5)

    # Device Output Title
    self.dev_title = wx.StaticText(self.panel, wx.ID_ANY, 'Detected Devices')
    self.dev_title_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.dev_title_sizer.Add(self.dev_title, 0, wx.ALL, 5)
    self.vbox.Add(self.dev_title_sizer, 0, wx.LEFT)

    # Device Output Window
    self.devices_output = wx.TextCtrl(
        self.panel,
        wx.ID_ANY,
        size=(500, 100),
        style=wx.TE_MULTILINE | wx.TE_READONLY)
    self.vbox.Add(self.devices_output, 0, wx.ALL | wx.EXPAND, 5)

    # Command Output Title
    self.comm_title = wx.StaticText(self.panel, wx.ID_ANY, 'Command Output')
    self.comm_title_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.comm_title_sizer.Add(self.comm_title, 0, wx.ALL, 5)
    self.vbox.Add(self.comm_title_sizer, 0, wx.LEFT)

    # Command Output Window
    self.cmd_output = wx.TextCtrl(
        self.panel,
        wx.ID_ANY,
        size=(500, 500),
        style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
    self.vbox.Add(self.cmd_output, 0, wx.ALL | wx.EXPAND, 5)

    self.panel.SetSizer(self.vbox)
    self.SetMenuBar(self.menubar)
    self.toolbar.Realize()
    self.statusbar = self.CreateStatusBar()
    self.statusbar.SetStatusText('Ready')
    self.SetSize((800, 800))
    self.SetTitle('Google AT-Factory-Tool')
    self.Center()
    self.Show(True)

    self.OnListDevices(None)

  def PrintToDeviceWindow(self, text):
    self.devices_output.WriteText(text)
    self.devices_output.WriteText('\n')

  def PrintToCmdWindow(self, text):
    self.ClearCommandWindow()
    self.cmd_output.WriteText(text)
    self.cmd_output.WriteText('\n')

  def OnListDevices(self, event=None):
    if event is not None:
      event.Skip()

    self.ClearDeviceWindow()
    try:
      devices = self.atft_manager.ListDevices()

      if devices['atfa_dev'] is not None:
        self.PrintToDeviceWindow('[ATFA] ' + devices['atfa_dev'])
      if devices['target_dev'] is not None:
        self.PrintToDeviceWindow('[Target] ' + devices['target_dev'])
    except fastboot_exceptions.DeviceNotFoundException:
      self.PrintToDeviceWindow('No devices found!')
    except fastboot_exceptions.FastbootFailure:
      self.PrintToCmdWindow('Fastboot command failed!')
    except Exception as e:  # pylint: disable=broad-except
      self.PrintException(e)

  def OnGetSerial(self, event):
    self.OnListDevices()
    self.PrintToCmdWindow('Getting ATFA Serial number')
    try:
      self.atft_manager.atfa_dev_manager.GetSerial()
    except fastboot_exceptions.DeviceNotFoundException:
      self.PrintToCmdWindow("Can't get serial number!  No Available ATFA!")
    except fastboot_exceptions.FastbootFailure:
      self.PrintToCmdWindow('Fastboot command failed!')
    except Exception as e:  # pylint: disable=broad-except
      self.PrintException(e)

  def OnNormalMode(self, event):
    self.OnListDevices()
    self.PrintToCmdWindow('Switching to Normal Mode')
    try:
      self.atft_manager.SwitchNormal()
    except fastboot_exceptions.DeviceNotFoundException:
      self.PrintToCmdWindow("Can't switch to Normal Mode!  No Available ATFA!")
    except fastboot_exceptions.FastbootFailure:
      self.PrintToCmdWindow('Fastboot command failed!')
    except Exception as e:  # pylint: disable=broad-except
      self.PrintException(e)

  def OnStorageMode(self, event):
    self.OnListDevices()
    try:
      self.PrintToCmdWindow('Switching to Storage Mode for' +
                            self.atft_manager.GetAtfaSerial())
      self.PrintToCmdWindow(self.atft_manager.
                            atfa_dev_manager.SwitchStorage())
    except fastboot_exceptions.DeviceNotFoundException:
      self.PrintToCmdWindow("Can't switch to Storage Mode!  No Available ATFA!")
    except fastboot_exceptions.FastbootFailure:
      self.PrintToCmdWindow('Fastboot command failed!')
    except Exception as e:  # pylint: disable=broad-except
      self.PrintException(e)

  def OnReboot(self, event):
    self.OnListDevices()
    try:
      self.PrintToCmdWindow('Rebooting' + self.atft_manager.GetAtfaSerial())
      self.atft_manager.ataf_dev_manager.Reboot()
    except fastboot_exceptions.DeviceNotFoundException:
      self.PrintToCmdWindow("Can't reboot!  No Available ATFA!")
    except fastboot_exceptions.FastbootFailure:
      self.PrintToCmdWindow('Fastboot command failed!')
    except Exception as e:  # pylint: disable=broad-except
      self.PrintException(e)

  def OnShutdown(self, event):
    self.OnListDevices()
    try:
      self.PrintToCmdWindow('Shutting down' +
                            self.atft_manager.GetAtfaSerial())
      self.atft_manager.atfa_dev_manager.Shutdown()
    except fastboot_exceptions.DeviceNotFoundException:
      self.PrintToCmdWindow("Can't shutdown!  No Available ATFA!")
    except fastboot_exceptions.FastbootFailure:
      self.PrintToCmdWindow('Fastboot command failed!')
    except Exception as e:  # pylint: disable=broad-except
      self.PrintException(e)

  def get_logs(self, event):
    self.OnListDevices()
    self.atft_manager.atfa_dev_manager.GetLogs()

  def OnQuit(self, event):
    self.Close()

  def ToggleStatusBar(self, event):
    if self.shst.IsChecked():
      self.statusbar.Show()
    else:
      self.statusbar.Hide()

  def ToggleToolBar(self, event):
    if self.shtl.IsChecked():
      self.toolbar.Show()
    else:
      self.toolbar.Hide()

  def ClearCommandWindow(self):
    # Clear output.
    self.cmd_output.SetValue('')

  def ClearDeviceWindow(self):
    # Clear device list.
    self.devices_output.SetValue('')

  def PrintException(self, e):
    self.PrintToCmdWindow(self.atft_manager.FormatException(e))


def main():
  # TODO(matta): Check if there's a atft.py already running and not run again
  # TODO(matta): Inject current host time into ATFA at startup
  # TODO(matta): Periodically poll for new fastboot devices?
  app = wx.App()
  Atft(None)
  app.MainLoop()


if __name__ == '__main__':
  main()
