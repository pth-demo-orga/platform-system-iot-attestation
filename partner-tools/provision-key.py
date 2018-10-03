#!/usr/bin/python

#
# Copyright 2018 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Scripts to provision attestation key to Android Things device.
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile

from aesgcm import AESGCM
import cryptography.exceptions
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import curve25519
import ec_helper


class _AtapSessionParameters(object):
  """Information stored for this AThings Attestation Protocol session.

  Attributes:
    algorithm: The key exchange algorithm.
    operation: The operation in this session.
    private_key: The host generated private key.
    public_key: The host generated public key.
    device_pub_key: The device side public key.
    shared_key: The computed shared key.
    auth_value: The challenge value.
    message_version: The ATAP message version.
  """

  def __init__(self):
    self.algorithm = 0
    self.operation = 0
    self.private_key = bytes()
    self.public_key = bytes()
    self.device_pub_key = bytes()
    self.shared_key = bytes()
    self.auth_value = bytes()
    self.message_version = None


class EncryptionAlgorithm(object):
  """The support encryption algorithm constant."""
  ALGORITHM_P256 = 1
  ALGORITHM_CURVE25519 = 2


# Version 2 adds SoM key suppport but is otherwise compatible with version 1.
_MESSAGE_VERSION_1 = 1
_MESSAGE_VERSION_2 = 2
_ALGORITHMS = {'p256': 1, 'x25519': 2}
_ECDH_KEY_LEN = 33
_VAR_LEN = 4
_HEADER_LEN = 8
_GCM_IV_LEN = 12
_GCM_TAG_LEN = 16
_HASH_LEN = 32
_HKDF_HASH_LEN = 16


def _get_message_version():
  return _MESSAGE_VERSION_1


def _write_operation_start(
    algorithm, operation, message_version, output_folder):
  """Writes a fresh Operation Start message to output folder.

  Generates an ECDHE key specified by <algorithm> and writes an Operation
  Start message for executing <operation> on the device.

  Args:
    algorithm: Integer specifying the curve to use for the session key.
        1: P256, 2: X25519
    operation: Specifies the operation. 1: Certify, 2: Issue, 3: Issue Encrypted
    message_version: The ATAP version. If message_version is None, than we
      select the default version according to the operation.
    output_folder: The folder to write operation_start message to.

  Raises:
    ValueError: algorithm or operation is is invalid.
  Returns:
    session_params: The session information.
  """

  if not algorithm or algorithm > 2 or algorithm < 1:
    raise ValueError('Invalid algorithm value.')

  if not operation or operation > 5 or operation < 1:
    raise ValueError('Invalid operation value.')

  # Generate new key for each provisioning session
  if algorithm == _ALGORITHMS['x25519']:
    private_key = curve25519.genkey()
    # Make 33 bytes to match P256
    public_key = curve25519.public(private_key) + '\0'
  elif algorithm == _ALGORITHMS['p256']:
    [private_key, public_key] = ec_helper.generate_p256_key()

  session_params = _AtapSessionParameters()
  session_params.operation = operation
  session_params.algorithm = algorithm
  session_params.private_key = private_key
  session_params.public_key = public_key

  # "Operation Start" Header
  # +2 for algo and operation bytes
  message_version = _get_message_version()

  session_params.message_version = message_version
  header = (message_version, 0, 0, 0, _ECDH_KEY_LEN + 2)
  operation_start = bytearray(struct.pack('<4B I', *header))

  # "Operation Start" Message
  op_start = (algorithm, operation, public_key)
  operation_start.extend(struct.pack('<2B 33s', *op_start))

  with open(os.path.join(output_folder, 'operation_start.bin'), 'wb') as f:
    f.write(operation_start)

  return session_params


