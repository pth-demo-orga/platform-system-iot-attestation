#!/usr/bin/python
"""Exceptions for At-Factory-Tool Manager (atftman).
"""


class DeviceNotFoundException(Exception):
  pass


class NoAlgorithmAvailableException(Exception):
  pass


class FastbootFailure(Exception):

  def __init__(self, msg):
    Exception.__init__(self)
    self.msg = msg

  def __str__(self):
    return self.msg
