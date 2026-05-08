**Threat Model**

- **We defend against:**
  - Database breach exposing stored rows (mitigated by AES-GCM encryption of mnemonics with keys derived from user passwords via PBKDF2).
  - Rainbow-table attack against stored emails (mitigated by storing SHA-256(email.lower().strip()) only as hex).
  - Offline brute-force of user passwords after DB steal (mitigated by PBKDF2 with high iteration count — see parameters below — and by requiring reasonably strong user passwords).

- **We do NOT defend against:**
  - Server compromise giving the attacker live access to the running process and memory (they could observe plaintext mnemonics during decryption).
  - Extremely weak user-selected passwords (e.g., "password123"). Encourage/require strong passwords and 2FA in production.

Document these limitations clearly in MAINNET_READINESS.md and in the user-facing registration disclaimer.

**Why AES-GCM and PBKDF2**

- AES-GCM is chosen because it provides authenticated encryption (confidentiality + integrity). A tampered ciphertext triggers an authentication failure (InvalidTag) instead of silently decrypting to garbage. AES-CBC without a separate HMAC would allow undetected tampering of stored mnemonics.
- Nonce (IV) for AES-GCM must be unique per encryption with the same key. Use a 12-byte random nonce per encryption. Store nonce alongside ciphertext so decryption can use the same nonce.
- PBKDF2 (with HMAC-SHA256) is used to derive the AES key from the user's password and a per-user salt. The iteration count is a tunable slowness parameter that raises the cost of offline guessing; we use a high iteration count (see constants in code) to make brute-force expensive.

**Storage formats and column choices**

- `user_id` TEXT PRIMARY KEY: UUID4 string. Chosen to avoid exposing auto-incrementing IDs and to allow safe reference from other tables.
- `email_hash` TEXT UNIQUE NOT NULL: store SHA-256(email.lower().strip()) as hex. Never store plaintext email. This prevents easy harvesting of emails from DB dumps and thwarts rainbow-table lookups for unsalted emails.
- `password_hash` TEXT NOT NULL: store bcrypt(password, rounds=12) output. Use bcrypt for password verification and storage rather than using the PBKDF2-derived key — bcrypt includes its own salt and is designed for password storage.
- `algo_address` TEXT UNIQUE NOT NULL: the Algorand public address (public information; not secret). Stored plaintext because addresses are used to identify on-chain funds.
- `encrypted_mnemonic` TEXT NOT NULL: stored as `nonce_hex:ciphertext_hex:tag_hex` (three hex fields joined by colons). AES-GCM produces a ciphertext and a 16-byte authentication tag; the nonce is required to decrypt. Storing all three in a single column in this format keeps them atomically readable/writable.
- `pbkdf2_salt` TEXT NOT NULL: 32 random bytes encoded as hex. Unique per user and never reused. Used as salt for PBKDF2 when deriving AES key from password. Must be stored so the server can re-derive the key when the user authenticates.
- `created_at` TEXT NOT NULL: ISO 8601 timestamp of account creation.
- `last_active_at` TEXT: ISO 8601 timestamp updated on user activity.
- `onboarding_complete` INTEGER DEFAULT 0: boolean flag (0/1). Set to 1 after first successful purchase.

**Storage and atomicity notes**

- Store `encrypted_mnemonic` as a single field in the `nonce_hex:ciphertext_hex:tag_hex` format so nonce and tag cannot be desynchronized from ciphertext by partial writes or inconsistent reads.
- Store `pbkdf2_salt` in its own column (hex). Salt is not secret but must be unique and persistently associated with the user.

**PBKDF2 parameters and recommendations**

- Use PBKDF2-HMAC-SHA256.
- Iteration count: 600,000 (2024 recommended baseline; tune higher if acceptable for UX/performance and server capacity).
- Salt length: 32 bytes (stored as hex).
- Derived key length: 32 bytes (AES-256).

**Password storage**

- Use bcrypt for password verification/storage with cost rounds=12. This is separate from PBKDF2 which derives the encryption key; bcrypt is specifically intended for storing/verifying passwords.

**Operational notes and hardening**

- Limit access to the database; restrict backups and logs.
- Rotate server keys and require hardware security modules (HSM) for production signing if custodial operation is intended on mainnet.
- Implement monitoring and alerting for anomalous access patterns.
- Consider Argon2id for password-based key derivation in future for stronger brute-force resistance (cryptography supports Argon2id where available), but keep compatibility and resource costs in mind.

**User-facing disclaimer**

- Clearly state that this is a custodial demo: a database breach could allow offline brute-force attempts on passwords and that server compromise can expose mnemonics in memory. Recommend strong unique passwords and backup of mnemonic by the user.
