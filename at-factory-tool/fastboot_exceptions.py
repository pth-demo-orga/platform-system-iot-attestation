# !/usr/bin/python
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

"""Exceptions for At-Factory-Tool Manager (atftman)."""


class AtftBaseException(Exception):

  def __init__(self):
    Exception.__init__(self)

  def __str__(self):
    if self.msg:
      return self.msg
    return ''


class DeviceNotFoundException(AtftBaseException):

  def __init__(self):
    AtftBaseException.__init__(self)
    self.msg = 'Device Not Found!'

  def SetMsg(self, msg):
    self.msg = msg


class NoAlgorithmAvailableException(AtftBaseException):
  pass


class FastbootFailure(AtftBaseException):

  def __init__(self, msg):
    AtftBaseException.__init__(self)
    self.msg = msg


class ProductNotSpecifiedException(AtftBaseException):

  def __init__(self):
    AtftBaseException.__init__(self)
    self.msg = 'Product Attribute File Not Selected!'


class ProductAttributesFileFormatError(AtftBaseException):

  def __init__(self, msg):
    AtftBaseException.__init__(self)
    self.msg = msg


class DeviceCreationException(AtftBaseException):

  def __init__(self, msg, device):
    AtftBaseException.__init__(self)
    self.device = device
    self.msg = 'Error while creating new device, fastboot error:' + msg


class OsVersionNotAvailableException(AtftBaseException):

  def __init__(self, device):
    AtftBaseException.__init__(self)
    self.device = device


class OsVersionNotCompatibleException(AtftBaseException):

  def __init__(self, device, version):
    AtftBaseException.__init__(self)
    self.device = device
    self.version = version


class NoKeysException(AtftBaseException):
  pass
