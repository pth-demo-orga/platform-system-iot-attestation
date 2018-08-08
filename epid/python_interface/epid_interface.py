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

"""python utility functions for EPID.

  1. sign a message
  2. verify a signature
  3. verify a EPID key certificate
"""

from ctypes import c_int
from ctypes import c_size_t
from ctypes import c_ubyte
from ctypes import cdll
from ctypes import create_string_buffer
from ctypes import POINTER
import datetime
import hashlib
import os
from pyasn1.codec.der import decoder
from pyasn1_modules import rfc5280
from pyasn1.type.error import PyAsn1Error
from pyasn1.type import namedtype
from pyasn1.type import univ
import sh

# EPID signature size without signature RL
EPID_SIG_SIZE = 360
# 256bit ECC curve byte size is 32
_EPID_COORD_LEN = 32
# EPID group ID length is 16 bytes
_EPID_GID_LEN = 16

# EPID private key group ID
_EPID_GID_START = 14
_EPID_GID_END = 30
# EPID private key Key location
_EPID_KEY_START = 30
_EPID_KEY_END = 158
# EPID private key sha-1 hash location
_EPID_SHA1_START = 158
_EPID_SHA1_END = 178

# hash algorithms
_HASH_ALGOS = {
    'SHA-256': 0,
    'SHA-384': 1,
    'SHA-512': 2,
    'SHA-512_256': 3,
    'SHA3_256': 4,
    'SHA3_384': 5,
    'SHA3_512': 6,
}


_HASH_ALGOS_ALT = {
    '-sha256': 0,
    '-sha512': 2,
}


def read_file(filename):
  try:
    with open(filename, 'rb') as f:
      buf = f.read()
  except IOError:
    buf = ''
  return buf


def convertHashAlg(hashalgo):
  """Convert hash algo string into an int recognized by EPID SDK.

  Currently only SHA256 and SHA512 is recognized.

  Args:
    hashalgo: a string, must be in _HASH_ALGOS or _HASH_ALGOS_ALT
  Return:
    int: enum defined by EPID SDK, see _HAHS_ALGOS
  Raises:
    RuntimeError: Unsupported hash function
  """
  if hashalgo in _HASH_ALGOS.keys():
    return c_int(_HASH_ALGOS[hashalgo])
  elif hashalgo in _HASH_ALGOS_ALT.keys():
    return c_int(_HASH_ALGOS_ALT[hashalgo])
  else:
    raise RuntimeError('Unsupported hash function')


def signmsg(privkey, pubkey, msg, hashalgo='SHA-512'):
  """Create signature with EPID key.

  Args:
    privkey: size must be 144; format: (data, size(byte))
            groupID   16
            A         64
            x         32
            f         32
    pubkey: size must be 144; format: (data, size(byte))
            groupID   16
            h1        64
            h2        64
            w         128
    msg: message to sign
    hashalgo: supported option see: _HASH_ALGOS, _HASH_ALGO_ALT

  Returns:
    signature: size=360

  Raises:
    RuntimeError:
  """
  # digest algorithm
  try:
    hashalg = convertHashAlg(hashalgo)
  except RuntimeError as e:
    raise e

  # create buffer to store signature
  sig = (c_ubyte * EPID_SIG_SIZE).from_buffer(bytearray(EPID_SIG_SIZE))
  sig_p = POINTER(c_ubyte)(sig)

  helper = cdll.LoadLibrary('./libepid.so')
  sign = helper.EpidApiSign
  sign.argtypes = [
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      c_int,
      POINTER(c_ubyte)
  ]

  status = sign(
      POINTER(c_ubyte)(create_string_buffer(msg)), len(msg),
      None, 0,
      POINTER(c_ubyte)(create_string_buffer(privkey)), len(privkey),
      POINTER(c_ubyte)(create_string_buffer(pubkey)), len(pubkey),
      None, 0,
      None, 0,
      hashalg,
      sig_p
  )

  if status:
    raise RuntimeError('signature failed: ', status)
  return bytes(bytearray(sig[0:360]))


