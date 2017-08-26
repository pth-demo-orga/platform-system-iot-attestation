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

#ifndef FAKE_ATAP_OPS_H_
#define FAKE_ATAP_OPS_H_

#include <libatap/libatap.h>

namespace atap {

// A delegate interface for ops callbacks. This allows tests to override default
// fake implementations.
class FakeAtapOpsDelegate {
 public:
  virtual ~FakeAtapOpsDelegate() {}
  virtual AtapResult read_product_id(
      AtapOps* ops, uint8_t product_id[ATAP_PRODUCT_ID_LEN]) = 0;

  virtual AtapResult get_auth_key_type(AtapOps* ops, AtapKeyType* key_type) = 0;

  virtual AtapResult read_auth_key_cert_chain(AtapOps* ops,
                                              AtapCertChain* cert_chain) = 0;

  virtual AtapResult write_attestation_key(AtapOps* ops,
                                           AtapKeyType key_type,
                                           const AtapBlob* key,
                                           const AtapCertChain* cert_chain) = 0;

  virtual AtapResult read_attestation_public_key(
      AtapOps* ops,
      AtapKeyType key_type,
      uint8_t pubkey[ATAP_KEY_LEN_MAX],
      uint32_t* pubkey_len) = 0;

  virtual AtapResult read_soc_global_key(
      AtapOps* ops, uint8_t global_key[ATAP_AES_128_KEY_LEN]) = 0;

  virtual AtapResult write_hex_uuid(AtapOps* ops,
                                    const uint8_t uuid[ATAP_HEX_UUID_LEN]) = 0;

  virtual AtapResult get_random_bytes(AtapOps* ops,
                                      uint8_t* buf,
                                      uint32_t buf_size) = 0;

  virtual AtapResult auth_key_sign(AtapOps* ops,
                                   const uint8_t* nonce,
                                   uint32_t nonce_len,
                                   uint8_t sig[ATAP_SIGNATURE_LEN_MAX],
                                   uint32_t* sig_len) = 0;

  virtual AtapResult ecdh_shared_secret_compute(
      AtapOps* ops,
      AtapCurveType curve,
      const uint8_t other_public_key[ATAP_ECDH_KEY_LEN],
      uint8_t public_key[ATAP_ECDH_KEY_LEN],
      uint8_t shared_secret[ATAP_ECDH_KEY_LEN]) = 0;

  virtual AtapResult aes_gcm_128_encrypt(
      AtapOps* ops,
      const uint8_t* plaintext,
      uint32_t len,
      const uint8_t iv[ATAP_GCM_IV_LEN],
      const uint8_t key[ATAP_AES_128_KEY_LEN],
      uint8_t* ciphertext,
      uint8_t tag[ATAP_GCM_TAG_LEN]) = 0;

  virtual AtapResult aes_gcm_128_decrypt(
      AtapOps* ops,
      const uint8_t* ciphertext,
      uint32_t len,
      const uint8_t iv[ATAP_GCM_IV_LEN],
      const uint8_t key[ATAP_AES_128_KEY_LEN],
      const uint8_t tag[ATAP_GCM_TAG_LEN],
      uint8_t* plaintext) = 0;

  virtual AtapResult sha256(AtapOps* ops,
                            const uint8_t* plaintext,
                            uint32_t plaintext_len,
                            uint8_t hash[ATAP_SHA256_DIGEST_LEN]) = 0;

  virtual AtapResult hkdf_sha256(AtapOps* ops,
                                 const uint8_t* salt,
                                 uint32_t salt_len,
                                 const uint8_t* ikm,
                                 uint32_t ikm_len,
                                 const uint8_t* info,
                                 uint32_t info_len,
                                 uint8_t* okm,
                                 int32_t okm_len) = 0;
};

// Provides fake implementations of ATAP ops. All instances of this class must
// be created on the same thread.
class FakeAtapOps : public FakeAtapOpsDelegate {
 public:
  FakeAtapOps();
  virtual ~FakeAtapOps();

