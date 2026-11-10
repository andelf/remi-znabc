local project = arg[1] or "."
package.path = project .. "/rime/lua/?.lua;" .. package.path
local Engine = require("znabc.engine")
local parser = require("znabc.parser")
local engine = Engine.new(project .. "/rime/znabc_data", nil, false)
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
local words, word_consumed = engine:query("fuke")
assert(word_consumed == 4 and words[1].text == "复课")
local singles, single_consumed, _, single_mode = engine:query("fuke", true)
assert(single_consumed == 2 and single_mode == "character" and #singles > #words)
local found
for _, row in ipairs(singles) do
  assert(not row.codes)
  if row.text == "复" then found = row end
end
assert(found)
local shape = string.format("%x", found.shape)
local filtered, filtered_consumed = engine:query("fu" .. shape .. "ke", true)
assert(filtered_consumed == 2 + #shape)
local includes_selected = false
for _, row in ipairs(filtered) do
  if row.text == "复" then includes_selected = true end
end
assert(includes_selected)
local shape_rows, _, _, shape_mode = engine:query("3235", true)
assert(shape_mode == "shape" and shape_rows[2].text == "你")
checks = checks + 6
for _, example in ipairs({{"shijie[", "世"}, {"shijie]", "界"},
    {"ni32hao63[", "你"}, {"ni32hao63]", "好"}}) do
  local rows, consumed, _, mode = engine:query(example[1], true)
  assert(mode == "word_character" and consumed == #example[1] and rows[1].text == example[2])
  checks = checks + 1
end
local extracted, extracted_consumed = engine:query("fuke]")
assert(extracted_consumed == 5 and extracted[1].text == "课" and extracted[2].text == "科")
assert(extracted[1].word == "复课" and extracted[2].word == "妇科")
local unique = {}
for _, row in ipairs(engine:query("shijie]")) do
  assert(not unique[row.text])
  unique[row.text] = true
end
for _, input in ipairs({"shi[", "3235]", "zhongguoren[", "ni32hao43]", "shi[xx", "shijie[]"}) do
  assert(#engine:query(input) == 0, input)
  checks = checks + 1
end
checks = checks + 3
for _, input in ipairs({"wenti", "ni32hao63", "zhongguoren", "wt"}) do
  local phrases, consumed, _, mode = engine:query(input)
  assert(mode == "phrase", input)
  local characters, character_consumed = engine:query(input, true)
  local menu, menu_consumed = engine:query_menu(input)
  assert(menu_consumed == consumed and #menu == #phrases + #characters, input)
  for index, phrase in ipairs(phrases) do
    assert(menu[index] == phrase and not phrase.consumed, input)
  end
  for index, character in ipairs(characters) do
    local item = menu[#phrases + index]
    assert(item.text == character.text and item.code == character.code, input)
    assert(item.consumed == character_consumed and not character.consumed, input)
  end
  checks = checks + 1
end
for _, input in ipairs({"wen", "3235", "shijie[", "shijie]", "shi[", "999"}) do
  local rows, consumed, _, mode = engine:query(input)
  local menu, menu_consumed, _, menu_mode = engine:query_menu(input)
  assert(#rows == #menu and consumed == menu_consumed and mode == menu_mode, input)
  checks = checks + 1
end
local only_characters = engine:query_menu("wenti", true)
assert(only_characters[1].text == "问" and not only_characters[1].codes)
checks = checks + 1
print("engine checks passed: " .. (checks + 7))

