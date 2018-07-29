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

"""Tests for epid_interface.py.

Tests include EPID signature/verification and EPID certificate check.
"""

import datetime
import epid_interface
import hashlib
from pyasn1.codec.der import decoder
from pyasn1.codec.der import encoder
from pyasn1_modules import rfc5280
from pyasn1.type.univ import ObjectIdentifier
from pyasn1.type.univ import tag
import sh
import unittest

class EpidSignatureTest(unittest.TestCase):
  g1pubkey = epid_interface.read_file('../testdata/group1pubkey.bin')
  g1privkey1 = epid_interface.read_file('../testdata/group1privkey1.bin')
  g1privkey2 = epid_interface.read_file('../testdata/group1privkey2.bin')
  g1privkey3 = epid_interface.read_file('../testdata/group1privkey3.bin')
  g2pubkey = epid_interface.read_file('../testdata/group2pubkey.bin')
  g2privkey1 = epid_interface.read_file('../testdata/group2privkey1.bin')
  g2privkey2 = epid_interface.read_file('../testdata/group2privkey2.bin')
  g2privkey3 = epid_interface.read_file('../testdata/group2privkey3.bin')

  # test sign and verify
  def testSignVerify1(self):
    msg = 'test message'
    sig = epid_interface.signmsg_atap(self.g1privkey1, msg)
    self.assertTrue(epid_interface.verifysig(sig, msg, self.g1pubkey))

  def testSignVerify2(self):
    msg = 'test message'
    sig = epid_interface.signmsg_atap(self.g1privkey1, msg)
    self.assertFalse(epid_interface.verifysig(sig, msg, self.g2pubkey))

  def testSignVerify3(self):
    msg1 = 'test message1'
    msg2 = 'test message2'
    sig = epid_interface.signmsg_atap(self.g1privkey1, msg1)
    self.assertFalse(epid_interface.verifysig(sig, msg2, self.g2pubkey))

  def testSignVerify4(self):
    msg = 'test message'
    sig = epid_interface.signmsg_atap(self.g1privkey1, msg, '-sha256')
    self.assertFalse(epid_interface.verifysig( \
                    sig, msg, self.g1pubkey, '-sha512'))


def checkTempFiles():
  # check tmp files are not deleted
  files = sh.ls().splitlines()
  return 'ca_pubkey.pem' in files or 'tbs_certificate.bin' in files \
         or 'signature.bin' in files


