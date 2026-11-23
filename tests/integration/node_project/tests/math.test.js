import { describe, it, expect } from 'vitest';
describe('math', () => {
  it('adds', () => { expect(1 + 1).toBe(2); });
  it('fails on purpose', () => { expect(2 * 2).toBe(5); });
  it.skip('skipped one', () => {});
});
