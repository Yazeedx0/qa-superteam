test('jest ok', () => { expect(1).toBe(1); });
test('jest bad', () => { expect({ a: 1 }).toEqual({ a: 2 }); });
test.todo('jest todo');
