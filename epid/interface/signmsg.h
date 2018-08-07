/*############################################################################
  # Copyright 2016-2017 Intel Corporation
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
  ############################################################################

  Original location: https://github.com/Intel-EPID-SDK/epid-sdk
  Modified EPID SDK interface for Android things

*/

#ifndef EPID_INTERFACE_SIGNMSG_H_
#define EPID_INTERFACE_SIGNMSG_H_

#include "epid/common/file_parser.h"
#include "epid/member/api.h"

#if defined __cplusplus
extern "C" {
#endif

/* Sign message with EPID key, separate public/private keys.
 *
 * input:
 * msg: message to sign
 * msg_len: message length
 * basename: basename, see documentation for details
 * basename_len: basename length
 * buf_privkey: private key format: (data, size(byte))
 *      groupID:    16
 *      A:          64
 *      x:          32
 *      f:          32
 * buf_privkey_size: 144
 * buf_pubkey: public key format:  (data, size(byte))
 *      groupID:    16
 *      h1:         64
 *      h2:         64
 *      w:          128
 * buf_pubkey_size: 272 or longer, excess are discarded
 * buf_sig_rl: signature revocation list
 * buf_sig_rl_size: signature revocation list size
 * buf_precomp: memory for precomp, no use if NULL
 * precomp_size: 1552
 * hash_algo: digest sha-256 ->0; sha-512->2
 *
 * output:
 * sig: signature
 *
 * return:
 * EpidStatus: 0->signed, others->error
 */
EpidStatus EpidApiSign(void const* msg,
                       size_t msg_len,
                       void const* basename,
                       size_t basename_len,
                       void const* buf_privkey,
                       size_t buf_privkey_size,
                       void const* buf_pubkey,
                       size_t buf_pubkey_size,
                       void const* buf_sig_rl,
                       size_t buf_sig_rl_size,
                       void const* buf_precomp,
                       size_t buf_precomp_size,
                       HashAlg hash_alg,
                       EpidSignature* sig);

/* Sign message with EPID key, bundled public and private keys.
 *
 * input:
 * msg: message to sign
 * msg_len: message length
 * basename: basename, see documentation for details
 * basename_len: basename length
 * buf_key: bundled private and public key format: (data, size(byte))
 *      groupID:    16
 *      A:          64
 *      x:          32
 *      f:          32
 *      h1:         64
 *      h2:         64
 *      w:          128
 * buf_pubkey_size: 400 or longer, excess are discarded
 * buf_sig_rl: signature revocation list
 * buf_sig_rl_size: signature revocation list size
 * buf_precomp: memory for precomp, no use if NULL
 * precomp_size: 1552
 * hash_algo: digest sha-256 ->0; sha-512->2
 *
 * output:
 * buf_sig: allocated memory for signature
 * sig_len: >=360
 *
 * return:
 * EpidStatus: 0->signed, others->error
 */
EpidStatus EpidApiSignAtap(void const* msg,
                           size_t msg_len,
                           void const* basename,
                           size_t basename_len,
                           void const* buf_key,
                           size_t buf_key_size,
                           void const* buf_sig_rl,
                           size_t buf_sig_rl_size,
                           void const* buf_precomp,
                           size_t buf_precomp_size,
                           HashAlg hash_alg,
                           void* buf_sig,
                           size_t* sig_len);

/* create precompute blob to accelerate later signing.
 *
 * input:
 * buf_key: bundled private and public key format: (data, size(byte))
 *      groupID:    16
 *      A:          64
 *      x:          32
 *      f:          32
 *      h1:         64
 *      h2:         64
 *      w:          128
 * buf_pubkey_size: 400 or longer, excess are discarded
 *
 * output:
 * buf_precomp: allocated memory for precomp
 * precomp_size: 1536
 *
 * return:
 * EpidStatus: 0->signed, others->error
 */
EpidStatus EpidApiSignPrecomp(void const* buf_key,
                              size_t buf_key_size,
                              void* buf_precomp,
                              size_t buf_size);
#if defined __cplusplus
}
#endif  // defined __cplusplus
#endif  // EPID_INTERFACE_SIGNMSG_H_