def signmsg_atap(key, msg, hashalgo='SHA-512'):
  """Create signature with EPID key.

  Args:
    key: size must be 400; format: (data, size(byte))
            groupID   16
            A         64
            x         32
            f         32
            h1        64
            h2        64
            w         128
    msg: message to sign
    hashalgo: supported option see: _HASH_ALGOS
            'SHA-256'
            'SHA-512'

  Returns:
    signature: size=360

  Raises:
    RuntimeError: Errors while signing
  """
  # digest algorithm
  try:
    hashalg = convertHashAlg(hashalgo)
  except RuntimeError as e:
    raise e

  # create buffer to store signature
  sig = (c_ubyte * EPID_SIG_SIZE).from_buffer(bytearray(EPID_SIG_SIZE))
  sig_p = POINTER(c_ubyte)(sig)
  sig_len = c_size_t()
  sig_len_p = POINTER(c_size_t)(sig_len)

  helper = cdll.LoadLibrary('./libepid.so')
  sign = helper.EpidApiSignAtap
  sign.argtypes = [
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      c_int,
      POINTER(c_ubyte), POINTER(c_size_t)
  ]

  status = sign(
      POINTER(c_ubyte)(create_string_buffer(msg)), len(msg),
      None, 0,
      POINTER(c_ubyte)(create_string_buffer(key)), len(key),
      None, 0,
      None, 0,
      hashalg,
      sig_p, sig_len_p
  )

  if status:
    raise RuntimeError('signature failed: ', status)
  return bytes(bytearray(sig[0:360]))


def verifysig(sig, msg, pubkey, hashalgo='SHA-512'):
  """Verify EPID key signature.

  Args:
    sig: signature
    msg: message to sign
    pubkey: size must be 144; format: (data, size(byte))
          groupID   16
          h1        64
          h2        64
          w         128
    hashalgo: supported option see: _HASH_ALGOS

  Returns:
      Boolean: True->verified, False->not verified
  """
  # digest algorithm
  try:
    hashalg = convertHashAlg(hashalgo)
  except RuntimeError:
    return False

  helper = cdll.LoadLibrary('./libepid.so')
  verify = helper.EpidApiVerify
  verify.argtypes = [
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      POINTER(c_ubyte), c_size_t,
      c_int
  ]

  status = verify(
      POINTER(c_ubyte)(create_string_buffer(sig)), len(sig),
      POINTER(c_ubyte)(create_string_buffer(msg)), len(msg),
      None, 0,
      None, 0,
      None, 0,
      None, 0,
      None, 0,
      POINTER(c_ubyte)(create_string_buffer(pubkey)), len(pubkey),
      None, 0,
      hashalg
  )

  return status == 0


def extract_private_key(buf):
  """Extract EPID private key from Intel format.

  Args:
    buf: buffer to read the file; format:(data, size(byte))
        productID       2
        key ID          8
        Security ver.   4
        group ID        16
        private key     128
        SHA1 of above   20
  Returns:
    private key: size = 144; format: (data, size(byte))
            groupID   16
            A         64
            x         32
            f         32
  Raises:
    RuntimeError:
  """
  # read key file
  if len(buf) != _EPID_SHA1_END:
    raise RuntimeError('Private key format error')
  # check hash value correct
  h = hashlib.new('sha1')
  h.update(buf[:_EPID_KEY_END])
  if h.digest() != buf[_EPID_SHA1_START:_EPID_SHA1_END]:
    raise RuntimeError('Private key format error')

  return buf[_EPID_GID_START:_EPID_KEY_END]


# ASN.1 schema object for pyasn1
class EpidGroupPublicKey(univ.Sequence):
  pass


EpidGroupPublicKey.componentType = namedtype.NamedTypes(
    namedtype.NamedType('gid', univ.Integer()),
    namedtype.NamedType('h1', univ.OctetString()),
    namedtype.NamedType('h2', univ.OctetString()),
    namedtype.NamedType('w', univ.OctetString()),
)


def extract_public_key(buf):
  """Extract EPID public Key from certificate.

  Args:
    buf: buffer containing EPID public key certificate DER format

  Returns:
    public key: size = 144; format: (data, size(byte))
          groupID   16
          h1        64
          h2        64
          w         128
  Raises:
    RuntimeError:
  """
  try:
    cert = decoder.decode(buf, asn1Spec=rfc5280.Certificate())[0]
  except PyAsn1Error:
    raise RuntimeError('public key format error')

  try:
    ret = extract_public_key_from_cert(cert)
  except RuntimeError as e:
    raise e
  return ret


