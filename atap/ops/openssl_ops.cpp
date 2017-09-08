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

#include "openssl_ops.h"

#include <memory>

#include <openssl/aead.h>
#include <openssl/curve25519.h>
#include <openssl/digest.h>
#include <openssl/ec.h>
#include <openssl/ecdh.h>
#include <openssl/hkdf.h>
#include <openssl/obj_mac.h>
#include <openssl/rand.h>
#include <openssl/sha.h>

namespace atap {

OpensslOps::OpensslOps() {}
OpensslOps::~OpensslOps() {}

AtapResult OpensslOps::get_random_bytes(uint8_t* buf, uint32_t buf_size) {
  if (RAND_bytes(buf, buf_size) != 1) {
    atap_error("Error getting random bytes");
    return ATAP_RESULT_ERROR_IO;
  }
  return ATAP_RESULT_OK;
}

AtapResult OpensslOps::ecdh_shared_secret_compute(
    AtapCurveType curve,
    const uint8_t other_public_key[ATAP_ECDH_KEY_LEN],
    uint8_t public_key[ATAP_ECDH_KEY_LEN],
    uint8_t shared_secret[ATAP_ECDH_SHARED_SECRET_LEN]) {
  if (curve == ATAP_CURVE_TYPE_X25519) {
    uint8_t x25519_priv_key[32];
    uint8_t x25519_pub_key[32];
    if (test_key_size_ == 32) {
      memcpy(x25519_priv_key, test_key_, 32);
      X25519_public_from_private(x25519_pub_key, x25519_priv_key);
    } else {
      // Generate an ephemeral key pair.
      X25519_keypair(x25519_pub_key, x25519_priv_key);
    }
    memset(public_key, 0, ATAP_ECDH_KEY_LEN);
    memcpy(public_key, x25519_pub_key, 32);
    X25519(shared_secret, x25519_priv_key, other_public_key);
  } else if (curve == ATAP_CURVE_TYPE_P256) {
    std::unique_ptr<EC_GROUP, decltype(&EC_GROUP_free)> group(
        EC_GROUP_new_by_curve_name(NID_X9_62_prime256v1), EC_GROUP_free);
    std::unique_ptr<EC_POINT, decltype(&EC_POINT_free)> other_point(
        EC_POINT_new(group.get()), EC_POINT_free);
    if (!EC_POINT_oct2point(group.get(),
                            other_point.get(),
                            other_public_key,
                            ATAP_ECDH_KEY_LEN,
                            NULL)) {
      atap_error("Deserializing other_public_key failed");
      return ATAP_RESULT_ERROR_CRYPTO;
    }

    EC_KEY* p256_priv_key;
    if (test_key_size_ > 0) {
      const uint8_t* buf_ptr = test_key_;
      p256_priv_key = d2i_ECPrivateKey(nullptr, &buf_ptr, test_key_size_);
      EC_KEY_set_group(p256_priv_key, group.get());
    } else {
      p256_priv_key = EC_KEY_new();
      if (!p256_priv_key) {
        atap_error("Error allocating EC key");
        return ATAP_RESULT_ERROR_OOM;
      }
      if (1 != EC_KEY_set_group(p256_priv_key, group.get())) {
        atap_error("EC_KEY_set_group failed");
        EC_KEY_free(p256_priv_key);
        return ATAP_RESULT_ERROR_CRYPTO;
      }
      if (1 != EC_KEY_generate_key(p256_priv_key)) {
        atap_error("EC_KEY_generate_key failed");
        EC_KEY_free(p256_priv_key);
        return ATAP_RESULT_ERROR_CRYPTO;
      }
    }
    std::unique_ptr<EC_KEY, decltype(&EC_KEY_free)> pkey(p256_priv_key,
                                                         EC_KEY_free);
    const EC_POINT* public_point = EC_KEY_get0_public_key(pkey.get());
    if (!EC_POINT_point2oct(group.get(),
                            public_point,
                            POINT_CONVERSION_COMPRESSED,
                            public_key,
                            ATAP_ECDH_KEY_LEN,
                            NULL)) {
      atap_error("Serializing public_key failed");
      return ATAP_RESULT_ERROR_CRYPTO;
    }

    if (-1 == ECDH_compute_key(shared_secret,
                               ATAP_ECDH_SHARED_SECRET_LEN,
                               other_point.get(),
                               pkey.get(),
                               NULL)) {
      atap_error("Error computing shared secret");
      return ATAP_RESULT_ERROR_CRYPTO;
    }
  } else {
    atap_error("Unsupported ECDH curve");
    return ATAP_RESULT_ERROR_UNSUPPORTED_OPERATION;
  }
  return ATAP_RESULT_OK;
}

AtapResult OpensslOps::aes_gcm_128_encrypt(
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
    atap_error("Error initializing EVP_AEAD_CTX");
    return ATAP_RESULT_ERROR_CRYPTO;
  }
  uint8_t* out_buf = (uint8_t*)malloc(len + ATAP_GCM_TAG_LEN);
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
    atap_error("Error encrypting");
    ret = ATAP_RESULT_ERROR_CRYPTO;
    goto out;
  }
  memcpy(ciphertext, out_buf, len);
  memcpy(tag, out_buf + len, ATAP_GCM_TAG_LEN);

out:
  free(out_buf);
  EVP_AEAD_CTX_cleanup(&ctx);
  return ret;
}

AtapResult OpensslOps::aes_gcm_128_decrypt(
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
    atap_error("Error initializing EVP_AEAD_CTX");
    return ATAP_RESULT_ERROR_CRYPTO;
  }
  uint8_t* in_buf = (uint8_t*)malloc(len + ATAP_GCM_TAG_LEN);
  memcpy(in_buf, ciphertext, len);
  memcpy(in_buf + len, tag, ATAP_GCM_TAG_LEN);
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
    atap_error("Error decrypting");
    ret = ATAP_RESULT_ERROR_CRYPTO;
    goto out;
  }
out:
  free(in_buf);
  EVP_AEAD_CTX_cleanup(&ctx);
  return ret;
}

AtapResult OpensslOps::sha256(const uint8_t* plaintext,
                              uint32_t plaintext_len,
                              uint8_t hash[ATAP_SHA256_DIGEST_LEN]) {
  SHA256(plaintext, plaintext_len, hash);
  return ATAP_RESULT_OK;
}

AtapResult OpensslOps::hkdf_sha256(const uint8_t* salt,
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
    atap_error("Error in key derivation");
    return ATAP_RESULT_ERROR_CRYPTO;
  }
  return ATAP_RESULT_OK;
}

void OpensslOps::SetEcdhKeyForTesting(const void* key_data,
                                      size_t size_in_bytes) {
  if (size_in_bytes > sizeof(test_key_)) {
    size_in_bytes = sizeof(test_key_);
  }
  if (size_in_bytes > 0) {
    memcpy(test_key_, key_data, size_in_bytes);
  }
  test_key_size_ = size_in_bytes;
}

}  // namespace atap
