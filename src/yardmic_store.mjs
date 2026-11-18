// Each 256K UTF-16 chunk fits comfortably inside D1's 2 MB row limit.
function chunks(value) {
  const text = JSON.stringify(value);
  const result = [];
  let start = 0;
  while (start < text.length) {
    let end = Math.min(start + 262144, text.length);
    const last = text.charCodeAt(end - 1);
    if (last >= 0xd800 && last <= 0xdbff) end--;
    result.push(text.slice(start, end));
    start = end;
  }
  return result;
}

export function yardmicStore(db, segment) {
  const query = (sql, ...args) => db.prepare(sql).bind(...args);
  const guard = 'EXISTS (SELECT 1 FROM yardmic_segments WHERE segment = ? AND token = ?)';
  return {
    async read() {
      const { results } = await query('SELECT value FROM yardmic_snapshot_chunks WHERE segment = ? ORDER BY ordinal', segment).all();
      return results.length ? JSON.parse(results.map((row) => row.value).join('')) : null;
    },
    async completedDate(date, cutoff) {
      const { results } = await query(
        'SELECT value, estimated_at FROM yardmic_completed_date_chunks WHERE date = ? AND estimated_at > ? ORDER BY ordinal',
        date, cutoff,
      ).all();
      return results.length ? { day: JSON.parse(results.map((row) => row.value).join("")), estimatedAt: results[0].estimated_at } : null;
    },
    async claim(now, rangeEnd) {
      const token = crypto.randomUUID();
      const result = await query(
        `UPDATE yardmic_segments SET token = ?, lease_until = ?, requested_end = ?
         WHERE segment = ? AND lease_until <= ? AND (retry_at <= ? OR (requested_end <> ? AND failures = 0))`,
        token, now + 30000, rangeEnd, segment, now, now, rangeEnd,
      ).run();
      return result.meta.changes ? token : null;
    },
    async save(token, value, nextAttempt, completed = [], cutoff) {
      const statements = [query(`DELETE FROM yardmic_snapshot_chunks WHERE segment = ? AND ${guard}`, segment, segment, token)];
      chunks(value).forEach((chunk, index) => statements.push(query(
        `INSERT INTO yardmic_snapshot_chunks (segment, ordinal, value) SELECT ?, ?, ? WHERE ${guard}`,
        segment, index, chunk, segment, token,
      )));
      if (completed.length) {
        statements.push(query(`DELETE FROM yardmic_completed_date_chunks WHERE estimated_at <= ? AND ${guard}`, cutoff, segment, token));
        for (const { day, estimatedAt } of completed) {
          statements.push(query(
            `DELETE FROM yardmic_completed_date_chunks WHERE date = ? AND estimated_at <= ? AND ${guard}`,
            day.date, estimatedAt, segment, token,
          ));
          chunks(day).forEach((chunk, index) => statements.push(query(
            `INSERT INTO yardmic_completed_date_chunks (date, ordinal, estimated_at, value)
             SELECT ?, ?, ?, ? WHERE ${guard}
             AND NOT EXISTS (SELECT 1 FROM yardmic_completed_date_chunks WHERE date = ? AND estimated_at > ?)`,
            day.date, index, estimatedAt, chunk, segment, token, day.date, estimatedAt,
          )));
        }
      }
      statements.push(query(
        'UPDATE yardmic_segments SET token = NULL, lease_until = 0, retry_at = ?, failures = 0 WHERE segment = ? AND token = ?',
        nextAttempt, segment, token,
      ));
      const results = await db.batch(statements);
      return Boolean(results.at(-1).meta.changes);
    },
    async fail(token, now) {
      await query(
        `UPDATE yardmic_segments SET token = NULL, lease_until = 0,
         retry_at = ? + MIN(900000, 120000 << MIN(failures, 3)), failures = MIN(failures + 1, 4)
         WHERE segment = ? AND token = ?`,
        now, segment, token,
      ).run();
    },
    async status() {
      return query('SELECT failures FROM yardmic_segments WHERE segment = ?', segment).first();
    },
  };
}