def extract_public_key_from_cert(cert):
  """Extract EPID public Key from certificate.

  Args:
    cert: PyAsn1 Certificate object

  Returns:
    public key: size = 144; format: (data, size(byte))
          groupID   16
          h1        64
          h2        64
          w         128
  Raises:
    RuntimeError:
  """

  try:
    pkey = decoder.decode(cert['tbsCertificate']['subjectPublicKeyInfo'][1].
                          asOctets(), asn1Spec=EpidGroupPublicKey())[0]
  except PyAsn1Error:
    raise RuntimeError('public key format error')

  gid = int(pkey['gid'])
  gid_str = ''

  while gid:
    gid_str = chr(gid & 255) + gid_str
    gid >>= 8

  if len(gid_str) > _EPID_GID_LEN:
    raise RuntimeError('public key format error')
  gid_str = gid_str.rjust(_EPID_GID_LEN, chr(0))

  # strip 0x04 char from each entry h1, h2, w
  h1 = pkey['h1'].asOctets()[1:]
  if len(h1) != _EPID_COORD_LEN * 2:
    raise RuntimeError('public key format error')

  h2 = pkey['h2'].asOctets()[1:]
  if len(h2) != _EPID_COORD_LEN * 2:
    raise RuntimeError('public key format error')

  w = pkey['w'].asOctets()[1:]
  if len(w) != _EPID_COORD_LEN * 4:
    raise RuntimeError('public key format error')

  return gid_str + h1 + h2 + w


def extract_dgst(buf):
  """Extract dgst algorithm from certificate file buffer.

  certificate must be a DER format.

  Args:
    buf: certificate file buffer

  Returns:
    string: algorithm option string '-sha512' '-sha256'

  Raises:
    RuntimeError:
  """
  try:
    cert = decoder.decode(buf, asn1Spec=rfc5280.Certificate())[0]
    oid = str(cert['tbsCertificate']['subjectPublicKeyInfo']
              ['algorithm']['algorithm'])
  except PyAsn1Error:
    raise RuntimeError('certificate format error')

  return extract_dgst_oid(oid)


def extract_dgst_oid(oid):
  """Extract dgst algorithm from an object identifier.

  Support algos are sha256 and sha512 only.

  Args:
    oid: a string contatining dgst algo string
  Return:
    dgst flag string '-sha256' or '-sha512'. EPID uses -sha256
  Raises:
    RuntimeError
  """
  if oid == '1.2.840.10045.4.3.4':
    return '-sha512'
  elif oid in ['1.2.840.10045.4.3.2', '1.2.840.113741.1.9.4.3']:
    return '-sha256'
  else:
    raise RuntimeError('dgst algorithm not supported')


def _remove_tmp_files(tmp_files):
  for tmp_file in tmp_files:
    try:
      os.remove(tmp_file)
    except OSError:
      pass


