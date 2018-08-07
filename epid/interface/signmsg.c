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

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "epid/common/src/memory.h"
#include "epid/common/stdtypes.h"
#include "epid/member/api.h"
#include "epid/member/src/context.h"
#include "epid/member/src/write_precomp.h"
#include "util/convutil.h"

// read random numbers from /dev/urandom
int SysPrngGen(unsigned int* rand_data, int num_bits, void* user_data) {
  (void)user_data;
  if (num_bits <= 0) return 0;
  if (num_bits % 8) return 1;
  FILE* urnd = fopen("/dev/urandom", "r");
  if (urnd) {
    int bytes = num_bits / 8;
    size_t ret = fread(rand_data, 1, bytes, urnd);
    fclose(urnd);
    if (!ret) return 1;
    return 0;
  } else {
    return 1;
  }
}

typedef struct EpidKeyATAP{
  GroupId gid;               ///< group ID
  ///priv key
  G1ElemStr A;               ///< an element in G1
  FpElemStr x;               ///< an integer between [0, p-1]
  FpElemStr f;               ///< an integer between [0, p-1]
  ///pub key
  G1ElemStr h1;              ///< an element in G1
  G1ElemStr h2;              ///< an element in G1
  G2ElemStr w;               ///< an element in G2

} EpidKeyATAP;

EpidStatus EpidApiSign(void const* msg, size_t msg_len,
                       void const* basename, size_t basename_len,
                       void const* buf_privkey, size_t buf_privkey_size,
                       void const* buf_pubkey, size_t buf_pubkey_size,
                       void const* buf_sig_rl, size_t buf_sig_rl_size,
                       void const* buf_precomp, size_t buf_precomp_size,
                       HashAlg hash_alg,
                       EpidSignature* sig) {
  EpidStatus sts = kEpidErr;
  MemberCtx* member = NULL;
  SigRl* sig_rl = NULL;
  size_t sig_len = 360;
  do {
    MemberParams params = {0};
    size_t member_size = 0;
    if (!sig) {
      sts = kEpidBadArgErr;
      break;
    }
    if (!buf_pubkey || buf_pubkey_size != sizeof(GroupPubKey)) {
      sts = kEpidBadArgErr;
      break;
    }
    if (!buf_privkey || buf_privkey_size != sizeof(PrivKey)) {
      sts = kEpidBadArgErr;
      break;
    }

    MemberPrecomp const* precomp = NULL;
    if (buf_precomp && buf_precomp_size == sizeof(MemberPrecomp)) {
      precomp = (MemberPrecomp const*)buf_precomp;
    }

    // need link RNG
    params.rnd_func = &SysPrngGen;
    params.rnd_param = NULL;
    params.f = NULL;

    // create member
    sts = EpidMemberGetSize(&params, &member_size);
    if (kEpidNoErr != sts) {
      break;
    }
    member = (MemberCtx*)calloc(1, member_size);
    if (!member) {
      sts = kEpidNoMemErr;
      break;
    }
    sts = EpidMemberInit(&params, member);
    if (kEpidNoErr != sts) {
      break;
    }

    sts = EpidMemberSetHashAlg(member, hash_alg);
    if (kEpidNoErr != sts) {
      break;
    }

    if (buf_privkey_size == sizeof(PrivKey)) {
      sts = EpidProvisionKey(member, (GroupPubKey const*)buf_pubkey,
                             (PrivKey const*)buf_privkey, precomp);
      if (kEpidNoErr != sts) {
        break;
      }
    } else {
      sts = kEpidBadArgErr;
      break;
    }

    // start member
    sts = EpidMemberStartup(member);
    if (kEpidNoErr != sts) {
      break;
    }

    // register any provided basename as allowed
    if (0 != basename_len) {
      sts = EpidRegisterBasename(member, basename, basename_len);
      if (kEpidNoErr != sts) {
        break;
      }
    }

    // TODO the interface does not support revocation lists
    // register sigRl if any
    if (buf_sig_rl && buf_sig_rl_size) {
      /*
      // buf_sig_rl include EpidFileHeader, signature RL and EcdsaSignature
      // signature is not checked
      size_t min_rl_file_size = 0;
      size_t empty_rl_size = 0;
      size_t rl_entry_size = 0;
      EpidFileHeader const* file_header = (EpidFileHeader*)buf_sig_rl;
      (void)file_header;
      if (!buf_sig_rl_size) {
        sts = kEpidBadArgErr;
        break;
      }
      empty_rl_size = sizeof(SigRl) - sizeof(((SigRl*)0)->bk[0]);
      rl_entry_size = sizeof(((SigRl*)0)->bk[0]);
      min_rl_file_size = sizeof(EpidFileHeader) + sizeof(SigRl) -
                         sizeof(((SigRl*)0)->bk[0]) + sizeof(EcdsaSignature);
      if (min_rl_file_size > buf_sig_rl_size) return kEpidBadArgErr;
      size_t sig_rl_size = buf_sig_rl_size -
                           sizeof(EpidFileHeader) - sizeof(EcdsaSignature);
      sig_rl = calloc(1, sig_rl_size);
      if (!sig_rl) {
        sts = kEpidMemAllocErr;
        break;
      }
      void const* buf_rl = buf_sig_rl + sizeof(EpidFileHeader);
      if (0 != memcpy_S(sig_rl, sig_rl_size, buf_rl, sig_rl_size)) {
        return kEpidBadArgErr;
      }

      sts = EpidMemberSetSigRl(member, sig_rl, sig_rl_size);
      if (kEpidNoErr != sts) {
        break;
      }
      */
    }

    if (sig_len != EpidGetSigSize(sig_rl)) {
      sts = kEpidMemAllocErr;
      break;
    }
    if (!sig) {
      sts = kEpidMemAllocErr;
      break;
    }

    // sign message
    sts = EpidSign(member, msg, msg_len, basename, basename_len, sig, sig_len);
    if (kEpidNoErr != sts) {
      break;
    }
    sts = kEpidNoErr;
  } while (0);  // do

  EpidMemberDeinit(member);
  if (member) free(member);

  if (sig_rl) free(sig_rl);
  return sts;
}

