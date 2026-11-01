local project = arg[1] or "."
package.path = project .. "/rime/lua/?.lua;" .. package.path
local engine = require("znabc.engine").new(project .. "/rime/znabc_data")
local parser = require("znabc.parser")
local candidates = {}
for _, rule in ipairs(engine.affixes) do
  candidates[#candidates + 1] = {codes = rule.codes}
end
for line in io.lines() do
  local direction, input = line:match("^(%d)\t(.+)$")
  direction = tonumber(direction)
  local units = parser.parse(input)
  local index = engine:affix_index(candidates, #input, units, #units == 1 and "character" or "phrase",
    #input + (direction == 1 and 1 or 0), direction == 1 and 0 or 1, false)
  print(index and table.concat(candidates[index + 1].codes, ",") or "-")
end
