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

#include <memory>

namespace atap {

FakeAtapOps::FakeAtapOps() {}
FakeAtapOps::~FakeAtapOps() {}

AtapResult FakeAtapOps::read_product_id(
    uint8_t product_id[ATAP_PRODUCT_ID_LEN]) {
  memset(product_id, 0x00, ATAP_PRODUCT_ID_LEN);
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::get_auth_key_type(AtapKeyType* key_type) {
  *key_type = key_type_;
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::read_auth_key_cert_chain(AtapCertChain* cert_chain) {
  if (key_type_ == ATAP_KEY_TYPE_NONE) {
    return ATAP_RESULT_ERROR_UNSUPPORTED_OPERATION;
  }
  cert_chain->entry_count = 1;
  AtapBlob* blob = &(cert_chain->entries[0]);
  blob->data_length = auth_cert_len_;
  blob->data = (uint8_t *)atap_malloc(auth_cert_len_);
  atap_memcpy(blob->data, auth_cert_, auth_cert_len_);
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::write_attestation_key(AtapKeyType key_type,
                                              const AtapBlob* key,
                                              const AtapCertChain* cert_chain) {
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::read_attestation_public_key(

    AtapKeyType key_type,
    uint8_t pubkey[ATAP_KEY_LEN_MAX],
    uint32_t* pubkey_len) {
  return ATAP_RESULT_ERROR_UNSUPPORTED_OPERATION;
}

AtapResult FakeAtapOps::read_soc_global_key(
    uint8_t global_key[ATAP_AES_128_KEY_LEN]) {
  return ATAP_RESULT_ERROR_UNSUPPORTED_OPERATION;
}

AtapResult FakeAtapOps::write_hex_uuid(const uint8_t uuid[ATAP_HEX_UUID_LEN]) {
  return ATAP_RESULT_OK;
}

AtapResult FakeAtapOps::auth_key_sign(const uint8_t* nonce,
                                      uint32_t nonce_len,
                                      uint8_t sig[ATAP_SIGNATURE_LEN_MAX],
                                      uint32_t* sig_len) {
  if (key_type_ == ATAP_KEY_TYPE_NONE) {
    return ATAP_RESULT_ERROR_UNSUPPORTED_OPERATION;
  }
  *sig_len = auth_sig_len_;
  atap_memcpy(sig, auth_sig_, auth_sig_len_);
  return ATAP_RESULT_OK;
}

void FakeAtapOps::set_auth(
    const AtapKeyType key_type, uint8_t* sig, uint32_t sig_len, uint8_t* cert,
    uint32_t cert_len) {
  key_type_ = key_type;
  auth_sig_len_ = sig_len;
  auth_cert_len_ = cert_len;
  if (key_type == ATAP_KEY_TYPE_NONE) {
    // clear the authentication data.
    if (auth_sig_) {
      atap_free(auth_sig_);
    }
    if (auth_cert_) {
      atap_free(auth_cert_);
    }
  } else {
    auth_sig_ = (uint8_t *)atap_malloc(sig_len);
    atap_memcpy(auth_sig_, sig, sig_len);
    auth_cert_ = (uint8_t *)atap_malloc(cert_len);
    atap_memcpy(auth_cert_, cert, cert_len);
  }
}

}  // namespace atap