def verify_cert_file(cert_f, cacert_f):
  """Verify certificate in cert_f is signed by cacert_f.

  cert_f may be an EPID key.
  cacert_f may not be an EPID key.

  Args:
    cert_f: certificate file to be checked DER format.
    cacert_f: CA certificate file DER format.

  Returns:
    String: 'OKAY' -> success, 'FAIL' + error message -> failure

  Exceptions:
    None
  """
  cert_type = rfc5280.Certificate()

  # temporary files
  ca_pubkey_f = 'ca_pubkey.pem'
  tbs_cert_f = 'tbs_certificate.bin'
  sig_f = 'signature.bin'

  tmp_files = [ca_pubkey_f, tbs_cert_f, sig_f]

  # extract tbs certificate
  try:
    parsed = sh.openssl('asn1parse', '-inform',
                        'DER', '-in', cert_f).splitlines()
  except sh.ErrorReturnCode as e:
    _remove_tmp_files(tmp_files)
    return 'FAIL openssl unable to read certificate' + e.message

  split = str(parsed[1]).replace('=', ' ').replace(':', ' ').split()

  tbs_cert_begin = int(split[0])
  tbs_cert_len = int(split[4]) + int(split[6])

  try:
    sh.dd('if='+cert_f, 'of='+tbs_cert_f, 'skip='+str(tbs_cert_begin), 'bs=1',
          'count='+str(tbs_cert_len))
  except sh.ErrorReturnCode as e:
    _remove_tmp_files(tmp_files)
    return 'FAIL failed to extract tbs certificate ' + e.message

  # extract signature from certificate
  # parse certificate
  try:
    cert = decoder.decode(read_file(cert_f), asn1Spec=cert_type)[0]
  except PyAsn1Error:
    _remove_tmp_files(tmp_files)
    return 'FAIL certificate parsing error'
  sig = cert['signature'].asOctets()

  # signature algo
  try:
    dgst_algo = extract_dgst_oid(str(cert['signatureAlgorithm']['algorithm']))
  except:
    _remove_tmp_files(tmp_files)
    return 'FAIL dgst algorithm not supported'

  # write signature to binary file
  try:
    with open(sig_f, 'wb') as f:
      f.write(sig)
  except IOError:
    _remove_tmp_files(tmp_files)
    return 'FAIL cannot wrtie to signature file'

  # get CA public key
  try:
    sh.openssl('x509', '-inform', 'DER', '-in', cacert_f, '-pubkey',
               '-noout', '-out', ca_pubkey_f)
  except sh.ErrorReturnCode as e:
    _remove_tmp_files(tmp_files)
    return 'FAIL CA certificate parsing error ' + e.message

  # check signature
  try:
    sh.openssl('dgst', dgst_algo, '-verify', ca_pubkey_f,
               '-signature', sig_f, tbs_cert_f)
  except sh.ErrorReturnCode as e:
    _remove_tmp_files(tmp_files)
    return 'FAIL signature check failed ' + e.message

  # parse CA certificate
  try:
    cacert = decoder.decode(read_file(cacert_f), asn1Spec=cert_type)[0]
  except PyAsn1Error:
    _remove_tmp_files(tmp_files)
    return 'FAIL CA certificate parsing error'

  # verify contents of cert files, including extensions.
  _remove_tmp_files(tmp_files)

  # check issuer in cert and subject in cacert match
  if cert['tbsCertificate']['issuer'] != cacert['tbsCertificate']['subject']:
    return 'FAIL certificate Issuer and CA certificate Subject do no match'

  res = verify_cert_validity(cert['tbsCertificate']['validity'])
  if res != 'OKAY':
    return res

  res = verify_cert_exts(cert['tbsCertificate']['extensions'],\
      cacert['tbsCertificate']['extensions'])
  if res != 'OKAY':
    return res
  return 'OKAY'


def verify_cert_validity(validity):
  """Verify a Validity object of a cert is currently valid.

  Input can be from any certificate. It may be an EPID key.

  Args:
    validity: rfc5280 Validity type defined in pyasn1_modules

  Returns:
    String: 'OKAY' -> success, 'FAIL' + error message -> failure

  Exceptions:
    None
  """

  # check certificate validity
  time_type = validity[0].getName()
  if validity[1].getName() != time_type:
    return 'FAIL certificate time format error'
  if time_type != 'utcTime':
    return 'FAIL certificate time format error'

  time_start = validity[0][time_type].asDateTime
  time_start = time_start.replace(tzinfo=None)
  time_now = datetime.datetime.utcnow()

  if (time_now - time_start).total_seconds() < 0:
    return 'FAIL certificate not valid yet'

  time_end = validity[1][time_type].asDateTime
  time_end = time_end.replace(tzinfo=None)

  if (time_end - time_now).total_seconds() < 0:
    return 'FAIL certificate expired'

  return 'OKAY'


