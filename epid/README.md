# EPID Interface Library

The directory contains a wrapper for EPID sdk library, libepid,
which provides an easier way to create EPID signatures and verify.
The EPID sdk is located at `platform/external/epid-sdk/`.

The C/C++ library contains two main functions `EPID_Sign` and
`EPID_Verify`. The python library include wrappers to call the
C/C++ functions, and functions to check EPID key certificate:
`verify_cert_file`.

## Files and Dierctories

* `interface/`
    + C/C++ interface library inplementations
* `python_interface/`
    + A python wrapper for the C/C++ library
    + Python functions for checking EPID certificates
    + Unittests for python functions
* `test/`
    + Unit tests for testing EPID sign/verify funtionalities of
      the C/C++ library.
* `testdata/`
    + Data files used for unit tests
* `Android.bp`
    + Build file used by Soong to build the library

## Build Instructions

The C/C++ libraries and unit tests can be built with Soong. They are
available on both the target and the host. Both shared and static
libraries are available. The build targets for the library and tests
are `libepid` and `libepid_utest`, respectively.

C/C++ shared library `libepid.so` is needed for the python interface.
A prebuilt library for linux x86_64 is in `python_interface/`

## `testdata/` Contents

Unittest data include EPID public and private keys for two different
EPID groups. An EPID certificate chain (in DER format) is also incuded.
* EPID group1:
    + `group1pubkey.bin`: public key binary
    + `group1privkey1.bin`, `group1privkey2.bin`, `group1privkey3.bin`:
    private keys
* EPID group2:
    + `group2pubkey.bin`: public key binary
    + `group2privkey1.bin`, `group2privkey2.bin`, `group2privkey3.bin`:
    private keys
* Certificate chain:
    + `cert0.cer`: certificate for the EPID key, leaf
    + `cert1.cer`: intermidiate CA certificate, used to sign `cert0.cer`
    + `cert2.cer`: root CA certificate, used to sign `cert0.cer`