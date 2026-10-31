local project = arg[1] or "."
package.path = project .. "/rime/lua/?.lua;" .. package.path
local Engine = require("znabc.engine")
local parser = require("znabc.parser")
local engine = Engine.new(project .. "/rime/znabc_data")
local checks = 0

local function includes(input, text)
  local candidates = engine:query(input)
  for _, candidate in ipairs(candidates) do
    if candidate.text == text then
      return true
    end
  end
  return false
end

for _, input in ipairs({"nihao", "ni3hao6", "ni32hao63", "ni32355hao6315"}) do
  assert(includes(input, "你好"), input)
  checks = checks + 1
end
for _, input in ipairs({"ni32hao43", "nihao32", "ni63hao32"}) do
  assert(not includes(input, "你好"), input)
  checks = checks + 1
end
assert(includes("ke18", "可") and not includes("ke15", "可"))
assert(includes("shi81", "时") and includes("shi81", "是") and includes("shi81", "匙"))
local shapes, consumed = engine:query("3235")
assert(#shapes == 3 and consumed == 4)
assert(shapes[1].text == "仂" and shapes[2].text == "你" and shapes[3].text == "仍")
local candidates, partial = engine:query("ni32hao43")
assert(#candidates > 0 and partial == 4)
for _, input in ipairs({"shi", "shi8", "shi81", "ni32", "hao63", "a", "sh", "s1", "n", "zhongguo", "nh", "nihao"}) do
  local rows, _, _, mode = engine:query(input)
  for index = 2, #rows do
    local left, right = rows[index - 1], rows[index]
    assert(left.weight >= right.weight, input)
    if left.weight == right.weight then
      if mode == "character" then
        assert(left.code < right.code, input)
      else
        assert(left.order < right.order, input)
      end
    end
  end
  checks = checks + 1
end
local units = parser.parse("chang'an")
assert(#units == 2 and parser.syllable(units[1].packed) == "chang")
assert(#engine:query("i") == 0)
assert(#engine:query("999") == 0)
print("engine checks passed: " .. (checks + 7))