  static FakeAtapOps* GetInstanceFromAtapOps(AtapOps* ops) {
    return reinterpret_cast<FakeAtapOps*>(ops->user_data);
  }

  AtapOps* atap_ops() {
    return &atap_ops_;
  }

  FakeAtapOpsDelegate* delegate() {
    return delegate_;
  }

  // Does not take ownership of |delegate|.
  void set_delegate(FakeAtapOpsDelegate* delegate) {
    delegate_ = delegate;
  }

  // FakeAtapOpsDelegate methods.
  AtapResult read_product_id(AtapOps* ops,
                             uint8_t product_id[ATAP_PRODUCT_ID_LEN]) override;

  AtapResult get_auth_key_type(AtapOps* ops, AtapKeyType* key_type) override;

  AtapResult read_auth_key_cert_chain(AtapOps* ops,
                                      AtapCertChain* cert_chain) override;

  AtapResult write_attestation_key(AtapOps* ops,
                                   AtapKeyType key_type,
                                   const AtapBlob* key,
                                   const AtapCertChain* cert_chain) override;

  AtapResult read_attestation_public_key(AtapOps* ops,
                                         AtapKeyType key_type,
                                         uint8_t pubkey[ATAP_KEY_LEN_MAX],
                                         uint32_t* pubkey_len) override;

  AtapResult read_soc_global_key(
      AtapOps* ops, uint8_t global_key[ATAP_AES_128_KEY_LEN]) override;

  AtapResult write_hex_uuid(AtapOps* ops,
                            const uint8_t uuid[ATAP_HEX_UUID_LEN]) override;

  AtapResult get_random_bytes(AtapOps* ops,
                              uint8_t* buf,
                              uint32_t buf_size) override;

  AtapResult auth_key_sign(AtapOps* ops,
                           const uint8_t* nonce,
                           uint32_t nonce_len,
                           uint8_t sig[ATAP_SIGNATURE_LEN_MAX],
                           uint32_t* sig_len) override;

  AtapResult ecdh_shared_secret_compute(
      AtapOps* ops,
      AtapCurveType curve,
      const uint8_t other_public_key[ATAP_ECDH_KEY_LEN],
      uint8_t public_key[ATAP_ECDH_KEY_LEN],
      uint8_t shared_secret[ATAP_ECDH_KEY_LEN]) override;

  AtapResult aes_gcm_128_encrypt(AtapOps* ops,
                                 const uint8_t* plaintext,
                                 uint32_t len,
                                 const uint8_t iv[ATAP_GCM_IV_LEN],
                                 const uint8_t key[ATAP_AES_128_KEY_LEN],
                                 uint8_t* ciphertext,
                                 uint8_t tag[ATAP_GCM_TAG_LEN]) override;

  AtapResult aes_gcm_128_decrypt(AtapOps* ops,
                                 const uint8_t* ciphertext,
                                 uint32_t len,
                                 const uint8_t iv[ATAP_GCM_IV_LEN],
                                 const uint8_t key[ATAP_AES_128_KEY_LEN],
                                 const uint8_t tag[ATAP_GCM_TAG_LEN],
                                 uint8_t* plaintext) override;

  AtapResult sha256(AtapOps* ops,
                    const uint8_t* plaintext,
                    uint32_t plaintext_len,
                    uint8_t hash[ATAP_SHA256_DIGEST_LEN]) override;

  AtapResult hkdf_sha256(AtapOps* ops,
                         const uint8_t* salt,
                         uint32_t salt_len,
                         const uint8_t* ikm,
                         uint32_t ikm_len,
                         const uint8_t* info,
                         uint32_t info_len,
                         uint8_t* okm,
                         int32_t okm_len) override;

 private:
  AtapOps atap_ops_;

  FakeAtapOpsDelegate* delegate_;
};

}  // namespace atap

#endif /* FAKE_ATAP_OPS_H_ */
