"""This module provides the serial number to USB location map on Linux.

It uses sysfs information.
"""
import os


class SerialMapper(object):
  """Maps serial number to its USB physical location.

  This class should run under Linux environment and use sysfs to enumerate the
  USB devices. Use the serial file's content to create the map.
  """

  USB_DEVICES_PATH = '/sys/bus/usb/devices/'

  def get_serial_map(self):
    """Get the serial_number -> USB location map.

    Returns:
      A Dictionary of {serial_number: USB location}
    """
    serial_to_location_map = {}
    # check if sysfs is mounted.
    if not os.path.exists(self.USB_DEVICES_PATH):
      return serial_to_location_map

    for device_folder_name in os.listdir(self.USB_DEVICES_PATH):
      device_folder = os.path.join(self.USB_DEVICES_PATH, device_folder_name)
      if os.path.isdir(device_folder):
        # The format of folder name should be either:
        # USB1, USB2... which are controllers (ignored).
        # bus-port[.port.port] which are devices.
        # bus-port[.port.port]:config.interface which are interfaces (ignored).
        if ':' not in device_folder and '-' in device_folder:
          serial_path = os.path.join(device_folder, 'serial')
          if os.path.isfile(serial_path):
            with open(serial_path) as f:
              serial = f.readline().rstrip('\n')
              serial_to_location_map[serial] = device_folder_name

    return serial_to_location_map
