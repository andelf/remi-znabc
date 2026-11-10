local project = arg[1] or "."
package.path = project .. "/rime/lua/?.lua;" .. package.path
local Engine = require("znabc.engine")
local UserDictionary = require("znabc.user_dictionary")
local parser = require("znabc.parser")
local original = Engine.new(project .. "/rime/znabc_data")
local expanded = Engine.new(project .. "/rime/znabc_data")
expanded.phrase_supplement_enabled = true
local function bucket_paths(directory)
  local paths = {}
  for first = 97, 122 do
    for second = 97, 122 do
      local path = directory .. "/" .. string.char(first, second) .. ".tsv"
      local file = io.open(path, "rb")
      if file then
        file:close()
        paths[#paths + 1] = path
      end
    end
  end
  return paths
end
local paths = bucket_paths(project .. "/rime/znabc_data/phrases")
local phrases, full, abbreviations, supplements, changed = 0, 0, 0, 0, 0
local timing = {}
local function signature(rows)
  local result = {}
  for _, row in ipairs(rows) do result[#result + 1] = table.concat(row.codes or {row.code}, ",") end
  return table.concat(result, ";")
end
local function verify(input, exact)
  local before, consumed = original:query(input)
  local started = os.clock()
  local after, after_consumed = expanded:query(input)
  timing[#timing + 1] = (os.clock() - started) * 1000
  if exact then
    assert(consumed == after_consumed and signature(before) == signature(after), input)
  elseif consumed == #input and #before > 0 then
    assert(after_consumed == consumed and after[1].text == before[1].text, input)
    local retained = {}
    for _, row in ipairs(after) do
      if row.source ~= "phrase_supplement" then retained[#retained + 1] = row end
    end
    assert(signature(before) == signature(retained), input)
    full = full + 1
  elseif consumed ~= after_consumed or (before[1] and after[1] and before[1].text ~= after[1].text) then
    changed = changed + 1
    print("changed partial:", input, before[1] and before[1].text, after[1] and after[1].text)
  end
end
local initial_inputs = {}
for _, path in ipairs(paths) do
  for line in io.lines(path) do
    local encoded = assert(line:match("^%d+\t[^\t]+\t([%d,]+)"))
    local reading, initials = {}, {}
    for value in encoded:gmatch("%d+") do
      local character = original.dictionary.characters[tonumber(value)]
      reading[#reading + 1] = parser.syllable(character.packed)
      initials[#initials + 1] = parser.initial_letter(math.floor(character.packed / 256))
    end
    verify(table.concat(reading), false)
    initial_inputs[table.concat(initials)] = true
    phrases = phrases + 1
  end
end
for input in pairs(initial_inputs) do
  local units = parser.parse(input)
  local abbreviated = false
  for _, unit in ipairs(units) do
    if unit.abbreviated and unit.packed ~= 65 * 256 and unit.packed ~= 69 * 256 and unit.packed ~= 79 * 256 then
      abbreviated = true
    end
  end
  if abbreviated then
    verify(input, true)
    abbreviations = abbreviations + 1
  end
end
local supplemental_paths = bucket_paths(project .. "/rime/znabc_data/phrase_supplement")
local example, example_input
for _, path in ipairs(supplemental_paths) do
  for line in io.lines(path) do
    local text, encoded = line:match("^%d+\t([^\t]+)\t([%d,]+)")
    local reading, codes = {}, {}
    for value in encoded:gmatch("%d+") do
      codes[#codes + 1] = tonumber(value)
      reading[#reading + 1] = parser.syllable(expanded.dictionary.characters[tonumber(value)].packed)
    end
    local input = table.concat(reading)
    for _, separator in ipairs({"", "'"}) do
      local rows, consumed = expanded:query(table.concat(reading, separator))
      local found = false
      for _, row in ipairs(rows) do if row.text == text then found = true end end
      assert(found and consumed == #table.concat(reading, separator), text .. " " .. input)
    end
    local rows = expanded:query(input, true)
    for _, row in ipairs(rows) do assert(row.source ~= "phrase_supplement") end
    if text == "二维码" then example, example_input = codes, input end
    supplements = supplements + 1
  end
end
assert(example, "缺少试用词：二维码")
local fallback, fallback_consumed = expanded:query_menu("zhongguoren")
assert(fallback[1].text == "中国人" and fallback_consumed == #"zhongguoren")
local has_shorter = false
for _, row in ipairs(fallback) do
  if row.text == "中国" then
    assert(row.consumed == #"zhongguo")
    has_shorter = true
  end
end
assert(has_shorter, "扩充长词应保留原短词的分段选择")
for _, input in ipairs({"erwma", "er88weima", example_input .. "q", example_input .. "[", example_input .. "]"}) do
  verify(input, true)
end
local database = {values = {}}
function database:query()
  return {iter = function() return pairs(self.values) end}
end
function database:update(key, value) self.values[key] = value return true end
function database:erase(key) self.values[key] = nil return true end
local store = UserDictionary.new(database)
local learned = Engine.new(project .. "/rime/znabc_data", store)
learned.phrase_supplement_enabled = true
assert(not learned:has_base(example))
assert(store:remember(example, learned:has_base(example)))
assert(store:get(example).stage == "temporary")
local rows = learned:query(example_input)
local occurrences = 0
for _, row in ipairs(rows) do if row.text == "二维码" then occurrences = occurrences + 1 end end
assert(occurrences == 1 and rows[1].text == "二维码")
learned.phrase_supplement_enabled = false
assert(learned:query(example_input)[1].text == "二维码")
assert(store:remove(example))
local reopened = Engine.new(project .. "/rime/znabc_data", UserDictionary.new(database))
reopened.phrase_supplement_enabled = true
for _, row in ipairs(reopened:query(example_input)) do assert(row.text ~= "二维码") end
reopened.user_enabled = false
for _, row in ipairs(reopened:query(example_input)) do assert(row.text ~= "二维码") end
expanded.phrase_supplement_enabled = false
verify(example_input, true)
assert(changed == 0, "原词输入的部分匹配发生变化")
table.sort(timing)
print(string.format("phrase supplement: %d base inputs, %d full-match orders preserved, %d abbreviations unchanged, %d reachable additions, %d changed partial matches; query p95 %.3f ms, max %.3f ms",
  phrases, full, abbreviations, supplements, changed, timing[math.ceil(#timing * 0.95)], timing[#timing]))
