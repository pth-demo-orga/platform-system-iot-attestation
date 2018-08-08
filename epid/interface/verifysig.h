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

#ifndef EPID_INTERFACE_VERIFYSIG_H_
#define EPID_INTERFACE_VERIFYSIG_H_

#include <stddef.h>
#include "epid/common/errors.h"
#include "epid/common/stdtypes.h"
#include "epid/common/types.h"

#if defined __cplusplus
extern "C" {
#endif

/* Verify EPID signature
 *
 * input:
 * sig: signature to check
 * sig_len: signature length
 * msg: message to sign
 * msg_len: message length
 * basename: basename, see documentation for details
 * basename_len: basename length
 *
 * *rl: revocation lists
 *
 * buf_pubkey: public key format:  (data, size(byte))
 *      groupID:      16
 *      h1:           64
 *      h2:           64
 *      w:            128
 * buf_pubkey_size: 272 or longer, excess are discarded
 * buf_precomp: precomp blob
 * precomp_size: 1552
 * hash_algo: digest sha-256 ->0; sha-512->2
 *
 * return:
 * EpidStatus 0->verified; others->not
 */
EpidStatus EpidApiVerify(void const* sig,
                         size_t sig_len,
                         void const* msg,
                         size_t msg_len,
                         void const* basename,
                         size_t basename_len,
                         void const* signed_priv_rl,
                         size_t signed_priv_rl_size,
                         void const* signed_sig_rl,
                         size_t signed_sig_rl_size,
                         void const* signed_grp_rl,
                         size_t signed_grp_rl_size,
                         VerifierRl const* ver_rl,
                         size_t ver_rl_size,
                         void const* buf_pubkey,
                         size_t buf_pubkey_size,
                         void const* buf_precomp,
                         size_t buf_precomp_size,
                         HashAlg hash_alg);

/* created precompute blob to accelerate later verifications
 * of the same EPID group.
 *
 * input:
 * buf_pubkey: public key format:  (data, size(byte))
 *      groupID:      16
 *      h1:           64
 *      h2:           64
 *      w:            128
 * buf_pubkey_size: 272 or longer, excess are discarded
 *
 * output:
 * buf_precomp: allocated memory for precomp
 * precomp_size: 1536
 *
 * return:
 * EpidStatus 0->success; others->not
 */
EpidStatus EpidApiVerifyPrecomp(void const* buf_key,
                                size_t buf_key_size,
                                void* buf_precomp,
                                size_t buf_size);
#if defined __cplusplus
}
#endif  // defined __cplusplus
#endif  // EPID_INTERFACE_VERIFYSIG_H_
