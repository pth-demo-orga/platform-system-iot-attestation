/*
 * Copyright (C) 2016 The Android Open Source Project
 *
 * Permission is hereby granted, free of charge, to any person
 * obtaining a copy of this software and associated documentation
 * files (the "Software"), to deal in the Software without
 * restriction, including without limitation the rights to use, copy,
 * modify, merge, publish, distribute, sublicense, and/or sell copies
 * of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
 * BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
 * ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
 * CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

#include "fake_atap_ops.h"

#include <base/files/file_util.h>
#include <base/strings/stringprintf.h>
#include <gtest/gtest.h>
#include <string>

#include <openssl/aead.h>
#include <openssl/curve25519.h>
#include <openssl/digest.h>
#include <openssl/ec.h>
#include <openssl/ecdh.h>
#include <openssl/hkdf.h>
#include <openssl/obj_mac.h>
#include <openssl/rand.h>
#include <openssl/sha.h>

#include "atap_unittest_util.h"

namespace atap {

AtapResult FakeAtapOps::read_product_id(
    AtapOps* ops, uint8_t product_id[ATAP_PRODUCT_ID_LEN]) {
  memset(product_id, 0x00, ATAP_PRODUCT_ID_LEN);
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::get_auth_key_type(AtapOps* ops, AtapKeyType* key_type) {
  *key_type = ATAP_KEY_TYPE_NONE;
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::read_auth_key_cert_chain(AtapOps* ops,
                                                 AtapCertChain* cert_chain) {
  return ATAP_RESULT_ERROR_UNSUPPORTED_OPERATION;
}

AtapResult FakeAtapOps::write_attestation_key(AtapOps* ops,
                                              AtapKeyType key_type,
                                              const AtapBlob* key,
                                              const AtapCertChain* cert_chain) {
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::read_attestation_public_key(
    AtapOps* ops,
    AtapKeyType key_type,
    uint8_t pubkey[ATAP_KEY_LEN_MAX],
    uint32_t* pubkey_len) {
  return ATAP_RESULT_ERROR_UNSUPPORTED_OPERATION;
}

AtapResult FakeAtapOps::read_soc_global_key(
    AtapOps* ops, uint8_t global_key[ATAP_AES_128_KEY_LEN]) {
  return ATAP_RESULT_ERROR_UNSUPPORTED_OPERATION;
}

AtapResult FakeAtapOps::write_hex_uuid(AtapOps* ops,
                                       const uint8_t uuid[ATAP_HEX_UUID_LEN]) {
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::get_random_bytes(AtapOps* ops,
                                         uint8_t* buf,
                                         uint32_t buf_size) {
  if (RAND_bytes(buf, buf_size) != 1) {
    fprintf(stderr, "Error getting random bytes\n");
    return ATAP_RESULT_ERROR_IO;
  }
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::auth_key_sign(AtapOps* ops,
                                      const uint8_t* nonce,
                                      uint32_t nonce_len,
                                      uint8_t sig[ATAP_SIGNATURE_LEN_MAX],
                                      uint32_t* sig_len) {
  return ATAP_RESULT_ERROR_UNSUPPORTED_OPERATION;
}

AtapResult FakeAtapOps::ecdh_shared_secret_compute(
    AtapOps* ops,
    AtapCurveType curve,
    const uint8_t other_public_key[ATAP_ECDH_KEY_LEN],
    uint8_t public_key[ATAP_ECDH_KEY_LEN],
    uint8_t shared_secret[ATAP_ECDH_SHARED_SECRET_LEN]) {
  if (curve == ATAP_CURVE_TYPE_X25519) {
    std::string ca_privkey;
    EXPECT_TRUE(base::ReadFileToString(base::FilePath(kCaX25519PrivateKey),
                                       &ca_privkey));
    std::string ca_pubkey;
    EXPECT_TRUE(
        base::ReadFileToString(base::FilePath(kCaX25519PublicKey), &ca_pubkey));
    memset(public_key, 0, ATAP_ECDH_KEY_LEN);
    memcpy(public_key,
           reinterpret_cast<uint8_t*>(&ca_pubkey[0]),
           ATAP_ECDH_KEY_LEN);
    X25519(shared_secret,
           reinterpret_cast<uint8_t*>(&ca_privkey[0]),
           other_public_key);
  } else if (curve == ATAP_CURVE_TYPE_P256) {
    EC_GROUP* group = EC_GROUP_new_by_curve_name(NID_X9_62_prime256v1);
    EC_POINT* other_point = EC_POINT_new(group);
    if (!EC_POINT_oct2point(
            group, other_point, other_public_key, ATAP_ECDH_KEY_LEN, NULL)) {
      fprintf(stderr, "Deserializing other_public_key failed\n");
      return ATAP_RESULT_ERROR_CRYPTO;
    }

    std::string ca_privkey;
    EXPECT_TRUE(
        base::ReadFileToString(base::FilePath(kCaP256PrivateKey), &ca_privkey));
    const uint8_t* buf_ptr = reinterpret_cast<const uint8_t*>(&ca_privkey[0]);
    EC_KEY* pkey = d2i_ECPrivateKey(nullptr, &buf_ptr, ca_privkey.size());
    if (!pkey) {
      fprintf(stderr, "Error reading ECC key\n");
      return ATAP_RESULT_ERROR_CRYPTO;
    }
    EC_KEY_set_group(pkey, group);

    const EC_POINT* public_point = EC_KEY_get0_public_key(pkey);
    if (!EC_POINT_point2oct(group,
                            public_point,
                            POINT_CONVERSION_COMPRESSED,
                            public_key,
                            ATAP_ECDH_KEY_LEN,
                            NULL)) {
      fprintf(stderr, "Serializing public_key failed\n");
      EC_KEY_free(pkey);
      return ATAP_RESULT_ERROR_CRYPTO;
    }

    if (-1 == ECDH_compute_key(shared_secret,
                               ATAP_ECDH_SHARED_SECRET_LEN,
                               other_point,
                               pkey,
                               NULL)) {
      fprintf(stderr, "Error computing shared secret\n");
      EC_KEY_free(pkey);
      return ATAP_RESULT_ERROR_CRYPTO;
    }
  } else {
    fprintf(stderr, "Unsupported ECDH curve: %d\n", curve);
    return ATAP_RESULT_ERROR_UNSUPPORTED_OPERATION;
  }
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::aes_gcm_128_encrypt(
    AtapOps* ops,
    const uint8_t* plaintext,
    uint32_t len,
    const uint8_t iv[ATAP_GCM_IV_LEN],
    const uint8_t key[ATAP_AES_128_KEY_LEN],
    uint8_t* ciphertext,
    uint8_t tag[ATAP_GCM_TAG_LEN]) {
  AtapResult ret = ATAP_RESULT_OK;
  EVP_AEAD_CTX ctx;
  if (!EVP_AEAD_CTX_init(&ctx,
                         EVP_aead_aes_128_gcm(),
                         key,
                         ATAP_AES_128_KEY_LEN,
                         ATAP_GCM_TAG_LEN,
                         NULL)) {
    fprintf(stderr, "Error initializing EVP_AEAD_CTX\n");
    return ATAP_RESULT_ERROR_CRYPTO;
  }
  uint8_t* out_buf = (uint8_t*)atap_malloc(len + ATAP_GCM_TAG_LEN);
  size_t out_len = len + ATAP_GCM_TAG_LEN;
  if (!EVP_AEAD_CTX_seal(&ctx,
                         out_buf,
                         &out_len,
                         len + ATAP_GCM_TAG_LEN,
                         iv,
                         ATAP_GCM_IV_LEN,
                         plaintext,
                         len,
                         NULL,
                         0)) {
    fprintf(stderr, "Error encrypting\n");
    ret = ATAP_RESULT_ERROR_CRYPTO;
    goto out;
  }
  atap_memcpy(ciphertext, out_buf, len);
  atap_memcpy(tag, out_buf + len, ATAP_GCM_TAG_LEN);

out:
  atap_free(out_buf);
  EVP_AEAD_CTX_cleanup(&ctx);
  return ret;
}

AtapResult FakeAtapOps::aes_gcm_128_decrypt(
    AtapOps* ops,
    const uint8_t* ciphertext,
    uint32_t len,
    const uint8_t iv[ATAP_GCM_IV_LEN],
    const uint8_t key[ATAP_AES_128_KEY_LEN],
    const uint8_t tag[ATAP_GCM_TAG_LEN],
    uint8_t* plaintext) {
  AtapResult ret = ATAP_RESULT_OK;
  EVP_AEAD_CTX ctx;
  if (!EVP_AEAD_CTX_init(&ctx,
                         EVP_aead_aes_128_gcm(),
                         key,
                         ATAP_AES_128_KEY_LEN,
                         ATAP_GCM_TAG_LEN,
                         NULL)) {
    fprintf(stderr, "Error initializing EVP_AEAD_CTX\n");
    return ATAP_RESULT_ERROR_CRYPTO;
  }
  uint8_t* in_buf = (uint8_t*)atap_malloc(len + ATAP_GCM_TAG_LEN);
  atap_memcpy(in_buf, ciphertext, len);
  atap_memcpy(in_buf + len, tag, ATAP_GCM_TAG_LEN);
  size_t out_len = len;
  if (!EVP_AEAD_CTX_open(&ctx,
                         plaintext,
                         &out_len,
                         len,
                         iv,
                         ATAP_GCM_IV_LEN,
                         in_buf,
                         len + ATAP_GCM_TAG_LEN,
                         NULL,
                         0)) {
    fprintf(stderr, "Error decrypting\n");
    ret = ATAP_RESULT_ERROR_CRYPTO;
    goto out;
  }
out:
  atap_free(in_buf);
  EVP_AEAD_CTX_cleanup(&ctx);
  return ret;
}

AtapResult FakeAtapOps::sha256(AtapOps* ops,
                               const uint8_t* plaintext,
                               uint32_t plaintext_len,
                               uint8_t hash[ATAP_SHA256_DIGEST_LEN]) {
  SHA256(plaintext, plaintext_len, hash);
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::hkdf_sha256(AtapOps* ops,
                                    const uint8_t* salt,
                                    uint32_t salt_len,
                                    const uint8_t* ikm,
                                    uint32_t ikm_len,
                                    const uint8_t* info,
                                    uint32_t info_len,
                                    uint8_t* okm,
                                    int32_t okm_len) {
  if (!HKDF(okm,
            okm_len,
            EVP_sha256(),
            ikm,
            ikm_len,
            salt,
            salt_len,
            info,
            info_len)) {
    fprintf(stderr, "Error in key derivation\n");
    return ATAP_RESULT_ERROR_CRYPTO;
  }
  return ATAP_RESULT_OK;
}

static AtapResult my_ops_read_product_id(
    AtapOps* ops, uint8_t product_id[ATAP_PRODUCT_ID_LEN]) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)->delegate()->read_product_id(
      ops, product_id);
}

static AtapResult my_ops_get_auth_key_type(AtapOps* ops,
                                           AtapKeyType* key_type) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)
      ->delegate()
      ->get_auth_key_type(ops, key_type);
}

static AtapResult my_ops_read_auth_key_cert_chain(AtapOps* ops,
                                                  AtapCertChain* cert_chain) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)
      ->delegate()
      ->read_auth_key_cert_chain(ops, cert_chain);
}

static AtapResult my_ops_write_attestation_key(
    AtapOps* ops,
    AtapKeyType key_type,
    const AtapBlob* key,
    const AtapCertChain* cert_chain) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)
      ->delegate()
      ->write_attestation_key(ops, key_type, key, cert_chain);
}

static AtapResult my_ops_read_attestation_public_key(
    AtapOps* ops,
    AtapKeyType key_type,
    uint8_t pubkey[ATAP_KEY_LEN_MAX],
    uint32_t* pubkey_len) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)
      ->delegate()
      ->read_attestation_public_key(ops, key_type, pubkey, pubkey_len);
}

static AtapResult my_ops_read_soc_global_key(
    AtapOps* ops, uint8_t global_key[ATAP_AES_128_KEY_LEN]) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)
      ->delegate()
      ->read_soc_global_key(ops, global_key);
}

static AtapResult my_ops_write_hex_uuid(AtapOps* ops,
                                        const uint8_t uuid[ATAP_HEX_UUID_LEN]) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)->delegate()->write_hex_uuid(
      ops, uuid);
}

static AtapResult my_ops_get_random_bytes(AtapOps* ops,
                                          uint8_t* buf,
                                          uint32_t buf_size) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)->delegate()->get_random_bytes(
      ops, buf, buf_size);
}

static AtapResult my_ops_auth_key_sign(AtapOps* ops,
                                       const uint8_t* nonce,
                                       uint32_t nonce_len,
                                       uint8_t sig[ATAP_SIGNATURE_LEN_MAX],
                                       uint32_t* sig_len) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)->delegate()->auth_key_sign(
      ops, nonce, nonce_len, sig, sig_len);
}

static AtapResult my_ops_ecdh_shared_secret_compute(
    AtapOps* ops,
    AtapCurveType curve,
    const uint8_t other_public_key[ATAP_ECDH_KEY_LEN],
    uint8_t public_key[ATAP_ECDH_KEY_LEN],
    uint8_t shared_secret[ATAP_ECDH_SHARED_SECRET_LEN]) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)
      ->delegate()
      ->ecdh_shared_secret_compute(
          ops, curve, other_public_key, public_key, shared_secret);
}

static AtapResult my_ops_aes_gcm_128_encrypt(
    AtapOps* ops,
    const uint8_t* plaintext,
    uint32_t len,
    const uint8_t iv[ATAP_GCM_IV_LEN],
    const uint8_t key[ATAP_AES_128_KEY_LEN],
    uint8_t* ciphertext,
    uint8_t tag[ATAP_GCM_TAG_LEN]) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)
      ->delegate()
      ->aes_gcm_128_encrypt(ops, plaintext, len, iv, key, ciphertext, tag);
}

static AtapResult my_ops_aes_gcm_128_decrypt(
    AtapOps* ops,
    const uint8_t* ciphertext,
    uint32_t len,
    const uint8_t iv[ATAP_GCM_IV_LEN],
    const uint8_t key[ATAP_AES_128_KEY_LEN],
    const uint8_t tag[ATAP_GCM_TAG_LEN],
    uint8_t* plaintext) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)
      ->delegate()
      ->aes_gcm_128_decrypt(ops, ciphertext, len, iv, key, tag, plaintext);
}

static AtapResult my_ops_sha256(AtapOps* ops,
                                const uint8_t* plaintext,
                                uint32_t plaintext_len,
                                uint8_t hash[ATAP_SHA256_DIGEST_LEN]) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)->delegate()->sha256(
      ops, plaintext, plaintext_len, hash);
}

static AtapResult my_ops_hkdf_sha256(AtapOps* ops,
                                     const uint8_t* salt,
                                     uint32_t salt_len,
                                     const uint8_t* ikm,
                                     uint32_t ikm_len,
                                     const uint8_t* info,
                                     uint32_t info_len,
                                     uint8_t* okm,
                                     uint32_t okm_len) {
  return FakeAtapOps::GetInstanceFromAtapOps(ops)->delegate()->hkdf_sha256(
      ops, salt, salt_len, ikm, ikm_len, info, info_len, okm, okm_len);
}

FakeAtapOps::FakeAtapOps() {
  atap_ops_.user_data = this;
  atap_ops_.read_product_id = my_ops_read_product_id;
  atap_ops_.get_auth_key_type = my_ops_get_auth_key_type;
  atap_ops_.read_auth_key_cert_chain = my_ops_read_auth_key_cert_chain;
  atap_ops_.write_attestation_key = my_ops_write_attestation_key;
  atap_ops_.read_attestation_public_key = my_ops_read_attestation_public_key;
  atap_ops_.read_soc_global_key = my_ops_read_soc_global_key;
  atap_ops_.write_hex_uuid = my_ops_write_hex_uuid;
  atap_ops_.get_random_bytes = my_ops_get_random_bytes;
  atap_ops_.auth_key_sign = my_ops_auth_key_sign;
  atap_ops_.ecdh_shared_secret_compute = my_ops_ecdh_shared_secret_compute;
  atap_ops_.aes_gcm_128_encrypt = my_ops_aes_gcm_128_encrypt;
  atap_ops_.aes_gcm_128_decrypt = my_ops_aes_gcm_128_decrypt;
  atap_ops_.sha256 = my_ops_sha256;
  atap_ops_.hkdf_sha256 = my_ops_hkdf_sha256;

  delegate_ = this;
}

FakeAtapOps::~FakeAtapOps() {}

}  // namespace atap
