import assert from "node:assert/strict";
import { complaintTypes } from "../src/index.ts";
assert.equal(complaintTypes.length, 13);
assert.ok(complaintTypes.includes("delivery_delay"));
console.log("typescript contract checks passed");
