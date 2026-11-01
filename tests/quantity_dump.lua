local project = arg[1] or "."
package.path = project .. "/rime/lua/?.lua;" .. package.path
local special = require("znabc.special").new(project .. "/rime/znabc_data")
for input in io.lines() do
  print(special:quantity_text(input) or "<invalid>")
end
