/*
 * Copyright 2018 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "interface/signmsg.h"
#include "interface/verifysig.h"

#include <cstdio>
#include <cstdlib>
#include <string>

#include <base/files/file_util.h>
#include <gtest/gtest.h>

class EpidTest : public ::testing::Test {
 public:
  // Fill string with random chars.
  // Return false if fails.
  bool random_msg(std::string* s);
  // Simplified function to call EPID_Sign_atap
  EpidStatus sign(const std::string& msg,
                  const std::string& privkey,
                  const std::string& precomp,
                  HashAlg alg,
                  std::string* sig,
                  size_t* sig_len);
  // Simplified function to call EPID_Verify
  EpidStatus verify(const std::string& msg,
                    const std::string& sig,
                    const std::string& pubkey,
                    const std::string& precomp,
                    HashAlg alg);
  // generate precomp blob for signing
  EpidStatus sign_precomp(const std::string& privkey,
                          std::string* precomp);
  // generate precomp blob for verification
  EpidStatus verify_precomp(const std::string& pubkey,
                            std::string* precomp);
};

constexpr char kEpidGroup1Pubkey[] = "testdata/group1pubkey.bin";
constexpr char kEpidGroup1Privkey1[] = "testdata/group1privkey1.bin";
constexpr char kEpidGroup1Privkey2[] = "testdata/group1privkey2.bin";
constexpr char kEpidGroup1Privkey3[] = "testdata/group1privkey3.bin";
constexpr char kEpidGroup2Pubkey[] = "testdata/group2pubkey.bin";
constexpr char kEpidGroup2Privkey1[] = "testdata/group2privkey1.bin";
constexpr char kEpidGroup2Privkey2[] = "testdata/group2privkey2.bin";
constexpr char kEpidGroup2Privkey3[] = "testdata/group2privkey3.bin";

constexpr size_t kEpidSigLen = 360;
constexpr size_t kEpidSignPrecompLen = 1536;
constexpr size_t kEpidVerifyPrecompLen = 1552;

bool EpidTest::random_msg(std::string* s) {
  if (s->empty()) return true;
  FILE* f = fopen("/dev/urandom", "rb");
  if (f) {
    size_t ret = fread((void*)s->data(), 1, s->size(), f);
    fclose(f);
    return ret == s->size();
  } else {
    return false;
  }
}

EpidStatus EpidTest::sign(const std::string& msg, const std::string& privkey,
                          const std::string& precomp, HashAlg alg,
                          std::string* sig, size_t* sig_len) {
  return EpidApiSignAtap(msg.data(), msg.size(), nullptr, 0, privkey.data(),
                         privkey.size(), nullptr, 0, precomp.data(),
                         precomp.size(), alg, &(*sig)[0], sig_len);
}

EpidStatus EpidTest::verify(const std::string& msg, const std::string& sig,
                            const std::string& pubkey,
                            const std::string& precomp, HashAlg alg) {
  return EpidApiVerify(sig.data(), sig.size(), msg.data(), msg.size(), nullptr,
                       0, nullptr, 0, nullptr, 0, nullptr, 0, nullptr, 0,
                       pubkey.data(), pubkey.size(), precomp.data(),
                       precomp.size(), alg);
}

EpidStatus EpidTest::sign_precomp(const std::string& privkey,
                                  std::string* precomp) {
  return EpidApiSignPrecomp(privkey.data(), privkey.size(),
                            &(*precomp)[0], precomp->size());
}

EpidStatus EpidTest::verify_precomp(const std::string& privkey,
                                    std::string* precomp) {
  return EpidApiVerifyPrecomp(privkey.data(), privkey.size(),
                              &(*precomp)[0], precomp->size());
}

TEST_F(EpidTest, SignMsgGroup1Privkey1Wrongkey) {
  // modify private key
  std::string privkey, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey));

  std::string precomps, precompv;
  std::string msg("test message");
  std::string sig(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kSha256;
  EpidStatus status = kEpidErr;

  // modify key
  privkey[privkey.size() - 1] = 0;
  status = sign(msg, privkey, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidBadArgErr);
}

TEST_F(EpidTest, SignVerifyMsgGroup1Privkey1MultipleSign) {
  // test repeated signatures for the same message are not identical
  // and all signatures pass verification
  std::string privkey, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey));

  std::string msg("test message");
  std::string sig1(kEpidSigLen, 0);
  std::string sig2(kEpidSigLen, 0);
  std::string sig3(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kSha256;
  EpidStatus status = kEpidErr;

  std::string precomps(kEpidSignPrecompLen, 0), precompv;
  status = sign_precomp(privkey, &precomps);
  EXPECT_EQ(status, kEpidNoErr);

  // sign same message three times
  status = sign(msg, privkey, precomps, alg, &sig1, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  ASSERT_EQ(sig_len, kEpidSigLen);
  status = sign(msg, privkey, precomps, alg, &sig2, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  ASSERT_EQ(sig_len, kEpidSigLen);
  status = sign(msg, privkey, precomps, alg, &sig3, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  ASSERT_EQ(sig_len, kEpidSigLen);
  EXPECT_NE(sig1, sig2);
  EXPECT_NE(sig1, sig3);
  EXPECT_NE(sig2, sig3);

  // verify three signatures against the same message
  status = verify(msg, sig1, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidNoErr);
  status = verify(msg, sig2, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidNoErr);
  status = verify(msg, sig3, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidNoErr);
}

TEST_F(EpidTest, SignVerifyMsgGroup1Privkey1MultipleSignPrecomp) {
  // test repeated signatures for the same message are not identical
  // and all signatures pass verification
  // use precomp
  std::string privkey, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey));

  std::string msg("test message");
  std::string sig1(kEpidSigLen, 0);
  std::string sig2(kEpidSigLen, 0);
  std::string sig3(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kSha256;
  EpidStatus status = kEpidErr;

  // precomp
  std::string precomps(kEpidSignPrecompLen, 0);
  std::string precompv(kEpidVerifyPrecompLen, 0);
  status = sign_precomp(privkey, &precomps);
  EXPECT_EQ(status, kEpidNoErr);
  status = verify_precomp(pubkey, &precompv);
  EXPECT_EQ(status, kEpidNoErr);

  // sign same message three times
  status = sign(msg, privkey, precomps, alg, &sig1, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  ASSERT_EQ(sig_len, kEpidSigLen);
  status = sign(msg, privkey, precomps, alg, &sig2, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  ASSERT_EQ(sig_len, kEpidSigLen);
  status = sign(msg, privkey, precomps, alg, &sig3, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  ASSERT_EQ(sig_len, kEpidSigLen);
  EXPECT_NE(sig1, sig2);
  EXPECT_NE(sig1, sig3);
  EXPECT_NE(sig2, sig3);

  // verify three signatures against the same message
  status = verify(msg, sig1, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidNoErr);
  status = verify(msg, sig2, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidNoErr);
  status = verify(msg, sig3, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidNoErr);
}

TEST_F(EpidTest, SignVerifyMsgGroup1Privkey1HashAlgos) {
  // sign with group1 private key1 and verify with different hash algos
  std::string privkey, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey));

  EpidStatus status = kEpidErr;
  std::string precomps, precompv;

  // test differnt hash algos sign/verify
  // supported Hash algos: sha256 sha384 sha512 sha512_256
  for (int i = 0; i <= 3; ++i) {
    std::string msg("test message");
    std::string sig(kEpidSigLen, 0);
    size_t sig_len = 0;
    HashAlg alg = (HashAlg)i;

    status = sign(msg, privkey, precomps, alg, &sig, &sig_len);
    EXPECT_EQ(status, kEpidNoErr);
    EXPECT_EQ(sig_len, kEpidSigLen);

    // verify with differernt hash algo
    // matched algos should succeed
    // mismatched algos should fail
    for (int j = 0; j <= 3; ++j) {
      HashAlg alg1 = (HashAlg)j;
      status = verify(msg, sig, pubkey, precompv, alg1);
      if (alg == alg1) {
        EXPECT_EQ(status, kEpidNoErr);
      } else {
        EXPECT_EQ(status, kEpidSigInvalid);
      }
    }
  }

  // test unsupported hash algo
  std::string msg("test message");
  std::string sig(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kInvalidHashAlg;

  status = sign(msg, privkey, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidBadArgErr);
  status = verify(msg, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidBadArgErr);

  alg = kSha3_512;
  status = sign(msg, privkey, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidBadArgErr);
  status = verify(msg, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidBadArgErr);
}

TEST_F(EpidTest, SignVerifyMsgGroup1Privkey1HashAlgosPrecomp) {
  // sign with group1 private key1 and verify with different hash algos
  // use precompute to speed up
  std::string privkey, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey));

  EpidStatus status = kEpidErr;

  std::string precomps(kEpidSignPrecompLen, 0);
  status = sign_precomp(privkey, &precomps);
  EXPECT_EQ(status, kEpidNoErr);

  std::string precompv(kEpidVerifyPrecompLen, 0);
  status = verify_precomp(pubkey, &precompv);
  EXPECT_EQ(status, kEpidNoErr);

  // test differnt hash algos sign/verify
  // supported Hash algos: sha256 sha384 sha512 sha512_256
  for (int i = 0; i <= 3; ++i) {
    std::string msg("test message");
    std::string sig(kEpidSigLen, 0);
    size_t sig_len = 0;
    HashAlg alg = (HashAlg)i;

    status = sign(msg, privkey, precomps, alg, &sig, &sig_len);
    EXPECT_EQ(status, kEpidNoErr);
    EXPECT_EQ(sig_len, kEpidSigLen);

    // verify with differernt hash algo
    // matched algos should succeed
    // mismatched algos should fail
    for (int j = 0; j <= 3; ++j) {
      HashAlg alg1 = (HashAlg)j;
      status = verify(msg, sig, pubkey, precompv, alg1);
      if (alg == alg1) {
        EXPECT_EQ(status, kEpidNoErr);
      } else {
        EXPECT_EQ(status, kEpidSigInvalid);
      }
    }
  }

  // test unsupported hash algo
  std::string msg("test message");
  std::string sig(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kInvalidHashAlg;

  status = sign(msg, privkey, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidBadArgErr);
  status = verify(msg, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidBadArgErr);

  alg = kSha3_512;
  status = sign(msg, privkey, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidBadArgErr);
  status = verify(msg, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidBadArgErr);
}

TEST_F(EpidTest, SignVerifyMsgAllGroupsAllPrivkeys) {
  // sign with private keys and verify with group public keys
  // two EPID groups, each with 3 private keys, are tested
  std::string privkey[2][3], pubkey[2];
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey[0]));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup2Pubkey), &pubkey[1]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1),
                                     &privkey[0][0]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup1Privkey2),
                                     &privkey[0][1]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup1Privkey3),
                                     &privkey[0][2]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup2Privkey1),
                                     &privkey[1][0]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup2Privkey2),
                                     &privkey[1][1]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup2Privkey3),
                                     &privkey[1][2]));

  // test differnt groups
  for (int i = 0; i < 6; ++i) {
    int group = i / 3;
    int member = i % 3;

    std::string msg("test message");
    std::string sig(kEpidSigLen, 0);
    size_t sig_len = 0;
    HashAlg alg = kSha256;
    EpidStatus status = kEpidErr;
    std::string precomps, precompv;

    status = sign(msg, privkey[group][member], precomps, alg, &sig, &sig_len);
    EXPECT_EQ(status, kEpidNoErr);
    EXPECT_EQ(sig_len, kEpidSigLen);

    status = verify(msg, sig, pubkey[group], precompv, alg);
    EXPECT_EQ(status, kEpidNoErr);
  }
}

TEST_F(EpidTest, SignVerifyMsgGroup1Privkey1MismatchMsg) {
  // read public/private keys
  std::string privkey, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey3), &privkey));

  const size_t kMsgLen = 10;
  std::string msg1(kMsgLen, 0);
  std::string msg2(kMsgLen, 0);
  while (msg1 == msg2) {
    ASSERT_TRUE(random_msg(&msg1));
    ASSERT_TRUE(random_msg(&msg2));
  }
  std::string sig(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kSha256;
  EpidStatus status = kEpidErr;
  std::string precomps, precompv;

  status = sign(msg1, privkey, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  EXPECT_EQ(sig_len, kEpidSigLen);

  status = verify(msg2, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidSigInvalid);
}

TEST_F(EpidTest, SignVerifyMsgMismatchGroupKey) {
  // sign with privkey and verify with pubkey of other group
  std::string privkey[2][3], pubkey[2];
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey[0]));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup2Pubkey), &pubkey[1]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1),
                                     &privkey[0][0]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup1Privkey2),
                                     &privkey[0][1]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup1Privkey3),
                                     &privkey[0][2]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup2Privkey1),
                                     &privkey[1][0]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup2Privkey2),
                                     &privkey[1][1]));
  ASSERT_TRUE(base::ReadFileToString(base::FilePath(kEpidGroup2Privkey3),
                                     &privkey[1][2]));

  std::string msg("test message");

  for (int i = 0; i < 6; ++i) {
    int group = i / 3;
    int other_group = (group == 0 ? 1 : 0);
    int member = i % 3;

    std::string msg("test message");
    std::string sig(kEpidSigLen, 0);
    size_t sig_len = 0;
    HashAlg alg = kSha256;
    EpidStatus status = kEpidErr;
    std::string precomps, precompv;

    status = sign(msg, privkey[group][member], precomps, alg, &sig, &sig_len);
    EXPECT_EQ(status, kEpidNoErr);
    EXPECT_EQ(sig_len, kEpidSigLen);

    status = verify(msg, sig, pubkey[other_group], precompv, alg);
    EXPECT_EQ(status, kEpidSigInvalid);
  }
}

TEST_F(EpidTest, SignWithPrecomp) {
  // generate precomp instances to speed up signing
  std::string privkey, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey));

  std::string precomps(kEpidSignPrecompLen, 0), precompv;
  std::string msg("test message");
  std::string sig(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kSha256;
  EpidStatus status = kEpidErr;

  // do precomp
  status = sign_precomp(privkey, &precomps);
  EXPECT_EQ(status, kEpidNoErr);

  // sign with precomp
  status = sign(msg, privkey, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  EXPECT_EQ(sig_len, kEpidSigLen);

  status = verify(msg, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidNoErr);
}

TEST_F(EpidTest, SignWithPrecompMismatchKey) {
  // generate precomp instances and sign with mismatched key
  std::string privkey1, privkey2, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey1));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey2), &privkey2));

  std::string precomps(kEpidSignPrecompLen, 0), precompv;
  std::string msg("test message");
  std::string sig(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kSha256;
  EpidStatus status = kEpidErr;

  // do precomp
  status = sign_precomp(privkey1, &precomps);
  EXPECT_EQ(status, kEpidNoErr);

  // sign with mismtached precomp
  status = sign(msg, privkey2, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  EXPECT_EQ(sig_len, kEpidSigLen);

  status = verify(msg, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidSigInvalid);
}

TEST_F(EpidTest, SignWithPrecompMismatchGroup) {
  // generate precomp instances and sign with mismatched key
  std::string privkey1, privkey2, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey1));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup2Privkey1), &privkey2));

  std::string precomps(kEpidSignPrecompLen, 0), precompv;
  std::string msg("test message");
  std::string sig(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kSha256;
  EpidStatus status = kEpidErr;

  // do precomp
  status = sign_precomp(privkey1, &precomps);
  EXPECT_EQ(status, kEpidNoErr);

  // sign with precomp
  status = sign(msg, privkey2, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  EXPECT_EQ(sig_len, kEpidSigLen);

  status = verify(msg, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidSigInvalid);
}

TEST_F(EpidTest, VerifyWithPrecomp) {
  // generate precomp instances and sign with mismatched key
  std::string privkey1, privkey2, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey1));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey2), &privkey2));

  std::string precomps, precompv(kEpidVerifyPrecompLen, 0);
  std::string msg("test message");
  std::string sig(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kSha256;
  EpidStatus status = kEpidErr;

  // do precomp
  status = verify_precomp(pubkey, &precompv);
  EXPECT_EQ(status, kEpidNoErr);

  // sign
  status = sign(msg, privkey1, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  EXPECT_EQ(sig_len, kEpidSigLen);

  // verify with precomp
  status = verify(msg, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidNoErr);

  // sign again
  status = sign(msg, privkey2, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  EXPECT_EQ(sig_len, kEpidSigLen);

  // verify with precomp
  status = verify(msg, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidNoErr);

  alg = kSha512;
  // sign again
  status = sign(msg, privkey2, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  EXPECT_EQ(sig_len, kEpidSigLen);

  // verify with precomp
  status = verify(msg, sig, pubkey, precompv, alg);
  EXPECT_EQ(status, kEpidNoErr);
}

TEST_F(EpidTest, VerifyWithPrecompMismatchGroup) {
  // generate precomp instances and sign with mismatched key
  std::string privkey, pubkey1, pubkey2;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey1));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup2Pubkey), &pubkey2));

  std::string precomps, precompv(kEpidVerifyPrecompLen, 0);
  std::string msg("test message");
  std::string sig(kEpidSigLen, 0);
  size_t sig_len = 0;
  HashAlg alg = kSha256;
  EpidStatus status = kEpidErr;

  // do precomp
  status = verify_precomp(pubkey2, &precompv);
  EXPECT_EQ(status, kEpidNoErr);

  // sign
  status = sign(msg, privkey, precomps, alg, &sig, &sig_len);
  EXPECT_EQ(status, kEpidNoErr);
  EXPECT_EQ(sig_len, kEpidSigLen);

  // verify with precomp
  status = verify(msg, sig, pubkey1, precompv, alg);
  EXPECT_EQ(status, kEpidBadArgErr);
}

TEST_F(EpidTest, PrecompBadInput) {
  // precomp input invalid
  std::string privkey, pubkey;
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Pubkey), &pubkey));
  ASSERT_TRUE(
      base::ReadFileToString(base::FilePath(kEpidGroup1Privkey1), &privkey));

  std::string precomps, precompv;
  EpidStatus status = kEpidErr;

  // do precomp
  status = sign_precomp(privkey, &precomps);
  EXPECT_EQ(status, kEpidBadArgErr);

  precomps.resize(kEpidSignPrecompLen - 1);
  status = sign_precomp(privkey, &precomps);
  EXPECT_EQ(status, kEpidBadArgErr);
  precomps.resize(kEpidSignPrecompLen + 1);
  status = sign_precomp(privkey, &precomps);
  EXPECT_EQ(status, kEpidBadArgErr);

  // do precomp
  status = verify_precomp(pubkey, &precompv);
  EXPECT_EQ(status, kEpidBadArgErr);

  precompv.resize(kEpidVerifyPrecompLen - 1);
  status = verify_precomp(pubkey, &precompv);
  EXPECT_EQ(status, kEpidBadArgErr);
  precompv.resize(kEpidVerifyPrecompLen + 1);
  status = verify_precomp(pubkey, &precompv);
  EXPECT_EQ(status, kEpidBadArgErr);
}