class EpidCertificateTest(unittest.TestCase):
  # EPID certificate file
  cert0_f = '../testdata/cert0.cer'
  # EPID key issuing CA certificate file, ECDSA key
  cert1_f = '../testdata/cert1.cer'
  # Root CA certificate file, ECDSA key
  cert2_f = '../testdata/cert2.cer'

  # read files into buf
  c0 = epid_interface.read_file(cert0_f)
  c1 = epid_interface.read_file(cert1_f)
  c2 = epid_interface.read_file(cert2_f)

  cert0 = decoder.decode(c0, asn1Spec=rfc5280.Certificate())[0]
  cert1 = decoder.decode(c1, asn1Spec=rfc5280.Certificate())[0]
  cert2 = decoder.decode(c2, asn1Spec=rfc5280.Certificate())[0]

  # test files read correctly
  def testReadFile(self):
    self.assertNotEqual(len(self.c0), 0)
    self.assertNotEqual(len(self.c1), 0)
    self.assertNotEqual(len(self.c2), 0)

  # test extract_public_key
  def testExtractEpidPublicKeyEmpty(self):
    with self.assertRaises(RuntimeError) as e:
      epid_interface.extract_public_key('')
    self.assertEqual(str(e.exception), 'public key format error')

  def testExtractEpidPublicKey0(self):
    key = epid_interface.extract_public_key(self.c0)
    self.assertEqual(len(key), 272)

  def testExtractEpidPublicKey1(self):
    with self.assertRaises(RuntimeError) as e:
      epid_interface.extract_public_key(self.c1)
    self.assertEqual(str(e.exception), 'public key format error')

  # test extract_dgst
  def testExtractDgstEmpty(self):
    with self.assertRaises(RuntimeError) as e:
      epid_interface.extract_dgst('')
    self.assertEqual(str(e.exception), 'certificate format error')

  def testExtractDgst0(self):
    dgst = epid_interface.extract_dgst(self.c0)
    self.assertEqual(dgst, '-sha256')

  def testExtractDgstOidEmpty(self):
    with self.assertRaises(RuntimeError) as e:
      dgst = epid_interface.extract_dgst_oid('')
    self.assertEqual(str(e.exception), 'dgst algorithm not supported')

  def testExtractDgstOid0(self):
    with self.assertRaises(RuntimeError) as e:
      dgst = epid_interface.extract_dgst_oid('1.2.840.10045.4.3.3')
    self.assertEqual(str(e.exception), 'dgst algorithm not supported')

  def testExtractDgstOid0(self):
    dgst = epid_interface.extract_dgst_oid('1.2.840.113741.1.9.4.3')
    self.assertEqual(dgst,  '-sha256')

  #test Certificate validity check
  def testCertificateValidityTime1(self):
    v = rfc5280.Validity()
    time2 = datetime.datetime.utcnow()
    time1 = time2 - datetime.timedelta(days=365)
    v[0]['utcTime'] = v[0]['utcTime'].fromDateTime(time1)
    v[1]['utcTime'] = v[1]['utcTime'].fromDateTime(time2)
    res = epid_interface.verify_cert_validity(v)
    self.assertEqual(res, 'FAIL certificate expired')

  def testCertificateValidityTime2(self):
    v = rfc5280.Validity()
    time1 = datetime.datetime.utcnow() + datetime.timedelta(days=1)
    time2 = time1 + datetime.timedelta(days=365)
    v[0]['utcTime'] = v[0]['utcTime'].fromDateTime(time1)
    v[1]['utcTime'] = v[1]['utcTime'].fromDateTime(time2)
    res = epid_interface.verify_cert_validity(v)
    self.assertEqual(res, 'FAIL certificate not valid yet')

  def testCertificateValidityTime3(self):
    v = rfc5280.Validity()
    time1 = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    time2 = time1 + datetime.timedelta(days=2)
    v[0]['utcTime'] = v[0]['utcTime'].fromDateTime(time1)
    v[1]['utcTime'] = v[1]['utcTime'].fromDateTime(time2)
    res = epid_interface.verify_cert_validity(v)
    self.assertEqual(res, 'OKAY')

  def testCertificateValidityFormat1(self):
    time1 = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    time2 = time1 + datetime.timedelta(days=2)
    v = rfc5280.Validity()
    v[0]['generalTime'] = v[0]['generalTime'].fromDateTime(time1)
    v[1]['utcTime'] = v[1]['utcTime'].fromDateTime(time2)
    res = epid_interface.verify_cert_validity(v)
    self.assertEqual(res, 'FAIL certificate time format error')

  def testCertificateValidityFormat2(self):
    time1 = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    time2 = time1 + datetime.timedelta(days=2)
    v = rfc5280.Validity()
    v[0]['utcTime'] = v[0]['utcTime'].fromDateTime(time1)
    v[1]['generalTime'] = v[1]['generalTime'].fromDateTime(time2)
    res = epid_interface.verify_cert_validity(v)
    self.assertEqual(res, 'FAIL certificate time format error')

  def testCertificateValidityFormat3(self):
    time1 = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    time2 = time1 + datetime.timedelta(days=2)
    v = rfc5280.Validity()
    v[0]['generalTime'] = v[0]['generalTime'].fromDateTime(time1)
    v[1]['generalTime'] = v[1]['generalTime'].fromDateTime(time2)
    res = epid_interface.verify_cert_validity(v)
    self.assertEqual(res, 'FAIL certificate time format error')

  # test extension checks
  def testExtensionCheckEmpty(self):
    # empty extensions
    ext = rfc5280.Extensions()
    caext = rfc5280.Extensions()
    res = epid_interface.verify_cert_exts(ext, caext)
    self.assertEqual(res, 'FAIL signer is not capable of signing certificate')

  def testExtensionCheckInvalidId(self):
    ext = rfc5280.Extension()
    ext['extnID'] = ObjectIdentifier('1.2.840.10045.4.3.3')
    # empty extensions
    exts = rfc5280.Extensions()
    caexts = rfc5280.Extensions()
    exts.append(ext)
    res = epid_interface.verify_cert_exts(exts, caexts)
    self.assertEqual(res, 'FAIL certificate unrecognized extension')

    exts = rfc5280.Extensions()
    caexts.append(ext)
    res = epid_interface.verify_cert_exts(exts, caexts)
    self.assertEqual(res, 'FAIL CA certificate unrecognized extension')

  def testExtensionCheckKeyIdentifiersFormat1(self):
    ext = rfc5280.Extension()
    caext = rfc5280.Extension()
    caext['extnID'] = rfc5280.id_ce_subjectKeyIdentifier
    caext['extnValue'] = '7712312'
    exts = rfc5280.Extensions()
    caexts = rfc5280.Extensions()
    caexts.append(caext)
    res = epid_interface.verify_cert_exts(exts, caexts)
    self.assertEqual(res, 'FAIL subjectKeyIdentifier parsing error')

  def testExtensionCheckKeyIdentifiersFormat2(self):
    exts = rfc5280.Extensions()
    caexts = rfc5280.Extensions()
    ext = rfc5280.Extension()
    ext['extnID'] = rfc5280.id_ce_authorityKeyIdentifier
    exts.setComponentByPosition(0, ext)
    exts[0]['extnValue'] =  '7712312'
    res = epid_interface.verify_cert_exts(exts, caexts)
    self.assertEqual(res, 'FAIL authorityKeyIdentifier parsing error')

  def testExtensionCheckKeyIdentifiersMatch1(self):
    exts = rfc5280.Extensions()
    caexts = rfc5280.Extensions()
    # give cacert CA so that the check will pass
    caexts.setComponentByPosition(0,
          self.cert1['tbsCertificate']['extensions'][2])
    exts.setComponentByPosition(0,
          self.cert0['tbsCertificate']['extensions'][0])
    res = epid_interface.verify_cert_exts(exts, caexts)
    # identifiers matching check is not mandotory
    # if authority or subject key ID is missing, check is expected to pass
    self.assertEqual(res, 'OKAY')

  def testExtensionCheckKeyIdentifiersMatch2(self):
    exts = rfc5280.Extensions()
    caexts = rfc5280.Extensions()
    # give cacert CA so that the check will pass
    caexts.setComponentByPosition(0,
          self.cert1['tbsCertificate']['extensions'][2])
    exts.setComponentByPosition(0,
          self.cert0['tbsCertificate']['extensions'][0])
    caexts.setComponentByPosition(1,
          self.cert1['tbsCertificate']['extensions'][5])
    res = epid_interface.verify_cert_exts(exts, caexts)
    self.assertEqual(res, 'OKAY')

  def testExtensionCheckKeyIdentifiersMatch3(self):
    exts = rfc5280.Extensions()
    caexts = rfc5280.Extensions()
    # give cacert CA so that the check will pass
    caexts.setComponentByPosition(0,
          self.cert1['tbsCertificate']['extensions'][2])
    caexts.setComponentByPosition(1,
          self.cert1['tbsCertificate']['extensions'][5])
    exts.setComponentByPosition(0,
          self.cert1['tbsCertificate']['extensions'][1])
    res = epid_interface.verify_cert_exts(exts, caexts)
    self.assertTrue(res.startswith('FAIL key Identifiers mismatch'))

  def testBasicConstraints1(self):
    exts = rfc5280.Extensions()
    caexts = rfc5280.Extensions()
    #cert CA true pathLen 0
    #cacert none
    exts.setComponentByPosition(0,
          self.cert1['tbsCertificate']['extensions'][2])
    res = epid_interface.verify_cert_exts(exts, caexts)
    self.assertEqual(res, 'FAIL signer is not capable of signing certificate')

  def testBasicConstraints(self):
    exts = rfc5280.Extensions()
    caexts = rfc5280.Extensions()
    #cert CA true pathLen 0
    #cacert CA true pathLen 0
    exts.setComponentByPosition(0,
          self.cert1['tbsCertificate']['extensions'][2])
    caexts.setComponentByPosition(0,
          self.cert1['tbsCertificate']['extensions'][2])
    res = epid_interface.verify_cert_exts(exts, caexts)
    self.assertEqual(res, 'FAIL signer is not capable of authorizing CA')

  def testBasicConstraints(self):
    exts = rfc5280.Extensions()
    caexts = rfc5280.Extensions()
    #cert CA true pathLen 2
    #cacert CA true pathLen 0
    caexts.setComponentByPosition(0,
          self.cert1['tbsCertificate']['extensions'][2])
    exts.setComponentByPosition(0,
          self.cert2['tbsCertificate']['extensions'][0])
    res = epid_interface.verify_cert_exts(exts, caexts)
    self.assertEqual(res, 'FAIL signer is not capable of authorizing CA')

  def testBasicConstraints(self):
    exts = rfc5280.Extensions()
    caexts = rfc5280.Extensions()
    #cert CA true pathLen 2
    #cacert CA true pathLen 2
    exts.setComponentByPosition(0,
          self.cert2['tbsCertificate']['extensions'][0])
    caexts.setComponentByPosition(0,
          self.cert2['tbsCertificate']['extensions'][0])
    res = epid_interface.verify_cert_exts(exts, caexts)
    self.assertEqual(res, 'FAIL certificate pathlen is not permissible')

  # test Certificate checks
  def testCertificate1(self):
    res = epid_interface.verify_cert_file(self.cert0_f, self.cert1_f)
    self.assertEqual('OKAY', res)
    self.assertFalse(checkTempFiles())

  def testCertificate2(self):
    res = epid_interface.verify_cert_file(self.cert1_f, self.cert2_f)
    self.assertEqual('OKAY', res)
    self.assertFalse(checkTempFiles())

  def testCertificate3(self):
    res = epid_interface.verify_cert_file(self.cert1_f, self.cert0_f)
    self.assertTrue(res.startswith('FAIL CA certificate parsing error'))
    self.assertFalse(checkTempFiles())

  def testCertificate4(self):
    res = epid_interface.verify_cert_file(self.cert2_f, self.cert1_f)
    self.assertTrue(res.startswith('FAIL signature check failed'))
    self.assertFalse(checkTempFiles())


if __name__ == '__main__':
  unittest.main()
