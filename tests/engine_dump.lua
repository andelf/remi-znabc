package.path = arg[1] .. "/rime/lua/?.lua;" .. package.path
local Engine = require("znabc.engine")
local engine = Engine.new(arg[1] .. "/rime/znabc_data", nil, false)
for input in io.lines() do
  local rows, consumed, _, mode = engine:query(input)
  local result = {mode, consumed}
  for _, row in ipairs(rows) do
    result[#result + 1] = (row.code and tostring(row.code) or table.concat(row.codes or {}, ",")) .. ":" .. row.weight
  end
  print(table.concat(result, "\t"))
end
