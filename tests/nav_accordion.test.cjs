"use strict";
const assert = require("node:assert/strict");
const {defaultOpenKeys, afterToggle} = require("../app/web/static/nav-accordion.js");

const all = ["system", "shop", "pg"];

// Page load: web panel and bot open together, a PasarGuard page opens only PasarGuard.
assert.deepEqual(defaultOpenKeys("system", all), ["system", "shop"]);
assert.deepEqual(defaultOpenKeys("shop", all), ["system", "shop"]);
assert.deepEqual(defaultOpenKeys("", all), ["system", "shop"]);
assert.deepEqual(defaultOpenKeys("pg", all), ["pg"]);
// Roles without some sections.
assert.deepEqual(defaultOpenKeys("system", ["system", "shop"]), ["system", "shop"]);
assert.deepEqual(defaultOpenKeys("system", ["system", "pg"]), ["system"]);
assert.deepEqual(defaultOpenKeys("pg", ["system", "pg"]), ["pg"]);
assert.deepEqual(defaultOpenKeys("shop", ["pg"]), ["pg"]); // only PasarGuard exists
assert.deepEqual(defaultOpenKeys("pg", ["system", "shop"]), ["system", "shop"]); // no PasarGuard section
assert.deepEqual(defaultOpenKeys("system", []), []);

// Opening PasarGuard closes the other two.
assert.deepEqual(afterToggle(["system", "shop"], "pg", all), ["pg"]);
// Opening web panel or bot closes PasarGuard and keeps the other one's state.
assert.deepEqual(afterToggle(["pg"], "shop", all), ["shop"]);
assert.deepEqual(afterToggle(["pg"], "system", all), ["system"]);
assert.deepEqual(afterToggle(["shop"], "system", all), ["system", "shop"]);
assert.deepEqual(afterToggle([], "shop", all), ["shop"]);
// Closing a section closes only that one.
assert.deepEqual(afterToggle(["system", "shop"], "shop", all), ["system"]);
assert.deepEqual(afterToggle(["system", "shop"], "system", all), ["shop"]);
assert.deepEqual(afterToggle(["pg"], "pg", all), []);
// Result keeps the DOM order and ignores unknown or unavailable keys.
assert.deepEqual(afterToggle(["shop"], "system", all), ["system", "shop"]);
assert.deepEqual(afterToggle(["ghost", "shop"], "system", all), ["system", "shop"]);
assert.deepEqual(afterToggle(["system"], "ghost", all), ["system"]);
assert.deepEqual(afterToggle(["system", "shop"], "pg", ["system", "shop"]), ["system", "shop"]);
// Inputs are never modified.
const open = ["system"];
afterToggle(open, "pg", all);
assert.deepEqual(open, ["system"]);
console.log("Nav accordion rules: defaults, exclusivity with PasarGuard and role subsets passed");
