local parser = require("znabc.parser")
local Dictionary = {}
Dictionary.__index = Dictionary

local function fields(line)
  local result = {}
  for value in (line .. "\t"):gmatch("(.-)\t") do
    result[#result + 1] = value
  end
  return result
end

function Dictionary.new(root, include_supplement)
  local self = setmetatable({root = root, characters = {}, initials = {}, phrases = {}, shapes = {},
    include_supplement = include_supplement ~= false}, Dictionary)
  local file, message = io.open(root .. "/characters.tsv", "rb")
  assert(file, "智能 ABC 数据未安装：" .. tostring(message))
  for line in file:lines() do
    local values = fields(line:gsub("\r$", ""))
    local code, packed = tonumber(values[1]), tonumber(values[3])
    local character = {code = code, text = values[2], packed = packed, shape = tonumber(values[4]), weight = tonumber(values[5])}
    self.characters[code] = character
    local initial = parser.initial_letter(math.floor(packed / 256))
    self.initials[initial] = self.initials[initial] or {}
    table.insert(self.initials[initial], character)
  end
  file:close()
  if self.include_supplement then
    file = io.open(root .. "/supplement/characters.tsv", "rb")
    if file then
      for line in file:lines() do
        local values = fields(line:gsub("\r$", ""))
        local code, packed = tonumber(values[1]), tonumber(values[3])
        assert(not self.characters[code], "补充字码与原字表冲突")
        local character = {code = code, text = values[2], packed = packed, shape = tonumber(values[4]),
          weight = tonumber(values[5]), source = "supplement"}
        self.characters[code] = character
        local initial = parser.initial_letter(math.floor(packed / 256))
        self.initials[initial] = self.initials[initial] or {}
        table.insert(self.initials[initial], character)
      end
      file:close()
    end
  end
  return self
end

function Dictionary:phrase_bucket(key)
  if self.phrases[key] then
    return self.phrases[key]
  end
  local result = {}
  local file = io.open(self.root .. "/phrases/" .. key .. ".tsv", "rb")
  if file then
    for line in file:lines() do
      local values = fields(line:gsub("\r$", ""))
      local codes = {}
      for value in values[3]:gmatch("%d+") do
        codes[#codes + 1] = tonumber(value)
      end
      local width = tonumber(values[1])
      result[width] = result[width] or {}
      table.insert(result[width], {text = values[2], codes = codes, weight = tonumber(values[4]), order = tonumber(values[5]), source = "base"})
    end
    file:close()
  end
  self.phrases[key] = result
  return result
end

function Dictionary:shape_bucket(initial)
  if self.shapes[initial] then
    return self.shapes[initial]
  end
  local result = {}
  local file = io.open(self.root .. "/shapes/" .. initial .. ".tsv", "rb")
  if file then
    for line in file:lines() do
      local values = fields(line:gsub("\r$", ""))
      result[values[1]] = result[values[1]] or {}
      table.insert(result[values[1]], {text = values[2], source = "shape", weight = 0})
    end
    file:close()
  end
  if self.include_supplement then
    file = io.open(self.root .. "/supplement/shapes/" .. initial .. ".tsv", "rb")
    if file then
      for line in file:lines() do
        local values = fields(line:gsub("\r$", ""))
        result[values[1]] = result[values[1]] or {}
        table.insert(result[values[1]], {text = values[2], source = "supplement", weight = 0})
      end
      file:close()
    end
  end
  self.shapes[initial] = result
  return result
end

return Dictionary

