# Key Provisioning Test Suite

This directory contains a test script to verify that a device
works with the Android Things key provisioning protocol. Usage:

./provision-test.py -a [p256|x25519] -s FASTBOOT_SERIAL_NUMBER
                    -o [ISSUE|ISSUE_ENC|ISSUE_SOM|ISSUE_ENC_SOM]
                    (--atapversion [1|2])

If atapversion is not specified, when the commmand is ISSUE | ISSUE_ENC, the
version is 1, when ISSUE_SOM | ISSUE_ENC_SOM, the version is 2. This would be
the lowest compatible version for the command. ISSUE | ISSUE_ENC should support
both version 1 and version 2, the corresponding keyset would be used to match
the protocol version.

## Dependencies

Install openssl, python cryptography, pycurve25519. Build ec_helper_native.so
in this directory ($ make ec_helper_native). Build and install fastboot from
AOSP master.

## How to get key sets

provision-test.py looks for key set payloads unencryped_*.keyset and
encrypted_*.keyset and under the keysets/ directory. Provided here are
files that contain test keys that do not verify to the real Android
Things Root CA. unencrypted_*.keyset is simply a raw CA Response
Message. encrypted_*.keyset encrypts unencrypted.keyset with a global key
of 16 zero bytes (AES128 gcm no padding). Unencrypted_product_version_1.keyset
is identical to unencrypted_product.keyset except that it has atap version 1.
