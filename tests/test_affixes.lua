local project = arg[1] or "."
package.path = project .. "/rime/lua/?.lua;" .. package.path
local engine = require("znabc.engine").new(project .. "/rime/znabc_data")
assert(#engine.affixes == 182)
local checks = 0
local function check(input, start, expected, single)
  local rows, consumed, units, mode = engine:query_menu(input, single)
  local index = engine:affix_index(rows, consumed, units, mode, #input, start, single)
  assert((index and rows[index + 1].text or nil) == expected, input)
  checks = checks + 1
end
check("jiuni32hao63", 0, "旧")
check("laoguanxi", 0, "老")
check("jiuguanxi", 0, nil)
check("wulixi", 0, nil)
check("xi", 4, "系")
check("xi", 0, nil)
check("de", 4, "的")
check("de3", 4, "的")
check("de38", 4, "的")
check("de1", 4, nil)
check("de8", 4, nil)
check("de", 0, nil)
check("di", 4, "地")
check("lilun", 4, "理论")
check("lilun", 0, nil)
check("shang", 4, "上")
check("jiuni32hao63", 0, nil, true)
check("xi", 4, nil, true)
check("shijie[", 4, nil)
check("3235", 4, nil)
check("v1", 4, nil)
for _, rule in ipairs(engine.affixes) do
  local units = {}
  for index, code in ipairs(rule.codes) do
    local character = assert(engine.dictionary.characters[code])
    units[index] = {packed = character.packed, shape = 0, finish = index}
  end
  local rows = {{codes = rule.codes, text = "test"}}
  for _, direction in ipairs({1, 2}) do
    if direction == 2 or #units == 1 then
      local index = engine:affix_index(rows, #units, units,
        #units == 1 and "character" or "phrase", #units + (direction == 1 and 1 or 0),
        direction == 1 and 0 or 1, false)
      if rule.direction ~= direction and rule.direction ~= 3 then
        assert(index == nil)
      end
      checks = checks + 1
    end
  end
end
print("affix checks passed: " .. checks)
