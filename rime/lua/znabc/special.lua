local Special = {}
Special.__index = Special

function Special.new(root)
  local self = setmetatable({root = root, quantity = {}, symbols = {}, extension = {}}, Special)
  local file, message = io.open(root .. "/quantity.tsv", "rb")
  assert(file, "智能 ABC 特殊模式数据未安装：" .. tostring(message))
  for line in file:lines() do
    local code, text = line:match("^(%d+)\t(.-)\r?$")
    self.quantity[tonumber(code)] = text
  end
  file:close()
  return self
end

function Special:quantity_text(input)
  if not input:match("^[iI]") or #input > 20 then
    return nil
  end
  local uppercase = input:sub(1, 1) == "I"
  local body = #input == 1 and "1" or input:sub(2)
  local result = {}
  for position = 1, #body do
    local code = body:byte(position)
    if code >= 97 and code <= 122 then code = code - 32 end
    if uppercase then
      if code >= 48 and code <= 57 then code = code - 48 end
      if code == 83 or code == 66 or code == 81 then code = code + 32 end
    end
    if not self.quantity[code] then return nil end
    result[#result + 1] = self.quantity[code]
  end
  return table.concat(result)
end

function Special:symbol_candidates(zone)
  if self.symbols[zone] then return self.symbols[zone] end
  local result = {}
  local file = io.open(self.root .. "/symbols/" .. zone .. ".tsv", "rb")
  if file then
    for line in file:lines() do
      local text, encoded = line:match("^(.-)\t(%x+)\r?$")
      result[#result + 1] = {text = text, comment = " GB2312 " .. encoded:upper(), source = "symbol"}
    end
    file:close()
  end
  self.symbols[zone] = result
  return result
end

function Special:extension_bucket(directory, initial)
  local key = directory .. "/" .. initial
  if self.extension[key] then return self.extension[key] end
  local result = {}
  local file = io.open(self.root .. "/" .. key .. ".tsv", "rb")
  if file then
    for line in file:lines() do
      local text, pinyin, shape, order = line:match("^(.-)\t([a-z]+)\t([1-8]+)\t(%d+)\r?$")
      result[#result + 1] = {text = text, pinyin = pinyin, shape = shape, order = tonumber(order),
        comment = " " .. pinyin .. " · " .. shape, source = "gbk"}
    end
    file:close()
  end
  self.extension[key] = result
  return result
end

function Special:gbk_candidates(input)
  local pinyin, shape = input:match("^([a-z]+)([1-8]*)$")
  local directory, initial
  if pinyin and #shape <= 6 then
    directory, initial = "gbk", pinyin:sub(1, 1)
  elseif input:match("^[1-8]+$") and #input <= 6 then
    pinyin, shape = "", input
    directory, initial = "gbk_shapes", input:sub(1, 1)
  else
    return {}
  end
  local result, seen = {}, {}
  for _, row in ipairs(self:extension_bucket(directory, initial)) do
    if row.pinyin:sub(1, #pinyin) == pinyin and row.shape:sub(1, #shape) == shape and not seen[row.text] then
      result[#result + 1] = row
      seen[row.text] = true
    end
  end
  return result
end

return Special
