local project = arg[1] or "."
package.path = project .. "/rime/lua/?.lua;" .. package.path
local Engine = require("znabc.engine")
local parser = require("znabc.parser")
local engine = Engine.new(project .. "/rime/znabc_data")
local original = Engine.new(project .. "/rime/znabc_data", nil, false)
local checks, seen = 0, {}

local function find(input, text)
  for _, candidate in ipairs(engine:query(input)) do
    if candidate.text == text then return candidate end
  end
end

local function preserves(input)
  local expected, consumed, _, mode = original:query(input)
  local actual, actual_consumed, _, actual_mode = engine:query(input)
  assert(mode == actual_mode and consumed == actual_consumed, input)
  for index, candidate in ipairs(expected) do
    assert(actual[index].text == candidate.text and actual[index].code == candidate.code and
      actual[index].weight == candidate.weight, input)
  end
  checks = checks + 1
end

local readings, characters = 0, {}
for code, character in pairs(engine.dictionary.characters) do
  if character.source == "supplement" then
    local input = parser.syllable(character.packed)
    local units = parser.parse(input)
    assert(#units == 1 and units[1].finish == #input and units[1].packed == character.packed, input)
    local candidate = assert(find(input, character.text), input)
    assert(candidate.code == code)
    if character.shape ~= 0 then
      local suffix = string.format("%x", character.shape):gsub("0$", "")
      assert(find(input .. suffix, character.text))
      assert(not find(input .. (suffix:sub(1, 1) == "1" and "8" or "1"), character.text))
    end
    readings = readings + 1
    characters[character.text] = true
  elseif not seen[character.packed] then
    local input = parser.syllable(character.packed)
    preserves(input)
    preserves(input .. string.format("%x", character.shape):gsub("0$", ""))
    seen[character.packed] = true
  end
end
assert(readings == 1660)
local count = 0
for _ in pairs(characters) do count = count + 1 end
assert(count == 1242)
for _, input in ipairs({"p", "j", "n", "sh", "zh", "m"}) do
  preserves(input)
  for _, row in ipairs(engine:query(input)) do
    assert(row.source ~= "supplement" or parser.syllable(row.packed) == input)
  end
end
assert(find("m", "呣"))
assert(find("pan33", "槃") and find("zhe71", "喆"))
assert(find("jie", "㛃") and not find("jie1", "㛃"))
assert(find("you", "尢") and find("wang", "尢") and not find("you2", "尢"))
assert(find("dai32", "垈"))
local boosted = assert(find("pan", "槃"))
boosted.weight = 999
preserves("pan")
boosted.weight = 0
for initial in ("12345678"):gmatch(".") do
  for input in pairs(original.dictionary:shape_bucket(initial)) do preserves(input) end
end
local shape_found = false
for _, row in ipairs(engine:query("335734")) do if row.text == "槃" then shape_found = true end end
assert(shape_found)
print("supplement checks passed: " .. readings .. " readings, " .. count .. " characters, " .. checks .. " original-order checks")