def verify_cert_exts(cert_exts, cacert_exts):
  """Verify the extensions of certificates cert_exts and cacert_exts.

  cert_exts is the extension of a certificate cert.
  cacert_exts is the extension of a certificate cacert.
  The key of cacert is used to sign cert.
  The checks include key usage, basic constraints and key identifiers.

  Args:
    cert: rfc5280 Extensions type defined in pyasn1_modules
    cacert: rfc5280 Extensions type defined in pyasn1_modules

  Returns:
    String: 'OKAY' -> success, 'FAIL' + error message -> failure

  Exceptions:
    None
  """
  cert_ext_map = rfc5280.certificateExtensionsMap

  # parse certificate extensions
  cert_ca_key_id = ''
  cert_bc_ca = False
  cert_bc_pathlen = -1
  # cert_keyusage_ca = -1
  # cert_keyusage_crl = -1

  for i in range(len(cert_exts)):
    extn_id = cert_exts[i]['extnID']
    if extn_id not in cert_ext_map.keys():
      return 'FAIL certificate unrecognized extension'

    if extn_id == rfc5280.id_ce_keyUsage:
      # keyUsage
      # check CA CRL capability only
      try:
        key_usage = decoder.decode(cert_exts[i]['extnValue'].asOctets(),
                                   asn1Spec=cert_ext_map[extn_id])[0]
      except PyAsn1Error:
        return 'FAIL keyUsage parsing error'
      # cert_keyusage_ca = key_usage[key_usage.namedValues['keyCertSign']]
      # cert_keyusage_crl = key_usage[key_usage.namedValues['cRLSign']]
    elif extn_id == rfc5280.id_ce_authorityKeyIdentifier:
      # authorityKeyIdentifier
      try:
        auth_key_id = decoder.decode(cert_exts[i]['extnValue'].asOctets(),
                                     asn1Spec=cert_ext_map[extn_id])[0]
      except PyAsn1Error:
        return 'FAIL authorityKeyIdentifier parsing error'
      if len(auth_key_id) < 1 or len(auth_key_id) > 3:
        return 'FAIL authorityKeyIdentifier parsing error'
      cert_ca_key_id = str(auth_key_id[0].asOctets())
    elif extn_id == rfc5280.id_ce_basicConstraints:
      # basicConstraints
      try:
        bc = decoder.decode(cert_exts[i]['extnValue'].asOctets(),
                            asn1Spec=cert_ext_map[extn_id])[0]
      except PyAsn1Error:
        return 'FAIL basicConstraints parsing error'
      if len(bc) == 1:
        cert_bc_ca = bool(bc[0])
      elif len(bc) == 2:
        cert_bc_ca = bool(bc[0])
        cert_bc_pathlen = int(bc[1])
      else:
        return 'FAIL basicConstraints parsing error'

  # parsing CA certificate extensions
  cacert_key_id = ''
  cacert_bc_ca = False
  cacert_bc_pathlen = -1
  cacert_keyusage_ca = -1
  # cacert_keyusage_crl = -1

  for i in range(len(cacert_exts)):
    extn_id = cacert_exts[i]['extnID']
    if extn_id not in cert_ext_map.keys():
      return 'FAIL CA certificate unrecognized extension'

    if extn_id == rfc5280.id_ce_keyUsage:
      # keyUsage
      # check CA CRL capability only
      try:
        key_usage = decoder.decode(cacert_exts[i]['extnValue'].asOctets(),
                                   asn1Spec=cert_ext_map[extn_id])[0]
      except PyAsn1Error:
        return 'FAIL CA keyUsage parsing error'
      cacert_keyusage_ca = key_usage[key_usage.namedValues['keyCertSign']]
      # cacert_keyusage_crl = key_usage[key_usage.namedValues['cRLSign']]
    elif extn_id == rfc5280.id_ce_subjectKeyIdentifier:
      # subjectKeyIdentifier
      try:
        subject_key_id = decoder.decode(cacert_exts[i]['extnValue'].asOctets(),
                                        asn1Spec=cert_ext_map[extn_id])[0]
      except PyAsn1Error:
        return 'FAIL subjectKeyIdentifier parsing error'
      cacert_key_id = str(subject_key_id.asOctets())
    elif extn_id == rfc5280.id_ce_basicConstraints:
      # basicConstraints
      try:
        bc = decoder.decode(cacert_exts[i]['extnValue'].asOctets(),
                            asn1Spec=cert_ext_map[extn_id])[0]
      except PyAsn1Error:
        return 'FAIL CA basicConstraints parsing error'
      if len(bc) == 1:
        cacert_bc_ca = bool(bc[0])
      elif len(bc) == 2:
        cacert_bc_ca = bool(bc[0])
        cacert_bc_pathlen = int(bc[1])
      else:
        return 'FAIL CA basicConstraints parsing error'

  if cert_ca_key_id and cacert_key_id and cert_ca_key_id != cacert_key_id:
    return 'FAIL key Identifiers mismatch' + cert_ca_key_id + cacert_key_id

  if (cacert_bc_ca and cacert_keyusage_ca == 0) or \
     (not cacert_bc_ca and cacert_keyusage_ca == 1):
    return 'FAIL contradicting CA capablity'

  if not cacert_bc_ca:
    return 'FAIL signer is not capable of signing certificate'

  if cacert_bc_ca and cacert_bc_pathlen == 0 and cert_bc_ca:
    return 'FAIL signer is not capable of authorizing CA'

  if cacert_bc_pathlen > -1 and cert_bc_ca and \
     (cert_bc_pathlen == -1 or cert_bc_pathlen >= cacert_bc_pathlen):
    return 'FAIL certificate pathlen is not permissible'

  # all checks pass, return 'OKAY'
  return 'OKAY'