EpidStatus EpidApiSignAtap(void const* msg, size_t msg_len,
                           void const* basename, size_t basename_len,
                           void const* buf_key, size_t buf_key_size,
                           void const* buf_sig_rl, size_t buf_sig_rl_size,
                           void const* buf_precomp, size_t buf_precomp_size,
                           HashAlg hash_alg,
                           void* buf_sig, size_t* buf_sig_len) {
  if (!buf_sig || !buf_sig_len) {
    return kEpidBadArgErr;
  }

  EpidSignature* sig = (EpidSignature*)buf_sig;
  *buf_sig_len = 360;

  GroupPubKey pubkey = {0};
  PrivKey privkey = {0};

  // get public key and private key from buf, no CA checks
  if (!buf_key || buf_key_size != sizeof(EpidKeyATAP)) {
    return kEpidBadArgErr;
  }
  EpidKeyATAP* buf_key_tmp = (EpidKeyATAP*)buf_key;

  pubkey.gid = buf_key_tmp->gid;
  pubkey.h1 = buf_key_tmp->h1;
  pubkey.h2 = buf_key_tmp->h2;
  pubkey.w = buf_key_tmp->w;

  privkey.gid = buf_key_tmp->gid;
  privkey.A = buf_key_tmp->A;
  privkey.x = buf_key_tmp->x;
  privkey.f = buf_key_tmp->f;

  return EpidApiSign(msg, msg_len,
                     basename, basename_len,
                     (void*) &privkey, sizeof(PrivKey),
                     (void*) &pubkey, sizeof(GroupPubKey),
                     buf_sig_rl, buf_sig_rl_size,
                     buf_precomp, buf_precomp_size,
                     hash_alg,
                     sig);

}

EpidStatus EpidApiSignPrecomp(void const* buf_key, size_t buf_key_size,
                              void* buf_precomp, size_t buf_precomp_size) {
  EpidStatus sts = kEpidErr;
  GroupPubKey pubkey = {0};
  PrivKey privkey = {0};
  MemberCtx* member = NULL;
  MemberParams params = {0};
  size_t member_size = 0;

  if (!buf_precomp || buf_precomp_size != sizeof(MemberPrecomp)) {
    return kEpidBadArgErr;
  }

  // get public key and private key from buf, no CA checks
  if (!buf_key || buf_key_size != sizeof(EpidKeyATAP)) {
    return kEpidBadArgErr;
  }
  EpidKeyATAP* buf_key_tmp = (EpidKeyATAP*)buf_key;

  pubkey.gid = buf_key_tmp->gid;
  pubkey.h1 = buf_key_tmp->h1;
  pubkey.h2 = buf_key_tmp->h2;
  pubkey.w = buf_key_tmp->w;

  privkey.gid = buf_key_tmp->gid;
  privkey.A = buf_key_tmp->A;
  privkey.x = buf_key_tmp->x;
  privkey.f = buf_key_tmp->f;

  do {
    // need link RNG
    params.rnd_func = &SysPrngGen;
    params.rnd_param = NULL;
    params.f = NULL;

    // create member
    sts = EpidMemberGetSize(&params, &member_size);
    if (kEpidNoErr != sts) {
      break;
    }
    member = (MemberCtx*)calloc(1, member_size);
    if (!member) {
      sts = kEpidNoMemErr;
      break;
    }
    sts = EpidMemberInit(&params, member);
    if (kEpidNoErr != sts) {
      break;
    }

    sts = EpidProvisionKey(member, &pubkey, &privkey, NULL);
    if (kEpidNoErr != sts) {
      break;
    }

    // start member and compute precomp
    sts = EpidMemberStartup(member);
    if (kEpidNoErr != sts) {
      break;
    }

    // write precomp to buf
    sts = EpidMemberWritePrecomp(member, (MemberPrecomp*)buf_precomp);
    if (kEpidNoErr != sts) {
      break;
    }
  } while (0);  // do

  EpidMemberDeinit(member);
  if (member) free(member);

  return kEpidNoErr;
}
