#!/usr/bin/python

#
# Copyright 2017 The Android Open Source Project
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
"""Test that implements the Android Things Attestation Provisioning protocol.

Enables testing of the device side of the Android Things Attestation
Provisioning (ATAP) Protocol without access to a CA or Android Things Factory
Appliance (ATFA).
"""

import argparse
import os
import struct
import subprocess

from aesgcm import AESGCM
import cryptography.exceptions
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import curve25519
import ec_helper


class _AtapSessionParameters(object):

  def __init__(self):
    self.algorithm = 0
    self.operation = 0
    self.private_key = bytes()
    self.public_key = bytes()
    self.device_pub_key = bytes()
    self.shared_key = bytes()
    self.auth_value = bytes()
    self.message_version = None


# Version 2 adds SoM key suppport but is otherwise compatible with version 1.
_MESSAGE_VERSION_1 = 1
_MESSAGE_VERSION_2 = 2
_OPERATIONS = {'ISSUE': 2, 'ISSUE_ENC': 3, 'ISSUE_SOM': 4, 'ISSUE_ENC_SOM': 5}
_ALGORITHMS = {'p256': 1, 'x25519': 2}
_ECDH_KEY_LEN = 33
_VAR_LEN = 4
_HEADER_LEN = 8
_GCM_IV_LEN = 12
_GCM_TAG_LEN = 16
_HASH_LEN = 32
_HKDF_HASH_LEN = 16


def _get_message_version(session_params):
  operation = session_params.operation
  if ((operation == _OPERATIONS['ISSUE_SOM']) or
      (operation == _OPERATIONS['ISSUE_ENC_SOM'])):
    return _MESSAGE_VERSION_2
  return _MESSAGE_VERSION_1


def _write_operation_start(algorithm, operation, message_version):
  """Writes a fresh Operation Start message to tmp/operation_start.bin.

  Generates an ECDHE key specified by <algorithm> and writes an Operation
  Start message for executing <operation> on the device.

  Args:
    algorithm: Integer specifying the curve to use for the session key.
        1: P256, 2: X25519
    operation: Specifies the operation. 1: Certify, 2: Issue, 3: Issue Encrypted
    message_version: The ATAP version. If message_version is None, than we
      select the default version according to the operation.

  Raises:
    ValueError: algorithm or operation is is invalid.
  Returns:
    session_params: The session information.
  """

  if algorithm > 2 or algorithm < 1:
    raise ValueError('Invalid algorithm value.')

  if operation > 5 or operation < 1:
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
  if not message_version:
    message_version = _get_message_version(session_params)

  session_params.message_version = message_version
  header = (message_version, 0, 0, 0, _ECDH_KEY_LEN + 2)
  operation_start = bytearray(struct.pack('<4B I', *header))

  # "Operation Start" Message
  op_start = (algorithm, operation, public_key)
  operation_start.extend(struct.pack('<2B 33s', *op_start))

  with open('tmp/operation_start.bin', 'wb') as f:
    f.write(operation_start)

  return session_params


