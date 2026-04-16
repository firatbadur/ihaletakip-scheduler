#!/usr/bin/env node
/**
 * EKAP signing parity reference for Python tests.
 *
 * Mirrors `generateEkapSigningHeaders` in the mobile app
 * (IhaleTakip/src/api/v1/calls.js), but accepts deterministic inputs so the
 * Python implementation can be verified to produce byte-for-byte identical
 * ciphertext for the same (guid, iv, timestamp) triple.
 *
 * Usage:
 *   node scripts/node_crypto_reference.js <guidString> <ivHex32> <timestampMs>
 *
 * Output: JSON
 *   {
 *     "api-version": "v1",
 *     "X-Custom-Request-Guid": ...,
 *     "X-Custom-Request-R8id": ...,
 *     "X-Custom-Request-Siv": ...,
 *     "X-Custom-Request-Ts": ...,
 *   }
 *
 * Requires: `npm install crypto-js` (dev only).
 */
const CryptoJS = require('crypto-js');

const [, , guid, ivHex, tsMs] = process.argv;
if (!guid || !ivHex || !tsMs) {
  console.error('usage: node node_crypto_reference.js <guid> <ivHex32> <timestampMs>');
  process.exit(2);
}
if (!/^[0-9a-fA-F]{32}$/.test(ivHex)) {
  console.error('ivHex must be 32 hex chars (16 bytes)');
  process.exit(2);
}

const KEY_UTF8 = 'Qm2LtXR0aByP69vZNKef4wMJ';
const key = CryptoJS.enc.Utf8.parse(KEY_UTF8);
const iv = CryptoJS.enc.Hex.parse(ivHex);

const encGuid = CryptoJS.AES.encrypt(guid, key, {
  iv,
  mode: CryptoJS.mode.CBC,
  padding: CryptoJS.pad.Pkcs7,
});

const encTs = CryptoJS.AES.encrypt(String(tsMs), key, {
  iv,
  mode: CryptoJS.mode.CBC,
  padding: CryptoJS.pad.Pkcs7,
});

const headers = {
  'api-version': 'v1',
  'X-Custom-Request-Guid': guid,
  'X-Custom-Request-R8id': encGuid.ciphertext.toString(CryptoJS.enc.Base64),
  'X-Custom-Request-Siv': CryptoJS.enc.Base64.stringify(iv),
  'X-Custom-Request-Ts': encTs.ciphertext.toString(CryptoJS.enc.Base64),
};

process.stdout.write(JSON.stringify(headers));