def _get_ca_response(ca_request, session_params, key_file):
  """Construct ca_response.bin.

  Parses the CA Request message at ca_request. Computes the session key from
  the ca_request, decrypts the inner request, verifies the SOM key signature,
  and issues or certifies attestation keys as applicable. The CA Response
  message containing test keys is written to ca_response.bin.

  Args:
    ca_request: The CA Request message from the device.
    session_params: Session information.
    key_file: The key file.
  Returns:
    ca response message.

  Raises:
    ValueError: ca_request is malformed.

  CA Request message format for reference, sizes in bytes

  cleartext header                            8
  cleartext device ephemeral public key       33
  cleartext GCM IV                            12
  cleartext inner ca request length           4
  encrypted header                            8
  encrypted SOM key certificate chain         variable
  encrypted SOM key authentication signature  variable
  encrypted product ID SHA256 hash            32
  encrypted RSA public key                    variable
  encrypted ECDSA public key                  variable
  encrypted edDSA public key                  variable
  cleartext GCM tag                           16

  For SoM:

  cleartext header                            8
  cleartext device ephemeral public key       33
  cleartext GCM IV                            12
  cleartext inner ca request length           4
  encrypted header                            8
  encrypted SOM ID SHA256 hash                32
  cleartext GCM tag                           16
  """

  pub_key_len = _ECDH_KEY_LEN
  min_message_length = (
      _HEADER_LEN + pub_key_len + _GCM_IV_LEN + _VAR_LEN + _HEADER_LEN +
      _VAR_LEN + _VAR_LEN + _HASH_LEN + _VAR_LEN + _VAR_LEN +
      _VAR_LEN + _GCM_TAG_LEN)
  if len(ca_request) < min_message_length:
    raise ValueError('Malformed message: Length invalid')

  # Unpack Request header
  end = _HEADER_LEN
  ca_req_start = ca_request[:end]
  (device_message_version, res1, res2, res3,
   device_message_len) = struct.unpack('<4B I', ca_req_start)

  if device_message_version > _MESSAGE_VERSION_2:
    raise ValueError('Malformed message: Unsupported protocol version')

  if res1 or res2 or res3:
    raise ValueError('Malformed message: Reserved values set')

  if device_message_len > len(ca_request) - _HEADER_LEN:
    raise ValueError('Malformed message: Incorrect device message length')

  # Extract AT device ephemeral public key
  start = _HEADER_LEN
  end = start + pub_key_len
  session_params.device_pub_key = bytes(ca_request[start:end])
  _derive_from_shared_secret(session_params)

  # Decrypt AES-128-GCM message using the shared_key
  # Extract the GCM IV
  start = _HEADER_LEN + pub_key_len
  end = start + _GCM_IV_LEN
  gcm_iv = bytes(ca_request[start:end])

  # Extract the encrypted message
  start = _HEADER_LEN + pub_key_len + _GCM_IV_LEN
  enc_message_len = _get_var_len(ca_request, start)

  if enc_message_len > len(ca_request) - _GCM_TAG_LEN - start - _VAR_LEN:
    raise ValueError('Encrypted message size %d too large' % enc_message_len)

  start += _VAR_LEN
  end = start + enc_message_len
  enc_message = bytes(ca_request[start:end])

  # Extract the GCM Tag
  gcm_tag = bytes(ca_request[-_GCM_TAG_LEN:])

  # Decrypt message
  try:
    data = AESGCM.decrypt(
        enc_message, session_params.shared_key, gcm_iv, gcm_tag)
  except cryptography.exceptions.InvalidTag:
    raise ValueError('Malformed message: GCM decrypt failed')

  # Unpack Inner header
  end = _HEADER_LEN
  ca_req_inner_header = data[:end]
  (inner_message_version, res1, res2, res3, inner_message_len) = struct.unpack(
      '<4B I', ca_req_inner_header)

  if device_message_version != inner_message_version:
    raise ValueError('Malformed message: Incorrect inner message version')

  if res1 or res2 or res3:
    raise ValueError('Malformed message: Reserved values set')

  remaining_bytes = len(ca_request) - _HEADER_LEN - pub_key_len
  remaining_bytes = remaining_bytes - _GCM_IV_LEN - _GCM_TAG_LEN
  if inner_message_len > remaining_bytes:
    raise ValueError('Malformed message: Incorrect device inner message length')

  inner_ca_response = _parse_inner_ca_request(data, key_file)

  (gcm_iv, encrypted_keyset, gcm_tag) = AESGCM.encrypt(
      inner_ca_response, session_params.shared_key)
   # "CA Response" Header
  header = (
      session_params.message_version,
      0, 0, 0, 12 + 4 + len(encrypted_keyset) + 16)
  ca_response = bytearray(struct.pack('<4B I', *header))

  struct_fmt = '12s I %ds 16s' % len(inner_ca_response)
  message = (gcm_iv, len(encrypted_keyset), encrypted_keyset, gcm_tag)
  ca_response.extend(struct.pack(struct_fmt, *message))

  return ca_response


