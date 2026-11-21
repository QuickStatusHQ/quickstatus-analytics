// The examples in schema/examples match schema/event.v1.json (the server vendors both).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const schema = JSON.parse(readFileSync(new URL("../schema/event.v1.json", import.meta.url), "utf8"));
const dir = new URL("../schema/examples/", import.meta.url);

for (const name of readdirSync(dir)) {
  test(`example ${name} matches the schema`, () => {
    const body = JSON.parse(readFileSync(new URL(name, dir), "utf8"));
    for (const key of schema.required) assert.ok(key in body, `missing ${key}`);
    for (const [key, value] of Object.entries(body)) {
      const prop = schema.properties[key];
      assert.ok(prop, `unknown field ${key}`);
      const types = [].concat(prop.type);
      const actual = value === null ? "null" : Number.isInteger(value) ? "integer" : typeof value;
      assert.ok(types.includes(actual), `${key}: ${actual} not in ${types}`);
      if (prop.pattern) assert.match(value, new RegExp(prop.pattern));
    }
  });
}
