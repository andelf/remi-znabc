package.path = arg[1] .. "/rime/lua/?.lua;" .. package.path
local parser = require("znabc.parser")
for input in io.lines() do
  local result = {}
  for _, unit in ipairs(parser.parse(input)) do
    result[#result + 1] = table.concat({unit.finish, unit.packed, unit.initial, unit.shape, unit.flags}, ",")
  end
  print(table.concat(result, ";"))
end

