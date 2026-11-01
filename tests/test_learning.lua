local project = arg[1] or "."
package.path = project .. "/rime/lua/?.lua;" .. package.path
local UserDictionary = require("znabc.user_dictionary")
local Engine = require("znabc.engine")
local parser = require("znabc.parser")

local database = {values = {}}
function database:query(prefix)
  local values = {}
  for key, value in pairs(self.values) do
    if key:sub(1, #prefix) == prefix then
      values[key] = value
    end
  end
  return {iter = function() return pairs(values) end}
end
function database:update(key, value)
  if self.fail then
    return false
  end
  self.values[key] = value
  return true
end
function database:erase(key)
  self.values[key] = nil
  return true
end

local tick = 100
local store = UserDictionary.new(database, {temporary_capacity = 2, clock = function()
  tick = tick + 1
  return tick
end})
local engine = Engine.new(project .. "/rime/znabc_data", store)
local function find(input, text)
  local rows = engine:query(input)
  for _, row in ipairs(rows) do
    if row.text == text then
      return row
    end
  end
end
local codes = {10166, 10166}
assert(not find("ni32ni32", "倪倪"))
assert(store:remember(codes, false))
assert(store:get(codes).stage == "temporary" and store:get(codes).uses == 0)
for _, input in ipairs({"ni32ni32", "ni3ni3", "nini", "nn"}) do
  assert(find(input, "倪倪"), input)
end
local extracted, consumed, _, mode = engine:query("nn]")
assert(mode == "word_character" and consumed == 3 and extracted[1].text == "倪")
assert(store:get(codes).uses == 0)
assert(not find("ni63ni32", "倪倪"))
for count = 1, 3 do
  assert(store:remember(codes, false))
  assert(store:get(codes).uses == count)
  assert(store:get(codes).stage == (count < 3 and "temporary" or "common"))
end
local reopened = UserDictionary.new(database)
assert(reopened:get(codes).stage == "common" and reopened:get(codes).uses == 3)
engine.user_enabled = false
assert(not find("nini", "倪倪"))
engine.user_enabled = true
assert(store:remove(codes))
assert(not find("nini", "倪倪"))
assert(store:remember(codes, false) and not store:get(codes))
assert(UserDictionary.new(database).entries[UserDictionary.key(codes)].stage == "deleted")

local first, second, third = {10170, 10166}, {10166, 10170}, {10170, 10170}
assert(store:remember(first, false))
assert(store:remember(second, false))
assert(store:remember(first, false))
assert(store:remember(third, false))
assert(store:get(first) and store:get(third) and not store:get(second))
database.fail = true
assert(not store:remember(first, false))
assert(store:get(first).uses == 1)
assert(not store:remember(second, false))
assert(store:get(first) and store:get(third) and not store:get(second))
database.fail = false

local rows = engine:query("nihao")
local phrase = rows[1]
assert(phrase.text == "你好" and engine:has_base(phrase.codes))
assert(store:remember(phrase.codes, true))
local occurrences = 0
for _, row in ipairs(engine:query("nihao")) do
  if row.text == "你好" then
    occurrences = occurrences + 1
  end
end
assert(occurrences == 1 and store:get(phrase.codes).stage == "history")

local longer
for initial = string.byte("a"), string.byte("z") do
  for next_initial = string.byte("a"), string.byte("z") do
    longer = engine.dictionary:phrase_bucket(string.char(initial, next_initial))[3]
    if longer and #longer > 0 then break end
  end
  if longer and #longer > 0 then break end
end
local long_codes = longer[1].codes
assert(store:remember({long_codes[1], long_codes[2]}, false))
local spelling = {}
for _, code in ipairs(long_codes) do
  spelling[#spelling + 1] = parser.syllable(engine.dictionary.characters[code].packed):lower()
end
local _, _, _, mode = engine:query(table.concat(spelling, "'"))
assert(mode == "phrase")
local longest = engine:query(table.concat(spelling, "'"))
assert(#longest[1].codes == 3)

store.temporary_capacity = 5
assert(store:remember({34068, 10166}, false))
assert(find("chongni32", "重倪") and not find("zhongni32", "重倪"))
assert(store:remember({34070, 10166}, false))
assert(find("chongni32", "重倪") and find("zhongni32", "重倪"))
store.temporary_capacity = 1
assert(store:remember({10166, 10166, 10166}, false))
local temporary_count = 0
for _, record in pairs(store.entries) do
  if record.stage == "temporary" then temporary_count = temporary_count + 1 end
end
assert(temporary_count == 1)

database.values["word/bad"] = "common\t3\t200"
database.values["word/1,2"] = "invalid\t3\t200"
assert(UserDictionary.new(database).entries.bad == nil)
print("learning checks passed: promotion, persistence, filtering, deletion, eviction, failed writes, deduplication, longest match, polyphonic codes")
