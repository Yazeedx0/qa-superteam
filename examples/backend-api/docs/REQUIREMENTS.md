# Ledger — Product Requirements

Ledger is a single-currency (USD) wallet service. Every registered user owns
exactly one wallet and can move money to other users' wallets. All amounts are
integers in cents.

## 1. Accounts and authentication

1.1. A user registers with an email address and a password. Passwords are
     8–128 characters long.

1.2. Email addresses are case-insensitive. Registration MUST be rejected with
     `409 Conflict` if the address matches an existing account ignoring letter
     case (`Alice@example.com` and `alice@example.com` are the same account),
     and login MUST accept the address in any letter case.

1.3. Registering creates the user's wallet with a balance of 0.

1.4. Login returns an opaque bearer token. Tokens expire 24 hours after login.
     Invalid credentials return `401 Unauthorized` without revealing whether
     the email exists.

1.5. Passwords are stored only as salted, slow hashes (PBKDF2-HMAC-SHA256).

1.6. Every endpoint except register and login requires
     `Authorization: Bearer <token>`; missing, invalid or expired tokens return
     `401 Unauthorized`.

## 2. Wallets

2.1. Balances can never go negative, under any sequence of requests.

2.2. A user can read only their own wallet. Requests for another user's
     wallet return `404 Not Found`, exactly as for a wallet that does not exist.

2.3. Deposits must be a whole number of cents, greater than 0 and at most
     1,000,000 cents ($10,000.00) per request. Anything else is rejected with
     `422 Unprocessable Entity` and the balance is unchanged.

## 3. Transfers

3.1. A transfer moves `amount_cents` (a positive integer) from the caller's
     wallet to the wallet `to_wallet_id`.

3.2. Fee: the sender pays a fee of 1% of `amount_cents`, rounded **up** to the
     next whole cent, with a minimum of 1 cent. The recipient receives the full
     `amount_cents`; the sender's balance decreases by `amount_cents + fee`.
     The fee is credited to the house wallet.

     | amount_cents | fee_cents | sender pays |
     |-------------:|----------:|------------:|
     | 1            | 1         | 2           |
     | 100          | 1         | 101         |
     | 101          | 2         | 103         |
     | 500          | 5         | 505         |
     | 990          | 10        | 1000        |

3.3. A transfer that would leave the sender with a negative balance (i.e. the
     balance is lower than `amount_cents + fee`) is rejected with
     `422 Unprocessable Entity` and no money moves.

3.4. Transfers to the caller's own wallet are rejected with `422`. Transfers
     to a wallet that does not exist return `404 Not Found`.

3.5. `memo` is optional free text of at most 140 characters.

3.6. Users may only see transfers they sent or received. `GET /transfers`
     lists exactly those, newest first. `GET /transfers/{id}` for a transfer
     the caller neither sent nor received returns `404 Not Found`, exactly as
     for a transfer that does not exist.

3.7. Large transfers may require additional review.

## 4. Idempotency

4.1. `POST /transfers` accepts an optional `Idempotency-Key` header
     (1–255 characters).

4.2. Keys are scoped per user. If the same user repeats a request with a key
     they already used, the API returns the original transfer (same id and
     body, status `201`) and no money moves a second time.

4.3. Reusing a key with a different request body (different `to_wallet_id`,
     `amount_cents` or `memo`) returns `409 Conflict`.

4.4. The same key used by two different users creates two independent
     transfers.

## 5. Out of scope for v1

- Pagination of `GET /transfers` (planned).
- Logout / token revocation, password reset, account deletion.
- Rate limiting (handled by the API gateway in front of this service).
- Multiple currencies.