def _parse_inner_ca_request(data, key_file):
  """Parse decrypted inner ca request and generate ca response.

  The inner ca request is for issuing product key.

  Args:
    data: Decrypted inner ca request.
    key_file: The key file.
  Returns:
    The inner ca response byte object.
  Raises:
    ValueError: inner ca request is malformed.
  """
  # SOM key certificate chain
  som_chain_start = _HEADER_LEN
  som_chain_len = _get_var_len(data, som_chain_start)

  # SOM key authentication signature
  som_sig_start = som_chain_start + _VAR_LEN + som_chain_len
  som_sig_len = _get_var_len(data, som_sig_start)

  # Product ID SHA-256 hash
  prod_id_start = som_sig_start + _VAR_LEN + som_sig_len

  # RSA public key to certify
  rsa_start = prod_id_start + _HASH_LEN
  rsa_len = _get_var_len(data, rsa_start)
  if rsa_len > 0:
    raise ValueError(
        'Certify operation not supported, set RSA public key length to zero')

  # ECDSA public key to certify
  ecdsa_start = rsa_start + _VAR_LEN + rsa_len
  ecdsa_len = _get_var_len(data, ecdsa_start)
  if ecdsa_len > 0:
    raise ValueError(
        'Certify operation not supported, set ECDSA public key length to zero')

  # edDSA public key to certify
  eddsa_start = prod_id_start + _VAR_LEN + _HASH_LEN
  eddsa_len = _get_var_len(data, eddsa_start)
  if eddsa_len > 0:
    raise ValueError(
        'Certify operation not supported, set edDSA public key length to zero')

  with open(key_file, 'rb') as infile:
    inner_ca_response = bytes(infile.read())

  return inner_ca_response


def _derive_from_shared_secret(session_params):
  """Generates the shared key based on ECDH and HKDF.

  Uses a particular ECDH algorithm and HKDF-SHA256 to create shared key and a
  auth value. The auth value would be sent to the device as a challenge to get
  som authentication if available. The generated shared key and auth value
  would be stored in session_params.

  Args:
    session_params: Session information.

  Raises:
    RuntimeError: Computing the shared secret fails.

  """

  hkdf_salt = session_params.public_key + session_params.device_pub_key

  if session_params.algorithm == _ALGORITHMS['p256']:
    ecdhe_shared_secret = ec_helper.compute_p256_shared_secret(
        session_params.private_key, session_params.device_pub_key)

  elif session_params.algorithm == _ALGORITHMS['x25519']:
    device_pub_key = session_params.device_pub_key[:-1]
    ecdhe_shared_secret = curve25519.shared(session_params.private_key,
                                            device_pub_key)

  hkdf = HKDF(
      algorithm=hashes.SHA256(),
      length=_HKDF_HASH_LEN,
      salt=hkdf_salt,
      info='KEY',
      backend=default_backend())
  session_params.shared_key = hkdf.derive(ecdhe_shared_secret)

  hkdf = HKDF(
      algorithm=hashes.SHA256(),
      length=_HKDF_HASH_LEN,
      salt=hkdf_salt,
      info='SIGN',
      backend=default_backend())
  session_params.auth_value = hkdf.derive(ecdhe_shared_secret)


def _get_algorithm_list(serial):
  """Get the supported algorithm list.

  Get the available algorithm list using getvar at-attest-dh
  at_attest_dh should be in format 1:p256,2:curve25519
  or 1:p256
  or 2:curve25519.

  Args:
    serial: The device serial number.
  Returns:
    The supported algorithm.
  """
  at_attest_dh = ''
  try:
    at_attest_dh = _get_var('at-attest-dh', serial)
  except subprocess.CalledProcessError as e:
    print 'Failed to get available exchange algorithm. Error: \n%s' % e.output
    sys.exit(-1)
  if not at_attest_dh:
    return None
  algorithm_strings = at_attest_dh.split(',')
  algorithm_list = []
  for algorithm_string in algorithm_strings:
    algorithm_list.append(int(algorithm_string.split(':')[0]))
  if EncryptionAlgorithm.ALGORITHM_CURVE25519 in algorithm_list:
    return EncryptionAlgorithm.ALGORITHM_CURVE25519
  elif EncryptionAlgorithm.ALGORITHM_P256 in algorithm_list:
    return EncryptionAlgorithm.ALGORITHM_P256
  return None