def _get_ca_response(ca_request, session_params):
  """Writes a CA Response message to tmp/ca_response.bin.

  Parses the CA Request message at ca_request. Computes the session key from
  the ca_request, decrypts the inner request, verifies the SOM key signature,
  and issues or certifies attestation keys as applicable. The CA Response
  message containing test keys is written to ca_response.bin.

  Args:
    ca_request: The CA Request message from the device.
    session_params: Session information.

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
  is_som_request = False
  if (session_params.operation == _OPERATIONS['ISSUE_SOM'] or
      session_params.operation == _OPERATIONS['ISSUE_ENC_SOM']):
    is_som_request = True

  pub_key_len = _ECDH_KEY_LEN

  if is_som_request:
    message_length = (
        _HEADER_LEN + pub_key_len + _GCM_IV_LEN + _VAR_LEN + _HEADER_LEN +
        _HASH_LEN + _GCM_TAG_LEN)
    if len(ca_request) != message_length:
      raise ValueError('Malformed message: Length invalid')
  else:
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

  if (device_message_version > _MESSAGE_VERSION_2 or
      (device_message_version < _MESSAGE_VERSION_2 and is_som_request)):
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

  if is_som_request:
    inner_ca_response = _parse_inner_ca_request_som(data, session_params)
  else:
    inner_ca_response = _parse_inner_ca_request_product(data, session_params)

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

  with open('tmp/ca_response.bin', 'wb') as f:
    f.write(ca_response)


def _parse_inner_ca_request_product(data, session_params):
  """Parse decrypted inner ca request and generate ca response.

  The inner ca request is for issuing product key.

  Args:
    data: Decrypted inner ca request.
    session_params: Session information.
  Returns:
    The inner ca response byte object.
  Raises:
    ValueError: inner ca request is malformed.
  """
  # SOM key certificate chain
  som_chain_start = _HEADER_LEN
  som_chain_len = _get_var_len(data, som_chain_start)
  if som_chain_len > 0:
    # Som authentication cert chain is not empty, read it out.
    som_chain = data[
        som_chain_start + _VAR_LEN: som_chain_start + _VAR_LEN + som_chain_len]

    with open('tmp/som_cert.bin', 'wb') as f:
      f.write(som_chain)
    cert_start = 0
    i = 0
    while cert_start < som_chain_len:
      cert_len = _get_var_len(som_chain, cert_start)
      cert_end = cert_start + _VAR_LEN + cert_len
      cert = som_chain[cert_start + _VAR_LEN : cert_end]
      # We output each certificate to a file.
      # User should do their own verification of the certificate chain.
      with open('tmp/som_cert_' + str(i) + '.bin', 'wb') as f:
        f.write(cert)
      cert_start = cert_end
      i += 1

  # SOM key authentication signature
  som_sig_start = som_chain_start + _VAR_LEN + som_chain_len
  som_sig_len = _get_var_len(data, som_sig_start)
  if som_sig_len > 0:
    print 'Som key signature found.'
    som_sig = data[
        som_sig_start + _VAR_LEN: som_sig_start + _VAR_LEN + som_sig_len]
    with open('tmp/som_sig.bin', 'wb') as f:
      f.write(som_sig)

    # Write the som key authentication challenge to file. This would be
    # verified against the signature.
    with open('tmp/auth_value.bin', 'wb') as f:
      f.write(session_params.auth_value)

    # Verify Som signature
    try:
      pubkey = subprocess.check_output(['openssl', 'x509', '-pubkey',
                                        '-in', 'tmp/som_cert_0.bin',
                                        '-inform', 'DER', '--noout'])
      with open('tmp/pubkey.pem', 'wb') as f:
        f.write(pubkey)
      digest_algorithm = '-sha512'
      cert_info = subprocess.check_output([
          'openssl', 'x509', '-noout', '-text', '-inform', 'DER',
          '-in', 'tmp/som_cert_0.bin'])
      for cert_info_line in cert_info.splitlines():
        if ('Signature Algorithm' in cert_info_line and
            'sha256' in cert_info_line):
          digest_algorithm = '-sha256'
          break
      subprocess.check_output([
          'openssl', 'dgst', digest_algorithm, '-verify', 'tmp/pubkey.pem',
          '-signature', 'tmp/som_sig.bin', 'tmp/auth_value.bin'])
    except subprocess.CalledProcessError as e:
      print 'Fail to verify som authentication signature!'
      raise e
    print 'Som authentication signature verified OK!'

  # Product ID SHA-256 hash
  prod_id_start = som_sig_start + _VAR_LEN + som_sig_len
  prod_id_end = prod_id_start + _HASH_LEN
  prod_id_hash = data[prod_id_start:prod_id_end]
  print 'product_id hash:' + prod_id_hash.encode('hex')

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

  # ATFA treats ISSUE and ISSUE_ENCRYPTED operations the same
  if session_params.operation == _OPERATIONS['ISSUE']:
    unencrypted_key_file = 'keysets/unencrypted_product.keyset'
    if session_params.message_version == _MESSAGE_VERSION_1:
      # Use inner message with version 1 for legacy support.
      unencrypted_key_file = 'keysets/unencrypted_product_version_1.keyset'
    with open(unencrypted_key_file, 'rb') as infile:
      inner_ca_response = bytes(infile.read())
  elif session_params.operation == _OPERATIONS['ISSUE_ENC']:
    encrypted_key_file = 'keysets/encrypted_product.keyset'
    if session_params.message_version == _MESSAGE_VERSION_1:
      # Use inner message with version 1 for legacy support.
      encrypted_key_file = 'keysets/encrypted_product_version_1.keyset'
    with open(encrypted_key_file, 'rb') as infile:
      inner_ca_response = bytes(infile.read())

  return inner_ca_response


def _parse_inner_ca_request_som(data, session_params):
  """Parse decrypted inner ca request and generate ca response.

  The inner ca request is for issuing som key.

  Args:
    data: Decrypted inner ca request.
    session_params: Session information.
  Returns:
    The inner ca response byte object.
  """
  som_id_start = _HEADER_LEN
  som_id_end = som_id_start + _HASH_LEN
  som_id_hash = data[som_id_start:som_id_end]
  print 'som_id hash:' + som_id_hash.encode('hex')

  if session_params.operation == _OPERATIONS['ISSUE_SOM']:
    with open('keysets/unencrypted_som.keyset', 'rb') as infile:
      inner_ca_response = bytes(infile.read())
  elif session_params.operation == _OPERATIONS['ISSUE_ENC_SOM']:
    with open('keysets/encrypted_som.keyset', 'rb') as infile:
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


def _get_var_len(data, index):
  """Reads the 4 byte little endian unsigned integer at data[index].

  Args:
    data: Start of bytearray
    index: Offset that indicates where the integer begins

  Returns:
    Little endian unsigned integer at data[index]
  """
  return struct.unpack('<I', data[index:index + 4])[0]


def main():
  parser = argparse.ArgumentParser(
      description='Test for Android Things key provisioning.')
  parser.add_argument(
      '-a',
      '--algorithm',
      type=str,
      choices=['p256', 'x25519'],
      required=True,
      dest='algorithm',
      help='Algorithm for deriving the ECDHE shared secret')
  parser.add_argument(
      '-s',
      '--serial',
      type=str,
      required=True,
      dest='serial',
      help='Fastboot serial device',
      metavar='FASTBOOT_SERIAL_NUMBER')
  parser.add_argument(
      '-o',
      '--operation',
      type=str,
      default='ISSUE',
      choices=['ISSUE', 'ISSUE_ENC', 'ISSUE_SOM', 'ISSUE_ENC_SOM'],
      dest='operation',
      help='Operation for provisioning the device')
  parser.add_argument(
      '--atapversion',
      type=int,
      required=False,
      choices=[_MESSAGE_VERSION_1, _MESSAGE_VERSION_2],
      dest='atap_version',
      help='AThings protocol message version')

  results = parser.parse_args()
  fastboot_device = results.serial
  algorithm = _ALGORITHMS[results.algorithm]
  operation = _OPERATIONS[results.operation]
  message_version = None
  if hasattr(results, 'atap_version'):
    message_version = results.atap_version
  session_params = _write_operation_start(algorithm, operation, message_version)
  print 'Wrote Operation Start message to tmp/operation_start.bin'
  os.system('fastboot -s %s stage tmp/operation_start.bin' % fastboot_device)
  os.system('fastboot -s %s oem at-get-ca-request' % fastboot_device)
  os.system('fastboot -s %s get_staged tmp/ca_request.bin' % fastboot_device)
  with open('tmp/ca_request.bin', 'rb') as f:
    ca_request = bytearray(f.read())
    _get_ca_response(ca_request, session_params)
  print 'Wrote CA Response message to tmp/ca_response.bin'
  os.system('fastboot -s %s stage tmp/ca_response.bin' % fastboot_device)
  os.system('fastboot -s %s oem at-set-ca-response' % fastboot_device)
  os.system('fastboot -s %s getvar at-attest-uuid' % fastboot_device)


if __name__ == '__main__':
  main()
