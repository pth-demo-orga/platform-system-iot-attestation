#!/usr/bin/python
"""Exceptions for At-Factory-Tool Manager (atftman).
"""


class DeviceNotFoundException(Exception):

  def __init__(self):
    Exception.__init__(self)
    self.msg = 'Device Not Found!'

  def SetMsg(self, msg):
    self.msg = msg

  def __str__(self):
    return self.msg


class NoAlgorithmAvailableException(Exception):
  pass


class FastbootFailure(Exception):

  def __init__(self, msg):
    Exception.__init__(self)
    self.msg = msg

  def __str__(self):
    return self.msg


class ProductNotSpecifiedException(Exception):

  def __str__(self):
    return 'Product Id Not Specified!'