def _get_var(var, serial):
  """Get a variable from the device.

  Note that the return value is in stderr instead of stdout.
  Args:
    var: The name of the variable.
    serial: The device serial number.
  Returns:
    The value for the variable.
  """
  if serial:
    out = subprocess.check_output(
        ['fastboot', '-s', serial, 'getvar', var],
        stderr=subprocess.STDOUT)
  else:
    out = subprocess.check_output(
        ['fastboot', 'getvar', var],
        stderr=subprocess.STDOUT)
  lines = out.splitlines()
  for line in lines:
    if line.startswith(var + ': '):
      value = line.replace(var + ': ', '').replace('\r', '')
  return value


def _get_var_len(data, index):
  """Reads the 4 byte little endian unsigned integer at data[index].

  Args:
    data: Start of bytearray
    index: Offset that indicates where the integer begins

  Returns:
    Little endian unsigned integer at data[index]
  """
  return struct.unpack('<I', data[index:index + 4])[0]


def _run_fastboot_command(commands, serial):
  """Execute a fastboot commands.

  Args:
    commands: The command to be executed.
    serial: The serial number of the device.
  """
  if serial:
    fastboot_commands = ['fastboot', '-s', serial]
  else:
    fastboot_commands = ['fastboot']

  subprocess.check_call(fastboot_commands + commands)


def main():
  parser = argparse.ArgumentParser(
      description='Test for Android Things key provisioning.')
  parser.add_argument(
      '-s',
      '--serial',
      type=str,
      required=False,
      dest='serial',
      help='Fastboot serial device',
      metavar='FASTBOOT_SERIAL_NUMBER')

  parser.add_argument(
      '-k',
      '--key',
      type=str,
      required=True,
      dest='key',
      help='Key file name',
      metavar='KEY_FILE_NAME')

  results = parser.parse_args()
  algorithm = _get_algorithm_list(results.serial)
  key_file = results.key
  # Operation is 'ISSUE'.
  operation = 2

  message_version = _get_message_version()

  print 'Start giving attestation key to the Android Things device'
  print 'Please keep device connected until operation finished.'

  temp_folder = tempfile.mkdtemp()
  try:
    session_params = _write_operation_start(
        algorithm, operation, message_version, temp_folder)
    _run_fastboot_command(
        ['stage', os.path.join(temp_folder, 'operation_start.bin')],
        results.serial)
    _run_fastboot_command(['oem', 'at-get-ca-request'], results.serial)
    _run_fastboot_command(
        ['get_staged', os.path.join(temp_folder, 'ca_request.bin')],
        results.serial)

    with open(os.path.join(temp_folder, 'ca_request.bin'), 'rb') as f:
      ca_request = bytearray(f.read())

    ca_response = _get_ca_response(ca_request, session_params, key_file)

    with open(os.path.join(temp_folder, 'ca_response.bin'), 'wb') as f:
      f.write(ca_response)

    _run_fastboot_command(
        ['stage', os.path.join(temp_folder, 'ca_response.bin')],
        results.serial)
    _run_fastboot_command(['oem', 'at-set-ca-response'], results.serial)
    at_attest_uuid = _get_var('at-attest-uuid', results.serial)
    print ('Giving attestation key succeed! Attestation UUID: %s' %
           at_attest_uuid)
  except subprocess.CalledProcessError as e:
    print 'Giving attestation key failed! Error: \n%s' % e.output
    print 'Please try again.'
  except ValueError as e:
    print 'Giving attestation key failed! Error: \n%s' % str(e)
    print 'Please check your key file format.'
  finally:
    shutil.rmtree(temp_folder)


if __name__ == '__main__':
  main()
