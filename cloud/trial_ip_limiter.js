import { DurableObject } from 'cloudflare:workers';

const MAX_TRIAL_WINDOWS_PER_IP = 3;

export class TrialIpLimiter extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    ctx.blockConcurrencyWhile(async () => {
      ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS claims (
          conversation_hash TEXT PRIMARY KEY,
          reservation_token TEXT NOT NULL,
          status TEXT NOT NULL,
          license_key TEXT,
          expires_at TEXT,
          store_name TEXT
        )
      `);
    });
  }

  reserve(conversationHash) {
    if (!/^[a-f0-9]{64}$/.test(conversationHash)) throw new Error('Invalid conversation hash');
    return this.ctx.storage.transactionSync(() => {
      const existing = this.ctx.storage.sql.exec(
        'SELECT status, license_key, expires_at, store_name FROM claims WHERE conversation_hash = ?',
        conversationHash
      ).toArray()[0];
      if (existing?.status === 'issued') {
        return { status: 'issued', license_key: existing.license_key, expires_at: existing.expires_at, store_name: existing.store_name };
      }
      if (existing) return { status: 'pending' };
      const count = this.ctx.storage.sql.exec('SELECT COUNT(*) AS count FROM claims').one().count;
      if (Number(count) >= MAX_TRIAL_WINDOWS_PER_IP) return { status: 'limit' };
      const token = crypto.randomUUID();
      this.ctx.storage.sql.exec(
        'INSERT INTO claims (conversation_hash, reservation_token, status) VALUES (?, ?, ?)',
        conversationHash, token, 'pending'
      );
      return { status: 'reserved', token };
    });
  }

  complete(conversationHash, token, licenseKey, expiresAt, storeName) {
    return this.ctx.storage.transactionSync(() => {
      const current = this.ctx.storage.sql.exec(
        'SELECT reservation_token, status FROM claims WHERE conversation_hash = ?', conversationHash
      ).toArray()[0];
      if (!current || current.status !== 'pending' || current.reservation_token !== token) {
        throw new Error('Trial reservation was changed');
      }
      this.ctx.storage.sql.exec(
        'UPDATE claims SET status = ?, license_key = ?, expires_at = ?, store_name = ? WHERE conversation_hash = ?',
        'issued', licenseKey, expiresAt, storeName, conversationHash
      );
      return { status: 'issued' };
    });
  }
}
